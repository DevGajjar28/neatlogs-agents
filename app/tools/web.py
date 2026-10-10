"""Web fetch/search, HTML to text, and light link discovery. v0: httpx + BeautifulSoup."""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

USER_AGENT = "SignalSDR/0.1 (+neatHack research; local demo)"
MAX_PAGES = 8
FETCH_TIMEOUT = 20.0


def normalize_url(url: str) -> str:
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url.rstrip("/")


def domain_of(url: str) -> str:
    host = urlparse(normalize_url(url)).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def html_to_text(html: str, max_chars: int = 12000) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    text = " ".join(soup.get_text(" ", strip=True).split())
    return text[:max_chars]


def fetch_url(url: str, *, client: httpx.Client | None = None) -> tuple[str | None, str | None]:
    """Return (final_url, text) or (None, None) on failure."""
    owns = client is None
    client = client or httpx.Client(
        timeout=FETCH_TIMEOUT,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
    )
    try:
        response = client.get(normalize_url(url))
        if response.status_code >= 400:
            return None, None
        ctype = response.headers.get("content-type", "")
        if "html" not in ctype and "text" not in ctype:
            return None, None
        return str(response.url), html_to_text(response.text)
    except httpx.HTTPError:
        return None, None
    finally:
        if owns:
            client.close()


def onsite_candidate_urls(home: str) -> list[str]:
    """Homepage plus common seller pages, same host only."""
    home = normalize_url(home)
    host = domain_of(home)
    paths = [
        "",
        "/pricing",
        "/customers",
        "/customers/case-studies",
        "/case-studies",
        "/about",
        "/about-us",
        "/product",
        "/products",
    ]
    urls: list[str] = []
    for path in paths:
        candidate = home if path == "" else home + path
        if domain_of(candidate) == host and candidate not in urls:
            urls.append(candidate)
    return urls[:MAX_PAGES]


def discover_more_onsite(home: str, html: str, limit: int = 4) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    host = domain_of(home)
    found: list[str] = []
    keywords = ("pricing", "customer", "case", "about", "product")
    for a in soup.find_all("a", href=True):
        href = a["href"]
        full = urljoin(home + "/", href)
        if domain_of(full) != host:
            continue
        low = full.lower()
        if any(k in low for k in keywords) and full not in found:
            found.append(normalize_url(full))
        if len(found) >= limit:
            break
    return found


def fetch_seller_pages(website: str) -> list[dict]:
    """Fetch up to MAX_PAGES on-site pages. Each item: url, text."""
    home = normalize_url(website)
    pages: list[dict] = []
    seen: set[str] = set()
    with httpx.Client(
        timeout=FETCH_TIMEOUT,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
    ) as client:
        # seed from known paths; also parse homepage for more links
        queue = onsite_candidate_urls(home)
        while queue and len(pages) < MAX_PAGES:
            url = queue.pop(0)
            if url in seen:
                continue
            seen.add(url)
            final_url, text = fetch_url(url, client=client)
            if not final_url or not text:
                continue
            pages.append({"url": final_url, "text": text})
            if len(pages) == 1:
                # only have text; re-fetch raw html for link discovery cheaply
                try:
                    raw = client.get(final_url)
                    if raw.status_code < 400:
                        for extra in discover_more_onsite(home, raw.text):
                            if extra not in seen and extra not in queue:
                                queue.append(extra)
                except httpx.HTTPError:
                    pass
    return pages


_CUSTOMER_HINT = re.compile(
    r"(?:customers?|case stud(?:y|ies)|trusted by|companies that|used by)\s*[:\-–]?\s*(.+)",
    re.I,
)


def heuristic_named_customers(pages: list[dict], limit: int = 12) -> list[str]:
    """Very naive name harvesting for v0; LLM refines later."""
    names: list[str] = []
    for page in pages:
        for match in _CUSTOMER_HINT.finditer(page["text"][:4000]):
            chunk = match.group(1)[:200]
            parts = re.split(r"[,|/]| and ", chunk)
            for part in parts:
                name = part.strip(" .•·")
                if 2 <= len(name) <= 40 and name[0].isupper() and name not in names:
                    names.append(name)
                if len(names) >= limit:
                    return names
    return names
