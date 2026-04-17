#Requires -Version 5.1
<#
.SYNOPSIS
    ZeroClaw Hustle Mode — free AI income accelerator for Windows
.DESCRIPTION
    Freelance intake, portfolio builder, job applications, weekly planning.
    All powered by free AI providers. Works offline via Ollama.
.EXAMPLE
    .\scripts\hustle-windows.ps1 setup
    .\scripts\hustle-windows.ps1 intake
    .\scripts\hustle-windows.ps1 intake https://www.upwork.com/jobs/~...
    .\scripts\hustle-windows.ps1 build "discord bot" "Python"
    .\scripts\hustle-windows.ps1 apply "Acme Corp"
    .\scripts\hustle-windows.ps1 plan
    .\scripts\hustle-windows.ps1 rate 75
#>

param(
    [Parameter(Position=0)][string]$Command  = "help",
    [Parameter(Position=1)][string]$Arg1     = "",
    [Parameter(Position=2)][string]$Arg2     = ""
)

$ErrorActionPreference = "Stop"

# ── Colors ────────────────────────────────────────────────────────────────────
function Write-Section { param([string]$t) Write-Host "`n━━  $t  ━━" -ForegroundColor Cyan }
function Write-Info    { param([string]$t) Write-Host "[hustle] $t" -ForegroundColor Green }
function Write-Note    { param([string]$t) Write-Host "[note]   $t" -ForegroundColor Yellow }
function Ask-User      { param([string]$t) Write-Host "?  $t`: " -ForegroundColor Cyan -NoNewline; Read-Host }

function Test-Cmd([string]$c) { $null -ne (Get-Command $c -ErrorAction SilentlyContinue) }

# ── Paths ─────────────────────────────────────────────────────────────────────
$Workspace   = if ($env:ZEROCLAW_WORKSPACE) { $env:ZEROCLAW_WORKSPACE } else { "$env:USERPROFILE\zeroclaw-workspace" }
$Projects    = "$Workspace\projects"
$ConfigDir   = if ($env:ZEROCLAW_CONFIG_DIR) { $env:ZEROCLAW_CONFIG_DIR } else { "$env:USERPROFILE\.zeroclaw" }
$HustleEnv   = "$ConfigDir\hustle.env"
$SkillsFile  = "$Workspace\skills.md"
$ResumeFile  = "$Workspace\resume.md"

foreach ($d in @("$Projects\portfolio","$Projects\freelance","$Projects\applications","$Projects\plans")) {
    New-Item -ItemType Directory -Path $d -Force | Out-Null
}

# Load persisted settings
$Rate   = 50
$Skills = ""
if (Test-Path $HustleEnv) {
    Get-Content $HustleEnv | ForEach-Object {
        if ($_ -match '^RATE=(.+)$')   { $Rate   = $Matches[1] }
        if ($_ -match '^SKILLS="?(.+?)"?$') { $Skills = $Matches[1] }
    }
}

# ── Helpers ───────────────────────────────────────────────────────────────────
function Require-ZeroClaw {
    if (-not (Test-Cmd "zeroclaw")) {
        Write-Error "zeroclaw not found. Run .\scripts\setup-windows.ps1 first."
        exit 1
    }
}

function Run-Agent([string]$prompt) {
    zeroclaw agent -m $prompt
}

function Read-Multiline([string]$label) {
    Write-Host $label -ForegroundColor Cyan
    Write-Host "(Paste text. Type END on its own line when done)" -ForegroundColor DarkGray
    $lines = @()
    while ($true) {
        $line = Read-Host
        if ($line -eq "END") { break }
        $lines += $line
    }
    return $lines -join "`n"
}

function Get-ResumeContext {
    if (Test-Path $ResumeFile) {
        return "My resume/background: " + (Get-Content $ResumeFile -Raw)
    }
    return "No resume file yet. Infer my background from skills: $Skills. Remind me to create $ResumeFile with my work history."
}

