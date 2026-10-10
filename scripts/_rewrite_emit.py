"""One-shot: rewrite events.append({...}) to emit() calls in agent modules."""

from __future__ import annotations

import re
from pathlib import Path

AGENT = {
    "planner.py": "planner",
    "product_researcher.py": "product_researcher",
    "buyer_finder.py": "buyer_finder",
    "account_researcher.py": "account_researcher",
    "email_writer.py": "email_writer",
    "verifier.py": "verifier",
    "approval_gate.py": "approval_gate",
    "sender.py": "sender",
}

pat = re.compile(r"events\.append\(\s*\{(?P<body>.*?)\}\s*\)", re.DOTALL)


def transform(text: str, agent: str) -> str:
    if "from app.infra.events import emit" not in text:
        lines = text.splitlines(True)
        insert_at = 0
        for i, line in enumerate(lines):
            if line.startswith("from ") or line.startswith("import "):
                insert_at = i + 1
        lines.insert(insert_at, "from app.infra.events import emit\n")
        text = "".join(lines)

    def repl(m: re.Match[str]) -> str:
        body = m.group("body")
        tm = re.search(r'["\']type["\']\s*:\s*["\']([^"\']+)["\']', body)
        if not tm:
            return m.group(0)
        etype = tm.group(1)
        keys = re.findall(r'["\'](\w+)["\']\s*:\s*([^,\n]+)', body)
        kwargs = []
        for k, v in keys:
            if k == "type":
                continue
            kwargs.append(f"{k}={v.strip()}")
        kw = (", " + ", ".join(kwargs)) if kwargs else ""
        return f'events = emit({{**state, "events": events}}, "{etype}", "{agent}"{kw})'

    return pat.sub(repl, text)


def main() -> None:
    root = Path("app/agents")
    for fname, agent in AGENT.items():
        path = root / fname
        src = path.read_text(encoding="utf-8")
        n = len(list(pat.finditer(src)))
        path.write_text(transform(src, agent), encoding="utf-8")
        print(fname, "rewrote", n, "appends")


if __name__ == "__main__":
    main()
