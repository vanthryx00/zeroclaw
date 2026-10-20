#!/usr/bin/env python3
"""
PhantomSwarm HUD — Interactive terminal heads-up display.
Shows all 13 agents live: strategy, responsibilities, current status.

Usage:
    python phantom_hud.py                    # live view, auto-refresh
    python phantom_hud.py --mission MSN-XXXX # pin to a mission
    python phantom_hud.py --once             # single snapshot, no loop
"""

import os
import sys
import time
import sqlite3
import json
import datetime
import argparse
import shutil

try:
    from dotenv import load_dotenv; load_dotenv()
except ImportError:
    pass

DB_PATH = os.environ.get("PHANTOM_DB", "./phantom_swarm.db")

# ANSI colour palette
class C:
    RESET  = "\033[0m"
    BOLD   = "\033[1m"
    DIM    = "\033[2m"
    RED    = "\033[31m"
    GREEN  = "\033[32m"
    YELLOW = "\033[33m"
    BLUE   = "\033[34m"
    MAGENTA= "\033[35m"
    CYAN   = "\033[36m"
    WHITE  = "\033[37m"
    BGBLK  = "\033[40m"
    BGRED  = "\033[41m"
    BGGRN  = "\033[42m"
    BGYLW  = "\033[43m"
    BGBLU  = "\033[44m"
    BGMAG  = "\033[45m"
    BGCYN  = "\033[46m"

def clr(): print("\033[2J\033[H", end="")
def mv(r, c): print(f"\033[{r};{c}H", end="")
def hide_cursor(): print("\033[?25l", end="")
def show_cursor(): print("\033[?25h", end="")

AGENTS = [
    ("01", "GHOST",   "Passive OSINT & Recon Chief",        C.CYAN,    "passive_osint,cert_transparency,dns_enum,breach_intel"),
    ("02", "SPECTER", "Attack Surface Mapper",               C.BLUE,    "port_model,subdomain_graph,vector_scoring,service_fp"),
    ("03", "CIPHER",  "Credential & Crypto Analyst",         C.YELLOW,  "hibp_query,credential_harvest,hash_crack,token_audit"),
    ("04", "WRAITH",  "Stealth & Evasion Planner",           C.GREEN,   "edr_bypass,lolbin_select,timing_window,footprint_min"),
    ("05", "PHANTOM", "Kill Chain Optimizer",                 C.MAGENTA, "attack_graph,beam_search,stealth_score,chain_rank"),
    ("06", "VENOM",   "Vulnerability Correlator",            C.RED,     "cve_match,exploit_db,severity_rank,patch_lag_calc"),
    ("07", "RAVEN",   "Social Engineering Analyst",          C.CYAN,    "phishing_craft,vishing_script,pretext_build,osint_link"),
    ("08", "COBRA",   "Lateral Movement Planner",            C.BLUE,    "smb_pth,ssh_hijack,kerb_roast,dcom_exec,rdp_hijack"),
    ("09", "HYDRA",   "Multi-Vector Coordinator",            C.GREEN,   "parallel_track,timing_sync,resource_alloc,abort_gate"),
    ("10", "ECLIPSE", "Temporal & Timing Analyst",           C.YELLOW,  "soc_blind_spots,weekend_ops,patch_window,fatigue_map"),
    ("11", "ORACLE",  "Evolution & Adaptive Learning",       C.MAGENTA, "bayes_update,laplace_smooth,pattern_delta,drift_alert"),
    ("12", "NEXUS",   "Intelligence Synthesis",              C.WHITE,   "bus_aggregate,coverage_map,gap_detect,brief_gen"),
    ("13", "SENTINEL","Human Operator Gate [MitM]",          C.RED,     "task_queue,approve/deny,critical_timeout,audit_log"),
]

STATUS_COLORS = {
    "idle":     C.DIM + C.WHITE,
    "running":  C.BOLD + C.GREEN,
    "complete": C.GREEN,
    "error":    C.BOLD + C.RED,
    "waiting":  C.YELLOW,
    "approved": C.GREEN,
    "denied":   C.RED,
    "pending":  C.YELLOW,
}

