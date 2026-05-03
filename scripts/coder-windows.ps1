# ================================================================
#  ZEROCLAW CODER  —  Elite Edition
#  Private AI coding partner. Persistent sessions. No fluff.
#
#  !! RUN IN POWERSHELL — NOT Git Bash, NOT CMD !!
#  Win+X → "Windows PowerShell" or "Terminal", then:
#
#    Set-ExecutionPolicy Bypass -Scope Process -Force
#    iex (irm "https://raw.githubusercontent.com/vanthryx00/zeroclaw/claude/zeroclaw-api-optimization-TQH0u/scripts/coder-windows.ps1")
#
#  FREE KEYS (60 seconds each):
#    Groq      → console.groq.com        (fastest)
#    Cerebras  → cloud.cerebras.ai       (fast)
#    Anthropic → console.anthropic.com   (smartest, $5 credit)
#    SambaNova → cloud.sambanova.ai      (solid, free)
#
#  COMMANDS:
#    /search <q>   web search → AI uses results
#    /run <file>   execute file → AI sees output
#    /read <file>  load file into context
#    /scan         scan project files into context
#    /git <cmd>    git command → AI sees output
#    /clip         read clipboard into context
#    /model        switch AI model
#    /compact      summarize old messages (free up tokens)
#    /export       save session as markdown
#    /files        list saved files
#    /stats        session statistics
#    /sessions     return to session list
#    /quit         save and exit
# ================================================================

Set-StrictMode -Off
$ErrorActionPreference = "Continue"
$ProgressPreference    = "SilentlyContinue"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
try { $Host.UI.RawUI.WindowTitle = "ZeroClaw Coder" } catch {}

# ── Paths ─────────────────────────────────────────────────────────────────────
$WS       = "$env:USERPROFILE\zeroclaw-projects"
$Sessions = "$WS\.sessions"
foreach ($d in @($WS, $Sessions)) { New-Item -ItemType Directory $d -Force | Out-Null }

# ── Script-level state ────────────────────────────────────────────────────────
$script:Provider     = "none"
$script:ApiKey       = ""
$script:AiModel      = ""
$script:Fallbacks    = @()
$script:CallCount    = 0
$script:StartTime    = Get-Date
$script:SessionFiles = @()

# ── UI ────────────────────────────────────────────────────────────────────────
function hi   { param([string]$t) Write-Host $t -ForegroundColor Cyan }
function ok   { param([string]$t) Write-Host $t -ForegroundColor Green }
function warn { param([string]$t) Write-Host $t -ForegroundColor Yellow }
function err  { param([string]$t) Write-Host $t -ForegroundColor Red }
function dim  { param([string]$t) Write-Host $t -ForegroundColor DarkGray }
function bold { param([string]$t) Write-Host $t -ForegroundColor White }
function nl   { Write-Host "" }

function Draw-Banner {
    param([string]$title = "ZEROCLAW CODER", [string]$sub = "")
    $w = 60
    hi ("  " + ([char]9556) + ([string][char]9552 * $w) + [char]9559)
    $p = [int](($w - $title.Length) / 2)
    hi ("  " + [char]9553 + (" " * $p) + $title + (" " * ($w - $p - $title.Length)) + [char]9553)
    if ($sub) {
        $s  = if ($sub.Length -gt $w) { $sub.Substring(0,$w) } else { $sub }
        $p2 = [int](($w - $s.Length) / 2)
        dim ("  " + [char]9553 + (" " * $p2) + $s + (" " * ($w - $p2 - $s.Length)) + [char]9553)
    }
    hi ("  " + [char]9562 + ([string][char]9552 * $w) + [char]9565)
}

function Show-Code {
    param([string]$code, [string]$lang = "")
    $lines  = $code -split "`n"
    $label  = if ($lang) { " $lang " } else { " code " }
    $dashes = "-" * [Math]::Max(0, 48 - $label.Length)
    nl
    Write-Host "  +--$label$dashes--+" -ForegroundColor DarkCyan
    $n = 1
    foreach ($line in $lines) {
        Write-Host ("  | {0,3} | " -f $n) -ForegroundColor DarkGray -NoNewline
        Write-Host $line -ForegroundColor White
        $n++
        if ($n -gt 80) { dim "  |      | ... ($($lines.Count - 80) more lines)"; break }
    }
    Write-Host ("  +" + ("-" * (52 + $label.Length)) + "+") -ForegroundColor DarkCyan
    nl
}

