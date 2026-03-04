"""
neon.fetchers
~~~~~~~~~~~~~
Layered fetchers: StaticFetcher → StealthFetcher → DynamicFetcher.

Each tier builds on the previous, adding more browser realism.
"""

from __future__ import annotations

import time
from typing import Optional

from .utils import generate_headers, generate_referer, detect_block
from .parser import NeonParser


# ---------------------------------------------------------------------------
# Shared "Response" dataclass (we don't depend on httpx Response directly)
# ---------------------------------------------------------------------------

class FetchResult:
    """Lightweight wrapper around a fetched page."""

    def __init__(self, html: str, url: str, status_code: int = 200,
                 headers: Optional[dict] = None, error: Optional[str] = None):
        self.html = html
        self.url = url
        self.status_code = status_code
        self.headers = headers or {}
        self.error = error
        self._parser: Optional[NeonParser] = None

    # ------------------------------------------------------------------
    # Parser proxy — lazily create parser
    # ------------------------------------------------------------------

    @property
    def page(self) -> NeonParser:
        if self._parser is None:
            self._parser = NeonParser(self.html, url=self.url,
                                      status_code=self.status_code,
                                      headers=self.headers)
        return self._parser

    def css(self, selector: str):
        return self.page.css(selector)

    def xpath(self, expr: str):
        return self.page.xpath(expr)

    def text(self, pattern: Optional[str] = None) -> str:
        return self.page.text(pattern)

    def links(self, same_domain_only: bool = False):
        return self.page.links(same_domain_only)

    def to_markdown(self) -> str:
        return self.page.to_markdown()

    def to_json(self, selector=None, attrs=None):
        return self.page.to_json(selector, attrs)

    @property
    def ok(self) -> bool:
        return self.error is None and 200 <= self.status_code < 300

    @property
    def is_blocked(self) -> bool:
        return detect_block(self.status_code, self.html)

    def __repr__(self) -> str:
        return f"<FetchResult url={self.url!r} status={self.status_code} blocked={self.is_blocked}>"


# ---------------------------------------------------------------------------
# Static Fetcher — fast HTTP with httpx + browser header spoofing
# ---------------------------------------------------------------------------

class StaticFetcher:
    """
    Fast HTTP fetcher using `httpx`.
    Spoofs browser headers but does *not* run JavaScript.

    Best for: static HTML pages, REST APIs, any server-rendered content.
    """

    def __init__(self, timeout: int = 20, retries: int = 3,
                 proxy: Optional[str] = None, browser: str = "chrome",
                 verify: bool = False):
        self.timeout = timeout
        self.retries = retries
        self.proxy = proxy
        self.browser = browser
        self.verify = verify  # False by default — avoids pyenv SSL cert issues

    def fetch(self, url: str, method: str = "GET", **kwargs) -> FetchResult:
        """Fetch *url* and return a :class:`FetchResult`."""
        try:
            import httpx  # type: ignore
        except ImportError:
            raise RuntimeError("httpx is required: pip install httpx")

        headers = generate_headers(self.browser)
        headers["Referer"] = generate_referer(url)

        proxies = {"http://": self.proxy, "https://": self.proxy} if self.proxy else None
        last_exc: Optional[Exception] = None

        for attempt in range(1, self.retries + 1):
            try:
                client_kwargs: dict = {
                    "follow_redirects": True,
                    "timeout": self.timeout,
                    "verify": self.verify,
                }
                if self.proxy:
                    client_kwargs["proxy"] = self.proxy

                with httpx.Client(**client_kwargs) as client:
                    resp = client.request(method, url, headers=headers, **kwargs)
                    return FetchResult(
                        html=resp.text,
                        url=str(resp.url),
                        status_code=resp.status_code,
                        headers=dict(resp.headers),
                    )
            except Exception as exc:
                last_exc = exc
                if attempt < self.retries:
                    time.sleep(1.0)

        return FetchResult(html="<html><body></body></html>", url=url, status_code=0,
                           error=str(last_exc))

    @classmethod
    def get(cls, url: str, **kwargs) -> FetchResult:
        return cls().fetch(url, "GET", **kwargs)


