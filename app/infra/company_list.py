"""Parse and validate user-provided company CSV lists."""

from __future__ import annotations

import csv
import io
import re
from typing import Any
from urllib.parse import urlparse

from app.infra.redact import redact_text

MAX_ROWS = 50
MAX_DESCRIPTION = 300

_HEADER_ALIASES = {
    "company_name": {"company_name", "company", "name", "company name"},
    "website": {"website", "domain", "url", "site", "company_website", "web"},
    "description": {"description", "notes", "about", "desc"},
}


def normalize_domain(raw: str) -> str | None:
    text = (raw or "").strip()
    if not text:
        return None
    if "://" not in text:
        text = "https://" + text
    try:
        parsed = urlparse(text)
    except Exception:
        return None
    host = (parsed.netloc or parsed.path or "").strip().lower()
    if not host or " " in host:
        return None
    if host.startswith("www."):
        host = host[4:]
    host = host.split("/")[0].split("?")[0].rstrip(".")
    if "." not in host or len(host) < 3:
        return None
    if not re.match(r"^[a-z0-9.-]+$", host):
        return None
    return host


def parse_companies_csv(raw: str) -> dict[str, Any]:
    """
    Parse CSV text into validated rows.

    Returns {rows: [{name, domain, description, status, reason}], ok_count}.
    status: ok | duplicate_domain | bad_website | missing_name | too_many
    Invalid rows are kept in the list (never silently dropped).

    Accepts a header row (company_name, website, …) or headerless lines like
    ``Mindarmor, https://mindarmor.ai``.
    """
    text = (raw or "").lstrip("\ufeff").strip()
    if not text:
        return {"rows": [], "ok_count": 0}

    # Probe first row: known headers vs data (name + domain/url).
    probe = next(csv.reader(io.StringIO(text)), [])
    probe_cells = [c.strip() for c in probe if c is not None]
    header_map = _map_headers(probe_cells)
    has_known_headers = "company_name" in header_map and "website" in header_map

    if has_known_headers:
        reader = csv.DictReader(io.StringIO(text))
        colmap = _map_headers(list(reader.fieldnames or []))
        data_iter = reader
        get_cells = lambda row: (  # noqa: E731
            str(row.get(colmap["company_name"]) or "").strip(),
            str(row.get(colmap["website"]) or "").strip(),
            str(row.get(colmap["description"]) or "").strip()
            if colmap.get("description")
            else "",
        )
    else:
        # Headerless: every line is data. Also covers unknown first-line headers
        # that would otherwise swallow the only company as column names.
        data_iter = csv.reader(io.StringIO(text))
        get_cells = lambda row: (  # noqa: E731
            str(row[0]).strip() if len(row) > 0 else "",
            str(row[1]).strip() if len(row) > 1 else "",
            str(row[2]).strip() if len(row) > 2 else "",
        )

    seen_domains: set[str] = set()
    rows_out: list[dict[str, Any]] = []
    ok_count = 0
    for i, row in enumerate(data_iter):
        if i >= MAX_ROWS:
            rows_out.append(
                {
                    "name": "",
                    "domain": "",
                    "description": "",
                    "status": "too_many",
                    "reason": f"Max {MAX_ROWS} companies",
                }
            )
            for _ in data_iter:
                rows_out.append(
                    {
                        "name": "",
                        "domain": "",
                        "description": "",
                        "status": "too_many",
                        "reason": f"Max {MAX_ROWS} companies",
                    }
                )
            break

        name, website_raw, description = get_cells(row)
        if len(description) > MAX_DESCRIPTION:
            description = description[:MAX_DESCRIPTION]
        description = redact_text(description) if description else ""

        # Skip blank lines
        if not name and not website_raw:
            continue

        if not name:
            rows_out.append(
                {
                    "name": name,
                    "domain": "",
                    "description": description,
                    "status": "missing_name",
                    "reason": "company_name is required",
                }
            )
            continue

        domain = normalize_domain(website_raw)
        if not domain:
            rows_out.append(
                {
                    "name": name,
                    "domain": "",
                    "description": description,
                    "status": "bad_website",
                    "reason": "website/domain is invalid",
                }
            )
            continue

        if domain in seen_domains:
            rows_out.append(
                {
                    "name": name,
                    "domain": domain,
                    "description": description,
                    "status": "duplicate_domain",
                    "reason": f"duplicate domain {domain}",
                }
            )
            continue

        seen_domains.add(domain)
        rows_out.append(
            {
                "name": name,
                "domain": domain,
                "description": description,
                "status": "ok",
                "reason": "",
            }
        )
        ok_count += 1

    return {"rows": rows_out, "ok_count": ok_count}


def ok_companies(parsed: dict[str, Any]) -> list[dict[str, str]]:
    """Return [{name, domain, description}] for ok rows only."""
    out: list[dict[str, str]] = []
    for row in parsed.get("rows") or []:
        if row.get("status") != "ok":
            continue
        out.append(
            {
                "name": str(row["name"]),
                "domain": str(row["domain"]),
                "description": str(row.get("description") or ""),
            }
        )
    return out


def validate_provided_companies(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Re-validate API-provided company rows; raise ValueError on failure."""
    if not rows:
        raise ValueError("provided_companies must not be empty")
    if len(rows) > MAX_ROWS:
        raise ValueError(f"provided_companies exceeds max {MAX_ROWS}")
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("each provided company must be an object")
        name = str(row.get("name") or "").strip()
        if not name:
            raise ValueError("company name is required")
        domain = normalize_domain(str(row.get("domain") or row.get("website") or ""))
        if not domain:
            raise ValueError(f"invalid website/domain for {name}")
        if domain in seen:
            raise ValueError(f"duplicate domain {domain}")
        seen.add(domain)
        description = str(row.get("description") or "").strip()
        if len(description) > MAX_DESCRIPTION:
            description = description[:MAX_DESCRIPTION]
        description = redact_text(description) if description else ""
        out.append({"name": name, "domain": domain, "description": description})
    return out


def _map_headers(fieldnames: list[str | None]) -> dict[str, str | None]:
    mapped: dict[str, str | None] = {}
    for raw in fieldnames:
        if raw is None:
            continue
        key = re.sub(r"\s+", " ", raw.strip().lower())
        for canonical, aliases in _HEADER_ALIASES.items():
            if key in aliases and canonical not in mapped:
                mapped[canonical] = raw
    return mapped
