#Requires -Version 5.1
<#
.SYNOPSIS
    ZeroClaw Windows setup — write, read, and store code online and offline.
.DESCRIPTION
    One-file setup. Copy, paste, and run once.
    Installs ZeroClaw, all free API providers, and Ollama offline mode.
    Creates a persistent code workspace at %USERPROFILE%\zeroclaw-workspace.
.EXAMPLE
    Set-ExecutionPolicy Bypass -Scope Process -Force; .\scripts\setup-windows.ps1
    Set-ExecutionPolicy Bypass -Scope Process -Force; .\scripts\setup-windows.ps1 -Model qwen2.5-coder:7b
    Set-ExecutionPolicy Bypass -Scope Process -Force; .\scripts\setup-windows.ps1 -SkipOllama
#>

param(
    [string]$Model      = "llama3.3",
    [switch]$SkipBuild,
    [switch]$SkipOllama
)

$ErrorActionPreference = "Stop"

# ── Colours ───────────────────────────────────────────────────────────────────
function Write-Section { param([string]$t) Write-Host "`n━━  $t  ━━" -ForegroundColor Cyan }
function Write-Info    { param([string]$t) Write-Host "[setup] $t" -ForegroundColor Green }
function Write-Note    { param([string]$t) Write-Host "[note]  $t" -ForegroundColor Yellow }
function Write-Err     { param([string]$t) Write-Host "[error] $t" -ForegroundColor Red; exit 1 }

function Test-Cmd([string]$c) { $null -ne (Get-Command $c -ErrorAction SilentlyContinue) }

function Add-ToUserPath([string]$dir) {
    $cur = [System.Environment]::GetEnvironmentVariable("PATH", "User")
    if ($cur -notlike "*$dir*") {
        [System.Environment]::SetEnvironmentVariable("PATH", "$dir;$cur", "User")
        $env:PATH = "$dir;" + $env:PATH
        Write-Note "Added $dir to user PATH (permanent — reopen terminal to use everywhere)."
    }
}

# ── SECTION 1: Prerequisites ──────────────────────────────────────────────────
Write-Section "Prerequisites"

# Git
if (-not (Test-Cmd "git")) {
    Write-Info "Installing Git via winget..."
    winget install --id Git.Git -e --silent --accept-package-agreements --accept-source-agreements
    $env:PATH += ";C:\Program Files\Git\cmd"
}
Write-Info "Git: $(git --version 2>$null)"

# Rust / cargo
if (-not (Test-Cmd "cargo")) {
    Write-Info "Installing Rust via rustup..."
    $rustupExe = "$env:TEMP\rustup-init.exe"
    Invoke-WebRequest -Uri "https://win.rustup.rs/x86_64" -OutFile $rustupExe -UseBasicParsing
    & $rustupExe -y --no-modify-path 2>&1 | Out-Null
    Remove-Item $rustupExe -Force -ErrorAction SilentlyContinue
    $cargoHome = "$env:USERPROFILE\.cargo\bin"
    Add-ToUserPath $cargoHome
    $env:PATH = "$cargoHome;" + $env:PATH
}
Write-Info "Rust: $(cargo --version 2>$null)"

# ── SECTION 2: Build / install zeroclaw ──────────────────────────────────────
Write-Section "Install ZeroClaw"

$installDir  = "$env:USERPROFILE\.local\bin"
$binaryPath  = "$installDir\zeroclaw.exe"
New-Item -ItemType Directory -Path $installDir -Force | Out-Null
Add-ToUserPath $installDir

if ((Test-Cmd "zeroclaw") -and -not $SkipBuild) {
    Write-Info "ZeroClaw already installed: $(& zeroclaw --version 2>$null)"
} else {
    $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
    $repoRoot  = Split-Path -Parent $scriptDir

    if (Test-Path "$repoRoot\Cargo.toml") {
        Write-Info "Building ZeroClaw from source (this may take a few minutes)..."
        Push-Location $repoRoot
        try {
            cargo build --release
            Copy-Item "target\release\zeroclaw.exe" $binaryPath -Force
            Write-Info "Installed to $binaryPath"
        } finally { Pop-Location }
    } else {
        Write-Err "ZeroClaw source not found and zeroclaw.exe not on PATH.`n  Clone the repo and run this script from inside it:`n    cd zeroclaw && .\scripts\setup-windows.ps1"
    }
}

