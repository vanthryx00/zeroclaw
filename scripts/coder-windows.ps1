# ============================================================
#  ZEROCLAW CODER
#  Online / offline / private AI coding partner
#
#  - Conversation list: every session saved, pick up anytime
#  - Online:  Groq, Anthropic, Cerebras, SambaNova (free)
#  - Offline: Ollama (auto-installs, no internet after setup)
#  - Private: all history stays on YOUR machine only
#
#  HOW TO RUN (PowerShell as Administrator):
#    Set-ExecutionPolicy Bypass -Scope Process -Force
#    iex (irm "https://raw.githubusercontent.com/vanthryx00/zeroclaw/claude/zeroclaw-api-optimization-TQH0u/scripts/coder-windows.ps1")
#
#  FREE API KEYS — setx then open new terminal:
#    setx GROQ_API_KEY      your-key   # console.groq.com
#    setx ANTHROPIC_API_KEY your-key   # console.anthropic.com
#    setx CEREBRAS_API_KEY  your-key   # cloud.cerebras.ai
#
#  COMMANDS DURING CHAT:
#    /search <query>   search the web
#    /read   <file>    load a file into context
#    /files            list files built this session
#    /save             save session now
#    /sessions         go back to session list
#    /quit             exit
# ============================================================

Set-StrictMode -Off
$ErrorActionPreference = "Continue"
$ProgressPreference    = "SilentlyContinue"

# ── Paths ─────────────────────────────────────────────────────────────────────
$WS       = "$env:USERPROFILE\zeroclaw-projects"
$Sessions = "$WS\.sessions"
foreach ($d in @($WS, $Sessions)) { New-Item -ItemType Directory $d -Force | Out-Null }

# ── Colors ────────────────────────────────────────────────────────────────────
function hi   { param([string]$t) Write-Host $t -ForegroundColor Cyan }
function ok   { param([string]$t) Write-Host $t -ForegroundColor Green }
function dim  { param([string]$t) Write-Host $t -ForegroundColor DarkGray }
function warn { param([string]$t) Write-Host $t -ForegroundColor Yellow }
function bold { param([string]$t) Write-Host $t -ForegroundColor White }

# ── Provider setup ────────────────────────────────────────────────────────────
$Provider = "none"; $ApiKey = ""; $AiModel = ""

if     ($env:GROQ_API_KEY)      { $Provider="groq";      $ApiKey=$env:GROQ_API_KEY;      $AiModel="llama-3.3-70b-versatile" }
elseif ($env:ANTHROPIC_API_KEY) { $Provider="anthropic"; $ApiKey=$env:ANTHROPIC_API_KEY; $AiModel="claude-opus-4-7" }
elseif ($env:CEREBRAS_API_KEY)  { $Provider="cerebras";  $ApiKey=$env:CEREBRAS_API_KEY;  $AiModel="llama-3.3-70b" }
elseif ($env:SAMBANOVA_API_KEY) { $Provider="sambanova"; $ApiKey=$env:SAMBANOVA_API_KEY; $AiModel="Meta-Llama-3.3-70B-Instruct" }
else {
    warn "No API key found — setting up Ollama for offline use..."
    if (-not (Get-Command ollama -EA SilentlyContinue)) {
        warn "Downloading Ollama installer..."
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
            try { if ((Invoke-WebRequest "http://localhost:11434/api/version" -UseBasicParsing -EA Stop).StatusCode -eq 200) { break } } catch {}
        }
    }
    $m = "qwen2.5-coder:7b"
    if ((& ollama list 2>$null) -notlike "*qwen2.5-coder*") {
        warn "Pulling $m (~4 GB, one-time)..."
        & ollama pull $m
    }
    $Provider="ollama"; $AiModel=$m
}

