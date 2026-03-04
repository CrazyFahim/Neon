"""
neon.cli
~~~~~~~~
Interactive command-line interface for Neon.

Usage::

    python -m neon.cli fetch https://example.com
    python -m neon.cli scrape https://quotes.toscrape.com --css ".quote .text"
    python -m neon.cli links https://example.com
    python -m neon.cli shell
"""

from __future__ import annotations

import sys
import json

try:
    import click
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text
    from rich import print as rprint
except ImportError:
    raise SystemExit("CLI dependencies missing. Run: pip install click rich")

from .engine import NeonEngine
from .scraper import Scraper

console = Console()

NEON_BANNER = """
[bold cyan] ███╗   ██╗███████╗ ██████╗ ███╗   ██╗[/bold cyan]
[bold cyan] ████╗  ██║██╔════╝██╔═══██╗████╗  ██║[/bold cyan]
[bold cyan] ██╔██╗ ██║█████╗  ██║   ██║██╔██╗ ██║[/bold cyan]
[bold cyan] ██║╚██╗██║██╔══╝  ██║   ██║██║╚██╗██║[/bold cyan]
[bold cyan] ██║ ╚████║███████╗╚██████╔╝██║ ╚████║[/bold cyan]
[bold cyan] ╚═╝  ╚═══╝╚══════╝ ╚═════╝ ╚═╝  ╚═══╝[/bold cyan]
[dim]  Browsing Engine · v1.0.0[/dim]
"""


# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------

@click.group()
@click.version_option("1.0.0", prog_name="neon")
def cli():
    """⚡ Neon — Browsing Engine with Web Scraping built-in."""
    pass


# ---------------------------------------------------------------------------
# fetch
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("url")
@click.option("--mode", default="auto", type=click.Choice(["auto", "static", "stealth", "dynamic"]),
              show_default=True, help="Fetcher mode.")
@click.option("--proxy", default=None, help="Proxy URL (http://host:port).")
@click.option("--markdown", "as_markdown", is_flag=True, default=False,
              help="Output page as Markdown.")
@click.option("--json", "as_json", is_flag=True, default=False,
              help="Output page metadata as JSON.")
@click.option("--timeout", default=20, show_default=True, help="Timeout in seconds.")
def fetch(url, mode, proxy, as_markdown, as_json, timeout):
    """Fetch a URL and display the result."""
    console.print(NEON_BANNER)

    with console.status(f"[cyan]Fetching {url}…[/cyan]"):
        engine = NeonEngine(mode=mode, proxy=proxy, timeout=timeout)
        result = engine.fetch(url)

    # Status line
    color = "green" if result.ok else "red"
    console.print(
        f"[{color}]● {result.status_code}[/{color}]  "
        f"[bold]{result.url}[/bold]  "
        f"[dim]{'⚠ blocked' if result.is_blocked else 'ok'}[/dim]"
    )

    if as_json:
        data = result.to_json()
        console.print_json(json.dumps(data, indent=2))
        return

    if as_markdown:
        md = result.to_markdown()
        console.print(Panel(md[:4000], title="[bold]Markdown[/bold]", border_style="cyan"))
        return

    # Default: show text
    text = result.text()[:3000]
    console.print(Panel(text, title=f"[bold]{url}[/bold]", border_style="cyan"))


# ---------------------------------------------------------------------------
# scrape
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("url")
@click.option("--css", "css_sel", default=None, help="CSS selector to scrape.")
@click.option("--xpath", "xpath_sel", default=None, help="XPath expression to scrape.")
@click.option("--attr", default=None, help="Extract an attribute instead of text.")
@click.option("--mode", default="auto", type=click.Choice(["auto", "static", "stealth", "dynamic"]),
              show_default=True)
@click.option("--json", "as_json", is_flag=True, default=False, help="Output as JSON.")
def scrape(url, css_sel, xpath_sel, attr, mode, as_json):
    """Scrape elements from a URL using CSS or XPath selectors."""
    if not css_sel and not xpath_sel:
        console.print("[red]Provide --css or --xpath selector.[/red]")
        sys.exit(1)

    with console.status(f"[cyan]Scraping {url}…[/cyan]"):
        engine = NeonEngine(mode=mode)
        result = engine.fetch(url)

    elements = result.css(css_sel) if css_sel else result.xpath(xpath_sel)

    if not elements:
        console.print("[yellow]No elements matched.[/yellow]")
        return

    table = Table(title=f"Results from [cyan]{url}[/cyan]", show_lines=True)
    table.add_column("#", style="dim", width=4)
    table.add_column("Text / Value", style="white")
    if attr:
        table.add_column(f"@{attr}", style="green")

    items = []
    for i, el in enumerate(elements, 1):
        text_val = el.text if hasattr(el, "text") else str(el)
        if attr:
            attr_val = el.get(attr) if hasattr(el, "get") else ""
            table.add_row(str(i), text_val[:120], attr_val)
            items.append({"text": text_val, attr: attr_val})
        else:
            table.add_row(str(i), text_val[:120])
            items.append({"text": text_val})

    if as_json:
        console.print_json(json.dumps(items, indent=2))
    else:
        console.print(table)
        console.print(f"\n[dim]Found {len(elements)} element(s).[/dim]")