# ── SECTION 3: Code workspace ─────────────────────────────────────────────────
Write-Section "Code workspace"

$workspaceDir = "$env:USERPROFILE\zeroclaw-workspace"
$projectsDir  = "$workspaceDir\projects"
$sessionsDir  = "$workspaceDir\sessions"

foreach ($d in @($projectsDir, $sessionsDir)) {
    New-Item -ItemType Directory -Path $d -Force | Out-Null
}

# Persist workspace path for ZeroClaw
$env:ZEROCLAW_WORKSPACE = $workspaceDir
[System.Environment]::SetEnvironmentVariable("ZEROCLAW_WORKSPACE", $workspaceDir, "User")

Write-Info "Workspace : $workspaceDir"
Write-Info "  projects\  — code files the agent writes and reads"
Write-Info "  sessions\  — conversation logs"

# ── SECTION 4: Config directory ───────────────────────────────────────────────
Write-Section "Config directory"

$configDir  = "$env:USERPROFILE\.zeroclaw"
$configFile = "$configDir\config.toml"
New-Item -ItemType Directory -Path $configDir -Force | Out-Null
Write-Info "Config directory: $configDir"

# ── SECTION 5: Write config.toml ──────────────────────────────────────────────
Write-Section "Config file"

if (Test-Path $configFile) {
    Write-Note "Config already exists at $configFile — skipping write."
    Write-Note "Delete it and re-run to regenerate, or edit it manually."
} else {
    # Single-quoted heredoc keeps every $ literal (no PowerShell interpolation).
    $toml = @'
# ~/.zeroclaw/config.toml — generated by setup-windows.ps1
#
# Online : set any free API key below and the agent uses it automatically.
#          If one provider rate-limits the agent falls through the whole chain.
# Offline: Ollama is the last entry in fallback_providers — always available,
#          no internet, no API key.
#
# Set a key (open new terminal after setx):
#   setx CEREBRAS_API_KEY  your-key
#   zeroclaw agent -m "Write a Python web scraper and save it to projects/scraper.py"
#
# Force offline mode:
#   zeroclaw agent --provider ollama -m "Debug this code for me"

provider    = "cerebras"
model       = "llama-3.3-70b"
temperature = 0.7

# ── Agent ─────────────────────────────────────────────────────────────────────
[agent]
max_tool_iterations  = 100     # raised from default 10
max_history_messages = 1000    # raised from default 50
parallel_tools       = true    # run independent tools concurrently

# ── Provider fallback chain ───────────────────────────────────────────────────
# Online free providers first, Ollama last (offline, zero cost, always on).
[reliability]
provider_retries    = 5
provider_backoff_ms = 500
fallback_providers  = [
  "sambanova",     # fast free inference
  "groq",          # generous free tier
  "hyperbolic",    # free credits
  "deepinfra",     # broad model hosting
  "featherless",   # free-tier serving
  "chutes",        # free community inference
  "novita",        # low-cost open models
  "siliconflow",   # free Qwen/DeepSeek
  "inference-net", # free-tier endpoint
  "ollama",        # offline fallback — no key, no internet needed
]

[reliability.model_fallbacks]
"llama-3.3-70b" = [
  "llama-3.3-70b",
  "Meta-Llama-3.3-70B-Instruct",
  "llama3-70b-8192",
  "meta-llama/Llama-3.3-70B-Instruct",
  "meta-llama/Llama-3.3-70B-Instruct-Turbo",
  "meta-llama/llama-3.3-70b-instruct",
  "deepseek-ai/DeepSeek-V3-0324",
  "deepseek-ai/DeepSeek-V3",
  "meta-llama/llama-3.3-70b-instruct/fp-8",
  "llama3.3",   # ollama model name — must be last
]

# ── Memory — persists code context across sessions ────────────────────────────
[memory]
backend                     = "sqlite"
response_cache_enabled      = true
response_cache_ttl_minutes  = 1440    # 24-hour cache: zero tokens on repeated calls
response_cache_max_entries  = 100000
snapshot_enabled            = true
snapshot_on_hygiene         = true
auto_save                   = true    # remember every conversation automatically
hygiene_enabled             = true
conversation_retention_days = 365     # keep a full year of history

# ── Web search (online mode) ──────────────────────────────────────────────────
[web_search]
enabled      = true
provider     = "duckduckgo"   # free, no key
max_results  = 10
timeout_secs = 30

# ── HTTP requests ─────────────────────────────────────────────────────────────
[http_request]
enabled           = true
max_response_size = 10000000
timeout_secs      = 60

# ── Browser automation ────────────────────────────────────────────────────────
[browser]
enabled = true
backend = "agent_browser"

# ── Composio (1000+ integrations) ────────────────────────────────────────────
[composio]
enabled = true

# ── Multimodal ────────────────────────────────────────────────────────────────
[multimodal]
max_images         = 16
max_image_size_mb  = 20
allow_remote_fetch = true

# ── Autonomy (full = acts on your instructions without extra confirmation) ────
[autonomy]
level                  = "full"
workspace_only         = false
max_actions_per_hour   = 100
max_cost_per_day_cents = 0      # hard zero — only free providers used

# ── Runtime ───────────────────────────────────────────────────────────────────
[runtime]
reasoning_enabled = true

# ── Scheduler ────────────────────────────────────────────────────────────────
[scheduler]
enabled        = true
max_tasks      = 1024
max_concurrent = 32

# ── Cron ──────────────────────────────────────────────────────────────────────
[cron]
enabled         = true
max_run_history = 1000

# ── Heartbeat ─────────────────────────────────────────────────────────────────
[heartbeat]
enabled          = true
interval_minutes = 15

# ── Cost cap ──────────────────────────────────────────────────────────────────
[cost]
enabled           = true
daily_limit_usd   = 0.00
monthly_limit_usd = 0.00

# ── Skills ────────────────────────────────────────────────────────────────────
[skills]
open_skills_enabled   = true
prompt_injection_mode = "full"
'@
    Set-Content -Path $configFile -Value $toml -Encoding UTF8
    Write-Info "Config written to $configFile"
}