# ── AI call ───────────────────────────────────────────────────────────────────
function Ask-AI {
    param([array]$history)
    switch ($Provider) {
        "anthropic" {
            $sys  = ($history | Where-Object { $_.role -eq "system" } | Select-Object -Last 1).content
            $msgs = $history | Where-Object { $_.role -ne "system" }
            $body = @{ model=$AiModel; max_tokens=8192; thinking=@{type="adaptive"}; system=$sys; messages=$msgs } | ConvertTo-Json -Depth 20
            $r = Invoke-RestMethod "https://api.anthropic.com/v1/messages" -Method POST `
                -Headers @{"x-api-key"=$ApiKey;"anthropic-version"="2023-06-01";"content-type"="application/json"} -Body $body
            return ($r.content | Where-Object { $_.type -eq "text" } | Select-Object -First 1).text
        }
        { $_ -in "groq","cerebras","sambanova" } {
            $urls = @{ groq="https://api.groq.com/openai/v1/chat/completions"; cerebras="https://api.cerebras.ai/v1/chat/completions"; sambanova="https://api.sambanova.ai/v1/chat/completions" }
            $body = @{ model=$AiModel; messages=$history; max_tokens=8192 } | ConvertTo-Json -Depth 20
            $r = Invoke-RestMethod $urls[$Provider] -Method POST `
                -Headers @{ Authorization="Bearer $ApiKey"; "Content-Type"="application/json" } -Body $body
            return $r.choices[0].message.content
        }
        "ollama" {
            $body = @{ model=$AiModel; messages=$history; stream=$false } | ConvertTo-Json -Depth 20
            $r = Invoke-RestMethod "http://localhost:11434/api/chat" -Method POST -ContentType "application/json" -Body $body
            return $r.message.content
        }
    }
}

# ── Web search ────────────────────────────────────────────────────────────────
function Search-Web {
    param([string]$query)
    try {
        $enc  = [System.Uri]::EscapeDataString($query)
        $r    = Invoke-RestMethod "https://api.duckduckgo.com/?q=$enc&format=json&no_redirect=1&no_html=1" -UseBasicParsing -EA Stop
        $parts = @()
        if ($r.AbstractText) { $parts += $r.AbstractText }
        if ($r.Answer)       { $parts += $r.Answer }
        $r.RelatedTopics | Select-Object -First 5 | ForEach-Object { if ($_.Text) { $parts += "- " + $_.Text } }
        if ($parts.Count -eq 0) {
            $html   = (Invoke-WebRequest "https://html.duckduckgo.com/html/?q=$enc" -UseBasicParsing -EA Stop).Content
            $parts  = [regex]::Matches($html, '<a class="result__snippet"[^>]*>([^<]+)') | Select-Object -First 5 | ForEach-Object { "- " + $_.Groups[1].Value.Trim() }
        }
        return "Search: '$query'`n" + ($parts -join "`n")
    } catch { return "Search failed: $_" }
}

# ── Code block saver ──────────────────────────────────────────────────────────
function Save-CodeBlocks {
    param([string]$response, [string]$projectDir)
    [regex]::Matches($response, '```(?:(\w+)\n)?([\s\S]*?)```') | ForEach-Object {
        $lang = $_.Groups[1].Value
        $code = $_.Groups[2].Value.Trim()
        if ($code.Length -lt 10) { return }
        Write-Host ""
        Write-Host "─── Code ($lang) ─────────────────────────────" -ForegroundColor DarkCyan
        $lines = $code.Split("`n")
        $lines | Select-Object -First 25 | ForEach-Object { Write-Host $_ }
        if ($lines.Count -gt 25) { dim "  ... ($($lines.Count - 25) more lines)" }
        Write-Host "──────────────────────────────────────────────" -ForegroundColor DarkCyan
        $f = Read-Host "  Save as (e.g. app.py) or Enter to skip"
        if ($f) {
            $dest = Join-Path $projectDir $f
            New-Item -ItemType Directory (Split-Path $dest) -Force | Out-Null
            Set-Content $dest $code -Encoding UTF8
            ok "  Saved: $dest"
            $script:SessionFiles += $dest
        }
    }
}

# ── Session persistence ───────────────────────────────────────────────────────
function Save-Session {
    param([string]$sessionFile, [string]$name, [string]$project, [array]$history, [array]$files)
    $data = @{
        name    = $name
        project = $project
        saved   = (Get-Date -Format "o")
        files   = $files
        history = $history
    }
    $data | ConvertTo-Json -Depth 20 | Set-Content $sessionFile -Encoding UTF8
}

function Load-Session {
    param([string]$sessionFile)
    $data = Get-Content $sessionFile -Raw | ConvertFrom-Json
    return $data
}

function Get-Sessions {
    Get-ChildItem "$Sessions\*.json" -EA SilentlyContinue | Sort-Object LastWriteTime -Descending
}

