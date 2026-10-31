"""Aegis command-line interface.

Usage:
    aegis                       # interactive session
    aegis "how do I enumerate SMB on 10.0.0.5?"   # one-shot
    aegis status                # show backend + config health
    aegis mode auto_safe        # change safety mode
    aegis scope add 10.0.0.0/24 # declare authorized target scope
    aegis scope list
    aegis audit -n 20           # show recent audit entries
    aegis doctor                # diagnose local model setup
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Optional

from . import __version__
from .agent import Agent
from .config import Config, VALID_MODES
from .executor import ExecutionResult
from .safety import Level

try:
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.panel import Panel
    from rich.prompt import Prompt
    from rich.table import Table
    _console = Console()
except ModuleNotFoundError:  # pragma: no cover
    _console = None


def _print(*args, **kwargs):
    if _console:
        _console.print(*args, **kwargs)
    else:
        print(*args)


LEVEL_COLOR = {
    Level.READ_ONLY: "green",
    Level.SAFE_WRITE: "cyan",
    Level.RISKY: "yellow",
    Level.OFFENSIVE: "magenta",
    Level.BLOCKED: "red",
}


# --------------------------------------------------------------------------
# Confirmation handler
# --------------------------------------------------------------------------

def make_confirm(auto_yes: bool = False):
    def confirm(verdict, command: str) -> bool:
        if auto_yes:
            return True
        color = LEVEL_COLOR.get(verdict.level, "white")
        _print(Panel(
            f"[bold]{command}[/bold]\n\n"
            f"level: [{color}]{verdict.label}[/{color}]\n"
            f"reason: {verdict.reason}",
            title="Aegis wants to run a command", border_style=color,
        ))
        if _console:
            answer = Prompt.ask("Run it?", choices=["y", "n", "e"], default="n")
        else:
            answer = input("Run it? [y/n/e(dit)] ").strip().lower() or "n"
        if answer == "e":
            edited = input("edit> ").strip()
            return bool(edited)
        return answer == "y"
    return confirm


def make_plan_confirm(auto_yes: bool = False):
    """Whole-plan approval (#47): show every classified step, approve once."""
    def confirm_plan(plan) -> bool:
        if _console:
            border = "red" if plan.max_level == Level.BLOCKED else \
                LEVEL_COLOR.get(plan.max_level, "white")
            _print(Panel(plan.render(), title="Aegis proposes a plan",
                         border_style=border))
            if auto_yes:
                return True
            answer = Prompt.ask("Run the whole plan?",
                                choices=["y", "n"], default="n")
        else:
            _print("Aegis proposes a plan:")
            _print(plan.render())
            if auto_yes:
                return True
            answer = input("Run the whole plan? [y/n] ").strip().lower() or "n"
        return answer == "y"
    return confirm_plan


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------

def cmd_status(cfg: Config) -> int:
    from .brain import BackendRouter
    router = BackendRouter(cfg)
    _print(Panel(router.status(), title="Aegis status", border_style="blue"))
    _print(f"config source: {cfg.source or '(defaults)'}")
    _print(f"config: {cfg.describe()}")
    return 0


def cmd_doctor(cfg: Config) -> int:
    from shutil import which
    checks = []

    def check(label, ok, hint=""):
        checks.append((label, ok, hint))

    check("python >= 3.9", sys.version_info >= (3, 9))
    check("ollama binary", which("ollama") is not None, "install: https://ollama.com")
    check("llama-cli binary", which("llama-cli") is not None,
          "build llama.cpp or install the package")
    model_ok = os.path.isfile(os.path.expanduser(cfg.model.llamacpp_model_path))
    check("llama.cpp GGUF model", model_ok, cfg.model.llamacpp_model_path)

    from .brain import BackendRouter
    router = BackendRouter(cfg)
    active = router.select()
    check("a model backend reachable", active is not None,
          "start `ollama serve` or `llama-server`")

    if _console:
        table = Table(title="Aegis doctor")
        table.add_column("check")
        table.add_column("result")
        table.add_column("hint")
        for label, ok, hint in checks:
            table.add_row(label, "[green]ok[/green]" if ok else "[red]missing[/red]", hint)
        _print(table)
    else:
        _print("Aegis doctor")
        for label, ok, hint in checks:
            status = "ok" if ok else "MISSING"
            _print(f"  [{status}] {label}" + (f" — {hint}" if hint and not ok else ""))
    _print(f"\nactive backend: {active.info() if active else 'NONE'}")
    return 0 if all(c[1] for c in checks) else 1


def cmd_scope(cfg: Config, args) -> int:
    if args.scope_action == "list":
        if not cfg.safety.authorized_targets:
            _print("No authorized scope declared. Offensive tools will be refused.")
            return 0
        for t in cfg.safety.authorized_targets:
            _print(f"  - {t}")
        return 0
    if args.scope_action == "add":
        for t in args.targets:
            if t not in cfg.safety.authorized_targets:
                cfg.safety.authorized_targets.append(t)
        _persist_scope(cfg)
        _print(f"Scope updated: {', '.join(cfg.safety.authorized_targets)}")
        return 0
    if args.scope_action == "clear":
        cfg.safety.authorized_targets = []
        _persist_scope(cfg)
        _print("Scope cleared.")
        return 0
    return 0


def _persist_scope(cfg: Config) -> None:
    path = os.path.expanduser("~/.config/aegis/config.toml")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    lines = ["[safety]", f'mode = "{cfg.safety.mode}"']
    targets = ", ".join(f'"{t}"' for t in cfg.safety.authorized_targets)
    lines.append(f"authorized_targets = [{targets}]")
    lines.append(f'workspace_root = "{cfg.safety.workspace_root}"')
    lines.append(f"allow_sudo = {str(cfg.safety.allow_sudo).lower()}")
    try:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
        _print(f"Saved to {path}")
    except OSError as exc:
        _print(f"[red]could not save config: {exc}[/red]")


def cmd_mode(cfg: Config, mode: str) -> int:
    if mode not in VALID_MODES:
        _print(f"[red]invalid mode. choose from: {', '.join(VALID_MODES)}[/red]")
        return 1
    cfg.safety.mode = mode
    _persist_scope(cfg)
    _print(f"Safety mode set to [bold]{mode}[/bold].")
    return 0


def cmd_audit(cfg: Config, args) -> int:
    from .audit import AuditLog
    log = AuditLog(cfg.interface.audit_log)
    action = getattr(args, "audit_action", "show") or "show"

    if action == "verify":
        ok, idx, msg = log.verify()
        color = "green" if ok else "red"
        _print(Panel(msg, title="Audit integrity", border_style=color))
        return 0 if ok else 1

    if action == "seal":
        out = getattr(args, "out", None) or "aegis-audit-seal.json"
        head = log.seal(out)
        _print(f"Sealed {log.count()} records; head hash {head[:16]}… written to {out}")
        return 0

    out = log.tail(getattr(args, "n", 20))
    if not out:
        _print("No audit entries yet.")
        return 0
    for rec in out:
        ts = time.strftime("%H:%M:%S", time.localtime(rec.get("ts", 0)))
        cmd = rec.get("command") or rec.get("event") or rec.get("kind") or "?"
        decision = rec.get("decision") or rec.get("status") or ""
        _print(f"{ts}  {decision:<10} {cmd}")
    return 0


def cmd_privacy(cfg: Config, args) -> int:
    from .privacy import PrivacyAuditor, TorController

    action = getattr(args, "privacy_action", "status") or "status"

    if action == "status":
        report = PrivacyAuditor(cfg).audit()
        _print(Panel(report.to_text(), title="Privacy audit", border_style="cyan"))
        return 0 if report.failures == 0 else 1

    if action == "tor":
        _print(Panel(TorController(cfg).status(), title="Tor status", border_style="magenta"))
        return 0

    if action in ("plan", "harden"):
        auditor = PrivacyAuditor(cfg)
        report = auditor.audit()
        plan = auditor.hardening_plan()
        _print(Panel(report.to_text(), title="Privacy audit", border_style="cyan"))
        if not plan:
            _print("[green]Nothing to fix — posture is already clean.[/green]")
            return 0
        _print(Panel("\n".join(plan), title="Hardening plan", border_style="yellow"))
        if action == "plan":
            return 0
        # apply: route each command through the executor (classified + audited)
        agent = Agent(cfg)
        agent.executor.confirm = make_confirm(getattr(args, "yes", False))
        for command in plan:
            if command.startswith("#") or not command.strip():
                continue
            result = agent.executor.run(command)
            status = "ran" if result.ran else result.decision
            _print(f"  [{status}] {command}")
        return 0

    if action == "wipe":
        _print(Panel(
            "Memory wipe on shutdown is a boot-time feature, not a runtime command.\n\n"
            "Install it with:\n"
            "  sudo bash build/privacy/30-amnesia.sh\n\n"
            "That drops /etc/systemd/system/aegis-memwipe.service, which overwrites\n"
            "free RAM on every shutdown to defeat cold-boot attacks.\n\n"
            "To wipe now (before shutting down):\n"
            "  sudo sdmem -fllv    # from the 'secure-delete' package",
            title="Memory wipe", border_style="blue",
        ))
        return 0

    if action == "newid":
        _print(Panel(TorController(cfg).new_identity(), title="Tor identity",
                     border_style="magenta"))
        return 0

    if action == "leaktest":
        from .privacy import dns_leak_test
        result = dns_leak_test(cfg, live=getattr(args, "live", False))
        color = "red" if result.verdict == "LEAK" else "green"
        _print(Panel(result.to_text(), title="DNS leak test", border_style=color))
        return 1 if result.verdict == "LEAK" else 0

    if action == "panic":
        from .privacy import PanicController
        controller = PanicController(cfg)
        plan = controller.plan()
        _print(Panel("\n".join(plan), title="Panic plan", border_style="red"))
        if not getattr(args, "yes", False):
            _print("[yellow]Dry run. Re-run with --yes to actually execute.[/yellow]")
            return 0
        agent = Agent(cfg)
        agent.executor.confirm = make_confirm(True)
        for command in plan:
            if command.startswith("#") or not command.strip():
                continue
            result = agent.executor.run(command)
            status = "ran" if result.ran else result.decision
            _print(f"  [{status}] {command}")
        return 0
    return 0


def cmd_rescue(cfg: Config, args) -> int:
    from .rescue import RescueScanner, RescueActions, RESCUE_MOUNT
    from .executor import Executor

    action = getattr(args, "rescue_action", "scan") or "scan"
    scanner = RescueScanner()
    executor = Executor(cfg)
    executor.confirm = make_confirm(getattr(args, "yes", False))
    actions = RescueActions(executor, RESCUE_MOUNT)

    if action == "scan":
        disks = scanner.list_disks()
        if not disks:
            _print("[yellow]No block devices found (are you running as root?).[/yellow]")
            return 1
        for disk in disks:
            rm = " [removable]" if disk.removable else ""
            _print(f"[bold]{disk.name}[/bold]  {disk.size}  {disk.model}{rm}")
            for part in disk.partitions:
                mark = " [dim](probable system)[/dim]" if part.is_probable_system() else ""
                label = f" label={part.label}" if part.label else ""
                _print(f"   {part.device}  {part.size}  {part.fstype or '?'}{label}{mark}")
        return 0

    if action == "mount":
        if not args.device:
            _print("[red]usage: aegis rescue mount <device>[/red]")
            return 1
        _print(actions.mount(args.device))
        return 0

    if action == "unmount":
        _print(actions.unmount())
        return 0

    if action == "diagnose":
        findings = scanner.diagnose(RESCUE_MOUNT)
        lines = [f"[{f.icon}] {f.severity.upper():<8} {f.summary}" for f in findings]
        for f in findings:
            if f.detail:
                lines.append(f"      {f.detail}")
        _print(Panel("\n".join(lines), title="Rescue diagnosis", border_style="yellow"))
        return 0

    if action == "plan":
        findings = scanner.diagnose(RESCUE_MOUNT)
        plan = scanner.repair_plan(findings, getattr(args, "device", "<device>"))
        if not plan:
            _print("[green]No structural repairs suggested.[/green]")
            return 0
        _print(Panel("\n".join(plan), title="Repair plan", border_style="yellow"))
        return 0

    if action == "chroot":
        raw = getattr(args, "chroot_cmd", None)
        cmd = " ".join(raw) if isinstance(raw, (list, tuple)) else (raw or "")
        if not cmd.strip():
            _print('[red]usage: aegis rescue chroot "<command>"[/red]')
            return 1
        actions.bind_mounts()
        _print(actions.chroot(cmd))
        return 0

    if action == "fsck":
        if not args.device:
            _print("[red]usage: aegis rescue fsck <device>[/red]")
            return 1
        _print(actions.fsck(args.device))
        return 0

    if action == "bootloader":
        from .rescue import (detect_bootloader, plan_bootloader_repair,
                             BootRepairRunner)
        root = getattr(args, "root", None) or RESCUE_MOUNT
        device = getattr(args, "device", None) or ""
        esp = getattr(args, "esp", None) or ""

        info = detect_bootloader(root, device=device, esp_device=esp)
        plan = plan_bootloader_repair(info, device=device, esp_device=esp,
                                      mountpoint=root)

        # Default is a dry run: show the plan and change nothing.
        if not getattr(args, "apply", False):
            _print(Panel(plan.render(), title="Bootloader repair (dry run)",
                         border_style="yellow"))
            return 0

        if plan.refusal:
            _print(Panel(plan.render(), title="Bootloader repair REFUSED",
                         border_style="red"))
            return 1

        _print(Panel(plan.render(), title="Bootloader repair (applying)",
                     border_style="red"))
        runner = BootRepairRunner(executor, root)

        def on_step(step, result):
            status = "ran" if result.ran else result.decision
            color = "green" if status == "ran" else "yellow"
            _print(f"[{color}]▸ [{status}][/{color}] {step.command}")
            out = (result.stdout or "").strip()
            if out:
                _print(out[:2000])
            if result.stderr and result.stderr.strip():
                _print(f"[red]{result.stderr.strip()[:1000]}[/red]")

        results = runner.run(plan, on_step=on_step)
        failed = sum(1 for _, r in results
                     if getattr(r, "ran", False) and r.exit_code not in (0, None))
        _print(f"[bold]Bootloader repair: {len(results)} step(s), "
               f"{failed} failed.[/bold]")
        return 1 if failed else 0
    return 0


def cmd_allow(cfg: Config, args) -> int:
    from .allowlist import AllowStore, MATCH_PREFIX
    from .safety import classify

    store = AllowStore(cfg.safety.allowlist_file)
    action = getattr(args, "allow_action", "list") or "list"

    if action == "list":
        _print(store.render())
        return 0

    if action == "add":
        command = (getattr(args, "allow_arg", None) or "").strip()
        if not command:
            _print("[red]usage: aegis allow add <command>[/red]")
            return 1
        verdict = classify(command, cfg)
        rule = store.add(command, verdict.level,
                         match=MATCH_PREFIX if getattr(args, "prefix", False) else "exact",
                         note="added manually")
        if rule is None:
            _print(
                f"[red]refusing to remember this command.[/red]\n"
                f"It classifies as [b]{verdict.label}[/b] ({verdict.reason}).\n"
                "Only read-only, safe-write and risky commands can be "
                "remembered. Offensive tooling is authorised with "
                "`aegis scope add`, never with an allowlist."
            )
            return 1
        _print(f"[green]remembered[/green] {rule.describe()}")
        if rule.match == MATCH_PREFIX:
            _print("[yellow]prefix rule — every command starting with this "
                   "string is now allowed.[/yellow]")
        return 0

    if action == "rm":
        rule_id = getattr(args, "allow_arg", None)
        if not rule_id:
            _print("[red]usage: aegis allow rm <id>[/red]")
            return 1
        if store.revoke(rule_id):
            _print(f"[green]revoked[/green] {rule_id}")
            return 0
        _print(f"[red]no such rule: {rule_id}[/red]")
        return 1

    if action == "clear":
        n = store.clear()
        _print(f"[green]cleared[/green] {n} remembered command(s)")
        return 0
    return 0


def cmd_snippet(cfg: Config, args) -> int:
    from .snippets import SnippetStore

    store = SnippetStore(cfg.learning.snippet_file)
    action = getattr(args, "snippet_action", "list") or "list"

    if action == "save":
        code = getattr(args, "code", None)
        if not code and getattr(args, "file", None):
            try:
                with open(args.file, encoding="utf-8") as fh:
                    code = fh.read()
            except OSError as exc:
                _print(f"[red]cannot read {args.file}: {exc}[/red]")
                return 1
        if not code:
            if sys.stdin.isatty():
                _print("[red]provide --code or --file (or pipe code on stdin)[/red]")
                return 1
            code = sys.stdin.read()
        tags = [t for t in (args.tags or "").split(",") if t]
        snip = store.save(
            args.title or "untitled", code, language=args.lang, tags=tags,
            description=args.description or "", filename=args.file or "", source="cli",
        )
        _print(f"Saved {snip.id}: {snip.title} ({snip.language})")
        return 0

    if action == "list":
        items = store.search("", language=args.lang, tag=args.tags, limit=200)
        if not items:
            _print("No snippets saved yet.")
            return 0
        for s in items:
            tagstr = f" tags={','.join(s.tags)}" if s.tags else ""
            _print(f"{s.id}  {s.title}  ({s.language}){tagstr}  uses={s.uses}")
        return 0

    if action == "search":
        items = store.search(args.value or "", language=args.lang, tag=args.tags)
        if not items:
            _print("No matches.")
            return 0
        for s in items:
            _print(f"{s.id}  {s.title}  ({s.language})")
            if s.description:
                _print(f"    {s.description}")
        return 0

    if action == "get":
        snip = store.get(args.value or "")
        if not snip:
            _print(f"[red]no snippet {args.value}[/red]")
            return 1
        store.bump(snip.id)
        _print(f"# {snip.id} {snip.title} ({snip.language})")
        _print(snip.code)
        return 0

    if action == "export":
        dest = args.dest or os.path.join(cfg.safety.workspace_root, "snippets")
        paths = store.export(dest)
        _print(f"Exported {len(paths)} snippets to {dest}")
        return 0
    return 0


def cmd_learn(cfg: Config, args) -> int:
    from .learning import LearningEngine

    engine = LearningEngine(cfg)
    action = getattr(args, "learn_action", "stats") or "stats"
    value = getattr(args, "value", None)
    tags = [t for t in (getattr(args, "tags", None) or "").split(",") if t]

    if action == "stats":
        stats = engine.stats()
        _print(Panel(
            f"snippets: {stats['snippets']['count']}  "
            f"(languages: {stats['snippets']['languages']})\n"
            f"experiences: {stats['experiences']['count']}  "
            f"(kinds: {stats['experiences']['kinds']})",
            title="Learning store", border_style="green",
        ))
        return 0

    if action == "remember":
        if not value:
            _print("[red]usage: aegis learn remember \"text\"[/red]")
            return 1
        exp = engine.record_lesson(value, tags)
        _print(f"Remembered {exp.id}: {exp.title}")
        return 0

    if action == "prefer":
        if not value:
            _print("[red]usage: aegis learn prefer \"text\"[/red]")
            return 1
        exp = engine.record_preference(value, tags)
        _print(f"Recorded preference {exp.id}: {exp.title}")
        return 0

    if action == "search":
        results = engine.experiences.search(value or "")
        if not results:
            _print("No matches.")
            return 0
        for e in results:
            _print(f"{e.id} ({e.kind}) {e.title}: {e.content[:200]}")
        return 0

    if action == "lessons":
        for e in engine.experiences.all():
            _print(f"{e.id} ({e.kind}) {e.title}")
        return 0

    if action == "forget":
        if not value:
            _print("[red]usage: aegis learn forget <id>[/red]")
            return 1
        ok = engine.experiences.delete(value)
        _print("forgotten" if ok else f"[red]no experience {value}[/red]")
        return 0 if ok else 1
    return 0


def cmd_setup(cfg: Config, args) -> int:
    from .setup import run_wizard
    return run_wizard(
        profile=getattr(args, "profile", None),
        model=getattr(args, "model", None),
        auto=getattr(args, "auto", False),
        pull=not getattr(args, "no_pull", False),
        yes=getattr(args, "yes", False),
        show_only=getattr(args, "show", False),
        on_log=lambda msg: _print(msg),
    )


# --------------------------------------------------------------------------
# Session
# --------------------------------------------------------------------------

def run_session(cfg: Config, agent: Agent, auto_yes: bool) -> int:
    agent.executor.confirm = make_confirm(auto_yes)
    agent.plan_confirm = make_plan_confirm(auto_yes)
    _print(Panel.fit(
        f"[bold]Aegis[/bold] v{__version__}  ·  offline security copilot\n"
        f"{cfg.describe()}\n\n"
        "Type a request, or :help for commands, :quit to exit.",
        border_style="blue",
    ))
    while True:
        try:
            if _console:
                text = Prompt.ask("[bold blue]aegis[/bold blue]")
            else:
                text = input("aegis> ")
        except (EOFError, KeyboardInterrupt):
            _print("\nbye.")
            return 0
        text = text.strip()
        if not text:
            continue
        if text in (":quit", ":q", "exit", "quit"):
            return 0
        if text in (":help", "help", ":h"):
            _print(_session_help())
            continue
        if text.startswith(":mode "):
            cmd_mode(cfg, text.split(None, 1)[1].strip())
            continue
        if text == ":status":
            _print(agent.status())
            continue
        if text.startswith(":scope "):
            _print("Use `aegis scope add <target>` from a separate shell.")
            continue
        if text == ":clear":
            agent.memory.clear()
            _print("History cleared.")
            continue
        if text == ":privacy":
            from .privacy import PrivacyAuditor
            _print(PrivacyAuditor(cfg).audit().to_text())
            continue
        if text == ":tor":
            from .privacy import TorController
            _print(TorController(cfg).status())
            continue
        if text == ":snippets":
            from .snippets import SnippetStore
            for s in SnippetStore(cfg.learning.snippet_file).all():
                _print(f"{s.id}  {s.title} ({s.language})")
            continue
        if text == ":learn":
            _print(agent.learning.stats())
            continue

        _run_agent(agent, text)


def _run_agent(agent: Agent, text: str, *, stream: bool = True) -> None:
    # Streaming renders prose as it arrives, so we track whether a line is open
    # and close it before any other output (command block, error, prompt).
    state = {"open": False}

    def _close_stream() -> None:
        if state["open"]:
            if _console:
                _console.print()
            else:
                sys.stdout.write("\n")
            state["open"] = False

    def on_token(chunk: str) -> None:
        if not chunk:
            return
        state["open"] = True
        if _console:
            # markup=False is essential: model output contains [brackets] that
            # rich would otherwise swallow as markup.
            _console.print(chunk, end="", markup=False, highlight=False,
                           soft_wrap=True)
        else:
            sys.stdout.write(chunk)
            sys.stdout.flush()

    def on_stream_end() -> None:
        _close_stream()

    def on_text(prose: str) -> None:
        _close_stream()
        if prose:
            if _console:
                _console.print(Markdown(prose))
            else:
                print(prose)

    def on_command(command: str, result: ExecutionResult) -> None:
        _close_stream()
        color = LEVEL_COLOR.get(result.verdict.level, "white")
        status = "ran" if result.ran else result.decision
        _print(f"[{color}]▸ [{status}] {command}[/{color}]")
        if result.ran:
            body = (result.stdout or "").strip()
            if body:
                _print(body[:4000])
            if result.stderr and result.stderr.strip():
                _print(f"[red]{result.stderr.strip()[:1500]}[/red]")

    def on_note(kind: str, summary: str) -> None:
        _close_stream()
        color = {"file": "cyan", "snippet": "green", "remember": "magenta"}.get(kind, "white")
        _print(f"[{color}]✎ {summary}[/{color}]")

    kwargs = dict(on_text=on_text, on_command=on_command, on_note=on_note)
    if stream:
        kwargs["on_token"] = on_token
        kwargs["on_stream_end"] = on_stream_end
    try:
        agent.ask(text, **kwargs)
    finally:
        _close_stream()


def _session_help() -> str:
    return (
        ":help            show this help\n"
        ":status          backend + config status\n"
        ":mode <mode>     confirm | auto_safe | auto_full | dry_run\n"
        ":privacy         run a privacy/leak audit\n"
        ":tor             show Tor port status\n"
        ":snippets        list saved code snippets\n"
        ":learn           show what Aegis has learned\n"
        ":clear           clear conversation history\n"
        ":quit            exit\n"
    )


# --------------------------------------------------------------------------
# Findings / notes / tasks / reports / diagnostics
# --------------------------------------------------------------------------

def _stores(cfg: Config):
    """Build the data stores from config, creating directories as needed."""
    from .findings import FindingStore
    from .notes import NoteStore
    from .tasks import TaskStore
    data = os.path.dirname(os.path.expanduser(cfg.interface.audit_log)) or "."
    return (
        FindingStore(os.path.join(data, "findings.jsonl")),
        NoteStore(os.path.join(data, "notes.jsonl")),
        TaskStore(os.path.join(data, "tasks.jsonl")),
    )


def cmd_finding(cfg: Config, args) -> int:
    store, _, _ = _stores(cfg)
    action = getattr(args, "finding_action", "list") or "list"

    if action == "add":
        title = args.title or args.query
        if not title:
            _print("[red]usage: aegis finding add \"title\" [--severity high] [--target X][/red]")
            return 1
        tags = [t for t in (args.tags or "").split(",") if t]
        f = store.add_finding(title, severity=args.severity or "info",
                              detail=args.detail or "", target=args.target or "",
                              evidence=args.evidence or "", tags=tags,
                              source=args.source or "manual")
        _print(f"Added {f.id}  {f.one_line()}")
        return 0

    if action == "list":
        items = store.search(args.query or "", severity=args.severity,
                             status=args.status, tag=args.tags)
        if not items:
            _print("No findings recorded.")
            return 0
        for f in items:
            _print(f"{f.id}  {f.one_line()}  ({f.status})")
        return 0

    if action == "show":
        f = store.get_finding(args.query or "")
        if not f:
            _print(f"[red]no finding {args.query}[/red]")
            return 1
        body = f"{f.one_line()}\nstatus: {f.status}\n"
        if f.detail:
            body += f"\n{f.detail}\n"
        if f.evidence:
            body += f"\n--- evidence ---\n{f.evidence[:2000]}\n"
        _print(Panel(body, title=f.id, border_style="cyan"))
        return 0

    if action == "status":
        f = store.set_status(args.query or "", args.value or "open")
        if not f:
            _print("[red]unknown finding or invalid status[/red]")
            return 1
        _print(f"{f.id} -> {f.status}")
        return 0

    if action == "summary":
        s = store.summary()
        lines = [f"total: {s['total']}", f"open high+: {s['open_high_plus']}", ""]
        lines += [f"  {sev:<9} {n}" for sev, n in s["by_severity"].items()]
        _print(Panel("\n".join(lines), title="Findings summary", border_style="cyan"))
        return 0

    if action == "rm":
        ok = store.delete(args.query or "")
        _print("removed" if ok else "[red]not found[/red]")
        return 0 if ok else 1
    return 0


def cmd_note(cfg: Config, args) -> int:
    _, store, _ = _stores(cfg)
    action = getattr(args, "note_action", "list") or "list"

    if action == "add":
        title = args.title or args.query
        if not title:
            _print("[red]usage: aegis note add \"title\" [--body text] [--tags a,b][/red]")
            return 1
        tags = [t for t in (args.tags or "").split(",") if t]
        n = store.add_note(title, args.body or "", tags=tags)
        _print(f"Added {n.id}: {n.title}")
        return 0

    if action == "list":
        items = store.search(args.query or "", tag=args.tags)
        if not items:
            _print("No notes yet.")
            return 0
        for n in items:
            first = (n.body.splitlines() or [""])[0][:70]
            _print(f"{n.id}  {n.title}  {first}")
        return 0

    if action == "show":
        n = store.get_note(args.query or "")
        if not n:
            _print(f"[red]no note {args.query}[/red]")
            return 1
        _print(Panel(n.body or "(empty)", title=f"{n.id}: {n.title}", border_style="green"))
        return 0

    if action == "append":
        n = store.append_to(args.query or "", args.body or "")
        _print(f"appended to {n.id}" if n else "[red]not found[/red]")
        return 0 if n else 1
    return 0


def cmd_task(cfg: Config, args) -> int:
    _, _, store = _stores(cfg)
    action = getattr(args, "task_action", "list") or "list"

    if action == "add":
        if not args.title:
            _print("[red]usage: aegis task add \"title\" [--priority high][/red]")
            return 1
        tags = [t for t in (args.tags or "").split(",") if t]
        t = store.add_task(args.title, priority=args.priority or "normal",
                           detail=args.detail or "", tags=tags)
        _print(f"Added {t.id}: {t.line()}")
        return 0

    if action == "list":
        _print(store.render())
        return 0

    if action == "done":
        t = store.set_status(args.title or "", "done")
        _print(f"done: {t.title}" if t else "[red]not found[/red]")
        return 0 if t else 1

    if action == "start":
        t = store.set_status(args.title or "", "doing")
        _print(f"started: {t.title}" if t else "[red]not found[/red]")
        return 0 if t else 1

    if action == "next":
        t = store.next_task()
        _print(t.line() if t else "Nothing left to do.")
        return 0

    if action == "plan":
        raw_steps = args.detail or args.title or ""
        steps = [s for s in raw_steps.split(";") if s.strip()]
        if not steps:
            _print("[red]usage: aegis task plan \"step one; step two; step three\"[/red]")
            return 1
        made = store.add_plan([s.strip() for s in steps],
                              tags=[t for t in (args.tags or "").split(",") if t])
        _print(f"Added {len(made)} task(s).")
        return 0

    if action == "clear":
        n = store.clear()
        _print(f"cleared {n} task(s)")
        return 0
    return 0


def cmd_report(cfg: Config, args) -> int:
    from .report import ReportBuilder
    from .diag import run_all

    findings, notes, tasks = _stores(cfg)
    title = args.title or "Aegis report"
    meta = {
        "mode": cfg.safety.mode,
        "workspace": cfg.safety.workspace_root,
        "authorized_targets": ", ".join(cfg.safety.authorized_targets) or "none",
    }
    if getattr(args, "diag", False):
        results = run_all()
        meta["diagnostics"] = "; ".join(r.one_line() for r in results if r.severity != "info") or "all normal"
    report = ReportBuilder(findings, notes, tasks).build(
        title, meta=meta, min_severity=args.min_severity)

    fmt = (args.format or "md").lower()
    text = report.to_html() if fmt == "html" else report.to_markdown()
    if args.out:
        path = os.path.expanduser(args.out)
        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
            _print(f"Wrote {fmt} report to {path}")
        except OSError as exc:
            _print(f"[red]could not write {path}: {exc}[/red]")
            return 1
    else:
        _print(text if fmt == "md" else "(HTML generated; use --out FILE)")
    return 0


def cmd_diag(cfg: Config, args) -> int:
    from .diag import run_all, worst
    results = run_all()
    lines = [r.one_line() for r in results]
    overall = worst(results)
    color = {"info": "green", "warn": "yellow", "critical": "red"}.get(overall, "white")
    lines.append("")
    lines.append(f"overall: {overall}")
    _print(Panel("\n".join(lines), title="Hardware diagnostics", border_style=color))
    return 0


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

KNOWN_SUBCOMMANDS = {
    "ask", "status", "doctor", "scope", "mode", "audit", "privacy", "rescue",
    "allow",
    "setup", "snippet", "learn", "finding", "note", "task", "report", "diag",
}

# Top-level flags that consume a following value (used to locate where a
# bare prompt starts when the user does not name the `ask` subcommand).
_VALUE_FLAGS = {"--config", "--mode"}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="aegis", description="Offline AI security copilot")
    p.add_argument("--config", help="path to config.toml")
    p.add_argument("--mode", choices=VALID_MODES, help="override safety mode")
    p.add_argument("--yes", action="store_true", help="auto-confirm commands (careful!)")
    p.add_argument("--version", action="version", version=f"aegis {__version__}")

    sub = p.add_subparsers(dest="command")

    ask = sub.add_parser("ask", help="ask a one-shot question (default)")
    ask.add_argument("prompt", nargs="*")

    sub.add_parser("status", help="show status")
    sub.add_parser("doctor", help="diagnose local model setup")

    scope = sub.add_parser("scope", help="manage authorized target scope")
    scope.add_argument("scope_action", choices=["add", "list", "clear"])
    scope.add_argument("targets", nargs="*")

    mode = sub.add_parser("mode", help="set safety mode")
    mode.add_argument("value", choices=VALID_MODES)

    audit = sub.add_parser("audit", help="inspect the tamper-evident audit log")
    audit.add_argument("audit_action", nargs="?",
                       choices=["show", "verify", "seal"], default="show")
    audit.add_argument("-n", type=int, default=20)
    audit.add_argument("--out", help="destination for `seal`")

    privacy = sub.add_parser("privacy", help="privacy posture, Tor, panic and leak tests")
    privacy.add_argument("privacy_action",
                         choices=["status", "tor", "plan", "harden", "wipe",
                                  "newid", "leaktest", "panic"],
                         nargs="?", default="status")
    privacy.add_argument("--live", action="store_true",
                         help="for leaktest: send a real probe to a public resolver")
    privacy.add_argument("--yes", action="store_true",
                         help="for panic: actually execute the plan")

    rescue = sub.add_parser("rescue", help="diagnose and repair an installed system")
    rescue.add_argument("rescue_action",
                        choices=["scan", "mount", "unmount", "diagnose", "plan",
                                 "chroot", "fsck", "bootloader"],
                        nargs="?", default="scan")
    rescue.add_argument("device", nargs="?", help="target device for mount/fsck")
    # NOTE: named chroot_cmd, not `command`, to avoid clobbering the top-level
    # subcommand dest in the shared argparse namespace.
    # NOTE: nargs="?", not "*". A subparser that mixes a greedy positional
    # with its own optionals (--root/--esp/--apply) drops those optionals when
    # the parent already consumed an optional such as --mode. Quoting the
    # chroot command sidesteps that argparse limitation entirely.
    rescue.add_argument("chroot_cmd", nargs="?",
                        help="command to run inside the chroot (quote it)")
    rescue.add_argument("--root", help="mounted root of the target system "
                        "(default /mnt/aegis-rescue)")
    rescue.add_argument("--esp", help="EFI system partition device (e.g. /dev/sda1)")
    rescue.add_argument("--apply", action="store_true",
                        help="execute the bootloader repair plan (default: dry run)")

    allow = sub.add_parser("allow", help="remembered command approvals")
    allow.add_argument("allow_action", choices=["list", "add", "rm", "clear"],
                       nargs="?", default="list")
    # A single positional, not nargs="*": mixing a greedy positional with
    # this subparser's own optional (--prefix) breaks parsing when a global
    # flag such as --mode is given first. Quote the command instead.
    allow.add_argument("allow_arg", nargs="?",
                       help="rule id (rm) or command to remember (add)")
    allow.add_argument("--prefix", action="store_true",
                       help="match any command starting with this string "
                            "(broad — off by default)")

    setup = sub.add_parser("setup", help="first-boot wizard: profile + model sizing")
    setup.add_argument("--profile", choices=["workstation", "amnesic", "rescue"],
                       help="privacy profile to apply")
    setup.add_argument("--model", help="override the model chosen for your RAM")
    setup.add_argument("--auto", action="store_true",
                       help="pick the profile automatically (unattended)")
    setup.add_argument("--no-pull", action="store_true",
                       help="write config but do not download the model")
    setup.add_argument("--show", action="store_true",
                       help="show the detected hardware and plan, change nothing")

    snippet = sub.add_parser("snippet", help="save and recall code snippets")
    snippet.add_argument("snippet_action",
                         choices=["save", "list", "search", "get", "export"],
                         nargs="?", default="list")
    snippet.add_argument("value", nargs="?", help="search query or snippet id")
    snippet.add_argument("--title")
    snippet.add_argument("--lang")
    snippet.add_argument("--tags", help="comma-separated")
    snippet.add_argument("--description")
    snippet.add_argument("--file", help="read code from this file")
    snippet.add_argument("--code", help="inline code")
    snippet.add_argument("--dest", help="export destination directory")

    learn = sub.add_parser("learn", help="inspect and edit what Aegis remembers")
    learn.add_argument("learn_action",
                       choices=["stats", "remember", "prefer", "search",
                                "lessons", "forget"],
                       nargs="?", default="stats")
    learn.add_argument("value", nargs="?", help="text, query, or experience id")
    learn.add_argument("--tags", help="comma-separated")

    finding = sub.add_parser("finding", help="record and manage findings")
    finding.add_argument("finding_action",
                         choices=["add", "list", "show", "status", "summary", "rm"],
                         nargs="?", default="list")
    finding.add_argument("query", nargs="?", help="search text or finding id")
    finding.add_argument("value", nargs="?", help="new status for `status`")
    finding.add_argument("--title")
    finding.add_argument("--severity", choices=["info", "low", "medium", "high", "critical"])
    finding.add_argument("--status", choices=["open", "confirmed", "false_positive", "fixed", "wont_fix"])
    finding.add_argument("--target")
    finding.add_argument("--detail")
    finding.add_argument("--evidence")
    finding.add_argument("--source")
    finding.add_argument("--tags", help="comma-separated")

    note = sub.add_parser("note", help="keep a research journal")
    note.add_argument("note_action", choices=["add", "list", "show", "append"],
                      nargs="?", default="list")
    note.add_argument("query", nargs="?", help="search text or note id")
    note.add_argument("--title")
    note.add_argument("--body")
    note.add_argument("--tags", help="comma-separated")

    task = sub.add_parser("task", help="plan and track multi-step work")
    task.add_argument("task_action",
                      choices=["add", "list", "done", "start", "next", "plan", "clear"],
                      nargs="?", default="list")
    task.add_argument("title", nargs="?", help="task title or id")
    task.add_argument("--priority", choices=["low", "normal", "high", "urgent"])
    task.add_argument("--detail", help="detail text, or '; '-separated steps for `plan`")
    task.add_argument("--tags", help="comma-separated")

    report = sub.add_parser("report", help="build a findings report")
    report.add_argument("--title")
    report.add_argument("--format", choices=["md", "html"], default="md")
    report.add_argument("--out", help="write to this file")
    report.add_argument("--min-severity",
                        choices=["info", "low", "medium", "high", "critical"])
    report.add_argument("--diag", action="store_true",
                        help="include a hardware diagnostic summary")

    sub.add_parser("diag", help="run hardware and system diagnostics")
    return p


