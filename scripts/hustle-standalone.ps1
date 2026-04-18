# ============================================================
#  ZEROCLAW HUSTLE — self-installing AI income accelerator
#  Copy this entire file, paste into PowerShell, press Enter.
#  No git clone. No compiler. No setup steps.
# ============================================================
#
#  What it does:
#    - Detects any free API key you already have
#    - If none: installs Ollama and runs 100% offline
#    - Menu: job intake, portfolio builder, job applications, income plan
#    - Saves every output to %USERPROFILE%\hustle-workspace\
#
#  To add a free API key (open new terminal after setx):
#    setx GROQ_API_KEY        your-key   # https://console.groq.com
#    setx CEREBRAS_API_KEY    your-key   # https://cloud.cerebras.ai
#    setx ANTHROPIC_API_KEY   your-key   # https://console.anthropic.com

Set-StrictMode -Off
$ErrorActionPreference = "Continue"
$ProgressPreference    = "SilentlyContinue"

# ── Workspace ─────────────────────────────────────────────────────────────────
$WS = "$env:USERPROFILE\hustle-workspace"
foreach ($d in @("$WS\jobs","$WS\portfolio","$WS\applications","$WS\plans")) {
    New-Item -ItemType Directory -Path $d -Force | Out-Null
}

# ── Colour helpers ────────────────────────────────────────────────────────────
function hi  { param([string]$t) Write-Host $t -ForegroundColor Cyan }
function ok  { param([string]$t) Write-Host "[ok]  $t" -ForegroundColor Green }
function bad { param([string]$t) Write-Host "[!!]  $t" -ForegroundColor Yellow }

# ── Saved settings ────────────────────────────────────────────────────────────
$cfg = "$WS\settings.txt"
$Rate   = 50
$Skills = "coding"
if (Test-Path $cfg) {
    Get-Content $cfg | ForEach-Object {
        if ($_ -match '^rate=(.+)')   { $Rate   = $Matches[1] }
        if ($_ -match '^skills=(.+)') { $Skills = $Matches[1] }
    }
}
function Save-Settings { Set-Content $cfg "rate=$Rate`nskills=$Skills" -Encoding UTF8 }

# ── AI provider detection & install ──────────────────────────────────────────
$Provider = "none"
$ApiKey   = ""
$Model    = ""

if ($env:GROQ_API_KEY) {
    $Provider = "groq";      $ApiKey = $env:GROQ_API_KEY
    $Model    = "llama-3.3-70b-versatile"
    ok "Provider: Groq (free)"
} elseif ($env:CEREBRAS_API_KEY) {
    $Provider = "cerebras";  $ApiKey = $env:CEREBRAS_API_KEY
    $Model    = "llama-3.3-70b"
    ok "Provider: Cerebras (free)"
} elseif ($env:ANTHROPIC_API_KEY) {
    $Provider = "anthropic"; $ApiKey = $env:ANTHROPIC_API_KEY
    $Model    = "claude-opus-4-7"
    ok "Provider: Anthropic (claude-opus-4-7)"
} elseif ($env:SAMBANOVA_API_KEY) {
    $Provider = "sambanova"; $ApiKey = $env:SAMBANOVA_API_KEY
    $Model    = "Meta-Llama-3.3-70B-Instruct"
    ok "Provider: SambaNova (free)"
} else {
    bad "No API key found — installing Ollama for offline use..."

    if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
        bad "Downloading Ollama installer..."
        $ins = "$env:TEMP\OllamaSetup.exe"
        Invoke-WebRequest "https://ollama.com/download/OllamaSetup.exe" -OutFile $ins -UseBasicParsing
        Start-Process $ins -ArgumentList "/S" -Wait
        Remove-Item $ins -Force -ErrorAction SilentlyContinue
        $env:PATH += ";$env:LOCALAPPDATA\Programs\Ollama"
    }

    # Start server
    if (-not (Get-Process ollama -ErrorAction SilentlyContinue)) {
        Start-Process ollama -ArgumentList "serve" -WindowStyle Hidden
        $ready = $false
        for ($i = 0; $i -lt 15; $i++) {
            Start-Sleep 2
            try {
                if ((Invoke-WebRequest "http://localhost:11434/api/version" -UseBasicParsing -EA Stop).StatusCode -eq 200) {
                    $ready = $true; break
                }
            } catch {}
        }
        if (-not $ready) { bad "Ollama server slow to start — continuing anyway" }
    }

    # Pull model
    $ollamaModel = "qwen2.5-coder:7b"
    $listed = & ollama list 2>$null
    if ($listed -notlike "*qwen2.5-coder*") {
        bad "Pulling $ollamaModel (~4 GB) — go make coffee..."
        & ollama pull $ollamaModel
    }

    $Provider = "ollama"
    $Model    = $ollamaModel
    ok "Provider: Ollama / $Model (offline, free)"
}

