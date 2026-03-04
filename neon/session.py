"""
neon.session
~~~~~~~~~~~~
Persistent session management with cookie jar, proxy support,
and optional browser-state save/restore.
"""

from __future__ import annotations

from typing import Optional
from .fetchers import StaticFetcher, StealthFetcher, DynamicFetcher, FetchResult


class NeonSession:
    """
    A reusable session that preserves cookies and state across requests.

    Usage::

        with NeonSession(mode='static') as session:
            r1 = session.get('https://example.com/login')
            r2 = session.get('https://example.com/dashboard')  # cookies carried over

    Modes
    -----
    ``static``
        Fast httpx-based requests with browser header spoofing.
    ``stealth``
        Playwright headless with stealth patches.  Slower but defeats most
        bot walls.
    ``dynamic``
        Full Playwright browser. Supports JS-heavy SPAs.
    """

    def __init__(
        self,
        mode: str = "static",
        proxy: Optional[str] = None,
        timeout: int = 20,
        headless: bool = True,
    ):
        if mode not in ("static", "stealth", "dynamic"):
            raise ValueError(f"Invalid mode {mode!r}. Choose 'static', 'stealth', or 'dynamic'.")
        self.mode = mode
        self.proxy = proxy
        self.timeout = timeout
        self.headless = headless

        # Cookie/storage state for static sessions
        self._cookies: dict[str, str] = {}
        # Playwright browser/context kept alive for browser sessions
        self._pw = None
        self._browser = None
        self._context = None

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> "NeonSession":
        if self.mode in ("stealth", "dynamic"):
            self._start_browser()
        return self

    def __exit__(self, *_):
        self.close()

    def _start_browser(self):
        try:
            from playwright.sync_api import sync_playwright  # type: ignore
            from .utils import generate_headers, generate_referer
        except ImportError:
            raise RuntimeError("playwright is required: pip install playwright && playwright install chromium")

        self._pw = sync_playwright().start()
        proxy_obj = {"server": self.proxy} if self.proxy else None
        self._browser = self._pw.chromium.launch(headless=self.headless)
        self._context = self._browser.new_context(
            user_agent=generate_headers()["User-Agent"],
            proxy=proxy_obj,
        )
        self._context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )

    def close(self):
        """Release all resources."""
        if self._context:
            self._context.close()
        if self._browser:
            self._browser.close()
        if self._pw:
            self._pw.stop()
        self._pw = self._browser = self._context = None

    # ------------------------------------------------------------------
    # HTTP-level requests (static mode)
    # ------------------------------------------------------------------

    def get(self, url: str, **kwargs) -> FetchResult:
        return self._request("GET", url, **kwargs)

    def post(self, url: str, **kwargs) -> FetchResult:
        return self._request("POST", url, **kwargs)

    def _request(self, method: str, url: str, **kwargs) -> FetchResult:
        if self.mode == "static":
            return self._static_request(method, url, **kwargs)
        return self._browser_request(url)

    def _static_request(self, method: str, url: str, **kwargs) -> FetchResult:
        try:
            import httpx  # type: ignore
        except ImportError:
            raise RuntimeError("httpx is required: pip install httpx")

        from .utils import generate_headers, generate_referer

        headers = generate_headers()
        headers["Referer"] = generate_referer(url)
        client_kwargs: dict = {
            "follow_redirects": True,
            "timeout": self.timeout,
            "verify": False,
            "cookies": self._cookies,
        }
        if self.proxy:
            client_kwargs["proxy"] = self.proxy

        with httpx.Client(**client_kwargs) as client:
            resp = client.request(method, url, headers=headers, **kwargs)
            # Persist cookies from this response
            self._cookies.update(dict(resp.cookies))
            return FetchResult(
                html=resp.text,
                url=str(resp.url),
                status_code=resp.status_code,
                headers=dict(resp.headers),
            )

    def _browser_request(self, url: str) -> FetchResult:
        if not self._context:
            raise RuntimeError("Call __enter__ first or use 'with NeonSession(...) as s:'")
        page = self._context.new_page()
        try:
            wait_until = "networkidle" if self.mode == "dynamic" else "domcontentloaded"
            resp = page.goto(url, wait_until=wait_until, timeout=self.timeout * 1000)
            html = page.content()
            status = resp.status if resp else 200
            headers = dict(resp.headers) if resp else {}
            final_url = page.url
        finally:
            page.close()
        return FetchResult(html=html, url=final_url, status_code=status, headers=headers)

    # ------------------------------------------------------------------
    # Cookie helpers
    # ------------------------------------------------------------------

    def set_cookie(self, name: str, value: str):
        self._cookies[name] = value

    def clear_cookies(self):
        self._cookies.clear()

    def __repr__(self) -> str:
        return f"<NeonSession mode={self.mode!r} proxy={self.proxy!r}>"
