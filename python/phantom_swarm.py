#!/usr/bin/env python3
"""
PhantomSwarm v2.0 — 13-Agent Autonomous Kill Chain Swarm
For AUTHORIZED ASSESSMENTS AND CTF ENGAGEMENTS ONLY.
Set PHANTOM_OPERATOR env var to claim authorship watermarks.
"""
import sys, os, json, sqlite3, hashlib, hmac, math, socket
import threading, queue, time, datetime, argparse, uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from enum import Enum

try:
    from dotenv import load_dotenv; load_dotenv()
except ImportError:
    pass

try:
    import phantom_graph as _pg; PG_AVAILABLE = True
except ImportError:
    PG_AVAILABLE = False

DB_PATH = os.environ.get("PHANTOM_DB", "./phantom_swarm.db")
OPERATOR_ID = os.environ.get("PHANTOM_OPERATOR", "OPERATOR")
WATERMARK_SECRET = os.environ.get("PHANTOM_SECRET", "phantom-swarm-default-key-change-me")

def get_operator_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]; s.close(); return ip
    except Exception:
        return "0.0.0.0"

def create_watermark(operator_id, mission_id, target):
    ts = datetime.datetime.utcnow().isoformat() + "Z"
    ip = get_operator_ip()
    payload = f"{operator_id}|{mission_id}|{target}|{ts}|{ip}"
    sig = hmac.new(WATERMARK_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return {"operator": operator_id, "mission_id": mission_id, "target": target,
            "timestamp_utc": ts, "originating_ip": ip, "signature": sig,
            "fingerprint": hashlib.sha256(payload.encode()).hexdigest()[:16].upper()}

def verify_watermark(wm):
    payload = f"{wm['operator']}|{wm['mission_id']}|{wm['target']}|{wm['timestamp_utc']}|{wm['originating_ip']}"
    expected = hmac.new(WATERMARK_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, wm.get("signature", ""))

def format_watermark(wm):
    v = "VALID" if verify_watermark(wm) else "INVALID"
    return (f"\n{'='*60}\n  PHANTOM WATERMARK [{v}]\n"
            f"  Operator:    {wm['operator']}\n  Mission:     {wm['mission_id']}\n"
            f"  Target:      {wm['target']}\n  Timestamp:   {wm['timestamp_utc']}\n"
            f"  Source IP:   {wm['originating_ip']}\n  Fingerprint: {wm['fingerprint']}\n"
            f"  Signature:   {wm['signature'][:32]}...\n{'='*60}\n")

class AgentRole(Enum):
    GHOST    = ("GHOST",    "01", "Passive OSINT & Recon Chief")
    SPECTER  = ("SPECTER",  "02", "Attack Surface Mapper")
    CIPHER   = ("CIPHER",   "03", "Credential & Crypto Analyst")
    WRAITH   = ("WRAITH",   "04", "Stealth & Evasion Planner")
    PHANTOM  = ("PHANTOM",  "05", "Kill Chain Optimizer")
    VENOM    = ("VENOM",    "06", "Vulnerability Correlator")
    RAVEN    = ("RAVEN",    "07", "Social Engineering Analyst")
    COBRA    = ("COBRA",    "08", "Lateral Movement Planner")
    HYDRA    = ("HYDRA",    "09", "Multi-Vector Coordinator")
    ECLIPSE  = ("ECLIPSE",  "10", "Temporal & Timing Analyst")
    ORACLE   = ("ORACLE",   "11", "Evolution & Adaptive Learning")
    NEXUS    = ("NEXUS",    "12", "Intelligence Synthesis")
    SENTINEL = ("SENTINEL", "13", "Human Operator Gate [MitM]")
    def __init__(self, codename, num, desc):
        self.codename = codename; self.num = num; self.desc = desc

class Priority(Enum):
    ROUTINE  = 1
    ELEVATED = 2
    HIGH     = 3
    CRITICAL = 4

@dataclass
class AgentTask:
    task_id: str; mission_id: str; agent: str; action: str
    params: dict; priority: Priority; status: str = "pending"
    result: Optional[dict] = None; created_at: str = ""
    resolved_at: str = ""; notes: str = ""
    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.datetime.utcnow().isoformat() + "Z"

@dataclass
class AgentMessage:
    msg_id: str; from_agent: str; to_agent: str
    mission_id: str; subject: str; body: dict; timestamp: str = ""
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.datetime.utcnow().isoformat() + "Z"

class OracleEngine:
    def __init__(self, db):
        self.db = db

    def record_outcome(self, technique_id, defender_profile, detected, succeeded):
        self.db.execute("INSERT INTO oracle_memory (technique_id,defender_profile,detected,succeeded,recorded_at) VALUES (?,?,?,?,?)",
            (technique_id, defender_profile, int(detected), int(succeeded), datetime.datetime.utcnow().isoformat()+"Z"))
        self.db.commit()

    def get_evolved_weights(self, technique_id, defender_profile):
        rows = self.db.execute("SELECT detected,succeeded FROM oracle_memory WHERE technique_id=? AND defender_profile=? ORDER BY recorded_at DESC LIMIT 50",
            (technique_id, defender_profile)).fetchall()
        if not rows: return {}
        n = len(rows)
        return {"technique_id": technique_id, "defender_profile": defender_profile, "samples": n,
                "evolved_detect_prob": round((sum(r["detected"] for r in rows)+1)/(n+2), 4),
                "evolved_success_prob": round((sum(r["succeeded"] for r in rows)+1)/(n+2), 4),
                "confidence": min(n/20.0, 1.0)}

    def defender_pattern_delta(self, defender_profile):
        deltas = []
        rows = self.db.execute("SELECT technique_id,AVG(detected) as ad,AVG(succeeded) as as_,COUNT(*) as n FROM oracle_memory WHERE defender_profile=? GROUP BY technique_id HAVING n>=5",
            (defender_profile,)).fetchall()
        for row in rows:
            recent = self.db.execute("SELECT AVG(detected) as rd,COUNT(*) as rn FROM (SELECT detected FROM oracle_memory WHERE technique_id=? AND defender_profile=? ORDER BY recorded_at DESC LIMIT 5)",
                (row["technique_id"], defender_profile)).fetchone()
            if recent and recent["rn"] >= 3 and abs(recent["rd"] - row["ad"]) > 0.20:
                deltas.append({"technique_id": row["technique_id"], "historical_detect": round(row["ad"],3),
                    "recent_detect": round(recent["rd"],3), "delta": round(abs(recent["rd"]-row["ad"]),3),
                    "trend": "HARDENING" if recent["rd"] > row["ad"] else "SOFTENING"})
        return sorted(deltas, key=lambda x: -x["delta"])

    def top_performing_chains(self, defender_profile, top_n=5):
        rows = self.db.execute("SELECT technique_id,AVG(succeeded) as s,1.0-AVG(detected) as st,COUNT(*) as n FROM oracle_memory WHERE defender_profile=? AND succeeded=1 GROUP BY technique_id HAVING n>=3 ORDER BY s*st DESC LIMIT ?",
            (defender_profile, top_n)).fetchall()
        return [dict(r) for r in rows]

    def memory_report(self):
        total = self.db.execute("SELECT COUNT(*) FROM oracle_memory").fetchone()[0]
        profiles = self.db.execute("SELECT defender_profile,COUNT(*) as n FROM oracle_memory GROUP BY defender_profile").fetchall()
        lines = ["\n=== ORACLE EVOLUTION MEMORY ===", f"Total records: {total}"]
        for p in profiles:
            shifts = self.defender_pattern_delta(p["defender_profile"])
            lines.append(f"  {p['defender_profile']:15} {p['n']:5} samples" + (f"  [{len(shifts)} shifts]" if shifts else ""))
        if total == 0: lines.append("  (No outcomes yet)")
        return "\n".join(lines)

class SentinelGate:
    def __init__(self, mission_id, db, auto_approve_routine=True):
        self.mission_id = mission_id; self.db = db
        self.auto_approve_routine = auto_approve_routine

    def submit(self, task):
        if task.priority in (Priority.ROUTINE, Priority.ELEVATED) and self.auto_approve_routine:
            task.status = "approved"; self._save(task); return "approved"
        task.status = "pending"; self._save(task); return "queued"

    def pending_tasks(self):
        rows = self.db.execute("SELECT * FROM swarm_tasks WHERE mission_id=? AND status='pending' ORDER BY created_at", (self.mission_id,)).fetchall()
        return [self._row_to_task(r) for r in rows]

    def operator_approve(self, task_id, notes=""):
        r = self.db.execute("SELECT * FROM swarm_tasks WHERE task_id=?", (task_id,)).fetchone()
        if not r or r["status"] != "pending": return False
        self.db.execute("UPDATE swarm_tasks SET status='approved',resolved_at=?,notes=? WHERE task_id=?",
            (datetime.datetime.utcnow().isoformat()+"Z", notes, task_id)); self.db.commit()
        print(f"  [SENTINEL] APPROVED: {task_id}"); return True

    def operator_deny(self, task_id, notes=""):
        r = self.db.execute("SELECT * FROM swarm_tasks WHERE task_id=?", (task_id,)).fetchone()
        if not r or r["status"] != "pending": return False
        self.db.execute("UPDATE swarm_tasks SET status='denied',resolved_at=?,notes=? WHERE task_id=?",
            (datetime.datetime.utcnow().isoformat()+"Z", notes, task_id)); self.db.commit()
        print(f"  [SENTINEL] DENIED: {task_id}"); return True

    def sentinel_dashboard(self):
        rows = self.db.execute("SELECT agent,action,priority,status,created_at FROM swarm_tasks WHERE mission_id=? ORDER BY created_at DESC LIMIT 30", (self.mission_id,)).fetchall()
        lines = [f"\n{'='*70}", f"  SENTINEL DASHBOARD - Mission {self.mission_id}", f"{'='*70}"]
        for r in rows:
            icon = {"approved":"v","denied":"x","pending":"?","complete":"#"}.get(r["status"],"?")
            lines.append(f"  [{r['agent']:<8}] {r['priority']:<10} [{icon}]{r['status']:<10} {r['action'][:40]}")
        lines.append(f"{'='*70}")
        return "\n".join(lines)

    def _save(self, task):
        self.db.execute("INSERT OR REPLACE INTO swarm_tasks (task_id,mission_id,agent,action,params_json,priority,status,result_json,created_at,resolved_at,notes) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (task.task_id, task.mission_id, task.agent, task.action, json.dumps(task.params),
             task.priority.name, task.status, json.dumps(task.result or {}),
             task.created_at, task.resolved_at, task.notes)); self.db.commit()

    def _row_to_task(self, r):
        return AgentTask(task_id=r["task_id"], mission_id=r["mission_id"], agent=r["agent"],
            action=r["action"], params=json.loads(r["params_json"] or "{}"),
            priority=Priority[r["priority"]], status=r["status"],
            result=json.loads(r["result_json"] or "{}"),
            created_at=r["created_at"], resolved_at=r["resolved_at"] or "", notes=r["notes"] or "")