# ---------------------------------------------------------------------------
# Stealth Fetcher — Playwright headless + stealth patches
# ---------------------------------------------------------------------------

class StealthFetcher:
    """
    Stealth browser fetcher using Playwright Chromium in headless mode.

    It patches `navigator.webdriver`, canvas fingerprinting, and other
    bot-detection signals.  Use when `StaticFetcher` gets blocked.
    """

    def __init__(self, headless: bool = True, timeout: int = 30_000,
                 proxy: Optional[str] = None, wait_for: str = "domcontentloaded"):
        self.headless = headless
        self.timeout = timeout
        self.proxy = proxy
        self.wait_for = wait_for

    def fetch(self, url: str) -> FetchResult:
        try:
            from playwright.sync_api import sync_playwright  # type: ignore
        except ImportError:
            raise RuntimeError(
                "playwright is required: pip install playwright && playwright install chromium"
            )

        proxy_obj = {"server": self.proxy} if self.proxy else None

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=self.headless)
            ctx = browser.new_context(
                user_agent=generate_headers()["User-Agent"],
                proxy=proxy_obj,
                extra_http_headers={"Referer": generate_referer(url)},
            )
            # Stealth patches
            ctx.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3]});
                window.chrome = {runtime: {}};
            """)
            page = ctx.new_page()
            try:
                resp = page.goto(url, wait_until=self.wait_for, timeout=self.timeout)
                html = page.content()
                status = resp.status if resp else 200
                headers = dict(resp.headers) if resp else {}
                final_url = page.url
            finally:
                browser.close()

        return FetchResult(html=html, url=final_url, status_code=status, headers=headers)

    @classmethod
    def fetch_url(cls, url: str, **kwargs) -> FetchResult:
        return cls(**kwargs).fetch(url)


# ---------------------------------------------------------------------------
# Dynamic Fetcher — full browser automation
# ---------------------------------------------------------------------------

class DynamicFetcher:
    """
    Full Playwright browser automation with optional page actions.

    Use for SPAs, infinite-scroll pages, or anything that requires real
    JavaScript execution and DOM interaction.
    """

    def __init__(self, headless: bool = True, timeout: int = 30_000,
                 proxy: Optional[str] = None,
                 wait_selector: Optional[str] = None,
                 network_idle: bool = False,
                 page_action=None):
        self.headless = headless
        self.timeout = timeout
        self.proxy = proxy
        self.wait_selector = wait_selector
        self.network_idle = network_idle
        self.page_action = page_action  # callable(page) for custom automation

    def fetch(self, url: str) -> FetchResult:
        try:
            from playwright.sync_api import sync_playwright  # type: ignore
        except ImportError:
            raise RuntimeError(
                "playwright is required: pip install playwright && playwright install chromium"
            )

        proxy_obj = {"server": self.proxy} if self.proxy else None
        wait_until = "networkidle" if self.network_idle else "domcontentloaded"

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=self.headless)
            ctx = browser.new_context(
                user_agent=generate_headers()["User-Agent"],
                proxy=proxy_obj,
            )
            ctx.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
            )
            page = ctx.new_page()
            try:
                resp = page.goto(url, wait_until=wait_until, timeout=self.timeout)
                if self.wait_selector:
                    page.wait_for_selector(self.wait_selector, timeout=self.timeout)
                if callable(self.page_action):
                    self.page_action(page)
                html = page.content()
                status = resp.status if resp else 200
                headers = dict(resp.headers) if resp else {}
                final_url = page.url
            finally:
                browser.close()

        return FetchResult(html=html, url=final_url, status_code=status, headers=headers)

    @classmethod
    def fetch_url(cls, url: str, **kwargs) -> FetchResult:
        return cls(**kwargs).fetch(url)
