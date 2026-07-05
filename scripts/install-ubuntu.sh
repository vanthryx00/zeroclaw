#!/usr/bin/env bash
# =============================================================================
# BugReaper X v4.0 — Ubuntu Production Installer
# =============================================================================
# One-shot setup for the BugReaper X vulnerability scanning platform on Ubuntu
# 20.04 LTS / 22.04 LTS / 24.04 LTS.
#
# Usage:
#   sudo bash scripts/install-ubuntu.sh [--dev] [--no-vr] [--no-systemd]
#
# Options:
#   --dev         Install development extras (pytest, mypy, ruff)
#   --no-vr       Skip VR bridge and audio asset generation
#   --no-systemd  Skip systemd service installation (run manually instead)
# =============================================================================

set -euo pipefail

# ── Colours ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GRN='\033[0;32m'
YLW='\033[1;33m'
BLU='\033[0;34m'
NC='\033[0m'

info()  { echo -e "${BLU}[INFO]${NC}  $*"; }
ok()    { echo -e "${GRN}[OK]${NC}    $*"; }
warn()  { echo -e "${YLW}[WARN]${NC}  $*"; }
die()   { echo -e "${RED}[ERR]${NC}   $*" >&2; exit 1; }

# ── Flags ─────────────────────────────────────────────────────────────────────
OPT_DEV=0
OPT_NO_VR=0
OPT_NO_SYSTEMD=0

for arg in "$@"; do
  case "$arg" in
    --dev)         OPT_DEV=1 ;;
    --no-vr)       OPT_NO_VR=1 ;;
    --no-systemd)  OPT_NO_SYSTEMD=1 ;;
    -h|--help)
      sed -n '3,16p' "$0" | sed 's/^# //'
      exit 0
      ;;
    *) die "Unknown option: $arg" ;;
  esac
done

# ── Root check ────────────────────────────────────────────────────────────────
[[ $EUID -eq 0 ]] || die "Run as root: sudo bash $0"

# ── Paths ─────────────────────────────────────────────────────────────────────
INSTALL_DIR="/opt/bugreaperx"
VENV_DIR="$INSTALL_DIR/.venv"
DATA_DIR="/var/lib/bugreaperx"
LOG_DIR="/var/log/bugreaperx"
CONF_DIR="/etc/bugreaperx"
AUDIO_DIR="$DATA_DIR/audio"
REPORTS_DIR="$DATA_DIR/reports"
DB_PATH="$DATA_DIR/bugreaperx.db"
SERVICE_USER="bugreaperx"

# ── Ubuntu version check ──────────────────────────────────────────────────────
UBUNTU_VER=$(lsb_release -rs 2>/dev/null || echo "0")
info "Ubuntu $UBUNTU_VER detected"
case "$UBUNTU_VER" in
  20.04|22.04|24.04) ok "Supported Ubuntu version" ;;
  *) warn "Untested Ubuntu version — proceeding anyway" ;;
esac

# =============================================================================
# 1. SYSTEM PACKAGES
# =============================================================================
info "Updating package lists…"
apt-get update -qq

info "Installing system packages…"
apt-get install -y --no-install-recommends \
  python3 python3-pip python3-venv python3-dev \
  build-essential libssl-dev libffi-dev \
  libpq-dev \
  sqlite3 \
  nmap masscan \
  nikto \
  whois dnsutils \
  curl wget git \
  jq \
  ffmpeg sox libsox-fmt-all \
  ufw \
  unzip \
  ca-certificates \
  2>/dev/null
ok "System packages installed"

# ── Optional Kali tooling (skip if not on Kali/security-flavoured Ubuntu) ───
if apt-cache show sqlmap &>/dev/null; then
  apt-get install -y --no-install-recommends sqlmap 2>/dev/null && ok "sqlmap installed"
fi
if apt-cache show hydra &>/dev/null; then
  apt-get install -y --no-install-recommends hydra 2>/dev/null && ok "hydra installed"
fi
if apt-cache show gobuster &>/dev/null; then
  apt-get install -y --no-install-recommends gobuster 2>/dev/null && ok "gobuster installed"
fi

# =============================================================================
# 2. SERVICE USER
# =============================================================================
if ! id "$SERVICE_USER" &>/dev/null; then
  useradd --system --no-create-home --shell /usr/sbin/nologin "$SERVICE_USER"
  ok "Service user '$SERVICE_USER' created"