class BaseAgent:
    def __init__(self, role, mission_id, db, sentinel, oracle, bus):
        self.role = role; self.codename = role.codename
        self.mission_id = mission_id; self.db = db
        self.sentinel = sentinel; self.oracle = oracle; self.bus = bus

    def emit(self, subject, body, to="ALL"):
        msg = AgentMessage(str(uuid.uuid4())[:8], self.codename, to, self.mission_id, subject, body)
        self.bus.append(msg)
        self.db.execute("INSERT INTO swarm_bus (msg_id,mission_id,from_agent,to_agent,subject,body_json,timestamp) VALUES (?,?,?,?,?,?,?)",
            (msg.msg_id, msg.mission_id, msg.from_agent, msg.to_agent, msg.subject, json.dumps(msg.body), msg.timestamp))
        self.db.commit()

    def submit_task(self, action, params, priority=Priority.ROUTINE):
        t = AgentTask(str(uuid.uuid4())[:12], self.mission_id, self.codename, action, params, priority)
        return self.sentinel.submit(t)

    def messages(self, subj=None):
        return [m for m in self.bus if m.to_agent in (self.codename,"ALL") and (not subj or subj in m.subject)]

    def log(self, msg):
        ts = datetime.datetime.utcnow().strftime("%H:%M:%S")
        print(f"  [{ts}][{self.codename:<8}] {msg}")
        self.db.execute("INSERT INTO swarm_log (mission_id,agent,message,timestamp) VALUES (?,?,?,?)",
            (self.mission_id, self.codename, msg, datetime.datetime.utcnow().isoformat()+"Z")); self.db.commit()

    def run(self, target, context): raise NotImplementedError

