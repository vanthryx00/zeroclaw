# ============================================================
#  ZEROCLAW CODER — AI coding partner, online + offline
#  Paste into PowerShell and press Enter.
#
#  Works like Claude Code: you talk, it builds with you.
#  Writes real files. Searches the web. Remembers your project.
#
#  Commands during chat:
#    /search <query>     search the web for anything
#    /read   <file>      load a file into the conversation
#    /files              list files created this session
#    /new    <name>      start a new project folder
#    /clear              clear conversation (keep project)
#    /quit               exit
#
#  Free API keys (setx, then open a new terminal):
#    setx GROQ_API_KEY      your-key   # console.groq.com  (fastest)
#    setx CEREBRAS_API_KEY  your-key   # cloud.cerebras.ai
#    setx ANTHROPIC_API_KEY your-key   # console.anthropic.com
# ============================================================

Set-StrictMode -Off
$ErrorActionPreference = "Continue"
$ProgressPreference    = "SilentlyContinue"

# ── Workspace ─────────────────────────────────────────────────────────────────
$WS = "$env:USERPROFILE\zeroclaw-projects"
New-Item -ItemType Directory -Path $WS -Force | Out-Null

# ── Colors ────────────────────────────────────────────────────────────────────
function hi   { param([string]$t) Write-Host $t -ForegroundColor Cyan }
function ok   { param([string]$t) Write-Host $t -ForegroundColor Green }
function dim  { param([string]$t) Write-Host $t -ForegroundColor DarkGray }
function warn { param([string]$t) Write-Host $t -ForegroundColor Yellow }

# ── Provider setup ────────────────────────────────────────────────────────────
$Provider = "none"; $ApiKey = ""; $AiModel = ""

if     ($env:GROQ_API_KEY)      { $Provider="groq";      $ApiKey=$env:GROQ_API_KEY;      $AiModel="llama-3.3-70b-versatile"       }
elseif ($env:ANTHROPIC_API_KEY) { $Provider="anthropic"; $ApiKey=$env:ANTHROPIC_API_KEY; $AiModel="claude-opus-4-7"              }
elseif ($env:CEREBRAS_API_KEY)  { $Provider="cerebras";  $ApiKey=$env:CEREBRAS_API_KEY;  $AiModel="llama-3.3-70b"               }
elseif ($env:SAMBANOVA_API_KEY) { $Provider="sambanova"; $ApiKey=$env:SAMBANOVA_API_KEY; $AiModel="Meta-Llama-3.3-70B-Instruct" }
else {
    warn "No API key — installing Ollama (offline mode)..."
    if (-not (Get-Command ollama -EA SilentlyContinue)) {
        warn "Downloading Ollama..."
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
        warn "Pulling $m (~4 GB, one-time download)..."
        & ollama pull $m
    }
    $Provider="ollama"; $AiModel=$m
}

