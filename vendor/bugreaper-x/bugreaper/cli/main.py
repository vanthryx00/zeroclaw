from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
from rich.table import Table
from rich import print as rprint

app = typer.Typer(name="bugreaper", help="BugReaper X — Autonomous Vulnerability Intelligence Platform")
console = Console()

BANNER = """
[bold red]██████╗ ███████╗ █████╗ ██████╗ ███████╗██████╗[/]
[bold red]██╔══██╗██╔════╝██╔══██╗██╔══██╗██╔════╝██╔══██╗[/]
[bold red]██████╔╝█████╗  ███████║██████╔╝█████╗  ██████╔╝[/]
[bold red]██╔══██╗██╔══╝  ██╔══██║██╔═══╝ ██╔══╝  ██╔══██╗[/]
[bold red]██║  ██║███████╗██║  ██║██║     ███████╗██║  ██║[/]
[bold red]╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝╚═╝     ╚══════╝╚═╝  ╚═╝[/]
[dim]BugReaper X v4.0 — Kairyx Security Solutions[/]
[dim]REAPER: Autonomous Vulnerability Intelligence[/]
"""


def _print_banner() -> None:
    console.print(Panel(BANNER, border_style="red", padding=(0, 2)))


@app.command()
def scan(
    target: str = typer.Argument(..., help="Target URL to scan"),
    scan_types: Optional[str] = typer.Option(None, "--types", "-t", help="Comma-separated scan types (all if omitted)"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Output file path"),
    fmt: str = typer.Option("html", "--format", "-f", help="Report format: html|json|markdown|csv|sarif|pdf"),
    aggressive: bool = typer.Option(False, "--aggressive", "-a", help="Enable aggressive scanning"),
    no_ai: bool = typer.Option(False, "--no-ai", help="Disable REAPER AI analysis"),
    burp: Optional[str] = typer.Option(None, "--burp", help="Burp Suite proxy URL (e.g. http://127.0.0.1:8080)"),
    timeout: int = typer.Option(30, "--timeout", help="Request timeout in seconds"),
) -> None:
    """Run a full vulnerability scan against a target."""
    _print_banner()

    from bugreaper.core.models import ScanConfig, ScanTarget, ScanType
    from bugreaper.core.engine import engine

    scan_type_list = list(ScanType)
    if scan_types:
        try:
            scan_type_list = [ScanType(t.strip()) for t in scan_types.split(",")]
        except ValueError as e:
            console.print(f"[red]Invalid scan type: {e}[/]")
            raise typer.Exit(1)

    scan_target = ScanTarget(url=target, timeout=timeout, proxy=burp)
    scan_config = ScanConfig(
        scan_types=scan_type_list,
        ai_analysis=not no_ai,
        burp_proxy=burp,
        aggressive=aggressive,
    )

    console.print(f"\n[bold green]▶ Scanning:[/] {target}")
    console.print(f"[dim]  Scanners: {len(scan_type_list)} modules | AI: {'enabled' if not no_ai else 'disabled'}[/]\n")

    phase_names = ["Network", "Enumeration", "Application", "Exploitation"]
    scanner_event_log: list[str] = []

    def handle_event(event_type: str, data: dict) -> None:
        if event_type == "phase_start":
            console.print(f"  [bold cyan]Phase {data['phase']}:[/] {' | '.join(data['scanners'])}")
        elif event_type == "scanner_complete":
            scanner_event_log.append(f"  ✓ {data['scanner']}: {data['count']} findings")
        elif event_type == "ai_analysis_start":
            console.print("\n  [bold magenta]⚡ REAPER AI analyzing...[/]")
        elif event_type == "scan_complete":
            console.print(f"\n  [bold green]✓ Scan complete[/] — {data['vuln_count']} vulnerabilities | Risk: {data['risk_score']}/10")

    engine.on_event(handle_event)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("[red]Scanning...", total=None)
        result = asyncio.run(engine.scan(scan_target, scan_config))
        progress.update(task, completed=True)

    _print_results_table(result)

    if output or fmt:
        from bugreaper.reporting.generator import generate_report
        out_path = output or f"bugreaper-report-{result.id[:8]}.{fmt}"
        generate_report(result, fmt, out_path)
        console.print(f"\n[green]✓ Report saved:[/] {out_path}")

    if result.ai_analysis:
        console.print("\n[bold magenta]REAPER Analysis:[/]")
        console.print(Panel(result.ai_analysis[:2000], border_style="magenta"))


@app.command()
def quick(
    target: str = typer.Argument(..., help="Target URL for quick scan"),
    fmt: str = typer.Option("json", "--format", "-f", help="Output format"),
) -> None:
    """Quick scan (headers, SSL, recon, OWASP only)."""
    _print_banner()

    from bugreaper.core.models import ScanConfig, ScanTarget, ScanType
    from bugreaper.core.engine import engine

    quick_types = [ScanType.HEADERS, ScanType.SSL, ScanType.RECON, ScanType.OWASP]
    result = asyncio.run(engine.scan(
        ScanTarget(url=target),
        ScanConfig(scan_types=quick_types, ai_analysis=False),
    ))
    _print_results_table(result)


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", "--host"),
    port: int = typer.Option(8900, "--port"),
    reload: bool = typer.Option(False, "--reload"),
) -> None:
    """Start the BugReaper X API server."""
    _print_banner()
    console.print(f"[bold green]Starting REAPER API Server[/] on http://{host}:{port}")
    try:
        import uvicorn
        from bugreaper.api.server import create_app
        uvicorn.run(create_app(), host=host, port=port, reload=reload)
    except ImportError:
        console.print("[red]uvicorn not installed. Run: pip install uvicorn[standard][/]")