function Save-HustleEnv {
    Set-Content -Path $HustleEnv -Value "RATE=$Rate`nSKILLS=`"$Skills`"" -Encoding UTF8
}

# ── COMMAND: setup ────────────────────────────────────────────────────────────
function Invoke-Setup {
    Write-Section "Hustle Mode — First-Time Setup"

    $inputSkills = Ask-User "Your main skills (e.g. Python, React, SQL, automation, APIs)"
    if ($inputSkills) { $global:Skills = $inputSkills }

    $inputRate = Ask-User "Target hourly rate in USD [50]"
    if ($inputRate) { $global:Rate = [int]$inputRate }

    Save-HustleEnv

    Set-Content -Path $SkillsFile -Encoding UTF8 -Value @"
# Skills & Rate

**Hourly rate:** `$$Rate/hr
**Skills:** $Skills
**Workspace:** $Workspace
**Updated:** $(Get-Date -Format yyyy-MM-dd)

## Add these manually
- GitHub URL:
- Portfolio URL:
- Strongest project link:
- Years of experience:
"@

    Write-Info "Seeding ZeroClaw memory with your background..."
    Run-Agent "Store this permanently in your memory about me:
- Skills: $Skills
- Hourly rate: `$$Rate/hour
- Workspace: $Workspace
- Code goes in: $Projects\
- When I say 'save it', write files into the right subfolder under $Projects\
- Always write COMPLETE working code — no TODOs or skeletons in the main path.
- You are my income-generating partner. Be direct, practical, and specific."

    Write-Host ""
    Write-Info "Setup complete."
    Write-Info "Rate: `$$Rate/hr   Skills: $Skills"
    Write-Note "Optionally add your resume to $ResumeFile for better application packages."
    Write-Note "Next step: .\scripts\hustle-windows.ps1 plan"
}

# ── COMMAND: intake ───────────────────────────────────────────────────────────
function Invoke-Intake([string]$source) {
    Write-Section "Job Intake"
    Require-ZeroClaw

    $jobText = if ($source -match '^https?://') {
        Write-Info "Fetching: $source"
        "Fetch and analyze this job posting URL: $source"
    } else {
        Read-Multiline "Paste the job posting:"
    }

    $slug = "job-$(Get-Date -Format yyyyMMdd-HHmm)"
    $dest = "$Projects\freelance\$slug"

    Write-Info "Analyzing..."

    Run-Agent "I need to win this freelance job. Analyze it completely and help me respond.

JOB POSTING:
$jobText

MY SKILLS: $Skills
MY RATE: `$$Rate/hour

Do all of this and save results to $dest\:

1. BRIEF.md — full scope breakdown:
   - Every technical deliverable (numbered list)
   - Hours estimate per deliverable (realistic, not optimistic)
   - Total hours x `$$Rate = project price
   - Timeline in days
   - Red flags or scope creep risks to clarify upfront

2. PROPOSAL.md — winning proposal ready to copy-paste:
   - Under 200 words
   - First sentence: show I understand their exact problem
   - Middle: mention 1-2 specific skills from my background that directly apply
   - End: clear price, timeline, and confident call to action
   - Do NOT use generic phrases like 'I am passionate' or 'I am a quick learner'

3. STARTER\ — scaffold the project folder structure for the main tech they need

After saving, print the price to quote and the 3 sentences from PROPOSAL.md to lead with."

    Write-Info "Intake saved to $dest"
    Write-Note "Copy proposal: Get-Content $dest\PROPOSAL.md"
}