# ── Core AI call (full conversation history) ──────────────────────────────────
function Ask-AI {
    param([array]$history)   # array of @{role=...; content=...}

    switch ($Provider) {
        "anthropic" {
            # Pull system message out, rest are messages
            $sys  = ($history | Where-Object { $_.role -eq "system" } | Select-Object -Last 1).content
            $msgs = $history | Where-Object { $_.role -ne "system" }
            $body = @{
                model      = $AiModel
                max_tokens = 8192
                thinking   = @{type="adaptive"}
                system     = $sys
                messages   = $msgs
            } | ConvertTo-Json -Depth 20
            $r = Invoke-RestMethod "https://api.anthropic.com/v1/messages" -Method POST `
                -Headers @{"x-api-key"=$ApiKey;"anthropic-version"="2023-06-01";"content-type"="application/json"} `
                -Body $body
            return ($r.content | Where-Object { $_.type -eq "text" } | Select-Object -First 1).text
        }
        { $_ -in "groq","cerebras","sambanova" } {
            $urls = @{groq="https://api.groq.com/openai/v1/chat/completions";cerebras="https://api.cerebras.ai/v1/chat/completions";sambanova="https://api.sambanova.ai/v1/chat/completions"}
            $body = @{model=$AiModel; messages=$history; max_tokens=8192} | ConvertTo-Json -Depth 20
            $r = Invoke-RestMethod $urls[$Provider] -Method POST `
                -Headers @{Authorization="Bearer $ApiKey";"Content-Type"="application/json"} -Body $body
            return $r.choices[0].message.content
        }
        "ollama" {
            $body = @{model=$AiModel; messages=$history; stream=$false} | ConvertTo-Json -Depth 20
            $r = Invoke-RestMethod "http://localhost:11434/api/chat" -Method POST -ContentType "application/json" -Body $body
            return $r.message.content
        }
    }
}

# ── Web search via DuckDuckGo (no key needed) ─────────────────────────────────
function Search-Web {
    param([string]$query)
    try {
        $enc = [System.Uri]::EscapeDataString($query)
        # DuckDuckGo instant answers
        $r = Invoke-RestMethod "https://api.duckduckgo.com/?q=$enc&format=json&no_redirect=1&no_html=1" -UseBasicParsing -EA Stop
        $parts = @()
        if ($r.AbstractText)  { $parts += $r.AbstractText }
        if ($r.Answer)        { $parts += $r.Answer }
        foreach ($t in ($r.RelatedTopics | Select-Object -First 5)) {
            if ($t.Text) { $parts += "- " + $t.Text }
        }
        if ($parts.Count -eq 0) {
            # Fallback: scrape first result snippet from HTML
            $html = (Invoke-WebRequest "https://html.duckduckgo.com/html/?q=$enc" -UseBasicParsing -EA Stop).Content
            $matches2 = [regex]::Matches($html, '<a class="result__snippet"[^>]*>([^<]+)')
            $parts = $matches2 | Select-Object -First 5 | ForEach-Object { "- " + $_.Groups[1].Value.Trim() }
        }
        return "Web search results for '$query':`n" + ($parts -join "`n")
    } catch {
        return "Web search failed: $_"
    }
}

# ── Read a file ───────────────────────────────────────────────────────────────
function Read-FileIntoContext {
    param([string]$path)
    if (-not $path) { $path = Read-Host "File path" }
    if (-not (Test-Path $path)) {
        # Try relative to project dir
        $path = Join-Path $ProjectDir $path
    }
    if (Test-Path $path) {
        $content = Get-Content $path -Raw -Encoding UTF8
        return "Contents of $path`:`n``````n$content`n``````"
    }
    return "File not found: $path"
}

# ── Extract and save code blocks from AI response ─────────────────────────────
function Extract-And-Save {
    param([string]$response, [string]$projectDir)

    # Find all fenced code blocks: ```lang\ncode\n```
    $pattern = '```(?:(\w+)\n)?([\s\S]*?)```'
    $matches2 = [regex]::Matches($response, $pattern)

    foreach ($m in $matches2) {
        $lang = $m.Groups[1].Value
        $code = $m.Groups[2].Value.Trim()
        if ($code.Length -lt 10) { continue }   # skip tiny snippets

        Write-Host ""
        Write-Host "─── Code block ($lang) ───────────────────────" -ForegroundColor DarkCyan
        Write-Host ($code | Select-Object -First 20 | Out-String).TrimEnd()
        if ($code.Split("`n").Count -gt 20) { dim "  ... ($(($code.Split("`n").Count - 20)) more lines)" }
        Write-Host "──────────────────────────────────────────────" -ForegroundColor DarkCyan

        $filename = Read-Host "  💾 Save as (e.g. app.py) or Enter to skip"
        if ($filename) {
            $dest = Join-Path $projectDir $filename
            New-Item -ItemType Directory -Path (Split-Path $dest) -Force | Out-Null
            Set-Content -Path $dest -Value $code -Encoding UTF8
            ok "  ✓ Saved: $dest"
            $script:SessionFiles += $dest
        }
    }
}

# ── Session state ─────────────────────────────────────────────────────────────
$ProjectName  = "project"
$ProjectDir   = "$WS\$ProjectName"
New-Item -ItemType Directory -Path $ProjectDir -Force | Out-Null
$SessionFiles = @()

$SystemPrompt = "You are an expert software engineer and coding partner. The user is building software and needs your help writing real, working code.

Rules:
- Write COMPLETE, working code. No placeholder comments, no TODOs in the main path.
- When writing code always use fenced code blocks with the language tag (e.g. \`\`\`python).
- After writing code, briefly explain what it does and what to do next.
- If the user asks you to search the web, you will receive search results — use them.
- If the user shares file contents, incorporate them into your understanding.
- Be direct. Don't over-explain. Keep momentum going.
- Always suggest the next logical step after completing something.

Project folder: $ProjectDir
Files created so far will be listed in the conversation."

$History = @(@{role="system"; content=$SystemPrompt})

# ── Header ────────────────────────────────────────────────────────────────────
Clear-Host
hi "╔══════════════════════════════════════════╗"
hi "║   ZEROCLAW CODER  —  AI coding partner  ║"
hi "╚══════════════════════════════════════════╝"
Write-Host "  Provider : $Provider / $AiModel" -ForegroundColor White
Write-Host "  Project  : $ProjectDir"           -ForegroundColor White
Write-Host ""
dim "  Commands: /search <query>  /read <file>  /files  /new <name>  /clear  /quit"
dim "  Just talk to start coding. Tell it what you want to build."
Write-Host ""

# ── Main chat loop ────────────────────────────────────────────────────────────
while ($true) {
    # Prompt
    Write-Host "You: " -ForegroundColor Green -NoNewline
    $input = Read-Host

    if (-not $input.Trim()) { continue }

    # ── Slash commands ────────────────────────────────────────────────────────
    if ($input.StartsWith("/")) {
        $parts = $input -split "\s+", 2
        $cmd   = $parts[0].ToLower()
        $arg   = if ($parts.Count -gt 1) { $parts[1] } else { "" }

        switch ($cmd) {
            "/quit" {
                Write-Host ""
                ok "Session ended. Your files are in: $ProjectDir"
                if ($SessionFiles.Count -gt 0) {
                    dim "Files created this session:"
                    $SessionFiles | ForEach-Object { dim "  $_" }
                }
                exit
            }
            "/files" {
                if ($SessionFiles.Count -eq 0) { dim "No files saved yet this session." }
                else { $SessionFiles | ForEach-Object { ok "  $_" } }
                continue
            }
            "/clear" {
                $History = @(@{role="system"; content=$SystemPrompt})
                warn "Conversation cleared (project and files kept)."
                continue
            }
            "/new" {
                $ProjectName = if ($arg) { $arg } else { Read-Host "Project name" }
                $ProjectDir  = "$WS\$ProjectName"
                New-Item -ItemType Directory -Path $ProjectDir -Force | Out-Null
                $SystemPrompt = $SystemPrompt -replace "Project folder:.*", "Project folder: $ProjectDir"
                $History = @(@{role="system"; content=$SystemPrompt})
                $SessionFiles = @()
                ok "Started project: $ProjectDir"
                continue
            }
            "/search" {
                if (-not $arg) { $arg = Read-Host "Search query" }
                warn "Searching: $arg ..."
                $searchResult = Search-Web $arg
                dim $searchResult
                # Feed into conversation
                $History += @{role="user"; content="[Web search for: $arg]`n$searchResult`n`nNow use these results to help me."}
                $reply = Ask-AI $History
                $History += @{role="assistant"; content=$reply}
                Write-Host ""
                Write-Host $reply
                Extract-And-Save $reply $ProjectDir
                continue
            }
            "/read" {
                $fileContent = Read-FileIntoContext $arg
                dim $fileContent
                $History += @{role="user"; content=$fileContent}
                ok "File loaded into conversation."
                continue
            }
            default {
                warn "Unknown command: $cmd"
                continue
            }
        }
    }

    # ── Regular message — send to AI ──────────────────────────────────────────
    $History += @{role="user"; content=$input}

    Write-Host ""
    Write-Host "AI: " -ForegroundColor Cyan -NoNewline
    warn "(thinking...)"

    try {
        $reply = Ask-AI $History
    } catch {
        warn "Error: $_"
        $History = $History[0..($History.Count-2)]   # remove failed user message
        continue
    }

    # Clear the "thinking" line and print reply
    Write-Host "`r    `r" -NoNewline
    Write-Host ""
    Write-Host "AI: " -ForegroundColor Cyan
    Write-Host $reply
    Write-Host ""

    # Add to history
    $History += @{role="assistant"; content=$reply}

    # Trim history to last 20 exchanges (keep system prompt)
    if ($History.Count -gt 42) {
        $History = @($History[0]) + $History[($History.Count-40)..$History.Count]
    }

    # Offer to save any code blocks
    Extract-And-Save $reply $ProjectDir
}