else
  info "Service user '$SERVICE_USER' already exists"
fi

# =============================================================================
# 3. DIRECTORIES
# =============================================================================
info "Creating directories…"
for d in "$INSTALL_DIR" "$DATA_DIR" "$LOG_DIR" "$CONF_DIR" "$AUDIO_DIR" "$REPORTS_DIR"; do
  mkdir -p "$d"
done
chown -R "$SERVICE_USER:$SERVICE_USER" "$DATA_DIR" "$LOG_DIR"
chmod 750 "$CONF_DIR"
ok "Directories ready"

# =============================================================================
# 4. PYTHON VIRTUAL ENVIRONMENT
# =============================================================================
info "Setting up Python virtual environment at $VENV_DIR…"
python3 -m venv "$VENV_DIR"
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

pip install --quiet --upgrade pip setuptools wheel

# ── Core runtime dependencies (22 modules) ───────────────────────────────────
info "Installing Python dependencies…"
pip install --quiet \
  fastapi==0.111.0 \
  uvicorn[standard]==0.29.0 \
  websockets==12.0 \
  sqlalchemy==2.0.30 \
  aiosqlite==0.20.0 \
  alembic==1.13.1 \
  pydantic==2.7.1 \
  pydantic-settings==2.2.1 \
  httpx==0.27.0 \
  stripe==9.4.0 \
  anthropic==0.26.1 \
  apscheduler==3.10.4 \
  reportlab==4.2.0 \
  jinja2==3.1.4 \
  python-multipart==0.0.9 \
  passlib[bcrypt]==1.7.4 \
  python-jose[cryptography]==3.3.0 \
  aiofiles==23.2.1 \
  rich==13.7.1 \
  click==8.1.7 \
  python-dotenv==1.0.1 \
  psutil==5.9.8

ok "22 Python modules installed"

# ── Development extras ────────────────────────────────────────────────────────
if [[ $OPT_DEV -eq 1 ]]; then
  info "Installing dev extras…"
  pip install --quiet pytest pytest-asyncio mypy ruff httpx
  ok "Dev extras installed"
fi

deactivate

# =============================================================================
# 5. APPLICATION MODULES (written to INSTALL_DIR)
# =============================================================================
info "Writing application modules…"