@app.command()
def report(
    scan_json: str = typer.Argument(..., help="Path to scan result JSON"),
    fmt: str = typer.Option("html", "--format", "-f"),
    output: Optional[str] = typer.Option(None, "--output", "-o"),
) -> None:
    """Generate a report from a saved scan result."""
    import json as json_mod
    from bugreaper.core.models import ScanResult
    from bugreaper.reporting.generator import generate_report

    try:
        data = json_mod.loads(Path(scan_json).read_text())
        result = ScanResult.model_validate(data)
        out = generate_report(result, fmt, output)
        console.print(f"[green]Report generated:[/] {out or 'stdout'}")
        if not output:
            console.print(out[:500])
    except Exception as e:
        console.print(f"[red]Error:[/] {e}")


@app.command()
def version() -> None:
    """Show BugReaper X version."""
    _print_banner()
    console.print("[bold]BugReaper X[/] v4.0.0 — Kairyx Security Solutions")
    console.print("[dim]REAPER: Reconnaissance, Exploitation and Penetration Intelligence Engine[/]")
    console.print("[dim]Fort Saskatchewan, Alberta | security@kairyx.io | bugreaper-x.ca[/]")


def _print_results_table(result: Any) -> None:
    counts = result.vuln_counts
    table = Table(title="Vulnerability Summary", show_header=True, header_style="bold blue")
    table.add_column("Severity", style="bold")
    table.add_column("Count", justify="center")

    colors = {
        "god-tier": "magenta", "critical": "red", "high": "orange3",
        "medium": "yellow", "low": "blue", "info": "dim",
    }
    for sev in ["god-tier", "critical", "high", "medium", "low", "info"]:
        count = counts.get(sev, 0)
        if count > 0:
            table.add_row(f"[{colors[sev]}]{sev.upper()}[/]", str(count))

    console.print(table)
    console.print(f"\n[bold]Total:[/] {len(result.vulnerabilities)} | [bold]Risk Score:[/] {result.risk_score}/10")


if __name__ == "__main__":
    app()