# ---------------------------------------------------------------------------
# links
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("url")
@click.option("--same-domain", is_flag=True, default=False, help="Same domain only.")
@click.option("--mode", default="auto", type=click.Choice(["auto", "static", "stealth", "dynamic"]),
              show_default=True)
def links(url, same_domain, mode):
    """Extract all links from a URL."""
    with console.status(f"[cyan]Fetching links from {url}…[/cyan]"):
        engine = NeonEngine(mode=mode)
        result = engine.fetch(url)

    found = result.links(same_domain_only=same_domain)
    if not found:
        console.print("[yellow]No links found.[/yellow]")
        return

    table = Table(title=f"Links on [cyan]{url}[/cyan]")
    table.add_column("#", style="dim", width=4)
    table.add_column("URL")
    for i, link in enumerate(found, 1):
        table.add_row(str(i), link)

    console.print(table)
    console.print(f"\n[dim]Total: {len(found)} link(s).[/dim]")


# ---------------------------------------------------------------------------
# shell  (interactive REPL)
# ---------------------------------------------------------------------------

@cli.command()
def shell():
    """Launch the interactive Neon scraping shell."""
    console.print(NEON_BANNER)
    console.print("[bold cyan]Interactive Shell[/bold cyan]  [dim]Type 'help' or 'exit'.[/dim]\n")

    engine = NeonEngine(mode="auto")
    current: dict = {}

    help_text = """
[bold]Commands[/bold]
  fetch <url>              Fetch a URL
  css <selector>           CSS selector on last result
  xpath <expr>             XPath on last result
  links                    Show links from last result
  text                     Show page text
  markdown                 Show page as Markdown
  json                     Show page metadata as JSON
  mode <auto|static|stealth|dynamic>  Change fetch mode
  help                     Show this message
  exit / quit              Exit the shell
"""

    while True:
        try:
            raw = console.input("[bold cyan]neon>[/bold cyan] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Goodbye.[/dim]")
            break

        if not raw:
            continue

        parts = raw.split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        if cmd in ("exit", "quit"):
            console.print("[dim]Goodbye.[/dim]")
            break

        elif cmd == "help":
            console.print(help_text)

        elif cmd == "fetch":
            if not arg:
                console.print("[red]Usage: fetch <url>[/red]")
                continue
            with console.status(f"[cyan]Fetching {arg}…[/cyan]"):
                current["result"] = engine.fetch(arg)
            r = current["result"]
            color = "green" if r.ok else "red"
            console.print(f"[{color}]● {r.status_code}[/{color}]  [bold]{r.url}[/bold]")

        elif cmd == "css":
            if "result" not in current:
                console.print("[yellow]Fetch a URL first.[/yellow]")
            elif not arg:
                console.print("[red]Usage: css <selector>[/red]")
            else:
                els = current["result"].css(arg)
                for i, el in enumerate(els, 1):
                    console.print(f"  [dim]{i}.[/dim] {el.text[:120]}")
                console.print(f"[dim]Found {len(els)} element(s).[/dim]")

        elif cmd == "xpath":
            if "result" not in current:
                console.print("[yellow]Fetch a URL first.[/yellow]")
            elif not arg:
                console.print("[red]Usage: xpath <expr>[/red]")
            else:
                els = current["result"].xpath(arg)
                for i, el in enumerate(els, 1):
                    text = el.text if hasattr(el, "text") else str(el)
                    console.print(f"  [dim]{i}.[/dim] {text[:120]}")
                console.print(f"[dim]Found {len(els)} node(s).[/dim]")

        elif cmd == "links":
            if "result" not in current:
                console.print("[yellow]Fetch a URL first.[/yellow]")
            else:
                lnks = current["result"].links()
                for i, l in enumerate(lnks[:30], 1):
                    console.print(f"  [dim]{i}.[/dim] [blue]{l}[/blue]")
                if len(lnks) > 30:
                    console.print(f"  [dim]… and {len(lnks)-30} more.[/dim]")

        elif cmd == "text":
            if "result" not in current:
                console.print("[yellow]Fetch a URL first.[/yellow]")
            else:
                console.print(current["result"].text()[:2000])

        elif cmd == "markdown":
            if "result" not in current:
                console.print("[yellow]Fetch a URL first.[/yellow]")
            else:
                console.print(current["result"].to_markdown()[:3000])

        elif cmd == "json":
            if "result" not in current:
                console.print("[yellow]Fetch a URL first.[/yellow]")
            else:
                console.print_json(json.dumps(current["result"].to_json(), indent=2))

        elif cmd == "mode":
            valid = {"auto", "static", "stealth", "dynamic"}
            if arg not in valid:
                console.print(f"[red]Invalid mode. Choose from: {', '.join(valid)}[/red]")
            else:
                engine = NeonEngine(mode=arg)  # type: ignore[arg-type]
                console.print(f"[green]Mode set to [bold]{arg}[/bold].[/green]")

        else:
            console.print(f"[red]Unknown command: {cmd!r}. Type 'help'.[/red]")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    cli()
