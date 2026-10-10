from __future__ import annotations

import re
from pathlib import Path

pat = re.compile(
    r"events\s*=\s*list\(\s*state\.get\(\s*[\"']events[\"']\s*\)\s*or\s*\[\s*\]\s*\)"
)


def main() -> None:
    for path in Path("app/agents").glob("*.py"):
        text = path.read_text(encoding="utf-8")
        agent = path.stem
        new, n = pat.subn(f'events = EventBag(state, "{agent}")', text)
        if not n:
            print(path.name, "EventBag sites", 0)
            continue
        if "from app.infra.events import EventBag" not in new:
            lines = new.splitlines(True)
            idx = 0
            for i, line in enumerate(lines):
                if line.startswith("from ") or line.startswith("import "):
                    idx = i + 1
            lines.insert(idx, "from app.infra.events import EventBag\n")
            new = "".join(lines)
        path.write_text(new, encoding="utf-8")
        print(path.name, "EventBag sites", n)


if __name__ == "__main__":
    main()