def open_db(path):
    if not os.path.exists(path):
        return None
    try:
        conn = sqlite3.connect(path); conn.row_factory = sqlite3.Row
        return conn
    except Exception:
        return None

def get_missions(db):
    if not db: return []
    try:
        return db.execute("SELECT mission_id,operator_id,target,status,created_at FROM missions ORDER BY created_at DESC LIMIT 10").fetchall()
    except Exception:
        return []

def get_agent_status(db, mission_id):
    if not db: return {}
    statuses = {}
    try:
        rows = db.execute("SELECT agent,message,timestamp FROM swarm_log WHERE mission_id=? ORDER BY timestamp DESC", (mission_id,)).fetchall()
        seen = set()
        for r in rows:
            if r["agent"] not in seen:
                statuses[r["agent"]] = {"last_msg": r["message"], "ts": r["timestamp"]}
                seen.add(r["agent"])
    except Exception:
        pass
    return statuses

def get_sentinel_queue(db, mission_id):
    if not db: return []
    try:
        return db.execute("SELECT task_id,agent,action,priority,status FROM swarm_tasks WHERE mission_id=? AND status='pending' ORDER BY created_at", (mission_id,)).fetchall()
    except Exception:
        return []

def get_oracle_summary(db):
    if not db: return {}
    try:
        total = db.execute("SELECT COUNT(*) FROM oracle_memory").fetchone()[0]
        profiles = db.execute("SELECT defender_profile,COUNT(*),AVG(succeeded),AVG(detected) FROM oracle_memory GROUP BY defender_profile").fetchall()
        return {"total": total, "profiles": [dict(p) for p in profiles]}
    except Exception:
        return {}

def get_chain_count(db, mission_id):
    if not db: return 0
    try:
        return db.execute("SELECT COUNT(*) FROM kill_chains WHERE engagement_id=?", (mission_id,)).fetchone()[0]
    except Exception:
        return 0

def term_width():
    return shutil.get_terminal_size((120, 40)).columns