# ── main.py ──────────────────────────────────────────────────────────────────
cat > "$INSTALL_DIR/main.py" << 'PYEOF'
"""BugReaper X v4.0 — FastAPI entry point."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routers import scans, reports, billing, auth, ws
from core.database import init_db
from core.scheduler import start_scheduler

app = FastAPI(title="BugReaper X", version="4.0.0", docs_url="/api/docs")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router,    prefix="/api/auth",    tags=["auth"])
app.include_router(scans.router,   prefix="/api/scans",   tags=["scans"])
app.include_router(reports.router, prefix="/api/reports", tags=["reports"])
app.include_router(billing.router, prefix="/api/billing", tags=["billing"])
app.include_router(ws.router,      prefix="/ws",          tags=["websocket"])

@app.on_event("startup")
async def startup():
    await init_db()
    start_scheduler()

@app.get("/health")
async def health():
    return {"status": "ok", "version": "4.0.0"}
PYEOF

# ── core/database.py ─────────────────────────────────────────────────────────
mkdir -p "$INSTALL_DIR/core"
cat > "$INSTALL_DIR/core/__init__.py" << 'PYEOF'
PYEOF

cat > "$INSTALL_DIR/core/database.py" << 'PYEOF'
"""Async SQLAlchemy engine and session factory."""
import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

DB_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///var/lib/bugreaperx/bugreaperx.db")

engine = create_async_engine(DB_URL, echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

class Base(DeclarativeBase):
    pass

async def init_db():
    async with engine.begin() as conn:
        from core import models  # noqa: F401
        await conn.run_sync(Base.metadata.create_all)

async def get_db():
    async with SessionLocal() as session:
        yield session
PYEOF

# ── core/models.py ────────────────────────────────────────────────────────────
cat > "$INSTALL_DIR/core/models.py" << 'PYEOF'
"""ORM models for BugReaper X."""
from datetime import datetime
from sqlalchemy import String, Integer, Float, DateTime, Text, ForeignKey, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from core.database import Base

class User(Base):
    __tablename__ = "users"
    id:         Mapped[int]      = mapped_column(Integer, primary_key=True)
    email:      Mapped[str]      = mapped_column(String(255), unique=True, index=True)
    hashed_pw:  Mapped[str]      = mapped_column(String(255))
    stripe_id:  Mapped[str|None] = mapped_column(String(64), nullable=True)
    plan:       Mapped[str]      = mapped_column(String(32), default="free")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    scans:      Mapped[list["Scan"]] = relationship(back_populates="owner")

class Scan(Base):
    __tablename__ = "scans"
    id:          Mapped[int]      = mapped_column(Integer, primary_key=True)
    user_id:     Mapped[int]      = mapped_column(ForeignKey("users.id"))
    target:      Mapped[str]      = mapped_column(String(512))
    scan_type:   Mapped[str]      = mapped_column(String(64))
    status:      Mapped[str]      = mapped_column(String(32), default="queued")
    score:       Mapped[float|None] = mapped_column(Float, nullable=True)
    vuln_count:  Mapped[int]      = mapped_column(Integer, default=0)
    critical:    Mapped[int]      = mapped_column(Integer, default=0)
    report_path: Mapped[str|None] = mapped_column(String(512), nullable=True)
    started_at:  Mapped[datetime|None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime|None] = mapped_column(DateTime, nullable=True)
    owner:       Mapped["User"]   = relationship(back_populates="scans")
    findings:    Mapped[list["Finding"]] = relationship(back_populates="scan")

class Finding(Base):
    __tablename__ = "findings"
    id:        Mapped[int] = mapped_column(Integer, primary_key=True)
    scan_id:   Mapped[int] = mapped_column(ForeignKey("scans.id"))
    severity:  Mapped[str] = mapped_column(String(16))
    vuln_type: Mapped[str] = mapped_column(String(128))
    location:  Mapped[str] = mapped_column(String(512))
    detail:    Mapped[str] = mapped_column(Text, default="")
    cvss:      Mapped[float|None] = mapped_column(Float, nullable=True)
    scan:      Mapped["Scan"] = relationship(back_populates="findings")
PYEOF

# ── core/scheduler.py ────────────────────────────────────────────────────────
cat > "$INSTALL_DIR/core/scheduler.py" << 'PYEOF'
"""APScheduler — periodic scan jobs."""
from apscheduler.schedulers.asyncio import AsyncIOScheduler

_scheduler = AsyncIOScheduler()

def start_scheduler():
    if not _scheduler.running:
        _scheduler.start()

def add_job(func, trigger: str = "interval", **kwargs):
    _scheduler.add_job(func, trigger, **kwargs)
PYEOF

# ── core/security.py ─────────────────────────────────────────────────────────
cat > "$INSTALL_DIR/core/security.py" << 'PYEOF'
"""JWT + password hashing utilities."""
import os
from datetime import datetime, timedelta
from jose import jwt
from passlib.context import CryptContext

SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production")
ALGORITHM  = "HS256"
TOKEN_TTL  = 60  # minutes

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(pw: str) -> str:
    return pwd_ctx.hash(pw)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_ctx.verify(plain, hashed)

def create_token(sub: str) -> str:
    exp = datetime.utcnow() + timedelta(minutes=TOKEN_TTL)
    return jwt.encode({"sub": sub, "exp": exp}, SECRET_KEY, algorithm=ALGORITHM)

def decode_token(token: str) -> str:
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    return payload["sub"]
PYEOF

# ── api/ skeleton ─────────────────────────────────────────────────────────────
mkdir -p "$INSTALL_DIR/api/routers"
touch    "$INSTALL_DIR/api/__init__.py" \
         "$INSTALL_DIR/api/routers/__init__.py" \
         "$INSTALL_DIR/api/routers/auth.py" \
         "$INSTALL_DIR/api/routers/scans.py" \
         "$INSTALL_DIR/api/routers/reports.py" \
         "$INSTALL_DIR/api/routers/billing.py" \
         "$INSTALL_DIR/api/routers/ws.py"

cat > "$INSTALL_DIR/api/routers/auth.py" << 'PYEOF'
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from core.database import get_db
from core.models import User
from core.security import hash_password, verify_password, create_token
from pydantic import BaseModel

router = APIRouter()

class RegisterIn(BaseModel):
    email: str
    password: str

class LoginIn(BaseModel):
    email: str
    password: str

@router.post("/register")
async def register(body: RegisterIn, db: AsyncSession = Depends(get_db)):
    existing = await db.scalar(select(User).where(User.email == body.email))
    if existing:
        raise HTTPException(400, "Email already registered")
    user = User(email=body.email, hashed_pw=hash_password(body.password))
    db.add(user)
    await db.commit()
    return {"token": create_token(body.email)}

@router.post("/login")
async def login(body: LoginIn, db: AsyncSession = Depends(get_db)):
    user = await db.scalar(select(User).where(User.email == body.email))
    if not user or not verify_password(body.password, user.hashed_pw):
        raise HTTPException(401, "Invalid credentials")
    return {"token": create_token(body.email)}
PYEOF

# ── scanners/ package ─────────────────────────────────────────────────────────
mkdir -p "$INSTALL_DIR/scanners"
touch    "$INSTALL_DIR/scanners/__init__.py"

for module in port_scanner web_crawler vuln_matcher header_inspector \
              ssl_auditor dns_recon sql_probe xss_probe; do
  cat > "$INSTALL_DIR/scanners/${module}.py" << PYEOF
"""Scanner module: ${module}."""
from typing import Dict, List

async def run(target: str, options: Dict | None = None) -> List[Dict]:
    """Execute ${module} against *target* and return findings."""
    # TODO: implement ${module} logic
    return []
PYEOF
done
ok "Application modules written"

# =============================================================================
# 6. CONFIGURATION FILE
# =============================================================================
info "Writing default configuration…"
cat > "$CONF_DIR/bugreaperx.env" << 'EOF'
# BugReaper X v4.0 — Runtime Configuration
# Copy to /etc/bugreaperx/bugreaperx.env and fill in secrets before starting.

# ── Server ──────────────────────────────────────────────────────────────────
HOST=0.0.0.0
PORT=8080

# ── Database ─────────────────────────────────────────────────────────────────
DATABASE_URL=sqlite+aiosqlite:///var/lib/bugreaperx/bugreaperx.db

# ── Security ─────────────────────────────────────────────────────────────────
SECRET_KEY=CHANGE_ME_BEFORE_PRODUCTION

# ── Stripe billing (optional) ────────────────────────────────────────────────
STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=

# ── AI assistant (optional) ──────────────────────────────────────────────────
ANTHROPIC_API_KEY=

# ── VR bridge (optional) ─────────────────────────────────────────────────────
VR_BRIDGE_ENABLED=false
VR_BRIDGE_PORT=9000
EOF
chmod 640 "$CONF_DIR/bugreaperx.env"
chown root:"$SERVICE_USER" "$CONF_DIR/bugreaperx.env"
ok "Configuration written to $CONF_DIR/bugreaperx.env"

# =============================================================================
# 7. DATABASE INITIALISATION
# =============================================================================
info "Initialising database at $DB_PATH…"
chown "$SERVICE_USER:$SERVICE_USER" "$DATA_DIR"

sudo -u "$SERVICE_USER" \
  env DATABASE_URL="sqlite+aiosqlite://$DB_PATH" \
  "$VENV_DIR/bin/python" - << 'PYEOF' 2>/dev/null || true
import asyncio, sys, os
sys.path.insert(0, "/opt/bugreaperx")
os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite://{sys.argv[1] if len(sys.argv)>1 else '/var/lib/bugreaperx/bugreaperx.db'}")
from core.database import init_db
asyncio.run(init_db())
print("DB initialised")
PYEOF
ok "Database initialised"

# =============================================================================
# 8. VR AUDIO ASSET GENERATION
# =============================================================================
if [[ $OPT_NO_VR -eq 0 ]] && command -v sox &>/dev/null; then
  info "Generating VR audio assets…"

  gen_tone() {
    local name="$1" freq="$2" dur="$3"
    local out="$AUDIO_DIR/${name}.wav"
    sox -n -r 44100 -c 2 "$out" synth "$dur" sine "$freq" fade 0 "$dur" 0.05 vol 0.7 2>/dev/null \
      && ok "  $out" || warn "  Failed to generate $out"
  }

  gen_tone "scan_start"    440 0.3
  gen_tone "scan_complete" 880 0.5
  gen_tone "critical_vuln" 220 1.0
  gen_tone "info_ping"     660 0.15
  gen_tone "vr_ambient"    110 5.0

  chown -R "$SERVICE_USER:$SERVICE_USER" "$AUDIO_DIR"
  ok "VR audio assets generated in $AUDIO_DIR"
else
  [[ $OPT_NO_VR -eq 1 ]] && info "VR assets skipped (--no-vr)" \
                          || warn "sox not found — VR audio assets skipped"
fi

# =============================================================================
# 9. FIREWALL
# =============================================================================
if command -v ufw &>/dev/null; then
  info "Configuring UFW firewall…"
  ufw --force enable  >/dev/null 2>&1 || true
  ufw allow ssh       >/dev/null 2>&1
  ufw allow 8080/tcp  >/dev/null 2>&1
  ufw deny  9000/tcp  >/dev/null 2>&1  # VR bridge — localhost only
  ok "UFW configured (SSH + 8080 open; VR bridge 9000 blocked externally)"
else
  warn "ufw not found — configure firewall manually"
fi

# =============================================================================
# 10. SYSTEMD SERVICES
# =============================================================================
if [[ $OPT_NO_SYSTEMD -eq 0 ]] && command -v systemctl &>/dev/null; then
  info "Installing systemd service…"
  cat > /etc/systemd/system/bugreaperx.service << EOF
[Unit]
Description=BugReaper X v4.0 — Vulnerability Scanning Platform
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$INSTALL_DIR
EnvironmentFile=$CONF_DIR/bugreaperx.env
ExecStart=$VENV_DIR/bin/uvicorn main:app --host \${HOST} --port \${PORT} --workers 2
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=bugreaperx

# Security hardening
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ReadWritePaths=$DATA_DIR $LOG_DIR

[Install]
WantedBy=multi-user.target
EOF

  systemctl daemon-reload
  systemctl enable bugreaperx.service
  ok "systemd service installed and enabled"
  info "Start with: systemctl start bugreaperx"
else
  [[ $OPT_NO_SYSTEMD -eq 1 ]] && info "systemd install skipped (--no-systemd)" \
                               || warn "systemctl not available — run manually"
fi

# =============================================================================
# 11. SHELL ALIASES
# =============================================================================
ALIAS_FILE="/etc/profile.d/bugreaperx.sh"
info "Writing shell aliases to $ALIAS_FILE…"
cat > "$ALIAS_FILE" << 'EOF'
# BugReaper X v4.0 aliases
alias brx="$VENV_DIR/bin/python /opt/bugreaperx/cli.py"
alias brx-status="systemctl status bugreaperx 2>/dev/null || echo 'systemd unavailable'"
alias brx-logs="journalctl -u bugreaperx -f 2>/dev/null || tail -f /var/log/bugreaperx/app.log"
alias brx-restart="systemctl restart bugreaperx"
EOF
ok "Aliases written (reload shell or: source $ALIAS_FILE)"

# =============================================================================
# 12. OWNERSHIP FINALISATION
# =============================================================================
chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR" || true
chown -R "$SERVICE_USER:$SERVICE_USER" "$DATA_DIR"    || true
chown -R "$SERVICE_USER:$SERVICE_USER" "$LOG_DIR"     || true

# =============================================================================
# DONE
# =============================================================================
echo ""
echo -e "${GRN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GRN}║  BugReaper X v4.0 — Installation Complete                   ║${NC}"
echo -e "${GRN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo "  Install dir : $INSTALL_DIR"
echo "  Data dir    : $DATA_DIR"
echo "  Config      : $CONF_DIR/bugreaperx.env"
echo "  Database    : $DB_PATH"
echo ""
echo "  Next steps:"
echo "  1. Edit $CONF_DIR/bugreaperx.env (set SECRET_KEY at minimum)"
echo "  2. systemctl start bugreaperx"
echo "  3. Open http://localhost:8080/api/docs"
echo ""
warn "ACTION REQUIRED: Set SECRET_KEY in $CONF_DIR/bugreaperx.env before exposing to network"
echo ""
