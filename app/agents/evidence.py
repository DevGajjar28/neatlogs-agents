"""Evidence card helpers shared by v0 agents."""

from __future__ import annotations

import hashlib
from datetime import date, datetime, timezone

from app.models import EvidenceCard


def evidence_id(fact: str, source_ref: str) -> str:
    digest = hashlib.sha256(f"{fact}|{source_ref}".encode("utf-8")).hexdigest()[:16]
    return f"ev_{digest}"


def make_evidence(
    fact: str,
    *,
    source_type: str,
    source_ref: str,
    confidence: str = "medium",
    observed_at: date | None = None,
) -> EvidenceCard:
    fact = fact.strip()
    if len(fact) > 200:
        fact = fact[:197] + "..."
    return EvidenceCard(
        id=evidence_id(fact, source_ref),
        fact=fact,
        source_type=source_type,  # type: ignore[arg-type]
        source_ref=source_ref,
        observed_at=observed_at,
        fetched_at=datetime.now(timezone.utc),
        confidence=confidence,  # type: ignore[arg-type]
    )
