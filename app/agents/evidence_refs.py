"""Deterministic evidence-id detection and stripping for outbound copy."""

from __future__ import annotations

import re

EV_RE = re.compile(r"\bev_[0-9a-f]{6,}\b", re.I)

# Parentheses or brackets wrapping one or more ids, comma/semicolon separated.
_WRAPPER_RE = re.compile(
    r"[\(\[]\s*"
    r"ev_[0-9a-f]{6,}"
    r"(?:\s*[,;]\s*ev_[0-9a-f]{6,})*"
    r"\s*[\)\]]",
    re.I,
)


def find_refs(text: str) -> list[str]:
    if not text:
        return []
    seen: list[str] = []
    for m in EV_RE.finditer(text):
        rid = m.group(0).lower()
        if rid not in seen:
            seen.append(rid)
    return seen


def strip_refs(text: str) -> str:
    """Remove evidence ids and their wrappers; tidy spaces/punctuation."""
    if not text:
        return text or ""
    out = _WRAPPER_RE.sub("", text)
    out = EV_RE.sub("", out)
    out = re.sub(r"[ \t]{2,}", " ", out)
    out = re.sub(r" +([,.;:!?])", r"\1", out)
    out = re.sub(r"\(\s*\)", "", out)
    out = re.sub(r"\[\s*\]", "", out)
    out = re.sub(r"[ \t]{2,}", " ", out)
    out = "\n".join(line.rstrip() for line in out.splitlines())
    return out.strip()