function Show-Badge {
    $c = switch ($script:Provider) {
        "groq"      { "Cyan" }
        "anthropic" { "Magenta" }
        "cerebras"  { "Blue" }
        "sambanova" { "Green" }
        "ollama"    { "Yellow" }
        default     { "DarkGray" }
    }
    Write-Host ("  [ {0} / {1} ]" -f $script:Provider.ToUpper(), $script:AiModel) -ForegroundColor $c
}

# ── Async AI call with animated spinner ───────────────────────────────────────
function Ask-AI {
    param([array]$history)

    $histJson = $history | ConvertTo-Json -Depth 20 -Compress
    $prov     = $script:Provider
    $key      = $script:ApiKey
    $model    = $script:AiModel

    $jobBlock = {
        param($prov, $key, $model, $histJson)
        $ErrorActionPreference = "Stop"
        $ProgressPreference    = "SilentlyContinue"
        $hist = $histJson | ConvertFrom-Json

        try {
            switch ($prov) {
                "anthropic" {
                    $sys  = ($hist | Where-Object { $_.role -eq "system" } | Select-Object -Last 1).content
                    $msgs = @($hist | Where-Object { $_.role -ne "system" })
                    $body = @{
                        model         = $model
                        max_tokens    = 16000
                        thinking      = @{ type = "adaptive" }
                        output_config = @{ effort = "xhigh" }
                        system        = $sys
                        messages      = $msgs
                    } | ConvertTo-Json -Depth 20
                    $r = Invoke-RestMethod "https://api.anthropic.com/v1/messages" -Method POST `
                        -Headers @{ "x-api-key" = $key; "anthropic-version" = "2023-06-01"; "content-type" = "application/json" } `
                        -Body $body -TimeoutSec 120
                    return ($r.content | Where-Object { $_.type -eq "text" } | Select-Object -First 1).text
                }
                { $_ -in @("groq","cerebras","sambanova") } {
                    $urls = @{
                        groq      = "https://api.groq.com/openai/v1/chat/completions"
                        cerebras  = "https://api.cerebras.ai/v1/chat/completions"
                        sambanova = "https://api.sambanova.ai/v1/chat/completions"
                    }
                    $body = @{
                        model       = $model
                        messages    = @($hist)
                        max_tokens  = 8192
                        temperature = 0.7
                    } | ConvertTo-Json -Depth 20
                    $r = Invoke-RestMethod $urls[$prov] -Method POST `
                        -Headers @{ Authorization = "Bearer $key"; "Content-Type" = "application/json" } `
                        -Body $body -TimeoutSec 120
                    return $r.choices[0].message.content
                }
                "ollama" {
                    $body = @{ model = $model; messages = @($hist); stream = $false } | ConvertTo-Json -Depth 20
                    $r = Invoke-RestMethod "http://localhost:11434/api/chat" -Method POST `
                        -ContentType "application/json" -Body $body -TimeoutSec 300
                    return $r.message.content
                }
            }
        } catch { return "__ERROR__: $_" }
    }

    $job    = Start-Job -ScriptBlock $jobBlock -ArgumentList $prov, $key, $model, $histJson
    $frames = @("|", "/", "-", "\")
    $i      = 0
    $t0     = Get-Date

    while ($job.State -eq "Running") {
        $s = [int]((Get-Date) - $t0).TotalSeconds
        Write-Host ("`r  {0}  thinking... {1}s   " -f $frames[$i % 4], $s) -NoNewline -ForegroundColor DarkCyan
        $i++
        Start-Sleep -Milliseconds 100
    }
    Write-Host ("`r" + (" " * 50) + "`r") -NoNewline

    $elapsed = [math]::Round(((Get-Date) - $t0).TotalSeconds, 1)
    $reply   = Receive-Job $job 2>$null
    Remove-Job $job -Force

    if (-not $reply -or $reply.StartsWith("__ERROR__:")) {
        # Auto-fallback to next provider
        foreach ($fb in $script:Fallbacks) {
            if ($fb.Provider -ne $prov) {
                warn "  Provider failed — switching to $($fb.Provider)..."
                $script:Provider = $fb.Provider
                $script:ApiKey   = $fb.ApiKey
                $script:AiModel  = $fb.Model
                return Ask-AI $history
            }
        }
        throw ($reply -replace "^__ERROR__: ", "")
    }

    $script:CallCount++
    dim ("  [{0}s  call #{1}]" -f $elapsed, $script:CallCount)
    return $reply
}

# ── Web search ────────────────────────────────────────────────────────────────
function Search-Web {
    param([string]$query)
    $parts = @()
    try {
        $enc = [System.Uri]::EscapeDataString($query)
        $r   = Invoke-RestMethod "https://api.duckduckgo.com/?q=$enc&format=json&no_redirect=1&no_html=1" -UseBasicParsing -EA Stop -TimeoutSec 10
        if ($r.AbstractText) { $parts += $r.AbstractText }
        if ($r.Answer)       { $parts += "Answer: $($r.Answer)" }
        $r.RelatedTopics | Select-Object -First 6 | ForEach-Object { if ($_.Text) { $parts += "- $($_.Text)" } }
    } catch {}

    if ($parts.Count -eq 0) {
        try {
            $enc  = [System.Uri]::EscapeDataString($query)
            $html = (Invoke-WebRequest "https://html.duckduckgo.com/html/?q=$enc" -UseBasicParsing -EA Stop -TimeoutSec 10).Content
            $parts = [regex]::Matches($html, '<a class="result__snippet"[^>]*>([^<]+)') |
                Select-Object -First 6 |
                ForEach-Object { "- " + [System.Net.WebUtility]::HtmlDecode($_.Groups[1].Value.Trim()) }
        } catch {}
    }

    if ($parts.Count -eq 0) { return "No results for: $query" }
    return "Web search: '$query'`n" + ($parts -join "`n")
}

# ── Project context scanner ───────────────────────────────────────────────────
function Get-ProjectContext {
    param([string]$dir)
    if (-not (Test-Path $dir)) { return "Directory not found: $dir" }
    $out = @("=== Project: $dir ===", "")

    $files = Get-ChildItem $dir -Recurse -File -EA SilentlyContinue |
        Where-Object { $_.FullName -notmatch '\\(node_modules|\.git|target|dist|build|__pycache__|\.venv|\.next|vendor)\\' } |
        Select-Object -First 80
    if ($files) {
        $out += "Files:"
        $files | ForEach-Object { $out += "  " + $_.FullName.Replace($dir,"").TrimStart("\") }
        $out += ""
    }

    foreach ($f in @("package.json","Cargo.toml","requirements.txt","pyproject.toml","go.mod","pom.xml","composer.json","Makefile",".env.example")) {
        $fp = Join-Path $dir $f
        if (Test-Path $fp) {
            $c = Get-Content $fp -Raw -EA SilentlyContinue
            if ($c -and $c.Length -lt 4000) {
                $out += "--- $f ---"
                $out += $c.Trim()
                $out += ""
            }
        }
    }
    return $out -join "`n"
}

# ── Code block handler ────────────────────────────────────────────────────────
function Handle-CodeBlocks {
    param([string]$response, [string]$projectDir)
    $matches = [regex]::Matches($response, '```(?:(\w+)\n)?([\s\S]*?)```')
    foreach ($m in $matches) {
        $lang = $m.Groups[1].Value
        $code = $m.Groups[2].Value.Trim()
        if ($code.Length -lt 10) { continue }
        Show-Code $code $lang
        Write-Host "  Save as (e.g. main.py) or Enter to skip: " -ForegroundColor Yellow -NoNewline
        $fname = (Read-Host).Trim()
        if ($fname) {
            $dest = Join-Path $projectDir $fname
            New-Item -ItemType Directory (Split-Path $dest -Parent) -Force | Out-Null
            if (Test-Path $dest) {
                $old = (Get-Content $dest -Raw -EA SilentlyContinue) -split "`n"
                $new = $code -split "`n"
                dim "  (overwriting: $($old.Count) -> $($new.Count) lines)"
            }
            Set-Content $dest $code -Encoding UTF8
            ok "  Saved: $dest"
            if ($script:SessionFiles -notcontains $dest) { $script:SessionFiles += $dest }
        }
    }
}

# ── Code runner ───────────────────────────────────────────────────────────────
function Run-File {
    param([string]$path, [string]$projectDir)
    if (-not $path) { Write-Host "  File to run: " -NoNewline; $path = (Read-Host).Trim() }
    if (-not [System.IO.Path]::IsPathRooted($path)) { $path = Join-Path $projectDir $path }
    if (-not (Test-Path $path)) { err "  Not found: $path"; return $null }

    $ext    = [System.IO.Path]::GetExtension($path).ToLower()
    $runner = switch ($ext) {
        ".py"  { "python" }
        ".js"  { "node" }
        ".ts"  { "npx ts-node" }
        ".rb"  { "ruby" }
        ".go"  { "go run" }
        ".sh"  { "bash" }
        ".ps1" { "powershell -ExecutionPolicy Bypass -File" }
        default { "" }
    }
    if (-not $runner) { warn "  Don't know how to run $ext files"; return $null }
    $rCmd = $runner.Split()[0]
    if (-not (Get-Command $rCmd -EA SilentlyContinue)) { warn "  $rCmd not found — is it installed?"; return $null }

    dim "  Running: $runner `"$path`""
    $output = try { (Invoke-Expression "$runner `"$path`" 2>&1") | Out-String } catch { "Error: $_" }

    nl
    Write-Host "  +-- output " + ("-" * 40) + "+" -ForegroundColor DarkGray
    ($output -split "`n") | Select-Object -First 50 | ForEach-Object { Write-Host "  | $_" -ForegroundColor Gray }
    Write-Host ("  +" + ("-" * 51) + "+") -ForegroundColor DarkGray
    nl

    return "Ran file: $path`nOutput:`n$output"
}

# ── Git helper ────────────────────────────────────────────────────────────────
function Run-Git {
    param([string]$gitArgs, [string]$dir)
    if (-not (Get-Command git -EA SilentlyContinue)) { warn "  git not installed"; return $null }
    Push-Location $dir
    $output = try { (Invoke-Expression "git $gitArgs 2>&1") | Out-String } catch { "Error: $_" }
    Pop-Location
    dim "  git $gitArgs"
    ($output -split "`n") | Select-Object -First 30 | ForEach-Object { dim "  $_" }
    return "git $gitArgs`n$output"
}

# ── Session helpers ───────────────────────────────────────────────────────────
function Save-Session {
    param([string]$file, [string]$name, [string]$dir, [array]$history, [array]$files)
    @{ name=$name; project=$dir; saved=(Get-Date -Format "o"); files=@($files); history=@($history) } |
        ConvertTo-Json -Depth 20 | Set-Content $file -Encoding UTF8
}

function Get-Sessions { Get-ChildItem "$Sessions\*.json" -EA SilentlyContinue | Sort-Object LastWriteTime -Descending }

function Format-Ago {
    param([datetime]$dt)
    $d = (Get-Date) - $dt
    if     ($d.TotalMinutes -lt 1) { "just now" }
    elseif ($d.TotalHours   -lt 1) { "$([int]$d.TotalMinutes)m ago" }
    elseif ($d.TotalDays    -lt 1) { "$([int]$d.TotalHours)h ago" }
    elseif ($d.TotalDays    -lt 7) { "$([int]$d.TotalDays)d ago" }
    else                           { $dt.ToString("MMM dd") }
}

function Export-Session {
    param([string]$name, [string]$dir, [array]$history)
    $lines = @("# $name", "", "_Exported: $(Get-Date -Format 'yyyy-MM-dd HH:mm')_", "")
    foreach ($msg in $history) {
        if ($msg.role -eq "system") { continue }
        $lines += if ($msg.role -eq "user") { "## You" } else { "## AI" }
        $lines += ""
        $lines += $msg.content
        $lines += ""
        $lines += "---"
        $lines += ""
    }
    $slug = ($name -replace '[^\w]','-').ToLower()
    $out  = "$dir\export-$slug-$(Get-Date -Format yyyyMMdd-HHmm).md"
    ($lines -join "`n") | Set-Content $out -Encoding UTF8
    ok "  Exported: $out"
}

# ── Provider init + health check ──────────────────────────────────────────────
function Test-ApiKey {
    param([string]$prov, [string]$key)
    try {
        switch ($prov) {
            "groq"      { Invoke-RestMethod "https://api.groq.com/openai/v1/models" -Headers @{Authorization="Bearer $key"} -TimeoutSec 8 -EA Stop | Out-Null; return $true }
            "cerebras"  { Invoke-RestMethod "https://api.cerebras.ai/v1/models"     -Headers @{Authorization="Bearer $key"} -TimeoutSec 8 -EA Stop | Out-Null; return $true }
            "anthropic" {
                $b = @{model="claude-haiku-4-5";max_tokens=1;messages=@(@{role="user";content="hi"})} | ConvertTo-Json
                Invoke-RestMethod "https://api.anthropic.com/v1/messages" -Method POST `
                    -Headers @{"x-api-key"=$key;"anthropic-version"="2023-06-01";"content-type"="application/json"} `
                    -Body $b -TimeoutSec 10 -EA Stop | Out-Null
                return $true
            }
            default { return $true }
        }
    } catch { return $false }
}

function Initialize-Providers {
    $all = @(
        @{ p="groq";      k=$env:GROQ_API_KEY;      m="llama-3.3-70b-versatile" }
        @{ p="anthropic"; k=$env:ANTHROPIC_API_KEY; m="claude-opus-4-7" }
        @{ p="cerebras";  k=$env:CEREBRAS_API_KEY;  m="llama-3.3-70b" }
        @{ p="sambanova"; k=$env:SAMBANOVA_API_KEY; m="Meta-Llama-3.3-70B-Instruct" }
    ) | Where-Object { $_.k }

    if ($all.Count -eq 0) { return $false }

    $script:Provider  = $all[0].p
    $script:ApiKey    = $all[0].k
    $script:AiModel   = $all[0].m
    $script:Fallbacks = @($all[1..($all.Count-1)] | ForEach-Object { @{Provider=$_.p;ApiKey=$_.k;Model=$_.m} })
    return $true
}

# ── Key setup wizard ──────────────────────────────────────────────────────────
function Show-KeyWizard {
    Clear-Host; nl
    Draw-Banner "ZEROCLAW CODER" "First-time setup"
    nl
    bold "  Get a FREE key in ~60 seconds:"
    nl
    Write-Host "    1  Groq        console.groq.com         fastest · free" -ForegroundColor Cyan
    Write-Host "    2  Cerebras    cloud.cerebras.ai         fast    · free" -ForegroundColor Cyan
    Write-Host "    3  Anthropic   console.anthropic.com     smartest · $5 credit" -ForegroundColor Magenta
    Write-Host "    4  SambaNova   cloud.sambanova.ai        solid   · free" -ForegroundColor Green
    Write-Host "    5  Ollama      offline · no key · slower" -ForegroundColor DarkGray
    nl
    Write-Host "  Paste your API key (or Enter for offline Ollama): " -ForegroundColor Yellow -NoNewline
    $entered = (Read-Host).Trim()

    if (-not $entered) {
        warn "  Setting up Ollama..."
        if (-not (Get-Command ollama -EA SilentlyContinue)) {
            warn "  Downloading Ollama installer..."
            $ins = "$env:TEMP\OllamaSetup.exe"
            Invoke-WebRequest "https://ollama.com/download/OllamaSetup.exe" -OutFile $ins -UseBasicParsing
            Start-Process $ins "/S" -Wait
            Remove-Item $ins -Force -EA SilentlyContinue
            $env:PATH += ";$env:LOCALAPPDATA\Programs\Ollama"
        }
        if (-not (Get-Process ollama -EA SilentlyContinue)) {
            Start-Process ollama "serve" -WindowStyle Hidden
            for ($i=0; $i -lt 15; $i++) {
                Start-Sleep 2
                try { if ((Invoke-WebRequest "http://localhost:11434/api/version" -UseBasicParsing -EA Stop -TimeoutSec 2).StatusCode -eq 200) { break } } catch {}
            }
        }
        $m = "qwen2.5-coder:7b"
        if ((& ollama list 2>$null) -notlike "*qwen2.5-coder*") {
            warn "  Downloading model (~4 GB)..."
            & ollama pull $m
        }
        $script:Provider = "ollama"; $script:ApiKey = ""; $script:AiModel = $m
        return
    }

    # Auto-detect provider from key prefix
    $pick = if     ($entered -like "gsk_*")    { "1" }
            elseif ($entered -like "sk-ant-*") { "3" }
            elseif ($entered -like "csk-*")    { "2" }
            else   { "" }

    if (-not $pick) {
        Write-Host "  Which provider?  1 Groq  2 Cerebras  3 Anthropic  4 SambaNova: " -ForegroundColor White -NoNewline
        $pick = (Read-Host).Trim()
    }

    $map = @{
        "1" = @{ p="groq";      n="GROQ_API_KEY";      m="llama-3.3-70b-versatile" }
        "2" = @{ p="cerebras";  n="CEREBRAS_API_KEY";  m="llama-3.3-70b" }
        "3" = @{ p="anthropic"; n="ANTHROPIC_API_KEY"; m="claude-opus-4-7" }
        "4" = @{ p="sambanova"; n="SAMBANOVA_API_KEY"; m="Meta-Llama-3.3-70B-Instruct" }
    }
    $sel = if ($map[$pick]) { $map[$pick] } else { $map["1"] }

    Write-Host "  Checking key... " -ForegroundColor DarkGray -NoNewline
    if (Test-ApiKey $sel.p $entered) { ok "valid" } else { warn "could not verify (continuing anyway)" }

    [System.Environment]::SetEnvironmentVariable($sel.n, $entered, "User")
    Set-Item "env:$($sel.n)" $entered
    $script:Provider = $sel.p; $script:ApiKey = $entered; $script:AiModel = $sel.m
    ok "  Key saved as $($sel.n) — won't ask again"
    Start-Sleep 1
}

# ── Session list ──────────────────────────────────────────────────────────────
function Show-SessionList {
    Clear-Host; nl
    Draw-Banner "ZEROCLAW CODER" ("$($script:Provider.ToUpper()) / $script:AiModel")
    nl

    $all = Get-Sessions
    if ($all.Count -eq 0) {
        dim "  No sessions yet."
    } else {
        bold "  Your conversations:"
        nl
        $i = 1
        foreach ($f in $all) {
            try {
                $d    = Get-Content $f.FullName -Raw | ConvertFrom-Json
                $msgs = ($d.history | Where-Object { $_.role -eq "user" }).Count
                $ago  = Format-Ago $f.LastWriteTime
                Write-Host ("  {0,3}.  " -f $i) -ForegroundColor DarkGray -NoNewline
                Write-Host ("{0,-38}" -f $d.name) -ForegroundColor White -NoNewline
                Write-Host ("{0,3} msgs  {1}" -f $msgs, $ago) -ForegroundColor DarkGray
            } catch {
                Write-Host ("  {0,3}.  {1}" -f $i, $f.Name) -ForegroundColor DarkGray
            }
            $i++
        }
    }

    nl
    Write-Host "    N  New conversation" -ForegroundColor Green
    Write-Host "    D# Delete a session  (e.g. D2)" -ForegroundColor DarkGray
    nl
    Write-Host "  Pick: " -ForegroundColor Cyan -NoNewline
    $choice = (Read-Host).Trim()

    if ($choice -match '^[dD](\d+)$') {
        $idx = [int]$Matches[1] - 1
        if ($idx -ge 0 -and $idx -lt $all.Count) {
            try { $nm = (Get-Content $all[$idx].FullName -Raw | ConvertFrom-Json).name } catch { $nm = $all[$idx].Name }
            Write-Host "  Delete '$nm'? (y/N): " -ForegroundColor Red -NoNewline
            if ((Read-Host).Trim() -ieq "y") { Remove-Item $all[$idx].FullName -Force; ok "  Deleted." }
        }
        return @{ action="list" }
    }
    if ($choice -match '^\d+$') {
        $idx = [int]$choice - 1
        if ($idx -ge 0 -and $idx -lt $all.Count) { return @{ action="resume"; file=$all[$idx].FullName } }
    }
    return @{ action="new" }
}

# ── Chat ──────────────────────────────────────────────────────────────────────
function Start-Chat {
    param([string]$sessionFile = "")

    $script:SessionFiles = @()
    $script:StartTime    = Get-Date
    $script:CallCount    = 0
    $history             = @()
    $isNew               = $true
    $sessionName         = ""
    $projectDir          = ""

    if ($sessionFile -and (Test-Path $sessionFile)) {
        $data                = Get-Content $sessionFile -Raw | ConvertFrom-Json
        $sessionName         = $data.name
        $projectDir          = $data.project
        $script:SessionFiles = @($data.files)
        $history             = @($data.history | ForEach-Object { @{ role=$_.role; content=$_.content } })
        $isNew               = $false
    } else {
        nl
        Write-Host "  Session name (e.g. 'discord bot', 'my portfolio'): " -ForegroundColor Cyan -NoNewline
        $sessionName = (Read-Host).Trim()
        if (-not $sessionName) { $sessionName = "session-$(Get-Date -Format yyyyMMdd-HHmm)" }
        $slug        = ($sessionName -replace '[^\w]','-').ToLower() -replace '-+','-'
        $projectDir  = "$WS\$slug"
        New-Item -ItemType Directory $projectDir -Force | Out-Null
        $sessionFile = "$Sessions\$(Get-Date -Format yyyyMMdd-HHmmss)-$slug.json"

        $history = @(@{
            role    = "system"
            content = "You are an elite software engineer and pair programming partner. Think: principal engineer at a top-tier tech company.

Your rules — non-negotiable:
1. Write COMPLETE working code. No TODOs, no placeholder stubs, no 'implement this yourself'.
2. Every code response uses a fenced block with the language tag (triple-backtick python, js, rust, etc).
3. After code: one short paragraph — what it does, any gotchas, recommended next step.
4. When fixing bugs: explain WHY it broke, not just what changed.
5. Think about edge cases, performance, and security automatically.
6. No padding. No 'Great question!', no 'Certainly!'. Start with the answer.
7. At most ONE clarifying question if something is genuinely ambiguous.
8. Remember everything in this conversation and build on it.

Your specialty: writing code that actually ships.

Project: $sessionName
Working directory: $projectDir"
        })
    }

    Clear-Host; nl
    Draw-Banner "ZEROCLAW CODER"
    Write-Host "  Session : $sessionName" -ForegroundColor White
    Write-Host "  Project : $projectDir"  -ForegroundColor DarkGray
    Show-Badge
    nl
    dim "  /search  /run  /read  /scan  /git  /clip  /model  /compact  /export  /stats  /sessions  /quit"
    if (-not $isNew) {
        ok "  Resumed — $( ($history | Where-Object {$_.role -eq 'user'}).Count ) messages in context"
    }
    nl

    while ($true) {
        Write-Host "  You: " -ForegroundColor Green -NoNewline
        $input = (Read-Host).Trim()
        if (-not $input) { continue }

        if ($input.StartsWith("/")) {
            $parts = $input -split "\s+", 2
            $cmd   = $parts[0].ToLower()
            $arg   = if ($parts.Count -gt 1) { $parts[1].Trim() } else { "" }

            switch ($cmd) {
                "/quit" {
                    Save-Session $sessionFile $sessionName $projectDir $history $script:SessionFiles
                    nl; ok "  Saved. Goodbye."
                    return "quit"
                }
                "/sessions" {
                    Save-Session $sessionFile $sessionName $projectDir $history $script:SessionFiles
                    return "sessions"
                }
                "/save" {
                    Save-Session $sessionFile $sessionName $projectDir $history $script:SessionFiles
                    ok "  Saved."
                    continue
                }
                "/export" {
                    Export-Session $sessionName $projectDir $history
                    continue
                }
                "/files" {
                    if ($script:SessionFiles.Count -eq 0) { dim "  No files saved yet." }
                    else { $script:SessionFiles | ForEach-Object { ok "  $_" } }
                    continue
                }
                "/stats" {
                    $userMsgs = ($history | Where-Object {$_.role -eq "user"}).Count
                    $elapsed  = [math]::Round(((Get-Date) - $script:StartTime).TotalMinutes, 1)
                    $chars    = ($history | ForEach-Object { $_.content.Length } | Measure-Object -Sum).Sum
                    nl
                    Write-Host "  +-- Session Stats " + ("-" * 35) + "+" -ForegroundColor DarkCyan
                    Write-Host ("  | Messages   : {0,-40}|" -f $userMsgs)         -ForegroundColor White
                    Write-Host ("  | AI calls   : {0,-40}|" -f $script:CallCount) -ForegroundColor White
                    Write-Host ("  | ~Tokens    : {0,-40}|" -f [int]($chars/4))   -ForegroundColor White
                    Write-Host ("  | Elapsed    : {0} min{1,-35}|" -f $elapsed, "") -ForegroundColor White
                    Write-Host ("  | Files saved: {0,-40}|" -f $script:SessionFiles.Count) -ForegroundColor White
                    Write-Host ("  | Provider   : {0}/{1,-30}|" -f $script:Provider, $script:AiModel) -ForegroundColor White
                    Write-Host ("  +" + ("-" * 53) + "+") -ForegroundColor DarkCyan
                    nl
                    continue
                }
                "/model" {
                    nl
                    Write-Host "  Current: $script:Provider / $script:AiModel" -ForegroundColor White
                    nl
                    Write-Host "  groq:llama-3.3-70b-versatile   groq:mixtral-8x7b-32768" -ForegroundColor Cyan
                    Write-Host "  anthropic:claude-opus-4-7       anthropic:claude-sonnet-4-6" -ForegroundColor Magenta
                    Write-Host "  cerebras:llama-3.3-70b" -ForegroundColor Blue
                    nl
                    Write-Host "  Enter provider:model (or just model): " -ForegroundColor Yellow -NoNewline
                    $m = (Read-Host).Trim()
                    if ($m -match '^(\w+):(.+)$') { $script:Provider = $Matches[1]; $script:AiModel = $Matches[2] }
                    elseif ($m) { $script:AiModel = $m }
                    ok "  Now using: $script:Provider / $script:AiModel"
                    continue
                }
                "/search" {
                    if (-not $arg) { Write-Host "  Search: " -NoNewline; $arg = (Read-Host).Trim() }
                    warn "  Searching: $arg"
                    $sr = Search-Web $arg
                    dim $sr
                    nl
                    $history += @{ role="user"; content="[Web search: $arg]`n$sr`nUse these results." }
                    $reply = try { Ask-AI $history } catch { err "  Error: $_"; $history = $history[0..($history.Count-2)]; continue }
                    $history += @{ role="assistant"; content=$reply }
                    nl; hi "  AI:"; nl; Write-Host $reply; nl
                    Handle-CodeBlocks $reply $projectDir
                    Save-Session $sessionFile $sessionName $projectDir $history $script:SessionFiles
                    continue
                }
                "/run" {
                    $out = Run-File $arg $projectDir
                    if ($out) {
                        $history += @{ role="user"; content=$out }
                        $reply = try { Ask-AI $history } catch { err "  Error: $_"; $history = $history[0..($history.Count-2)]; continue }
                        $history += @{ role="assistant"; content=$reply }
                        nl; hi "  AI:"; nl; Write-Host $reply; nl
                        Handle-CodeBlocks $reply $projectDir
                        Save-Session $sessionFile $sessionName $projectDir $history $script:SessionFiles
                    }
                    continue
                }
                "/read" {
                    $p = if ($arg) { $arg } else { (Read-Host "  File path").Trim() }
                    if (-not [System.IO.Path]::IsPathRooted($p)) { $p = Join-Path $projectDir $p }
                    if (Test-Path $p) {
                        $history += @{ role="user"; content="File: $p`n``````n$(Get-Content $p -Raw -Encoding UTF8)`n``````" }
                        ok "  Loaded: $p"
                    } else { warn "  Not found: $p" }
                    continue
                }
                "/scan" {
                    warn "  Scanning project..."
                    $ctx = Get-ProjectContext $projectDir
                    $history += @{ role="user"; content="[Project scan]`n$ctx`nI've shared my project. Remember it." }
                    ok "  Project context loaded ($($ctx.Length) chars)."
                    continue
                }
                "/git" {
                    if (-not $arg) { Write-Host "  git command: " -NoNewline; $arg = (Read-Host).Trim() }
                    $out = Run-Git $arg $projectDir
                    if ($out) {
                        $history += @{ role="user"; content=$out }
                        $reply = try { Ask-AI $history } catch { err "  Error: $_"; $history = $history[0..($history.Count-2)]; continue }
                        $history += @{ role="assistant"; content=$reply }
                        nl; hi "  AI:"; nl; Write-Host $reply; nl
                        Handle-CodeBlocks $reply $projectDir
                        Save-Session $sessionFile $sessionName $projectDir $history $script:SessionFiles
                    }
                    continue
                }
                "/clip" {
                    try {
                        $clip = Get-Clipboard -EA Stop
                        if ($clip) {
                            $history += @{ role="user"; content="[Clipboard]`n$clip" }
                            ok "  Clipboard loaded ($($clip.Length) chars)."
                        } else { warn "  Clipboard is empty." }
                    } catch { warn "  Clipboard unavailable." }
                    continue
                }
                "/compact" {
                    $nonSys = @($history | Where-Object { $_.role -ne "system" })
                    if ($nonSys.Count -lt 16) { dim "  Context is small — no need to compact."; continue }
                    warn "  Summarizing conversation..."
                    $dump    = ($nonSys | ForEach-Object { "$($_.role): $($_.content.Substring(0,[Math]::Min(400,$_.content.Length)))" }) -join "`n"
                    $sumReq  = @(@{ role="user"; content="Summarize this conversation in 250 words, keeping all code decisions, file names, and current task state:`n$dump" })
                    $summary = try { Ask-AI $sumReq } catch { "Summary failed."; continue }
                    $sys     = @($history | Where-Object { $_.role -eq "system" } | Select-Object -First 1)
                    $history = $sys + @(@{ role="assistant"; content="[Summary of prior conversation: $summary]" })
                    ok "  Compacted. Context reduced."
                    continue
                }
                default {
                    warn "  Unknown command."
                    dim "  /search /run /read /scan /git /clip /model /compact /export /stats /sessions /quit"
                    continue
                }
            }
        }

        # ── Send to AI ────────────────────────────────────────────────────────
        $history += @{ role="user"; content=$input }
        nl

        $reply = try { Ask-AI $history } catch {
            err "  AI error: $_"
            $history = $history[0..($history.Count-2)]
            nl; continue
        }

        $history += @{ role="assistant"; content=$reply }

        # Keep system + last 50 non-system messages
        $sys    = @($history | Where-Object { $_.role -eq "system" })
        $nonSys = @($history | Where-Object { $_.role -ne "system" })
        if ($nonSys.Count -gt 50) {
            $history = $sys + $nonSys[($nonSys.Count-50)..($nonSys.Count-1)]
        }

        nl; hi "  AI:"; nl
        Write-Host $reply
        nl

        Handle-CodeBlocks $reply $projectDir
        Save-Session $sessionFile $sessionName $projectDir $history $script:SessionFiles
    }
}

# ── Boot ──────────────────────────────────────────────────────────────────────
if (-not (Initialize-Providers)) { Show-KeyWizard }

# ── Main loop ─────────────────────────────────────────────────────────────────
while ($true) {
    $result = Show-SessionList
    $r = switch ($result.action) {
        "new"    { Start-Chat }
        "resume" { Start-Chat -sessionFile $result.file }
        "list"   { "sessions" }
    }
    if ($r -eq "quit") { break }
}