function Format-TimeAgo {
    param([datetime]$dt)
    $diff = (Get-Date) - $dt
    if     ($diff.TotalMinutes -lt 1)  { return "just now" }
    elseif ($diff.TotalHours   -lt 1)  { return "$([int]$diff.TotalMinutes)m ago" }
    elseif ($diff.TotalDays    -lt 1)  { return "$([int]$diff.TotalHours)h ago" }
    elseif ($diff.TotalDays    -lt 7)  { return "$([int]$diff.TotalDays)d ago" }
    else                               { return $dt.ToString("MMM dd") }
}

# ── Session list screen ───────────────────────────────────────────────────────
function Show-SessionList {
    Clear-Host
    hi "╔══════════════════════════════════════════════════╗"
    hi "║   ZEROCLAW CODER  —  private AI coding partner  ║"
    hi "╚══════════════════════════════════════════════════╝"
    Write-Host "  Provider : $Provider / $AiModel" -ForegroundColor White
    Write-Host "  Storage  : $Sessions" -ForegroundColor DarkGray
    Write-Host ""

    $files = Get-Sessions
    if ($files.Count -eq 0) {
        dim "  No past sessions yet."
    } else {
        bold "  Past conversations:"
        Write-Host ""
        $i = 1
        foreach ($f in $files) {
            try {
                $d     = Get-Content $f.FullName -Raw | ConvertFrom-Json
                $msgs  = ($d.history | Where-Object { $_.role -eq "user" }).Count
                $ago   = Format-TimeAgo $f.LastWriteTime
                Write-Host ("  {0,2}.  {1,-32} {2,4} msgs   {3}" -f $i, $d.name, $msgs, $ago) -ForegroundColor White
            } catch {
                Write-Host ("  {0,2}.  {1}" -f $i, $f.Name) -ForegroundColor White
            }
            $i++
        }
    }

    Write-Host ""
    bold "   N.  New conversation"
    Write-Host ""
    $choice = Read-Host "  Pick a number or N"
    return @{ files=$files; choice=$choice }
}