# ── COMMAND: build ────────────────────────────────────────────────────────────
function Invoke-Build([string]$type, [string]$stack) {
    Write-Section "Portfolio Project Builder"
    Require-ZeroClaw

    if (-not $type) { $type  = Ask-User "Project type (e.g. 'discord bot', 'web scraper', 'REST API', 'CLI tool')" }
    if (-not $stack) {
        $stack = Ask-User "Tech stack (e.g. 'Python', 'React + Node') [Enter = auto-pick]"
        if (-not $stack) { $stack = "whatever is the best fit for this project type" }
    }

    $slug = ($type -replace ' ','-').ToLower() + "-$(Get-Date -Format yyyyMMdd)"
    $dest = "$Projects\portfolio\$slug"

    Write-Info "Building: $type | Stack: $stack"
    Write-Info "Output: $dest"

    Run-Agent "Build me a complete portfolio project that will impress hiring managers and win freelance clients.

PROJECT TYPE: $type
TECH STACK: $stack
SAVE TO: $dest\
MY SKILLS: $Skills

Hard requirements — no excuses:
1. ALL core functionality must be implemented (zero TODO stubs in the main path)
2. Real error handling — catch failures, give useful messages
3. README.md with: what it does, why it matters, setup in under 5 minutes, 3 usage examples
4. requirements.txt / package.json / go.mod — all deps pinned to a version
5. .gitignore
6. Clean code: typed where the language supports it, consistent naming, no dead code
7. At least one 'wow' feature that makes it memorable — suggest it and build it

After building, tell me:
- What makes this impressive to someone hiring for $type roles
- 3 specific job titles that should see this in my portfolio
- GitHub repo description under 100 chars"

    Write-Info "Project saved to $dest"
    Write-Note "Push to GitHub:  cd $dest; git init; git add .; git commit -m 'feat: $type'; git push"
}

# ── COMMAND: apply ────────────────────────────────────────────────────────────
function Invoke-Apply([string]$company) {
    Write-Section "Job Application Package"
    Require-ZeroClaw

    if (-not $company) { $company = Ask-User "Company name or job title (for file naming)" }

    $slug = ($company -replace ' ','-').ToLower() + "-$(Get-Date -Format yyyyMMdd)"
    $dest = "$Projects\applications\$slug"

    $jobText  = Read-Multiline "Paste the full job description:"
    $annual   = [int]$Rate * 2000
    $resume   = Get-ResumeContext

    Write-Info "Building application package for: $company"

    Run-Agent "Help me land this job. Build a complete application package.

JOB DESCRIPTION:
$jobText

$resume
MY SKILLS: $Skills
RATE / SALARY TARGET: `$$Rate/hr = ~`$$annual/year

Save all files to $dest\ and create:

1. COVER_LETTER.md — 3 tight paragraphs, zero fluff:
   Para 1: One specific thing about this company that makes me want this role
   Para 2: My most directly relevant project or result — specific numbers if possible
   Para 3: Confident close, availability, next step

2. RESUME_BULLETS.md — 8 resume bullets to add or update:
   - STAR format: Situation, Task, Action, Result
   - Quantify with %, `$, users, speed, scale
   - Mirror their exact wording from the job description

3. PORTFOLIO_MAP.md — which projects to highlight and what to say in 30 seconds each

4. SKILL_GAPS.md — what they want that I'm missing:
   - Gap, fastest way to close it, specific resource

5. INTERVIEW_PREP.md — 5 likely questions + strong answers including one failure/challenge question

After saving, tell me the single most important thing to nail in this application."

    Write-Info "Application package saved to $dest"
    Write-Note "Review:  dir $dest"
}

# ── COMMAND: plan ─────────────────────────────────────────────────────────────
function Invoke-Plan {
    Write-Section "Weekly Income Plan"
    Require-ZeroClaw

    $current = Ask-User "Current weekly income in USD [0]"
    if (-not $current) { $current = "0" }

    $goal = Ask-User "Weekly income goal in USD (e.g. 500, 1000, 2000)"
    if (-not $goal) { $goal = "500" }

    $hours = Ask-User "Hours available per week for hustle work"
    if (-not $hours) { $hours = "20" }

    $blockers = Ask-User "Biggest blocker right now (or Enter to skip)"
    if (-not $blockers) { $blockers = "not stated" }

    $gap    = [int]$goal - [int]$current
    $planFile = "$Projects\plans\plan-$(Get-Date -Format yyyy-MM-dd).md"

    Run-Agent "Build me a real, specific, actionable weekly income plan. No motivational fluff.

MY SITUATION:
- Skills: $Skills
- Hourly rate: `$$Rate/hour
- Current weekly income: `$$current
- Goal: `$$goal/week
- Available hours: $hours hrs/week
- Blockers: $blockers

Save a full plan to $planFile with these sections:

1. GAP ANALYSIS
   - Weekly gap: `$$gap needed
   - Billable hours required at `$$Rate/hr to close it
   - Most direct path to those hours

2. TOP 5 ACTIONS THIS WEEK (ranked by income impact)
   - Specific, not vague: not 'build portfolio' but 'build X and post on Upwork under Y category'
   - Estimated income impact per action

3. FREELANCE TARGETS
   - 5 specific Upwork/Fiverr job categories matching my skills
   - For each: realistic rate, exact profile headline, what a winning proposal looks like

4. DAILY SCHEDULE
   - Given $hours hrs/week, day-by-day hour allocation
   - Balance: income-generating (applying, client work) vs. building (portfolio, skills)

5. QUICK WINS THIS WEEK
   - 1-2 portfolio pieces I can build in 1-2 days that directly support the freelance targets

6. 3 OUTREACH MESSAGES
   - LinkedIn or cold email to potential clients — specific to my skills, ready to send

7. 30-DAY MILESTONE
   - One measurable number that tells me I'm on track by day 30

Be honest. If `$$goal/week is unrealistic in $hours hours, say so and tell me what IS realistic."

    Write-Info "Plan saved to $planFile"
    Write-Note "Read it: Get-Content '$planFile'"
}

# ── COMMAND: rate ─────────────────────────────────────────────────────────────
function Invoke-Rate([string]$newRate) {
    if (-not $newRate) { $newRate = Ask-User "New hourly rate in USD" }
    $global:Rate = [int]$newRate
    Save-HustleEnv
    Write-Info "Rate set to `$$Rate/hour"
    Run-Agent "Update my rate in your memory: I now charge `$$Rate/hour."
}

