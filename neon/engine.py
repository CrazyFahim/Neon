"""
neon.engine
~~~~~~~~~~~
NeonEngine — the central fetch coordinator.

It tries fetchers in order (static → stealth → dynamic) and returns
the first non-blocked result.
"""

from __future__ import annotations

from typing import Optional, Literal
from .fetchers import StaticFetcher, StealthFetcher, DynamicFetcher, FetchResult


FetcherMode = Literal["auto", "static", "stealth", "dynamic"]


class NeonEngine:
    """
    Central fetch coordinator.

    Modes
    -----
    ``auto``  (default)
        Try Static → Stealth → Dynamic, escalating when blocked.
    ``static``
        HTTP only — fastest, no JS.
    ``stealth``
        Playwright headless with anti-detection patches.
    ``dynamic``
        Full browser with JS execution and optional page actions.

    Parameters
    ----------
    mode:
        Default fetch mode.
    proxy:
        Optional proxy URL (``http://host:port``).
    timeout:
        Seconds to wait per request.
    headless:
        Run browser in headless mode (stealth / dynamic only).

    Example::

        engine = NeonEngine()
        result = engine.fetch("https://example.com")
        print(result.css("h1")[0].text)
    """

    def __init__(
        self,
        mode: FetcherMode = "auto",
        proxy: Optional[str] = None,
        timeout: int = 20,
        headless: bool = True,
    ):
        self.mode = mode
        self.proxy = proxy
        self.timeout = timeout
        self.headless = headless

    # ------------------------------------------------------------------
    # Core fetch
    # ------------------------------------------------------------------

    def fetch(self, url: str, mode: Optional[FetcherMode] = None,
              wait_selector: Optional[str] = None,
              network_idle: bool = False,
              page_action=None) -> FetchResult:
        """
        Fetch *url* and return a :class:`~neon.fetchers.FetchResult`.

        Parameters
        ----------
        url:
            Target URL.
        mode:
            Override the engine's default mode for this single request.
        wait_selector:
            CSS selector to wait for (dynamic mode only).
        network_idle:
            Wait until no network activity (dynamic mode only).
        page_action:
            ``callable(page)`` for custom Playwright automation.
        """
        effective_mode = mode or self.mode

        if effective_mode == "static":
            return self._static(url)
        if effective_mode == "stealth":
            return self._stealth(url)
        if effective_mode == "dynamic":
            return self._dynamic(url, wait_selector, network_idle, page_action)
        # auto
        return self._auto(url, wait_selector, network_idle, page_action)

    # ------------------------------------------------------------------
    # Internal fetch helpers
    # ------------------------------------------------------------------

    def _static(self, url: str) -> FetchResult:
        fetcher = StaticFetcher(proxy=self.proxy, timeout=self.timeout)
        return fetcher.fetch(url)

    def _stealth(self, url: str) -> FetchResult:
        fetcher = StealthFetcher(proxy=self.proxy, timeout=self.timeout * 1000,
                                 headless=self.headless)
        return fetcher.fetch(url)

    def _dynamic(self, url: str, wait_selector=None,
                 network_idle=False, page_action=None) -> FetchResult:
        fetcher = DynamicFetcher(
            proxy=self.proxy, timeout=self.timeout * 1000,
            headless=self.headless,
            wait_selector=wait_selector,
            network_idle=network_idle,
            page_action=page_action,
        )
        return fetcher.fetch(url)

    def _auto(self, url: str, wait_selector=None,
              network_idle=False, page_action=None) -> FetchResult:
        """
        Progressive escalation: static → stealth → dynamic.
        """
        # Tier 1: fast HTTP
        result = self._static(url)
        if result.ok and not result.is_blocked:
            return result

        # Tier 2: stealth browser
        try:
            result = self._stealth(url)
            if result.ok and not result.is_blocked:
                return result
        except Exception:
            pass

        # Tier 3: full dynamic browser
        try:
            result = self._dynamic(url, wait_selector, network_idle, page_action)
        except Exception:
            pass

        return result

    # ------------------------------------------------------------------
    # Convenience class methods
    # ------------------------------------------------------------------

    @classmethod
    def get(cls, url: str, **kwargs) -> FetchResult:
        """One-shot fetch with auto mode."""
        return cls(**kwargs).fetch(url)