# ── Main program loop ─────────────────────────────────────────────────────────
function Start-Chat {
    param([string]$sessionFile = "", [string]$sessionName = "", [string]$projectDir = "")

    $SessionFiles = @()
    $History      = @()
    $isNew        = $true

    if ($sessionFile -and (Test-Path $sessionFile)) {
        # Resume existing session
        $data         = Load-Session $sessionFile
        $sessionName  = $data.name
        $projectDir   = $data.project
        $SessionFiles = @($data.files)
        # Rebuild history array from saved data
        $History = $data.history | ForEach-Object { @{ role=$_.role; content=$_.content } }
        $isNew   = $false
        ok "Resumed: $sessionName"
    } else {
        # New session
        if (-not $sessionName) {
            Write-Host ""
            Write-Host "  Session name (e.g. 'discord bot', 'my portfolio'): " -ForegroundColor Cyan -NoNewline
            $sessionName = Read-Host
            if (-not $sessionName) { $sessionName = "session-$(Get-Date -Format yyyyMMdd-HHmm)" }
        }
        $slug       = ($sessionName -replace '[^\w]','-').ToLower()
        $projectDir = "$WS\$slug"
        New-Item -ItemType Directory $projectDir -Force | Out-Null
        $sessionFile = "$Sessions\$(Get-Date -Format yyyyMMdd-HHmmss)-$slug.json"

        $sysPrompt = "You are an expert software engineer and coding partner. The user is building real software.

Rules:
- Write COMPLETE working code. No TODOs, no placeholder stubs in the main path.
- Always wrap code in fenced blocks with the language tag (```python, ```js, etc).
- After writing code explain briefly what it does and what the next step is.
- If web search results are provided, use them.
- If a file is shared, read it and incorporate it.
- Be direct and keep momentum going.
- Remember everything from this conversation.

Project: $sessionName
Files go in: $projectDir"

        $History = @(@{ role="system"; content=$sysPrompt })
    }

    Clear-Host
    hi "╔══════════════════════════════════════════════════╗"
    hi "║   ZEROCLAW CODER                                 ║"
    hi "╚══════════════════════════════════════════════════╝"
    Write-Host "  Session  : $sessionName" -ForegroundColor White
    Write-Host "  Project  : $projectDir"  -ForegroundColor White
    Write-Host "  Provider : $Provider / $AiModel" -ForegroundColor DarkGray
    Write-Host ""
    dim "  /search <q>  /read <file>  /files  /save  /sessions  /quit"
    if (-not $isNew) {
        $userMsgs = ($History | Where-Object { $_.role -eq "user" }).Count
        dim "  Loaded $userMsgs past messages. Keep going where you left off."
    }
    Write-Host ""

    while ($true) {
        Write-Host "You: " -ForegroundColor Green -NoNewline
        $userInput = Read-Host
        if (-not $userInput.Trim()) { continue }

        # ── Slash commands ────────────────────────────────────────────────────
        if ($userInput.StartsWith("/")) {
            $parts = $userInput -split "\s+", 2
            $cmd   = $parts[0].ToLower()
            $arg   = if ($parts.Count -gt 1) { $parts[1] } else { "" }

            switch ($cmd) {
                "/quit" {
                    Save-Session $sessionFile $sessionName $projectDir $History $SessionFiles
                    Write-Host ""
                    ok "Saved. Goodbye."
                    return "quit"
                }
                "/sessions" {
                    Save-Session $sessionFile $sessionName $projectDir $History $SessionFiles
                    ok "Saved. Going to session list..."
                    return "sessions"
                }
                "/save" {
                    Save-Session $sessionFile $sessionName $projectDir $History $SessionFiles
                    ok "Session saved."
                    continue
                }
                "/files" {
                    if ($SessionFiles.Count -eq 0) { dim "No files saved yet." }
                    else { $SessionFiles | ForEach-Object { ok "  $_" } }
                    continue
                }
                "/search" {
                    if (-not $arg) { $arg = Read-Host "Search for" }
                    warn "Searching: $arg ..."
                    $sr = Search-Web $arg
                    dim $sr
                    $History += @{ role="user"; content="[Web search: $arg]`n$sr`nUse these results to help." }
                    Write-Host ""; warn "Thinking..."
                    $reply = Ask-AI $History
                    $History += @{ role="assistant"; content=$reply }
                    Write-Host "`r             `r" -NoNewline
                    Write-Host ""; hi "AI:"; Write-Host $reply; Write-Host ""
                    Save-CodeBlocks $reply $projectDir
                    Save-Session $sessionFile $sessionName $projectDir $History $SessionFiles
                    continue
                }
                "/read" {
                    $p = if ($arg) { $arg } else { Read-Host "File path" }
                    if (-not (Test-Path $p)) { $p = Join-Path $projectDir $p }
                    if (Test-Path $p) {
                        $fc = "File: $p`n``````n" + (Get-Content $p -Raw -Encoding UTF8) + "`n``````"
                        $History += @{ role="user"; content=$fc }
                        ok "Loaded: $p"
                    } else { warn "Not found: $p" }
                    continue
                }
                default { warn "Unknown command. Try /search /read /files /save /sessions /quit"; continue }
            }
        }

        # ── Send to AI ────────────────────────────────────────────────────────
        $History += @{ role="user"; content=$userInput }
        Write-Host ""; warn "Thinking..."

        try {
            $reply = Ask-AI $History
        } catch {
            warn "Error calling AI: $_"
            $History = $History[0..($History.Count - 2)]
            continue
        }

        Write-Host "`r             `r" -NoNewline
        Write-Host ""; hi "AI:"
        Write-Host $reply
        Write-Host ""

        $History += @{ role="assistant"; content=$reply }

        # Keep last 40 messages + system prompt to avoid token overflow
        if ($History.Count -gt 42) {
            $History = @($History[0]) + $History[($History.Count - 40)..($History.Count - 1)]
        }

        Save-CodeBlocks $reply $projectDir
        Save-Session $sessionFile $sessionName $projectDir $History $SessionFiles
    }
}

# ── Entry point: session list loop ────────────────────────────────────────────
while ($true) {
    $result = Show-SessionList
    $files  = $result.files
    $choice = $result.choice

    if ($choice -match '^\d+$') {
        $idx = [int]$choice - 1
        if ($idx -ge 0 -and $idx -lt $files.Count) {
            $action = Start-Chat -sessionFile $files[$idx].FullName
            if ($action -eq "quit") { break }
            # else "sessions" — loop back to list
            continue
        }
    }

    # N or anything else = new session
    $action = Start-Chat
    if ($action -eq "quit") { break }
}
