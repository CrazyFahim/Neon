"""
neon.utils
~~~~~~~~~~
Shared utility functions for the Neon browsing engine.
"""

from __future__ import annotations

import re
import random
from typing import Optional
from urllib.parse import urljoin, urlparse


# ---------------------------------------------------------------------------
# Realistic browser headers
# ---------------------------------------------------------------------------

_CHROME_VERSIONS = ["124.0.0.0", "123.0.0.0", "122.0.0.0", "121.0.0.0"]
_FIREFOX_VERSIONS = ["125.0", "124.0", "123.0"]
_PLATFORMS = [
    "Windows NT 10.0; Win64; x64",
    "Macintosh; Intel Mac OS X 10_15_7",
    "X11; Linux x86_64",
]


def generate_headers(browser: str = "chrome") -> dict[str, str]:
    """Return a realistic set of HTTP headers for the given browser."""
    platform = random.choice(_PLATFORMS)

    if browser == "firefox":
        version = random.choice(_FIREFOX_VERSIONS)
        ua = f"Mozilla/5.0 ({platform}; rv:{version}) Gecko/20100101 Firefox/{version}"
        return {
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            # Note: Accept-Encoding intentionally omitted — httpx decompresses automatically
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
        }

    # Default: Chrome
    version = random.choice(_CHROME_VERSIONS)
    major = version.split(".")[0]
    ua = (
        f"Mozilla/5.0 ({platform}) AppleWebKit/537.36 "
        f"(KHTML, like Gecko) Chrome/{version} Safari/537.36"
    )
    return {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        # Note: Accept-Encoding intentionally omitted — httpx decompresses automatically
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-CH-UA": f'"Chromium";v="{major}", "Google Chrome";v="{major}", "Not-A.Brand";v="99"',
        "Sec-CH-UA-Mobile": "?0",
        "Sec-CH-UA-Platform": '"Windows"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
    }


def generate_referer(url: str) -> str:
    """Generate a convincing Google-search referer for the given URL."""
    parsed = urlparse(url)
    domain = parsed.netloc.replace("www.", "")
    return f"https://www.google.com/search?q={domain}"


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------

def normalize_url(url: str, base: Optional[str] = None) -> str:
    """Resolve *url* against *base* and return the absolute form."""
    if base:
        return urljoin(base, url)
    return url


def is_valid_url(url: str) -> bool:
    """Return True if *url* looks like a proper HTTP/HTTPS URL."""
    try:
        parsed = urlparse(url)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False


def same_domain(url: str, base: str) -> bool:
    """Return True if both URLs share the same netloc."""
    return urlparse(url).netloc == urlparse(base).netloc


# ---------------------------------------------------------------------------
# HTML → Markdown
# ---------------------------------------------------------------------------

def html_to_markdown(html: str) -> str:
    """Convert raw HTML to GitHub-style Markdown. Falls back gracefully."""
    try:
        import markdownify  # type: ignore
        return markdownify.markdownify(html, heading_style="ATX", strip=["script", "style"])
    except ImportError:
        # Naive fallback: strip tags
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"\s{2,}", "\n", text)
        return text.strip()


# ---------------------------------------------------------------------------
# Anti-bot / block detection
# ---------------------------------------------------------------------------

_BLOCK_PATTERNS = [
    r"captcha",
    r"cloudflare",
    r"access denied",
    r"robot",
    r"bot detected",
    r"403 forbidden",
    r"please verify",
    r"are you human",
    r"ddos-guard",
    r"just a moment",
]
_BLOCK_RE = re.compile("|".join(_BLOCK_PATTERNS), re.IGNORECASE)


def detect_block(status_code: int, html: str) -> bool:
    """
    Heuristically determine whether the response looks like a bot-block page.

    Returns True if blocked, False if the page looks legitimate.
    """
    if status_code in (403, 429, 503):
        return True
    if _BLOCK_RE.search(html[:4096]):
        return True
    # Very short pages are suspicious
    if len(html.strip()) < 300:
        return True
    return False
