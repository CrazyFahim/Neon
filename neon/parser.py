"""
neon.parser
~~~~~~~~~~~
HTML response parser — CSS, XPath, text extraction, markdown, JSON output.
"""

from __future__ import annotations

import re
import json
from typing import Any, Optional, Union
from urllib.parse import urljoin

from .utils import html_to_markdown


class _Element:
    """Thin wrapper around an lxml element with a rich API."""

    def __init__(self, el, base_url: str = ""):
        self._el = el
        self._base_url = base_url

    # ------------------------------------------------------------------
    # Text helpers
    # ------------------------------------------------------------------

    @property
    def text(self) -> str:
        """All inner text (including descendants), stripped."""
        from lxml.etree import tostring  # type: ignore
        raw = self._el.text_content() if hasattr(self._el, "text_content") else (self._el.text or "")
        return raw.strip()

    @property
    def html(self) -> str:
        """Outer HTML of this element."""
        from lxml import etree
        return etree.tostring(self._el, encoding="unicode", method="html")

    @property
    def inner_html(self) -> str:
        """Inner HTML of this element."""
        from lxml import etree
        result = self._el.text or ""
        for child in self._el:
            result += etree.tostring(child, encoding="unicode", method="html")
        return result

    # ------------------------------------------------------------------
    # Attribute helpers
    # ------------------------------------------------------------------

    @property
    def attrib(self) -> dict[str, str]:
        return dict(self._el.attrib)

    def get(self, attr: str, default: str = "") -> str:
        return self._el.get(attr, default)

    # ------------------------------------------------------------------
    # Sub-selection
    # ------------------------------------------------------------------

    def css(self, selector: str) -> list["_Element"]:
        from cssselect import GenericTranslator
        from lxml import etree
        xpath = GenericTranslator().css_to_xpath(selector)
        return [_Element(e, self._base_url) for e in self._el.xpath(xpath)]

    def xpath(self, expr: str) -> list[Union["_Element", str]]:
        results = self._el.xpath(expr)
        out = []
        for r in results:
            if isinstance(r, str):
                out.append(r)
            else:
                out.append(_Element(r, self._base_url))
        return out

    def __repr__(self) -> str:
        tag = getattr(self._el, "tag", "?")
        return f"<Element {tag!r} text={self.text[:40]!r}>"


class NeonParser:
    """
    Parse an HTML string and provide a rich querying API.

    Example::

        page = NeonParser(html, url="https://example.com")
        titles = page.css("h1, h2")
        links  = page.links()
        md     = page.to_markdown()
    """

    def __init__(self, html: str, url: str = "", status_code: int = 200,
                 headers: Optional[dict] = None):
        self.url = url
        self.status_code = status_code
        self.headers = headers or {}
        self._html = html
        self._root = self._parse(html)

    # ------------------------------------------------------------------
    # Building the tree
    # ------------------------------------------------------------------

    @staticmethod
    def _parse(html: str):
        if not html or not html.strip():
            # Return an empty document root to avoid crashes
            from lxml.html import fromstring  # type: ignore
            return fromstring("<html><body></body></html>")
        try:
            from lxml.html import fromstring  # type: ignore
            return fromstring(html)
        except Exception:
            raise RuntimeError("lxml is required: pip install lxml")

    # ------------------------------------------------------------------
    # Selection
    # ------------------------------------------------------------------

    def css(self, selector: str) -> list[_Element]:
        """Return all elements matching *selector* (CSS)."""
        try:
            from cssselect import GenericTranslator  # type: ignore
        except ImportError:
            raise RuntimeError("cssselect is required: pip install cssselect")
        xpath_expr = GenericTranslator().css_to_xpath(selector)
        return [_Element(e, self.url) for e in self._root.xpath(xpath_expr)]

    def xpath(self, expr: str) -> list[Union[_Element, str]]:
        """Return all nodes matching an XPath expression."""
        results = self._root.xpath(expr)
        out: list[Union[_Element, str]] = []
        for r in results:
            if isinstance(r, str):
                out.append(r)
            else:
                out.append(_Element(r, self.url))
        return out

    def find(self, tag: str, attrs: Optional[dict] = None, **kw) -> Optional[_Element]:
        """BeautifulSoup-style: find first element matching tag + attribute filters."""
        results = self.find_all(tag, attrs, **kw)
        return results[0] if results else None

    def find_all(self, tag: str, attrs: Optional[dict] = None, **kw) -> list[_Element]:
        """BeautifulSoup-style: find all elements matching tag + attribute filters."""
        attrs = {**(attrs or {}), **kw}
        parts = [tag]
        for k, v in attrs.items():
            k = "class" if k == "class_" else k
            parts.append(f'[@{k}="{v}"]')
        selector = "".join(parts)
        try:
            return [_Element(e, self.url) for e in self._root.xpath(f".//{selector}")]
        except Exception:
            return []

    # ------------------------------------------------------------------
    # Text / regex
    # ------------------------------------------------------------------

    def text(self, pattern: Optional[str] = None) -> str:
        """
        Return all visible text from the page.
        If *pattern* is given, return only the first regex match group.
        """
        raw = self._root.text_content()
        if pattern:
            m = re.search(pattern, raw)
            return m.group(1) if m and m.lastindex else (m.group(0) if m else "")
        return re.sub(r"\s{2,}", "\n", raw).strip()

    def find_by_text(self, text: str, tag: str = "*") -> list[_Element]:
        """Find elements whose text content contains *text* (case-insensitive)."""
        expr = f".//{tag}[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{text.lower()}')]"
        return [_Element(e, self.url) for e in self._root.xpath(expr)]

    # ------------------------------------------------------------------
    # Links
    # ------------------------------------------------------------------

    def links(self, same_domain_only: bool = False) -> list[str]:
        """Extract all `<a href>` links, resolved to absolute URLs."""
        from .utils import same_domain as _same_domain
        hrefs = []
        for a in self._root.xpath(".//a[@href]"):
            href = a.get("href", "").strip()
            if not href or href.startswith("#") or href.startswith("javascript:"):
                continue
            full = urljoin(self.url, href)
            if same_domain_only and not _same_domain(full, self.url):
                continue
            hrefs.append(full)
        return list(dict.fromkeys(hrefs))  # deduplicate preserving order

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def to_markdown(self) -> str:
        """Convert the page body to Markdown."""
        return html_to_markdown(self._html)

    def to_json(self, selector: Optional[str] = None, attrs: Optional[list[str]] = None) -> list[dict[str, Any]]:
        """
        Extract structured data.
        If *selector* is given, return attrs of matched elements.
        Otherwise return page metadata.
        """
        if selector:
            elements = self.css(selector)
            result = []
            for el in elements:
                if attrs:
                    result.append({a: el.get(a) for a in attrs})
                else:
                    result.append({"text": el.text, "html": el.html, **el.attrib})
            return result

        # Page metadata
        title_els = self.css("title")
        desc_els = self.css('meta[name="description"]')
        return [{
            "url": self.url,
            "status_code": self.status_code,
            "title": title_els[0].text if title_els else "",
            "description": desc_els[0].get("content") if desc_els else "",
            "links_count": len(self.links()),
        }]

    def __repr__(self) -> str:
        title = self.css("title")
        t = title[0].text[:60] if title else "?"
        return f"<NeonParser url={self.url!r} title={t!r} status={self.status_code}>"