# ── Core AI call ──────────────────────────────────────────────────────────────
function Ask-AI {
    param([string]$prompt, [string]$system = "You are a senior software engineer and freelance consultant. Be direct, specific, and practical. Write complete working code when asked.")

    $msgs = @(
        @{role="system"; content=$system},
        @{role="user";   content=$prompt}
    )

    switch ($Provider) {

        "anthropic" {
            $body = @{
                model      = $Model
                max_tokens = 8192
                thinking   = @{type="adaptive"}
                system     = $system
                messages   = @(@{role="user"; content=$prompt})
            } | ConvertTo-Json -Depth 10
            $r = Invoke-RestMethod "https://api.anthropic.com/v1/messages" -Method POST `
                -Headers @{"x-api-key"=$ApiKey;"anthropic-version"="2023-06-01";"content-type"="application/json"} `
                -Body $body
            return ($r.content | Where-Object { $_.type -eq "text" } | Select-Object -First 1).text
        }

        "groq" {
            $body = @{model=$Model; messages=$msgs; max_tokens=8192} | ConvertTo-Json -Depth 10
            $r = Invoke-RestMethod "https://api.groq.com/openai/v1/chat/completions" -Method POST `
                -Headers @{Authorization="Bearer $ApiKey";"Content-Type"="application/json"} `
                -Body $body
            return $r.choices[0].message.content
        }

        "cerebras" {
            $body = @{model=$Model; messages=$msgs; max_tokens=8192} | ConvertTo-Json -Depth 10
            $r = Invoke-RestMethod "https://api.cerebras.ai/v1/chat/completions" -Method POST `
                -Headers @{Authorization="Bearer $ApiKey";"Content-Type"="application/json"} `
                -Body $body
            return $r.choices[0].message.content
        }

        "sambanova" {
            $body = @{model=$Model; messages=$msgs; max_tokens=8192} | ConvertTo-Json -Depth 10
            $r = Invoke-RestMethod "https://api.sambanova.ai/v1/chat/completions" -Method POST `
                -Headers @{Authorization="Bearer $ApiKey";"Content-Type"="application/json"} `
                -Body $body
            return $r.choices[0].message.content
        }

        "ollama" {
            $body = @{model=$Model; messages=$msgs; stream=$false} | ConvertTo-Json -Depth 10
            $r = Invoke-RestMethod "http://localhost:11434/api/chat" -Method POST `
                -ContentType "application/json" -Body $body
            return $r.message.content
        }
    }
}

function Save-And-Print {
    param([string]$path, [string]$content)
    Set-Content -Path $path -Value $content -Encoding UTF8
    Write-Host ""
    Write-Host $content
    Write-Host ""
    ok "Saved to: $path"
}

function Paste-Block {
    param([string]$label)
    Write-Host "$label (type END on its own line when done):" -ForegroundColor Cyan
    $lines = @()
    while ($true) { $l = Read-Host; if ($l -eq "END") { break }; $lines += $l }
    return $lines -join "`n"
}

# ── 1. Job intake ─────────────────────────────────────────────────────────────
function Do-Intake {
    hi "`n── Job Intake ──"
    $job = Paste-Block "Paste the job posting"
    $slug = "job-$(Get-Date -Format yyyyMMdd-HHmm)"
    $dir  = "$WS\jobs\$slug"
    New-Item -ItemType Directory $dir -Force | Out-Null

    ok "Analyzing..."
    $result = Ask-AI "Analyze this freelance job posting. My skills: $Skills. My rate: `$$Rate/hr.

JOB:
$job

Produce two sections:

## BRIEF
- List every deliverable (numbered)
- Hours estimate per deliverable
- Total cost at `$$Rate/hr
- Timeline
- Any red flags to clarify

## PROPOSAL (under 200 words, ready to paste)
- Open by showing you understand their exact problem
- Reference 1-2 specific skills from: $Skills
- Give clear price and timeline
- End with a direct call to action
- Zero generic phrases like 'passionate' or 'quick learner'"

    Save-And-Print "$dir\intake.md" $result
}

# ── 2. Portfolio project builder ──────────────────────────────────────────────
function Do-Build {
    hi "`n── Portfolio Builder ──"
    $type  = Read-Host "Project type (e.g. discord bot, web scraper, REST API, CLI tool)"
    $stack = Read-Host "Tech stack (e.g. Python, React, FastAPI) [Enter = auto-pick]"
    if (-not $stack) { $stack = "best fit for a $type project" }

    $slug = ($type -replace '\s+','-').ToLower() + "-$(Get-Date -Format yyyyMMdd)"
    $dir  = "$WS\portfolio\$slug"
    New-Item -ItemType Directory $dir -Force | Out-Null

    ok "Building $type in $stack..."
    $result = Ask-AI "Build a complete, impressive portfolio project. My skills: $Skills.

TYPE: $type
STACK: $stack
SAVE LOCATION (mention this in your response): $dir\

Rules — no exceptions:
1. Write ALL core functionality. Zero TODO stubs.
2. Real error handling with useful messages.
3. Write a README.md: what it does, 5-minute setup, 3 usage examples.
4. List all dependencies (requirements.txt / package.json / etc).
5. Include a .gitignore.
6. Add one memorable 'wow' feature — say what it is, then build it.
7. Code must look like a senior developer wrote it.

After the code, write:
## TO DEPLOY
Step by step to get this running locally.

## WHY THIS IMPRESSES
What a hiring manager or client sees that makes them want to hire me."

    Save-And-Print "$dir\project.md" $result
    ok "Add to GitHub: cd `"$dir`"; git init; git add .; git commit -m `"feat: $type`""
}

# ── 3. Job application package ────────────────────────────────────────────────
function Do-Apply {
    hi "`n── Job Application ──"
    $company = Read-Host "Company or role name"
    $job     = Paste-Block "Paste the full job description"

    $slug = ($company -replace '\s+','-').ToLower() + "-$(Get-Date -Format yyyyMMdd)"
    $dir  = "$WS\applications\$slug"
    New-Item -ItemType Directory $dir -Force | Out-Null
    $annual = [int]$Rate * 2000

    ok "Building application package..."
    $result = Ask-AI "Help me land this job. Build a complete application package.

JOB:
$job

MY SKILLS: $Skills
MY TARGET: `$$Rate/hr (~`$$annual/yr)

Write these sections:

## COVER LETTER
3 paragraphs:
1. One specific thing about this company that excites me (be specific, not generic)
2. My most relevant achievement — with a real number if possible
3. Confident close with availability

## RESUME BULLETS
8 bullet points to add to my resume:
- STAR format: Situation, Task, Action, Result
- Match their exact wording from the job description
- Quantify everything possible

## PORTFOLIO MAP
Which types of projects to highlight and the 30-second pitch for each

## SKILL GAPS
What they want that I'm missing — and the fastest way to close each gap

## INTERVIEW PREP
5 likely questions + strong answers. Include one about a failure or challenge."

    Save-And-Print "$dir\application.md" $result
}

# ── 4. Weekly income plan ─────────────────────────────────────────────────────
function Do-Plan {
    hi "`n── Weekly Income Plan ──"
    $current  = Read-Host "Current weekly income in USD [0]"
    $goal     = Read-Host "Weekly income goal in USD (e.g. 500, 1000, 2000)"
    $hours    = Read-Host "Hours available per week for hustle work"
    $blockers = Read-Host "Biggest blocker right now (Enter to skip)"

    if (-not $current)  { $current  = "0" }
    if (-not $goal)     { $goal     = "500" }
    if (-not $hours)    { $hours    = "20" }
    if (-not $blockers) { $blockers = "none mentioned" }

    $planFile = "$WS\plans\plan-$(Get-Date -Format yyyy-MM-dd).md"

    ok "Building your plan..."
    $result = Ask-AI "Build me a real, brutally honest weekly income plan. No motivational fluff.

MY SITUATION:
- Skills: $Skills
- Rate: `$$Rate/hour
- Current weekly income: `$$current
- Goal: `$$goal/week
- Available hours: $hours hrs/week
- Blockers: $blockers

Write these sections:

## GAP ANALYSIS
- Gap: `$$goal - `$$current per week
- Billable hours needed at `$$Rate/hr
- Most direct path to those hours — be specific

## TOP 5 ACTIONS THIS WEEK
Ranked by income impact. Each must be specific:
Not 'apply to jobs' — but 'search Upwork for Excel automation under `$50-100 budget, apply to 5 postings using this exact headline: ...'

## FREELANCE TARGETS
5 Upwork or Fiverr categories that match my skills:
- Category name
- Realistic rate
- Profile headline that wins
- What the top proposal says

## DAILY SCHEDULE
Given $hours hrs/week, show me day-by-day what to do and for how long

## QUICK WINS
1-2 things I can build or do in the next 48 hours that generate income or directly lead to it

## 3 OUTREACH MESSAGES
Ready-to-send LinkedIn or cold email messages. Specific to my skills.

## 30-DAY TARGET
One number. If I execute this plan, what weekly income am I hitting by day 30?

If `$$goal/week is not realistic in $hours hours at `$$Rate/hr, tell me what IS and why."

    Save-And-Print $planFile $result
}

# ── 5. Resume builder ─────────────────────────────────────────────────────────
function Do-Resume {
    hi "`n── Resume Builder ──"
    $exp  = Read-Host "Years of experience (or 0 if self-taught)"
    $edu  = Read-Host "Education (e.g. 'CS degree', 'self-taught', 'bootcamp')"
    $best = Read-Host "Your best project or thing you've built (describe it briefly)"
    $tgt  = Read-Host "Target role (e.g. 'Python developer', 'freelance automation', 'full-stack')"

    $resumeFile = "$WS\resume.md"
    ok "Building your resume..."
    $result = Ask-AI "Build a complete, professional resume for someone trying to break into paid work.

MY BACKGROUND:
- Skills: $Skills
- Experience: $exp years
- Education: $edu
- Best project/work: $best
- Target role: $tgt
- Target rate: `$$Rate/hr

Write a full resume in markdown with these sections:

## SUMMARY (3 sentences)
- What I do
- My strongest technical skill with a specific example
- What I'm looking for

## SKILLS
Group into categories (Languages, Frameworks, Tools, etc.)
List everything from: $Skills — and infer related skills a developer with these skills would have

## PROJECTS (3 entries, make them sound impressive)
For each: name, 1-line description, tech stack, 2-3 bullet points of what it does/achieved
If I mentioned a real project use it. Otherwise invent plausible ones based on my skills.

## EXPERIENCE
If $exp years > 0: write 1-2 experience entries with realistic bullet points
If self-taught/0: write a 'Freelance Projects' section instead

## EDUCATION
Based on: $edu

## CONTACT PLACEHOLDER
[Your Name] | [email] | [GitHub URL] | [LinkedIn URL]

After the resume write:
## WHAT TO FILL IN
Exactly which blanks I need to replace with real info"

    Save-And-Print $resumeFile $result
    ok "Resume saved. Edit $resumeFile to fill in your real name/email/links."
}

# ── 6. Freelance profile builder ──────────────────────────────────────────────
function Do-Profile {
    hi "`n── Freelance Profile Builder ──"
    $platform = Read-Host "Platform (upwork / fiverr / toptal / linkedin)"
    $niche    = Read-Host "Your niche (e.g. 'Python automation', 'React developer', 'data scraping')"

    $dir = "$WS\profiles"; New-Item -ItemType Directory $dir -Force | Out-Null
    $file = "$dir\$platform-$(Get-Date -Format yyyyMMdd).md"

    ok "Writing your $platform profile..."
    $result = Ask-AI "Write a complete, high-converting freelance profile for $platform.

MY SKILLS: $Skills
MY NICHE: $niche
MY RATE: `$$Rate/hr
PLATFORM: $platform

Write every section I need to fill in on $platform:

## HEADLINE / TITLE
3 options, ranked. Each under 70 chars. Use power words. Mention the niche and a result.

## PROFILE OVERVIEW / BIO (300-400 words)
- Hook: open with the client's pain point, not 'I am a developer'
- What I do and who I help
- How I work (process, communication, reliability)
- A specific result or project that proves I can deliver
- Clear call to action
Do NOT start with 'I'. Do NOT use phrases like 'passionate', 'hardworking', 'guru'.

## SKILLS TAGS
20 exact skill tags to add on $platform (match their autocomplete options)

## PORTFOLIO PIECE DESCRIPTIONS
3 project descriptions formatted for $platform portfolio section:
- Project title
- What the client needed
- What I built
- Result (use numbers where possible)

## HOURLY RATE STRATEGY
Given `$$Rate/hr target and my experience level, what should I charge to start, when to raise it, and how

## FIRST 5 PROPOSALS
The exact strategy for my first 5 bids: what job types to target, what to say, how to stand out with zero reviews"

    Save-And-Print $file $result
}

# ── 7. Fiverr gig generator ───────────────────────────────────────────────────
function Do-Gig {
    hi "`n── Fiverr Gig Generator ──"
    $service = Read-Host "What service will this gig offer? (e.g. 'Python web scraper', 'Discord bot', 'Excel automation')"

    $dir = "$WS\gigs"; New-Item -ItemType Directory $dir -Force | Out-Null
    $slug = ($service -replace '\s+','-').ToLower() + "-$(Get-Date -Format yyyyMMdd)"
    $file = "$dir\$slug.md"

    ok "Generating Fiverr gig..."
    $result = Ask-AI "Create a complete, high-ranking Fiverr gig for this service: $service
My skills: $Skills. My rate target: `$$Rate/hr.

## GIG TITLE (3 options)
Each under 80 chars. Include the main keyword. Focus on the result, not the technology.

## CATEGORY & SUBCATEGORY
Exact Fiverr category path to list this under

## SEARCH TAGS
5 tags (max 20 chars each) that buyers actually search for

## GIG DESCRIPTION (750-900 words)
Structure:
- Line 1: Bold statement of what the buyer gets (not who I am)
- What's included (bullet list)
- Why choose me (specific, not generic)
- My process (numbered steps, builds trust)
- FAQ (3 questions buyers actually ask)
- CTA: 'Message me before ordering so I can confirm I can help'

## PACKAGES (Basic / Standard / Premium)
For each: name, description, delivery time, revisions, price, what's included

## GIG IMAGES
3 image concepts that would make someone click (describe what to show, what text to overlay)

## FIRST WEEK STRATEGY
How to get the first order with zero reviews: pricing, promotion, buyer requests"

    Save-And-Print $file $result
}

# ── 8. Update settings ────────────────────────────────────────────────────────
function Do-Settings {
    hi "`n── Settings ──"
    $r = Read-Host "Hourly rate in USD [$Rate]"
    $s = Read-Host "Your skills (comma separated) [$Skills]"
    if ($r) { $Rate   = $r }
    if ($s) { $Skills = $s }
    Save-Settings
    ok "Saved. Rate: `$$Rate/hr | Skills: $Skills"
}

# ── Main menu loop ────────────────────────────────────────────────────────────
Write-Host ""
hi "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
hi "  HUSTLE MODE  —  AI income accelerator"
hi "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
Write-Host "  Provider : $Provider / $Model"
Write-Host "  Workspace: $WS"
Write-Host "  Rate     : `$$Rate/hr   Skills: $Skills"
Write-Host ""

while ($true) {
    Write-Host "  1.  Analyze a job posting + draft proposal"   -ForegroundColor White
    Write-Host "  2.  Build a portfolio project"                -ForegroundColor White
    Write-Host "  3.  Create a job application package"         -ForegroundColor White
    Write-Host "  4.  Weekly income action plan"                -ForegroundColor White
    Write-Host "  5.  Build your resume from scratch"           -ForegroundColor White
    Write-Host "  6.  Write your Upwork/Fiverr profile"         -ForegroundColor White
    Write-Host "  7.  Generate a Fiverr gig listing"            -ForegroundColor White
    Write-Host "  8.  Update skills + rate"                     -ForegroundColor DarkGray
    Write-Host "  9.  Exit"                                     -ForegroundColor DarkGray
    Write-Host ""
    $choice = Read-Host "Choice"

    switch ($choice) {
        "1" { Do-Intake }
        "2" { Do-Build }
        "3" { Do-Apply }
        "4" { Do-Plan }
        "5" { Do-Resume }
        "6" { Do-Profile }
        "7" { Do-Gig }
        "8" { Do-Settings }
        "9" { Write-Host "Good luck." -ForegroundColor Green; break }
        default { bad "Enter 1-9" }
    }
    if ($choice -eq "9") { break }
    Write-Host ""
}
