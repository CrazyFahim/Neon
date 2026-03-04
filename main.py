#!/usr/bin/env python3
"""
main.py — Neon Browsing Engine Demo
====================================

Demonstrates the core features:
  1. Static fetch + CSS selection
  2. Link extraction
  3. Markdown conversion
  4. Spider crawl
  5. CLI (shown as code snippets)
"""

from __future__ import annotations

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    console = Console()
except ImportError:
    raise SystemExit("Run: pip install rich")

from neon import NeonEngine, Scraper, Spider


console.print("""
[bold cyan] ███╗   ██╗███████╗ ██████╗ ███╗   ██╗[/bold cyan]
[bold cyan] ████╗  ██║██╔════╝██╔═══██╗████╗  ██║[/bold cyan]
[bold cyan] ██╔██╗ ██║█████╗  ██║   ██║██╔██╗ ██║[/bold cyan]
[bold cyan] ██║╚██╗██║██╔══╝  ██║   ██║██║╚██╗██║[/bold cyan]
[bold cyan] ██║ ╚████║███████╗╚██████╔╝██║ ╚████║[/bold cyan]
[bold cyan] ╚═╝  ╚═══╝╚══════╝ ╚═════╝ ╚═╝  ╚═══╝[/bold cyan]
[dim]  Browsing Engine Demo · v1.0.0[/dim]
""")


# ---------------------------------------------------------------------------
# 1. Basic fetch
# ---------------------------------------------------------------------------
console.rule("[bold cyan]1. Static Fetch — example.com[/bold cyan]")

engine = NeonEngine(mode="static")

with console.status("[cyan]Fetching https://example.com …[/cyan]"):
    result = engine.fetch("https://example.com")

color = "green" if result.ok else "red"
console.print(f"[{color}]● {result.status_code}[/{color}]  [bold]{result.url}[/bold]  "
              f"[dim]{'🚧 blocked' if result.is_blocked else '✓ ok'}[/dim]")


# ---------------------------------------------------------------------------
# 2. CSS selector
# ---------------------------------------------------------------------------
console.rule("[bold cyan]2. CSS Selection[/bold cyan]")

h1_elements = result.css("h1")
p_elements  = result.css("p")

console.print(f"[green]<h1> tags found:[/green] {len(h1_elements)}")
for el in h1_elements:
    console.print(f"  [bold]{el.text}[/bold]")

console.print(f"\n[green]<p> tags found:[/green] {len(p_elements)}")
for el in p_elements[:3]:
    console.print(f"  {el.text[:100]}")


# ---------------------------------------------------------------------------
# 3. Link extraction
# ---------------------------------------------------------------------------
console.rule("[bold cyan]3. Link Extraction[/bold cyan]")

links = result.links()
table = Table(title="Links on example.com", show_lines=False)
table.add_column("#", style="dim", width=4)
table.add_column("URL", style="blue")

for i, link in enumerate(links[:10], 1):
    table.add_row(str(i), link)

console.print(table)
console.print(f"[dim]Total links: {len(links)}[/dim]")


# ---------------------------------------------------------------------------
# 4. Markdown export
# ---------------------------------------------------------------------------
console.rule("[bold cyan]4. Markdown Export[/bold cyan]")

md = result.to_markdown()
console.print(Panel(md[:800], title="[bold]Page as Markdown[/bold]", border_style="cyan"))


# ---------------------------------------------------------------------------
# 5. Scraper — quotes.toscrape.com
# ---------------------------------------------------------------------------
console.rule("[bold cyan]5. Scraper — quotes.toscrape.com[/bold cyan]")

scraper = Scraper(mode="static")

with console.status("[cyan]Scraping quotes.toscrape.com …[/cyan]"):
    quotes_result = scraper.get("https://quotes.toscrape.com")

quote_els  = quotes_result.css(".quote .text")
author_els = quotes_result.css(".quote .author")

q_table = Table(title="Scraped Quotes", show_lines=True)
q_table.add_column("#", style="dim", width=4)
q_table.add_column("Author", style="magenta")
q_table.add_column("Quote", style="white")

for i, (q, a) in enumerate(zip(quote_els[:5], author_els[:5]), 1):
    q_table.add_row(str(i), a.text, q.text[:80])

console.print(q_table)


# ---------------------------------------------------------------------------
# 6. Spider
# ---------------------------------------------------------------------------
console.rule("[bold cyan]6. Spider — quotes.toscrape.com[/bold cyan]")


class QuoteSpider(Spider):
    name = "quotes"
    start_urls = ["https://quotes.toscrape.com/"]
    mode = "static"
    delay = 0.5
    max_pages = 3

    def parse(self, result):
        for q, a in zip(result.css(".quote .text"), result.css(".quote .author")):
            yield {"quote": q.text, "author": a.text}

        next_btn = result.css(".next a")
        if next_btn:
            yield next_btn[0].get("href")


with console.status("[cyan]Running spider (max 3 pages)…[/cyan]"):
    data = QuoteSpider().start()

s_table = Table(title=f"Spider Results ({len(data)} items)", show_lines=True)
s_table.add_column("#", style="dim", width=4)
s_table.add_column("Author", style="magenta")
s_table.add_column("Quote", style="white")

for i, item in enumerate(data[:8], 1):
    s_table.add_row(str(i), item.get("author", ""), item.get("quote", "")[:80])

console.print(s_table)


# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
console.rule()
console.print("""
[bold green]✓ Demo complete![/bold green]

[bold]CLI usage:[/bold]
  [cyan]python -m neon.cli fetch https://example.com[/cyan]
  [cyan]python -m neon.cli scrape https://quotes.toscrape.com --css ".quote .text"[/cyan]
  [cyan]python -m neon.cli links https://example.com[/cyan]
  [cyan]python -m neon.cli shell[/cyan]
""")
