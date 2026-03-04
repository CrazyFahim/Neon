"""
neon.scraper
~~~~~~~~~~~~
High-level Scraper and Spider — the primary user-facing interface.
"""

from __future__ import annotations

import time
from collections import deque
from typing import Any, Callable, Optional

from .engine import NeonEngine, FetcherMode
from .fetchers import FetchResult
from .utils import same_domain, is_valid_url, normalize_url


class Scraper:
    """
    High-level one-shot scraper.

    Example::

        scraper = Scraper()
        result  = scraper.get("https://quotes.toscrape.com")
        quotes  = [el.text for el in result.css(".quote .text")]
        print(quotes)
    """

    def __init__(
        self,
        mode: FetcherMode = "auto",
        proxy: Optional[str] = None,
        timeout: int = 20,
        headless: bool = True,
        delay: float = 0.0,
    ):
        self._engine = NeonEngine(mode=mode, proxy=proxy, timeout=timeout, headless=headless)
        self._delay = delay

    def get(self, url: str, selector: Optional[str] = None, **kwargs) -> FetchResult:
        """
        Fetch *url* and return a :class:`~neon.fetchers.FetchResult`.

        If *selector* is given, the result will also have a convenience
        ``.matches`` attribute containing the matched elements.
        """
        result = self._engine.fetch(url, **kwargs)
        if selector:
            result.matches = result.css(selector)  # type: ignore[attr-defined]
        return result

    def scrape(self, url: str, selector: str, attr: Optional[str] = None) -> list[str]:
        """
        Convenient one-liner: fetch *url*, select elements via *selector*,
        return their text (or *attr* value) as a list of strings.
        """
        result = self.get(url)
        elements = result.css(selector)
        if attr:
            return [el.get(attr) for el in elements if el.get(attr)]
        return [el.text for el in elements if el.text.strip()]

    def crawl(
        self,
        start_url: str,
        callback: Callable[[FetchResult], Any],
        max_pages: int = 50,
        max_depth: int = 3,
        same_domain_only: bool = True,
        delay: float = 1.0,
    ) -> list[Any]:
        """
        BFS crawl starting from *start_url*.

        Parameters
        ----------
        start_url:
            The seed URL.
        callback:
            Called with each :class:`~neon.fetchers.FetchResult`.
            If it returns a non-None value it is appended to the results list.
        max_pages:
            Maximum number of pages to visit.
        max_depth:
            Maximum link depth from the seed.
        same_domain_only:
            If True (default), follow only links on the same domain.
        delay:
            Seconds to wait between requests.
        """
        visited: set[str] = set()
        queue: deque[tuple[str, int]] = deque([(start_url, 0)])
        results: list[Any] = []

        while queue and len(visited) < max_pages:
            url, depth = queue.popleft()
            if url in visited:
                continue
            visited.add(url)

            result = self._engine.fetch(url)
            item = callback(result)
            if item is not None:
                results.append(item)

            if depth < max_depth:
                for link in result.links(same_domain_only=same_domain_only):
                    if link not in visited and is_valid_url(link):
                        queue.append((link, depth + 1))

            if delay > 0:
                time.sleep(delay)

        return results


class Spider:
    """
    Scrapy-inspired spider interface.

    Subclass this, set ``start_urls``, and implement ``parse(result)``.

    Example::

        class QuoteSpider(Spider):
            start_urls = ["https://quotes.toscrape.com/"]

            def parse(self, result):
                for q in result.css(".quote"):
                    yield {"text": q.css(".text")[0].text,
                           "author": q.css("small.author")[0].text}

                next_btn = result.css(".next a")
                if next_btn:
                    yield next_btn[0].get("href")   # string → follow as next URL

        data = QuoteSpider().start()
        print(data)
    """

    name: str = "spider"
    start_urls: list[str] = []
    mode: FetcherMode = "auto"
    delay: float = 1.0
    max_pages: int = 200
    proxy: Optional[str] = None
    headless: bool = True

    def __init__(self):
        self._engine = NeonEngine(
            mode=self.mode, proxy=self.proxy, headless=self.headless
        )
        self._visited: set[str] = set()
        self._items: list[Any] = []

    def parse(self, result: FetchResult):
        """Override in subclass. Yield dicts (items) or URL strings (follow)."""
        raise NotImplementedError

    def start(self) -> list[Any]:
        """Run the spider and return all collected items."""
        queue: deque[str] = deque(self.start_urls)

        while queue and len(self._visited) < self.max_pages:
            url = queue.popleft()
            if not is_valid_url(url) or url in self._visited:
                continue
            self._visited.add(url)

            result = self._engine.fetch(url)
            for output in self.parse(result):
                if isinstance(output, str):
                    next_url = normalize_url(output, url)
                    if is_valid_url(next_url) and next_url not in self._visited:
                        queue.append(next_url)
                elif isinstance(output, dict):
                    self._items.append(output)

            if self.delay > 0:
                time.sleep(self.delay)

        return self._items