# ── SECTION 6: Ollama (offline mode) ─────────────────────────────────────────
Write-Section "Ollama — offline mode"

if ($SkipOllama) {
    Write-Note "Skipping Ollama setup (-SkipOllama flag set)."
} else {
    # Install Ollama if missing
    if (-not (Test-Cmd "ollama")) {
        Write-Info "Installing Ollama via winget..."
        winget install --id Ollama.Ollama -e --silent --accept-package-agreements --accept-source-agreements
        $ollamaDir = "$env:LOCALAPPDATA\Programs\Ollama"
        if (Test-Path $ollamaDir) {
            Add-ToUserPath $ollamaDir
            $env:PATH = "$ollamaDir;" + $env:PATH
        }
    }

    # Start server if not already running
    if (-not (Get-Process "ollama" -ErrorAction SilentlyContinue)) {
        Write-Info "Starting Ollama server..."
        Start-Process "ollama" -ArgumentList "serve" -WindowStyle Hidden
        # Wait up to 30 s for the API to respond
        $ready = $false
        for ($i = 0; $i -lt 15; $i++) {
            Start-Sleep -Seconds 2
            try {
                $r = Invoke-WebRequest -Uri "http://localhost:11434/api/version" `
                                       -UseBasicParsing -ErrorAction Stop
                if ($r.StatusCode -eq 200) { $ready = $true; break }
            } catch { }
        }
        if (-not $ready) { Write-Note "Ollama server didn't respond in 30 s — check it manually." }
    }

    # Pull model if not already present
    $listed = ollama list 2>$null
    if ($listed -notlike "*$Model*") {
        Write-Info "Pulling model '$Model' (downloads several GB — go make a coffee)..."
        ollama pull $Model
    } else {
        Write-Info "Model '$Model' already present — skipping pull."
    }
    Write-Info "Ollama ready: $Model at http://localhost:11434"
}

# ── SECTION 7: Free API key reference ────────────────────────────────────────
Write-Section "Free API keys"

$providers = @(
    [pscustomobject]@{ Name="Cerebras";      Url="https://cloud.cerebras.ai";    Var="CEREBRAS_API_KEY"      },
    [pscustomobject]@{ Name="Groq";          Url="https://console.groq.com";     Var="GROQ_API_KEY"          },
    [pscustomobject]@{ Name="SambaNova";     Url="https://cloud.sambanova.ai";   Var="SAMBANOVA_API_KEY"     },
    [pscustomobject]@{ Name="Hyperbolic";    Url="https://app.hyperbolic.xyz";   Var="HYPERBOLIC_API_KEY"    },
    [pscustomobject]@{ Name="DeepInfra";     Url="https://deepinfra.com";        Var="DEEPINFRA_API_KEY"     },
    [pscustomobject]@{ Name="Featherless";   Url="https://featherless.ai";       Var="FEATHERLESS_API_KEY"   },
    [pscustomobject]@{ Name="Chutes";        Url="https://chutes.ai";            Var="CHUTES_API_KEY"        },
    [pscustomobject]@{ Name="Novita";        Url="https://novita.ai";            Var="NOVITA_API_KEY"        },
    [pscustomobject]@{ Name="SiliconFlow";   Url="https://siliconflow.cn";       Var="SILICONFLOW_API_KEY"   },
    [pscustomobject]@{ Name="inference.net"; Url="https://inference.net";        Var="INFERENCE_NET_API_KEY" },
    [pscustomobject]@{ Name="Anthropic";     Url="https://console.anthropic.com";Var="ANTHROPIC_API_KEY"     }
)

Write-Host ""
Write-Host "  Sign up (all free tiers) — paste key with setx, open new terminal:" -ForegroundColor White
Write-Host ""
$hdr = "  {0,-15}  {1,-36}  {2}" -f "PROVIDER","SIGNUP URL","WINDOWS COMMAND"
Write-Host $hdr -ForegroundColor DarkGray
Write-Host ("  " + "-"*80) -ForegroundColor DarkGray
foreach ($p in $providers) {
    Write-Host ("  {0,-15}  {1,-36}  setx {2} your-key" -f $p.Name, $p.Url, $p.Var)
}
Write-Host ""
Write-Note "setx writes permanently to user environment — reopen terminal after running it."
Write-Note "Anthropic key unlocks claude-opus-4-7 with adaptive thinking + xhigh effort."
Write-Note "No keys at all? Ollama is already configured — go offline, zero cost."

# ── SECTION 8: Smoke test ─────────────────────────────────────────────────────
$anyKey = $providers | Where-Object {
    [System.Environment]::GetEnvironmentVariable($_.Var)
} | Select-Object -First 1

if ($anyKey -and (Test-Cmd "zeroclaw")) {
    Write-Section "Smoke test"
    Write-Info "API key detected ($($anyKey.Name)) — running end-to-end test..."
    zeroclaw agent -m "Reply with exactly the word: READY"
    Write-Info "Smoke test passed."
} elseif (-not $SkipOllama -and (Test-Cmd "zeroclaw") -and (Test-Cmd "ollama")) {
    Write-Section "Smoke test"
    Write-Info "No API key set — testing offline with Ollama ($Model)..."
    zeroclaw agent --provider ollama --model $Model -m "Reply with exactly the word: READY"
    Write-Info "Smoke test passed."
}

# ── SECTION 9: Done ───────────────────────────────────────────────────────────
Write-Section "Done"
Write-Host ""
Write-Host "  ZeroClaw is ready." -ForegroundColor Green
Write-Host ""
Write-Host ("  Workspace : " + $workspaceDir) -ForegroundColor White
Write-Host ("  Config    : " + $configFile)   -ForegroundColor White
Write-Host ("  Offline   : Ollama / $Model")   -ForegroundColor White
Write-Host ""
Write-Host "  QUICK START:" -ForegroundColor Cyan
Write-Host '  zeroclaw agent -m "Write a Python hello-world and save it to projects\hello.py"'
Write-Host '  zeroclaw agent -m "Read projects\hello.py and add a main guard"'
Write-Host '  zeroclaw agent -m "Store note: rate limit is 100 req/min"'
Write-Host '  zeroclaw agent -m "Search the web for the latest Python best practices"'
Write-Host ('  zeroclaw agent --provider ollama -m "Review projects\hello.py offline"')
Write-Host ""
Write-Host "  CODE WORKFLOW:" -ForegroundColor Cyan
Write-Host "  1. Tell the agent what to build in plain English"
Write-Host ("  2. Files are written to " + $projectsDir)
Write-Host "  3. Memory persists — the agent remembers decisions across sessions"
Write-Host "  4. Lose internet? Ollama takes over automatically"
Write-Host ""
