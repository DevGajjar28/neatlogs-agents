"""Fault injection for recovery evidence runs."""

from __future__ import annotations

import random
from dataclasses import dataclass, field

# Real LangGraph node names (see app/graph.py). Alias maps docs name → real node.
VALID_KILL_NODES = frozenset(
    {
        "planner",
        "product_researcher",
        "buyer_propose_icp",
        "icp_gate",
        "buyer_search",
        "account_enrich",
        "account_company",
        "account_join",
        "email_writer",
        "verifier",
        "approval_gate",
        "sender",
    }
)
KILL_ALIASES = {
    "account_researcher": "account_enrich",
}

_kill_armed: bool = False


class ChaosFault(Exception):
    """Synthetic failure injected by chaos flags."""

    def __init__(self, kind: str, status_code: int, headers: dict | None = None, body: dict | None = None):
        self.kind = kind
        self.status_code = status_code
        self.headers = headers or {}
        self.body = body or {}
        super().__init__(f"chaos:{kind}:{status_code}")


class ChaosConfigError(ValueError):
    """Invalid chaos flag (e.g. bad kill_after node)."""


class ChaosLlmBadJson(RuntimeError):
    """Injected once when --chaos llm_bad_json is set."""

    def __init__(self) -> None:
        super().__init__("chaos:llm_bad_json")


@dataclass
class ChaosController:
    flags: set[str] = field(default_factory=set)
    kill_after: str | None = None
    _429_seen: set[str] = field(default_factory=set)
    _403_fields_fired: bool = False
    llm_bad_fired: bool = False

    @classmethod
    def from_csv(cls, raw: str | None) -> "ChaosController":
        if not raw:
            return cls()
        flags: set[str] = set()
        kill_after: str | None = None
        for part in raw.split(","):
            token = part.strip()
            if not token:
                continue
            if token.startswith("kill_after="):
                node = token.split("=", 1)[1].strip()
                kill_after = _resolve_kill_node(node)
                flags.add(token)
            else:
                flags.add(token)
        return cls(flags=flags, kill_after=kill_after)

    def maybe_fail(self, endpoint: str) -> None:
        if "crust_429" in self.flags and endpoint not in self._429_seen:
            self._429_seen.add(endpoint)
            raise ChaosFault(
                "crust_429",
                429,
                headers={"x-ratelimit-reset": "3"},
                body={"error": {"type": "rate_limit_error", "message": "chaos 429"}},
            )

        if "crust_5xx" in self.flags and random.random() < 0.2:
            raise ChaosFault(
                "crust_5xx",
                503,
                body={"error": {"type": "server_error", "message": "chaos 5xx"}},
            )

        if (
            "crust_403_fields" in self.flags
            and not self._403_fields_fired
            and endpoint == "/person/enrich"
        ):
            self._403_fields_fired = True
            raise ChaosFault(
                "crust_403_fields",
                403,
                body={
                    "error": {
                        "type": "permission_error",
                        "message": "fields denied",
                        "metadata": [{"denied_fields": ["contact.business_emails"]}],
                    }
                },
            )

    def maybe_bad_llm_json(self) -> None:
        """Raise once so the caller falls back (invalid structured JSON)."""
        if "llm_bad_json" in self.flags and not self.llm_bad_fired:
            self.llm_bad_fired = True
            raise ChaosLlmBadJson()


def _resolve_kill_node(node: str) -> str:
    resolved = KILL_ALIASES.get(node, node)
    if resolved not in VALID_KILL_NODES:
        valid = ", ".join(sorted(VALID_KILL_NODES | set(KILL_ALIASES)))
        raise ChaosConfigError(
            f"invalid kill_after={node!r}; valid names: {valid}"
        )
    return resolved


def arm_kill_after() -> None:
    """Called when the named kill_after node returns; next node start will exit."""
    global _kill_armed
    _kill_armed = True


def kill_armed() -> bool:
    return _kill_armed


def clear_kill_armed() -> None:
    global _kill_armed
    _kill_armed = False


_controller: ChaosController | None = None


def get_chaos() -> ChaosController:
    global _controller
    if _controller is None:
        _controller = ChaosController()
    return _controller


def set_chaos(raw: str | None) -> ChaosController:
    global _controller
    clear_kill_armed()
    _controller = ChaosController.from_csv(raw)
    return _controller