def draw_hud(db, mission_id=None, missions=None):
    clr()
    W = term_width()
    now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

    # Header
    hdr = " PHANTOM SWARM v2.0 — OPERATOR HUD "
    pad = (W - len(hdr)) // 2
    print(C.BOLD + C.BGBLK + C.CYAN + "=" * W + C.RESET)
    print(C.BOLD + C.BGBLK + C.CYAN + " " * pad + hdr + " " * (W - pad - len(hdr)) + C.RESET)
    print(C.BOLD + C.BGBLK + C.CYAN + "=" * W + C.RESET)
    print(f"  {C.DIM}Updated: {now}   DB: {DB_PATH}{C.RESET}")
    print()

    # Mission selector
    if missions is None:
        missions = get_missions(db)

    active_mission = None
    if mission_id:
        for m in missions:
            if m["mission_id"] == mission_id:
                active_mission = m; break
    elif missions:
        active_mission = missions[0]

    if not missions:
        print(f"  {C.YELLOW}No missions found. Run: python phantom_swarm.py deploy --target <target>{C.RESET}")
        print()
    else:
        print(f"  {C.BOLD}RECENT MISSIONS{C.RESET}")
        for m in missions[:5]:
            marker = C.BOLD + C.GREEN + " *" if (active_mission and m["mission_id"] == active_mission["mission_id"]) else "  "
            print(f"  {marker}{C.CYAN}{m['mission_id']}{C.RESET}  {m['target']:<28} {C.DIM}{m['created_at'][:19]}{C.RESET}")
        print()

    # Agent grid
    agent_statuses = get_agent_status(db, active_mission["mission_id"]) if active_mission else {}
    sentinel_q = get_sentinel_queue(db, active_mission["mission_id"]) if active_mission else []
    chain_count = get_chain_count(db, active_mission["mission_id"]) if active_mission else 0
    oracle_data = get_oracle_summary(db)

    print(f"  {C.BOLD}{'#':>3}  {'AGENT':<10} {'ROLE':<32} {'RESPONSIBILITIES':<40} {'STATUS'}{C.RESET}")
    print("  " + "-" * (W - 4))

    for num, name, role, color, resp in AGENTS:
        st = agent_statuses.get(name, {})
        last = st.get("last_msg", "idle")[:38] if st else "idle"
        status_word = "running" if st else "idle"
        if name == "SENTINEL":
            if sentinel_q:
                status_word = "pending"
                last = f"{len(sentinel_q)} tasks awaiting approval"
            else:
                status_word = "clear"
                last = "queue clear"
        elif name == "ORACLE":
            n = oracle_data.get("total", 0)
            if n: last = f"{n} outcomes recorded"; status_word = "complete"
        elif name == "PHANTOM" and chain_count:
            last = f"{chain_count} chains optimized"; status_word = "complete"

        scol = STATUS_COLORS.get(status_word, C.DIM + C.WHITE)
        resp_short = resp[:38]
        print(f"  {color}{C.BOLD}{num:>3}  {name:<10}{C.RESET}  {C.DIM}{role:<32}{C.RESET}  {C.DIM}{resp_short:<38}{C.RESET}  {scol}{last[:30]}{C.RESET}")

    print()

    # SENTINEL queue
    print(f"  {C.BOLD}SENTINEL QUEUE{C.RESET}  ({len(sentinel_q)} pending)")
    print("  " + "-" * 60)
    if sentinel_q:
        for t in sentinel_q[:8]:
            pcol = {4: C.RED, 3: C.YELLOW, 2: C.CYAN, 1: C.GREEN}.get(
                {"CRITICAL":4,"HIGH":3,"ELEVATED":2,"ROUTINE":1}.get(t["priority"],1), C.WHITE)
            print(f"    [{pcol}{t['priority']:<8}{C.RESET}] {C.CYAN}{t['task_id']}{C.RESET}  [{t['agent']:<8}]  {t['action'][:50]}")
        print(f"\n    To approve: {C.CYAN}python phantom_swarm.py approve --mission-id <MSN> --task-id <ID>{C.RESET}")
    else:
        print(f"    {C.GREEN}All clear.{C.RESET}")
    print()

    # ORACLE
    print(f"  {C.BOLD}ORACLE EVOLUTION MEMORY{C.RESET}  ({oracle_data.get('total', 0)} outcomes)")
    print("  " + "-" * 60)
    for p in oracle_data.get("profiles", [])[:6]:
        succ = p.get("AVG(succeeded)", 0) or 0
        det = p.get("AVG(detected)", 0) or 0
        bar = int(succ * 20) * "#" + int((1-succ) * 20) * "."
        print(f"    {p['defender_profile']:<14} n={p['COUNT(*)']:<4} succ={succ:.0%} det={det:.0%}  [{bar}]")
    if not oracle_data.get("profiles"):
        print(f"    {C.DIM}No evolution data yet. Record outcomes: python phantom_swarm.py evolve --record T1003:smb:1:1{C.RESET}")
    print()

    # Footer
    print("  " + "=" * (W - 4))
    cmds = [
        ("deploy", "new mission"),
        ("status", "SENTINEL queue"),
        ("report", "full report"),
        ("evolve", "ORACLE memory"),
        ("watermark", "verify identity"),
    ]
    cmd_line = "  Cmds: " + "  |  ".join(f"{C.CYAN}python phantom_swarm.py {k}{C.RESET} ({v})" for k, v in cmds)
    print(cmd_line)
    print(f"  {C.DIM}Refresh: Ctrl+C to exit | --once for single snapshot{C.RESET}")
    sys.stdout.flush()

def main():
    p = argparse.ArgumentParser(prog="phantom_hud")
    p.add_argument("--mission", help="Pin to a specific mission ID")
    p.add_argument("--once", action="store_true", help="Single snapshot, no loop")
    p.add_argument("--interval", type=int, default=5, help="Refresh interval seconds (default 5)")
    p.add_argument("--db", default=DB_PATH, help="Database path")
    args = p.parse_args()

    global DB_PATH
    DB_PATH = args.db

    hide_cursor()
    try:
        while True:
            db = open_db(DB_PATH)
            missions = get_missions(db)
            draw_hud(db, args.mission, missions)
            if db: db.close()
            if args.once:
                break
            time.sleep(args.interval)
    except KeyboardInterrupt:
        pass
    finally:
        show_cursor()
        print()

if __name__ == "__main__":
    main()