# ── MAIN ──────────────────────────────────────────────────────────────────────
switch ($Command.ToLower()) {
    "setup"  { Invoke-Setup }
    "intake" { Invoke-Intake  $Arg1 }
    "build"  { Invoke-Build   $Arg1 $Arg2 }
    "apply"  { Invoke-Apply   $Arg1 }
    "plan"   { Invoke-Plan }
    "rate"   { Invoke-Rate    $Arg1 }
    default  {
        Write-Host ""
        Write-Host "ZeroClaw Hustle Mode" -ForegroundColor Cyan -NoNewline
        Write-Host " — free AI income accelerator"
        Write-Host ""
        Write-Host "  .\scripts\hustle-windows.ps1 setup                    " -NoNewline; Write-Host "Set skills + rate (run once)" -ForegroundColor DarkGray
        Write-Host "  .\scripts\hustle-windows.ps1 intake [url]             " -NoNewline; Write-Host "Analyze a job, draft a proposal" -ForegroundColor DarkGray
        Write-Host "  .\scripts\hustle-windows.ps1 build  [type] [stack]   " -NoNewline; Write-Host "Build a portfolio project" -ForegroundColor DarkGray
        Write-Host "  .\scripts\hustle-windows.ps1 apply  [company]        " -NoNewline; Write-Host "Full job application package" -ForegroundColor DarkGray
        Write-Host "  .\scripts\hustle-windows.ps1 plan                    " -NoNewline; Write-Host "Weekly income action plan" -ForegroundColor DarkGray
        Write-Host "  .\scripts\hustle-windows.ps1 rate   [USD/hr]         " -NoNewline; Write-Host "Update your hourly rate" -ForegroundColor DarkGray
        Write-Host ""
        Write-Host "  Workspace: $Workspace" -ForegroundColor DarkGray
        Write-Host "  Projects:  $Projects"  -ForegroundColor DarkGray
        Write-Host ""
    }
}
