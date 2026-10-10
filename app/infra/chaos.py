"""Fault injection for recovery evidence runs."""

from __future__ import annotations

import random
from dataclasses import dataclass, field


class ChaosFault(Exception):
    """Synthetic failure injected by chaos flags."""

    def __init__(self, kind: str, status_code: int, headers: dict | None = None, body: dict | None = None):
        self.kind = kind
        self.status_code = status_code
        self.headers = headers or {}
        self.body = body or {}
        super().__init__(f"chaos:{kind}:{status_code}")


@dataclass
class ChaosController:
    flags: set[str] = field(default_factory=set)
    _429_seen: set[str] = field(default_factory=set)
    _403_fields_fired: bool = False

    @classmethod
    def from_csv(cls, raw: str | None) -> "ChaosController":
        if not raw:
            return cls()
        flags = {part.strip() for part in raw.split(",") if part.strip()}
        # support kill_after=node as a single token
        return cls(flags=flags)

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


_controller: ChaosController | None = None


def get_chaos() -> ChaosController:
    global _controller
    if _controller is None:
        _controller = ChaosController()
    return _controller


def set_chaos(raw: str | None) -> ChaosController:
    global _controller
    _controller = ChaosController.from_csv(raw)
    return _controller