class GhostAgent(BaseAgent):
    def run(self, target, context):
        self.log(f"Passive recon: {target}")
        import urllib.request
        findings = []
        try:
            req = urllib.request.Request(f"https://crt.sh/?q=%.{target}&output=json", headers={"User-Agent":"PhantomSwarm/2.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
            subs = set()
            for e in data[:100]:
                for s in e.get("name_value","").split("\n"):
                    s = s.strip().lstrip("*.") 
                    if s.endswith(target) and s != target: subs.add(s)
            self.log(f"{len(subs)} subdomains via cert transparency")
            findings.append({"type":"subdomains","count":len(subs),"sample":list(subs)[:5]})
        except Exception as e:
            self.log(f"crt.sh: {e}")
        dns_hits = []
        for p in ["www","mail","vpn","remote","api","dev","admin","git","jenkins","jira","staging"]:
            try:
                ips = [r[4][0] for r in socket.getaddrinfo(f"{p}.{target}", None)]
                dns_hits.append(f"{p}.{target} -> {list(set(ips))[0]}")
            except: pass
        self.log(f"DNS: {len(dns_hits)} records")
        findings.append({"type":"dns","records":dns_hits})
        self.emit("recon_complete", {"findings":findings,"target":target})
        return {"agent":"GHOST","findings":findings}

class SpecterAgent(BaseAgent):
    def run(self, target, context):
        self.log(f"Attack surface mapping: {target}")
        msgs = self.messages("recon_complete")
        recon = msgs[-1].body if msgs else {}
        surface, vectors = [], []
        for f in recon.get("findings",[]):
            if f.get("type")=="subdomains":
                for s in f.get("sample",[]):
                    surface.append({"node":s,"type":"subdomain","exposure":"external"})
            if f.get("type")=="dns":
                for r in f.get("records",[]):
                    svc = r.split(".")[0]
                    surface.append({"node":r,"type":"dns_service","likely_service":svc})
        services = [n.get("likely_service","") for n in surface]
        if any(s in ("mail","owa") for s in services): vectors.append({"vector":"Email portal phishing","tid":"T1566","priority":"HIGH"})
        if any(s in ("vpn","remote") for s in services): vectors.append({"vector":"VPN exploit/brute","tid":"T1133","priority":"HIGH"})
        if any(s in ("git","jenkins","jira") for s in services): vectors.append({"vector":"DevOps credential leak","tid":"T1552","priority":"HIGH"})
        if not vectors: vectors.append({"vector":"General web attack surface","tid":"T1190","priority":"MEDIUM"})
        self.log(f"{len(surface)} nodes, {len(vectors)} vectors")
        self.emit("surface_mapped", {"surface":surface,"vectors":vectors})
        return {"agent":"SPECTER","surface":surface,"vectors":vectors}

class CipherAgent(BaseAgent):
    def run(self, target, context):
        self.log("Credential attack surface analysis")
        ops = [{"op":"Query HaveIBeenPwned domain","tid":"T1589.002","p":"ROUTINE"},
               {"op":"Search Dehashed for email:pass pairs","tid":"T1552","p":"ROUTINE"},
               {"op":"GitHub hardcoded credential search","tid":"T1552.001","p":"HIGH"},
               {"op":"S3/GCS bucket exposure check","tid":"T1530","p":"HIGH"}]
        for op in ops: self.submit_task(op["op"], {"target":target,"tid":op["tid"]}, Priority[op["p"]])
        self.emit("credential_ops", {"ops":ops})
        self.log(f"Queued {len(ops)} credential tasks")
        return {"agent":"CIPHER","ops":ops}

class WraithAgent(BaseAgent):
    def run(self, target, context):
        dp = context.get("defender_profile","smb")
        self.log(f"Evasion planning for {dp}")
        from phantom_graph import DEFENDER_PROFILES
        profile = DEFENDER_PROFILES.get(dp, DEFENDER_PROFILES["smb"])
        plan = []
        edr = profile["edr_coverage"]
        if edr > 0.8:
            plan += [{"technique":"Memory-resident payloads","reason":"High EDR blocks disk writes"},
                     {"technique":"Process hollowing","reason":"Evades static signatures"}]
        elif edr > 0.5:
            plan += [{"technique":"Obfuscated scripts","reason":"Defeats basic static analysis"},
                     {"technique":"Certutil/BITS transfer","reason":"Whitelisted in most orgs"}]
        else:
            plan += [{"technique":"Staged payload","reason":"Low EDR: basic obfuscation sufficient"}]
        plan.append({"technique":f"Operate {profile.get('low_watch_hours',[2,3,4])[:3]} UTC","reason":"Blind spot hours"})
        self.emit("evasion_plan", {"plan":plan,"defender":dp})
        self.log(f"{len(plan)} evasion techniques")
        return {"agent":"WRAITH","plan":plan}

class PhantomAgent(BaseAgent):
    def run(self, target, context):
        self.log("Kill chain optimization")
        from phantom_graph import AttackGraphBuilder, KillChainOptimizer
        dp = context.get("defender_profile","smb")
        obj = context.get("objective","data_exfiltration")
        b = AttackGraphBuilder(self.mission_id, dp, self.db)
        nodes = b.build()
        chains = KillChainOptimizer(self.mission_id, b, obj, self.db).find_chains(5)
        summaries = []
        for i, kc in enumerate(chains, 1):
            summaries.append({"rank":i,"chain_id":kc.chain_id,"tactics":[n["tactic"] for n in kc.nodes],
                "cumulative_success":kc.cumulative_success,"stealth":kc.stealth_score,
                "detect_risk":kc.cumulative_detection_risk})
        self.emit("chains_optimized", {"chains":summaries,"objective":obj})
        self.log(f"{len(chains)} chains found, {len(nodes)} nodes")
        return {"agent":"PHANTOM","chains":summaries}

class VenomAgent(BaseAgent):
    def run(self, target, context):
        self.log("Vulnerability correlation")
        msgs = self.messages("surface_mapped")
        vectors = msgs[-1].body.get("vectors",[]) if msgs else []
        correlations = []
        for v in vectors:
            tid = v.get("tid","")
            if tid=="T1133": correlations.append({"surface":v["vector"],"intel":"Check CVE-2024-21887, CVE-2023-46805 (Ivanti), CVE-2022-40684 (FortiGate)","severity":"CRITICAL","tid":tid})
            elif tid=="T1190": correlations.append({"surface":v["vector"],"intel":"OWASP Top10, unpatched CMS (WordPress/Drupal)","severity":"HIGH","tid":tid})
            elif tid=="T1552": correlations.append({"surface":v["vector"],"intel":"GitHub token scan, Jenkins console, Jira API leaks","severity":"HIGH","tid":tid})
        for c in [x for x in correlations if x["severity"]=="CRITICAL"]:
            self.submit_task(f"CVE: {c['surface'][:50]}", {"intel":c["intel"]}, Priority.HIGH)
        self.emit("vuln_correlations", {"correlations":correlations})
        self.log(f"{len(correlations)} correlations")
        return {"agent":"VENOM","correlations":correlations}

class RavenAgent(BaseAgent):
    def run(self, target, context):
        self.log("Social engineering analysis")
        vectors = [
            {"vector":"Spear-phish via LinkedIn impersonation","target":"IT/Finance/Exec","technique":"T1566.002","effectiveness":0.65},
            {"vector":"Vishing: impersonate IT support","target":"Helpdesk","technique":"T1598","effectiveness":0.55},
            {"vector":"Fake recruiter + resume macro","target":"HR","technique":"T1566.001","effectiveness":0.70},
            {"vector":"USB drop (branded)","target":"Any employee","technique":"T1091","effectiveness":0.40},
        ]
        for v in vectors:
            self.submit_task(f"SE: {v['vector'][:50]}", {"vector":v,"target":target}, Priority.HIGH)
        self.emit("se_vectors", {"vectors":vectors})
        self.log(f"{len(vectors)} SE vectors queued")
        return {"agent":"RAVEN","vectors":vectors}

class CobraAgent(BaseAgent):
    def run(self, target, context):
        self.log("Lateral movement planning")
        paths = [
            {"path":"SMB Pass-the-Hash","techniques":["T1021.002","T1550.002"],"detect_risk":"MEDIUM"},
            {"path":"SSH key forwarding/hijack","techniques":["T1021.004","T1563"],"detect_risk":"LOW"},
            {"path":"Kerberoasting -> crack -> privesc","techniques":["T1558.003","T1110.002"],"detect_risk":"MEDIUM"},
            {"path":"DCOM/WMI lateral","techniques":["T1021.003","T1047"],"detect_risk":"LOW"},
            {"path":"RDP session hijack (TSCON)","techniques":["T1021.001","T1563.002"],"detect_risk":"LOW"},
        ]
        self.emit("lateral_paths", {"paths":paths})
        self.log(f"{len(paths)} pivot paths")
        return {"agent":"COBRA","paths":paths}

class HydraAgent(BaseAgent):
    def run(self, target, context):
        self.log("Multi-vector coordination")
        chains = len([m for m in self.bus if m.subject=="chains_optimized" and m.mission_id==self.mission_id])
        se = len([m for m in self.bus if m.subject=="se_vectors" and m.mission_id==self.mission_id])
        scenarios = [{"name":"Hybrid SE+technical","desc":"RAVEN phish -> PHANTOM kill chain","complexity":"HIGH"}]
        if chains and se: scenarios.insert(0,{"name":"Parallel: phish+VPN bruteforce","desc":"Dual-track initial access","complexity":"MEDIUM"})
        scenarios.append({"name":"Low-and-slow","desc":"Credential harvest + ECLIPSE-timed exploit","complexity":"MEDIUM"})
        self.emit("multi_vector", {"scenarios":scenarios})
        self.log(f"{len(scenarios)} scenarios")
        return {"agent":"HYDRA","scenarios":scenarios}

class EclipseAgent(BaseAgent):
    def run(self, target, context):
        self.log("Temporal window analysis")
        from phantom_graph import DEFENDER_PROFILES
        dp = context.get("defender_profile","smb")
        profile = DEFENDER_PROFILES.get(dp, DEFENDER_PROFILES["smb"])
        now = datetime.datetime.utcnow()
        windows = []
        for day_off in range(7):
            day = now + datetime.timedelta(days=day_off)
            for h in profile.get("low_watch_hours",[]):
                is_weekend = day.weekday() >= 5
                risk = 0.05 * (0.5 if is_weekend else 1.0) * (1.0 - profile["alert_fatigue_factor"]*0.4)
                if not profile["soc_24x7"]: risk *= 0.4
                windows.append({"dt":f"{day.strftime('%Y-%m-%d')} {h:02d}:00 UTC","risk":round(risk,4),"weekend":is_weekend})
        windows.sort(key=lambda x: x["risk"])
        top = windows[:5]
        self.emit("timing_ready", {"windows":top,"patch_lag":profile["patch_lag_days"]})
        self.log(f"Top window: {top[0]['dt'] if top else 'none'}")
        return {"agent":"ECLIPSE","windows":top}

class OracleAgentWrapper(BaseAgent):
    def run(self, target, context):
        self.log("Evolution analysis")
        dp = context.get("defender_profile","smb")
        shifts = self.oracle.defender_pattern_delta(dp)
        if shifts:
            for d in shifts[:3]: self.log(f"  SHIFT: {d['technique_id']} {d['trend']} d={d['delta']:.2f}")
        top = self.oracle.top_performing_chains(dp)
        self.emit("oracle_ready", {"shifts":shifts,"top":top})
        return {"agent":"ORACLE","shifts":shifts,"top":top}

class NexusAgent(BaseAgent):
    def run(self, target, context):
        self.log("Intelligence synthesis")
        msgs = [m for m in self.bus if m.mission_id==self.mission_id]
        pending = self.db.execute("SELECT COUNT(*) FROM swarm_tasks WHERE mission_id=? AND status='pending'", (self.mission_id,)).fetchone()[0]
        synth = {
            "total_messages": len(msgs),
            "agents_reported": list({m.from_agent for m in msgs}),
            "recon_done": any(m.subject=="recon_complete" for m in msgs),
            "chains_done": any(m.subject=="chains_optimized" for m in msgs),
            "evasion_done": any(m.subject=="evasion_plan" for m in msgs),
            "timing_done": any(m.subject=="timing_ready" for m in msgs),
            "sentinel_pending": pending,
        }
        done = sum([synth["recon_done"],synth["chains_done"],synth["evasion_done"],synth["timing_done"]])
        synth["pct"] = int(done/4*100)
        self.emit("synthesis", synth)
        self.log(f"{synth['pct']}% complete, {pending} SENTINEL pending")
        return {"agent":"NEXUS","synthesis":synth}

class PhantomSwarmCommander:
    def __init__(self, db):
        self.db = db; self.oracle = OracleEngine(db); self._missions = {}

    def deploy_mission(self, target, operator_id, defender_profile="smb",
                       objective="data_exfiltration", scope=""):
        mid = f"MSN-{hashlib.sha1(f'{target}{operator_id}{time.time()}'.encode()).hexdigest()[:6].upper()}"
        wm = create_watermark(operator_id, mid, target)
        self.db.execute("INSERT INTO missions (mission_id,operator_id,target,defender_profile,objective,scope,status,watermark_json,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (mid, operator_id, target, defender_profile, objective, scope, "active", json.dumps(wm),
             datetime.datetime.utcnow().isoformat()+"Z"))
        self.db.commit()
        print(format_watermark(wm))
        print(f"  [SWARM] Mission {mid} | Target: {target} | Operator: {operator_id} | Defender: {defender_profile}")
        bus, sentinel = [], SentinelGate(mid, self.db)
        ctx = {"defender_profile":defender_profile,"objective":objective}
        agent_defs = [
            (AgentRole.GHOST, GhostAgent), (AgentRole.SPECTER, SpecterAgent),
            (AgentRole.CIPHER, CipherAgent), (AgentRole.WRAITH, WraithAgent),
            (AgentRole.PHANTOM, PhantomAgent), (AgentRole.VENOM, VenomAgent),
            (AgentRole.RAVEN, RavenAgent), (AgentRole.COBRA, CobraAgent),
            (AgentRole.HYDRA, HydraAgent), (AgentRole.ECLIPSE, EclipseAgent),
            (AgentRole.ORACLE, OracleAgentWrapper), (AgentRole.NEXUS, NexusAgent),
        ]
        results = {}
        print()
        for role, Cls in agent_defs:
            print(f"  [{role.num}][{role.codename:<8}] {role.desc}")
            try: results[role.codename] = Cls(role, mid, self.db, sentinel, self.oracle, bus).run(target, ctx)
            except Exception as e: print(f"           ERROR: {e}")
        print(f"\n  [SWARM] {len(agent_defs)} agents done. SENTINEL review pending.")
        self._missions[mid] = {"sentinel":sentinel,"bus":bus,"results":results}
        return mid

    def deploy_multi(self, targets, operator_id, defender_profile="smb",
                     objective="data_exfiltration", split="auto"):
        ids = []
        for i, t in enumerate(targets, 1):
            print(f"\n  [HYDRA] Assignment {i}/{len(targets)}: {t}")
            ids.append(self.deploy_mission(t, operator_id, defender_profile, objective, f"multi {i}/{len(targets)}"))
        print(f"\n  [HYDRA] All {len(ids)} assignments deployed")
        return ids

    def get_sentinel(self, mid):
        if mid in self._missions: return self._missions[mid]["sentinel"]
        return SentinelGate(mid, self.db)

    def full_report(self, mid):
        row = self.db.execute("SELECT * FROM missions WHERE mission_id=?", (mid,)).fetchone()
        if not row: return "Mission not found."
        wm = json.loads(row["watermark_json"])
        logs = self.db.execute("SELECT agent,message,timestamp FROM swarm_log WHERE mission_id=? ORDER BY timestamp", (mid,)).fetchall()
        tasks = self.db.execute("SELECT agent,action,priority,status FROM swarm_tasks WHERE mission_id=? ORDER BY created_at", (mid,)).fetchall()
        chains = self.db.execute("SELECT id,cumulative_success,cumulative_detection_risk,stealth_score FROM kill_chains WHERE engagement_id=? ORDER BY stealth_score DESC LIMIT 5", (mid,)).fetchall()
        lines = ["="*70, f"  PHANTOM SWARM - MISSION {mid}",
                 f"  Target: {row['target']}  Profile: {row['defender_profile']}", "="*70,
                 format_watermark(wm), "AGENT LOG:", "-"*60]
        for l in logs: lines.append(f"  {l['timestamp'][11:19]} [{l['agent']:<8}] {l['message']}")
        lines += ["", "TASKS:", "-"*60]
        for t in tasks:
            icon = {"approved":"v","denied":"x","pending":"?"}.get(t["status"],"?")
            lines.append(f"  [{icon}][{t['agent']:<8}][{t['priority']:<8}] {t['action'][:55]}")
        if chains:
            lines += ["", "KILL CHAINS:", "-"*60]
            for i, c in enumerate(chains, 1):
                lines.append(f"  #{i} stealth={c['stealth_score']:.0%} success={c['cumulative_success']:.0%} detect={c['cumulative_detection_risk']:.0%}")
        lines.append("="*70)
        return "\n".join(lines)

def init_db(db_path=DB_PATH):
    conn = sqlite3.connect(db_path); conn.row_factory = sqlite3.Row
    conn.cursor().executescript("""
        CREATE TABLE IF NOT EXISTS missions (
            mission_id TEXT PRIMARY KEY, operator_id TEXT NOT NULL, target TEXT NOT NULL,
            defender_profile TEXT DEFAULT 'smb', objective TEXT DEFAULT 'data_exfiltration',
            scope TEXT, status TEXT DEFAULT 'active', watermark_json TEXT, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS swarm_tasks (
            task_id TEXT PRIMARY KEY, mission_id TEXT NOT NULL, agent TEXT NOT NULL,
            action TEXT NOT NULL, params_json TEXT, priority TEXT NOT NULL,
            status TEXT DEFAULT 'pending', result_json TEXT,
            created_at TEXT NOT NULL, resolved_at TEXT, notes TEXT);
        CREATE TABLE IF NOT EXISTS swarm_bus (
            msg_id TEXT PRIMARY KEY, mission_id TEXT NOT NULL, from_agent TEXT NOT NULL,
            to_agent TEXT NOT NULL, subject TEXT NOT NULL, body_json TEXT, timestamp TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS swarm_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT, mission_id TEXT NOT NULL,
            agent TEXT NOT NULL, message TEXT NOT NULL, timestamp TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS oracle_memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT, technique_id TEXT NOT NULL,
            defender_profile TEXT NOT NULL, detected INTEGER DEFAULT 0,
            succeeded INTEGER DEFAULT 0, recorded_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS kill_chains (
            id TEXT PRIMARY KEY, engagement_id TEXT NOT NULL, chain_json TEXT NOT NULL,
            cumulative_success REAL, cumulative_detection_risk REAL, stealth_score REAL,
            objective TEXT, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS attack_nodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT, engagement_id TEXT NOT NULL,
            technique_id TEXT NOT NULL, technique_name TEXT NOT NULL, tactic TEXT NOT NULL,
            success_prob REAL NOT NULL, detect_prob REAL NOT NULL, stealth_score REAL NOT NULL, notes TEXT);
    """)
    conn.commit(); return conn

BANNER = r"""
  PHANTOM SWARM v2.0 - 13-Agent Autonomous Kill Chain Swarm
  SENTINEL-GATED | ORACLE-EVOLVED | WATERMARKED
  [AUTHORIZED ASSESSMENT AND CTF USE ONLY]
"""

def main():
    print(BANNER)
    p = argparse.ArgumentParser(prog="phantom_swarm")
    sub = p.add_subparsers(dest="command")
    d = sub.add_parser("deploy"); d.add_argument("--target",required=True); d.add_argument("--operator-id",default=OPERATOR_ID); d.add_argument("--defender",default="smb",choices=["startup","smb","enterprise","healthcare","financial","government"]); d.add_argument("--objective",default="data_exfiltration",choices=["data_exfiltration","ransomware","persistence","credential_theft","lateral_spread","crown_jewels"]); d.add_argument("--scope",default="")
    m = sub.add_parser("multi"); m.add_argument("--targets",nargs="+",required=True); m.add_argument("--operator-id",default=OPERATOR_ID); m.add_argument("--defender",default="smb"); m.add_argument("--objective",default="data_exfiltration"); m.add_argument("--team-split",default="auto")
    st = sub.add_parser("status"); st.add_argument("--mission-id",required=True)
    ap = sub.add_parser("approve"); ap.add_argument("--mission-id",required=True); ap.add_argument("--task-id",required=True); ap.add_argument("--notes",default="")
    dn = sub.add_parser("deny"); dn.add_argument("--mission-id",required=True); dn.add_argument("--task-id",required=True); dn.add_argument("--notes",default="")
    rp = sub.add_parser("report"); rp.add_argument("--mission-id",required=True)
    ev = sub.add_parser("evolve"); ev.add_argument("--record"); ev.add_argument("--shifts",action="store_true")
    wm = sub.add_parser("watermark"); wm.add_argument("--verify"); wm.add_argument("--create")
    sub.add_parser("list")
    args = p.parse_args()
    if not args.command: p.print_help(); return
    db = init_db(); cmd = PhantomSwarmCommander(db)
    sentinel_get = lambda mid: cmd.get_sentinel(mid)
    if args.command=="deploy":
        mid = cmd.deploy_mission(args.target, args.operator_id or OPERATOR_ID, args.defender, args.objective, args.scope)
        print(f"\n[+] {mid}  |  python phantom_swarm.py report --mission-id {mid}")
    elif args.command=="multi":
        ids = cmd.deploy_multi(args.targets, args.operator_id or OPERATOR_ID, args.defender, args.objective, args.team_split)
        for i in ids: print(f"  {i}")
    elif args.command=="status":
        s = sentinel_get(args.mission_id); print(s.sentinel_dashboard())
        for t in s.pending_tasks(): print(f"  PENDING: {t.task_id} | {t.agent} | {t.action[:60]}")
    elif args.command=="approve": sentinel_get(args.mission_id).operator_approve(args.task_id, args.notes)
    elif args.command=="deny": sentinel_get(args.mission_id).operator_deny(args.task_id, args.notes)
    elif args.command=="report": print(cmd.full_report(args.mission_id))
    elif args.command=="evolve":
        print(cmd.oracle.memory_report())
        if args.record:
            try:
                tid, prof, det, suc = args.record.split(":")
                cmd.oracle.record_outcome(tid, prof, bool(int(det)), bool(int(suc))); print(f"[ORACLE] Recorded {tid}/{prof}")
            except: print("Format: TID:PROFILE:0|1:0|1")
        if args.shifts:
            for prof in ["startup","smb","enterprise","healthcare","financial","government"]:
                shifts = cmd.oracle.defender_pattern_delta(prof)
                if shifts: print(f"\n{prof.upper()}: {[s['technique_id']+' '+s['trend'] for s in shifts[:3]]}")
    elif args.command=="watermark":
        if args.verify:
            try:
                wm_data = json.loads(Path(args.verify).read_text())
                wm_obj = wm_data.get("watermark") or wm_data
                print(format_watermark(wm_obj))
                print("VALID" if verify_watermark(wm_obj) else "INVALID")
            except Exception as e: print(f"Error: {e}")
        else:
            wm_obj = create_watermark(OPERATOR_ID, args.create or "IDENTITY-CHECK", args.create or "N/A")
            print(format_watermark(wm_obj)); print(json.dumps(wm_obj, indent=2))
    elif args.command=="list":
        rows = db.execute("SELECT mission_id,operator_id,target,status,created_at FROM missions ORDER BY created_at DESC").fetchall()
        for r in rows: print(f"{r['mission_id']:<15} {r['operator_id']:<15} {r['target']:<30} {r['status']:<10} {r['created_at'][:19]}")

if __name__ == "__main__":
    main()