def _normalize_argv(argv: list) -> list:
    """Insert the implicit `ask` subcommand when the user passes a bare prompt.

    argparse cannot combine an optional positional with subparsers, so we route
    `aegis "do a thing"` to `aegis ask "do a thing"` ourselves while leaving
    real subcommands and flag-only invocations untouched.
    """
    raw = list(argv)
    if not raw:
        return ["ask"]

    # Find the first bare argument, skipping any leading flags and their
    # values. The subcommand need not be at index 0: `aegis --mode dry_run
    # privacy tor` is a real invocation, and checking only raw[0] would rewrite
    # it to `ask privacy tor` — silently running a chat prompt instead of the
    # command the user asked for.
    i = 0
    while i < len(raw):
        tok = raw[i]
        if tok in _VALUE_FLAGS:
            i += 2
            continue
        if tok.startswith("-"):
            i += 1
            continue
        break

    if i >= len(raw):
        return raw  # flags only (e.g. --version, --yes): no prompt
    if raw[i] in KNOWN_SUBCOMMANDS:
        return raw  # a real subcommand: leave the argv untouched
    return raw[:i] + ["ask"] + raw[i:]


def main(argv: Optional[list] = None) -> int:
    parser = build_parser()
    if argv is None:
        argv = sys.argv[1:]
    args = parser.parse_args(_normalize_argv(argv))
    cfg = Config.load(args.config)
    if args.mode:
        cfg.safety.mode = args.mode

    if args.command == "status":
        return cmd_status(cfg)
    if args.command == "doctor":
        return cmd_doctor(cfg)
    if args.command == "scope":
        return cmd_scope(cfg, args)
    if args.command == "mode":
        return cmd_mode(cfg, args.value)
    if args.command == "audit":
        return cmd_audit(cfg, args)
    if args.command == "privacy":
        return cmd_privacy(cfg, args)
    if args.command == "allow":
        return cmd_allow(cfg, args)

    if args.command == "rescue":
        return cmd_rescue(cfg, args)
    if args.command == "setup":
        return cmd_setup(cfg, args)
    if args.command == "snippet":
        return cmd_snippet(cfg, args)
    if args.command == "learn":
        return cmd_learn(cfg, args)
    if args.command == "finding":
        return cmd_finding(cfg, args)
    if args.command == "note":
        return cmd_note(cfg, args)
    if args.command == "task":
        return cmd_task(cfg, args)
    if args.command == "report":
        return cmd_report(cfg, args)
    if args.command == "diag":
        return cmd_diag(cfg, args)

    agent = Agent(cfg)
    prompt = getattr(args, "prompt", None)
    if prompt:
        agent.executor.confirm = make_confirm(args.yes)
        agent.plan_confirm = make_plan_confirm(args.yes)
        _run_agent(agent, " ".join(prompt))
        return 0
    return run_session(cfg, agent, args.yes)


if __name__ == "__main__":
    raise SystemExit(main())
