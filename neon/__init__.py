"""
neon
~~~~
Browsing engine with web scraping built in by default.

Quick start::

    from neon import Scraper, NeonEngine, NeonSession

    # One-shot scrape
    scraper = Scraper()
    result  = scraper.get("https://quotes.toscrape.com")
    quotes  = [el.text for el in result.css(".quote .text")]

    # Low-level engine
    from neon import NeonEngine
    result = NeonEngine.get("https://example.com")
    print(result.to_markdown())

    # Session (persistent cookies)
    from neon import NeonSession
    with NeonSession(mode='static') as s:
        page = s.get('https://example.com')
"""

from .engine import NeonEngine
from .fetchers import StaticFetcher, StealthFetcher, DynamicFetcher, FetchResult
from .parser import NeonParser
from .scraper import Scraper, Spider
from .session import NeonSession
from .utils import (
    generate_headers,
    generate_referer,
    normalize_url,
    is_valid_url,
    same_domain,
    html_to_markdown,
    detect_block,
)

__version__ = "1.0.0"
__author__ = "Neon Contributors"

__all__ = [
    # Core
    "NeonEngine",
    "Scraper",
    "Spider",
    "NeonSession",
    # Fetchers
    "StaticFetcher",
    "StealthFetcher",
    "DynamicFetcher",
    "FetchResult",
    # Parser
    "NeonParser",
    # Utils
    "generate_headers",
    "generate_referer",
    "normalize_url",
    "is_valid_url",
    "same_domain",
    "html_to_markdown",
    "detect_block",
]
