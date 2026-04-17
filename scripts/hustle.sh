#!/usr/bin/env bash
# hustle.sh — ZeroClaw income accelerator
# Freelance intake · Portfolio builder · Job applications · Weekly planning
#
# Run once to set up:
#   bash scripts/hustle.sh setup
#
# Then use daily:
#   bash scripts/hustle.sh intake          — paste a job posting, get a proposal
#   bash scripts/hustle.sh intake <url>    — fetch and analyze a job URL
#   bash scripts/hustle.sh build           — generate a real portfolio project
#   bash scripts/hustle.sh apply <company> — full job application package
#   bash scripts/hustle.sh plan            — weekly income action plan
#   bash scripts/hustle.sh rate <USD/hr>   — update your hourly rate

set -euo pipefail

# ── Colors ────────────────────────────────────────────────────────────────────
if [ -t 1 ]; then
    BOLD='\033[1m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'
    YELLOW='\033[1;33m'; RESET='\033[0m'
else
    BOLD=''; GREEN=''; CYAN=''; YELLOW=''; RESET=''
fi

info()    { echo -e "${GREEN}[hustle]${RESET} $*"; }
section() { echo -e "\n${BOLD}${CYAN}━━  $*  ━━${RESET}"; }
note()    { echo -e "${YELLOW}[note]${RESET}  $*"; }
ask()     { echo -en "${CYAN}?${RESET}  $*: "; }

# ── Paths ─────────────────────────────────────────────────────────────────────
WORKSPACE="${ZEROCLAW_WORKSPACE:-$HOME/zeroclaw-workspace}"
PROJECTS="$WORKSPACE/projects"
CONFIG_DIR="${ZEROCLAW_CONFIG_DIR:-$HOME/.zeroclaw}"
HUSTLE_ENV="$CONFIG_DIR/hustle.env"
SKILLS_FILE="$WORKSPACE/skills.md"
RESUME_FILE="$WORKSPACE/resume.md"

mkdir -p "$PROJECTS/portfolio" "$PROJECTS/freelance" \
         "$PROJECTS/applications" "$PROJECTS/plans"

# Load saved settings (rate + skills persist across runs)
RATE=50
SKILLS=""
[[ -f "$HUSTLE_ENV" ]] && source "$HUSTLE_ENV"

# ── Helpers ───────────────────────────────────────────────────────────────────
require_zeroclaw() {
    command -v zeroclaw &>/dev/null && return
    echo "ERROR: zeroclaw not found. Run scripts/setup-free.sh first."
    exit 1
}

run_agent() { zeroclaw agent -m "$1"; }

read_multiline() {
    echo -e "${CYAN}$1${RESET}"
    echo "(Paste text then press Ctrl-D on a blank line when done)"
    cat
}

resume_context() {
    if [[ -f "$RESUME_FILE" ]]; then
        echo "My resume/background: $(cat "$RESUME_FILE")"
    else
        echo "No resume file yet — infer my background from my skills: $SKILLS. Remind me to create $RESUME_FILE with my work history."
    fi
}

# ── COMMAND: setup ────────────────────────────────────────────────────────────
cmd_setup() {
    section "Hustle Mode — First-Time Setup"

    ask "Your main skills (e.g. Python, React, SQL, automation, APIs)"
    read -r input_skills
    SKILLS="${input_skills:-coding}"

    ask "Target hourly rate in USD [50]"
    read -r input_rate
    RATE="${input_rate:-50}"

    # Persist settings
    cat > "$HUSTLE_ENV" << EOF
RATE=$RATE
SKILLS="$SKILLS"
EOF

    # Write a skills file the agent can read later
    cat > "$SKILLS_FILE" << EOF
# Skills & Rate

**Hourly rate:** \$$RATE/hr
**Skills:** $SKILLS
**Workspace:** $WORKSPACE
**Updated:** $(date +%Y-%m-%d)

## Add these manually
- GitHub URL:
- Portfolio URL:
- Strongest project link:
- Years of experience:
EOF

    info "Seeding ZeroClaw memory with your background..."
    run_agent "Store this permanently in your memory about me:
- Skills: $SKILLS
- Hourly rate: \$$RATE/hour
- Workspace: $WORKSPACE
- Code goes in: $PROJECTS/
- When I say 'save it', write files into the appropriate subfolder under $PROJECTS/
- When I ask you to build something, write COMPLETE working code — not skeletons or TODOs.
- You are my income-generating partner. Be direct, practical, and specific."

    echo ""
    info "Setup complete."
    info "Rate: \$$RATE/hr   Skills: $SKILLS"
    note "Optionally add your resume to $RESUME_FILE for better application packages."
    note "Next step: bash scripts/hustle.sh plan"
}

# ── COMMAND: intake — analyze a job posting and draft a proposal ──────────────
cmd_intake() {
    section "Job Intake"
    require_zeroclaw

    local source="${1:-}"
    local job_text

    if [[ "$source" =~ ^https?:// ]]; then
        info "Fetching: $source"
        job_text="Fetch and analyze this job posting URL: $source"
    else
        job_text=$(read_multiline "Paste the job posting:")
    fi

    local slug="job-$(date +%Y%m%d-%H%M)"
    local dest="$PROJECTS/freelance/$slug"

    info "Analyzing..."

    run_agent "I need to win this freelance job. Analyze it completely and help me respond.

JOB POSTING:
$job_text

MY SKILLS: $SKILLS
MY RATE: \$$RATE/hour

Do all of this and save results to $dest/:

1. BRIEF.md — full scope breakdown:
   - Every technical deliverable (numbered list)
   - Hours estimate per deliverable (realistic, not optimistic)
   - Total hours × \$$RATE = project price
   - Timeline in days
   - Red flags or scope creep risks to clarify upfront

2. PROPOSAL.md — winning proposal ready to copy-paste:
   - Under 200 words
   - First sentence: show I understand their exact problem
   - Middle: mention 1-2 specific skills from my background that directly apply
   - End: clear price, timeline, and confident call to action
   - Do NOT use generic phrases like 'I am passionate' or 'I am a quick learner'

3. STARTER/ — skeleton code or boilerplate for the main tech they need:
   - File structure only (no need to implement, just scaffold it right)

After saving, print:
- The price to quote (in bold)
- The 3 sentences from PROPOSAL.md to lead with"

    info "Intake saved to $dest"
    note "Copy proposal: cat $dest/PROPOSAL.md"
}

# ── COMMAND: build — generate a complete portfolio project ────────────────────
cmd_build() {
    section "Portfolio Project Builder"
    require_zeroclaw

    local type="${1:-}"
    local stack="${2:-}"

    if [[ -z "$type" ]]; then
        ask "Project type (e.g. 'discord bot', 'web scraper', 'REST API', 'CLI tool', 'data dashboard')"
        read -r type
    fi

    if [[ -z "$stack" ]]; then
        ask "Tech stack (e.g. 'Python', 'React + Node', 'FastAPI') [Enter = auto-pick best fit]"
        read -r stack
        [[ -z "$stack" ]] && stack="whatever is the best fit for this type of project"
    fi

    local slug
    slug="$(echo "$type" | tr ' ' '-' | tr '[:upper:]' '[:lower:]')-$(date +%Y%m%d)"
    local dest="$PROJECTS/portfolio/$slug"

    info "Building: $type | Stack: $stack"
    info "Output: $dest"

    run_agent "Build me a complete portfolio project that will impress hiring managers and win freelance clients.

PROJECT TYPE: $type
TECH STACK: $stack
SAVE TO: $dest/
MY SKILLS: $SKILLS

Hard requirements — no excuses:
1. ALL core functionality must be implemented (zero TODO stubs in the main path)
2. Real error handling — catch failures, give useful messages
3. README.md with: what it does, why it matters, setup in under 5 minutes, 3 usage examples
4. requirements.txt / package.json / go.mod — all deps pinned to a version
5. .gitignore
6. Code quality: typed where the language supports it, consistent naming, no dead code
7. At least one 'wow' feature that makes it memorable (suggest what that should be and implement it)

After building, tell me:
- What makes this impressive to someone hiring for $type roles
- 3 specific job titles that should see this in my portfolio
- What to write as the GitHub repo description (under 100 chars)"

    info "Project saved to $dest"
    note "Push to GitHub:  cd $dest && git init && git add . && git commit -m 'feat: $type' && git push"
}

# ── COMMAND: apply — full job application package ─────────────────────────────
cmd_apply() {
    section "Job Application Package"
    require_zeroclaw

    local company="${1:-}"
    if [[ -z "$company" ]]; then
        ask "Company name or job title (for file naming)"
        read -r company
    fi

    local slug
    slug="$(echo "$company" | tr ' ' '-' | tr '[:upper:]' '[:lower:]')-$(date +%Y%m%d)"
    local dest="$PROJECTS/applications/$slug"

    local job_text
    job_text=$(read_multiline "Paste the full job description:")

    info "Building application package for: $company"

    local annual
    annual=$(( RATE * 2000 ))

    run_agent "Help me land this job. Build a complete application package.

JOB DESCRIPTION:
$job_text

$(resume_context)
MY SKILLS: $SKILLS
RATE / SALARY TARGET: \$$RATE/hr = ~\$$annual/year

Save all files to $dest/ and create:

1. COVER_LETTER.md — 3 tight paragraphs, zero fluff:
   Para 1: One specific thing about this company that makes me want this role (research it)
   Para 2: My most directly relevant project or result — specific numbers if possible
   Para 3: Confident close, availability, next step

2. RESUME_BULLETS.md — 8 resume bullets to add or update:
   - STAR format: Situation → Task → Action → Result
   - Quantify: %, \$, users, speed, scale — make up plausible numbers if needed
   - Mirror their exact wording from the job description

3. PORTFOLIO_MAP.md — which of my projects to highlight:
   - Project name → why it matters to them → what to say about it in 30 seconds

4. SKILL_GAPS.md — what they want that I'm missing:
   - Gap → fastest way to close it → specific resource (course, project, doc)
   - Honest priority: which gaps matter most vs. which to ignore

5. INTERVIEW_PREP.md — 5 likely interview questions + strong answers:
   - Based on the job requirements and my background
   - Include one answer about a failure/challenge (they always ask)

After saving, tell me the single most important thing to nail in this application."

    info "Application package saved to $dest"
    note "Review: ls $dest"
}

# ── COMMAND: plan — weekly income action plan ─────────────────────────────────
cmd_plan() {
    section "Weekly Income Plan"
    require_zeroclaw

    ask "Current weekly income in USD [0]"
    read -r current
    current="${current:-0}"

    ask "Weekly income goal in USD (e.g. 500, 1000, 2000)"
    read -r goal
    goal="${goal:-500}"

    ask "Hours available per week for hustle work"
    read -r hours
    hours="${hours:-20}"

    ask "Biggest blocker right now (or Enter to skip)"
    read -r blockers
    blockers="${blockers:-not stated}"

    local plan_file="$PROJECTS/plans/plan-$(date +%Y-%m-%d).md"

    run_agent "Build me a real, specific, actionable weekly income plan. No motivational fluff.

MY SITUATION:
- Skills: $SKILLS
- Hourly rate: \$$RATE/hour
- Current weekly income: \$$current
- Goal: \$$goal/week
- Available hours: $hours hrs/week
- Blockers: $blockers

Save a full plan to $plan_file with these sections:

1. GAP ANALYSIS
   - Weekly gap: \$$goal - \$$current = \$$(( goal - current )) needed
   - How many billable hours at \$$RATE/hr to close it: $(echo "scale=1; ($goal - $current) / $RATE" | bc 2>/dev/null || echo "calculate this") hrs
   - Most direct path to those hours

2. TOP 5 ACTIONS THIS WEEK (ranked by income impact)
   - Each action must be specific: not 'build portfolio' but 'build a Python web scraper for real estate data and post on Upwork under Data Extraction'
   - Include estimated income impact per action

3. FREELANCE TARGETS
   - 5 specific Upwork/Fiverr/Toptal job categories matching my skills
   - For each: realistic rate, exact profile headline to use, what to put in my top-rated proposal

4. DAILY SCHEDULE
   - Given $hours hrs/week, build a day-by-day hour allocation
   - Balance: income-generating (applying, client work) vs. capability-building (portfolio, skills)

5. QUICK WINS THIS WEEK
   - 1-2 portfolio pieces I can build in 1-2 days that directly support the freelance targets above

6. 3 OUTREACH MESSAGES
   - LinkedIn InMail or cold email to potential clients
   - Specific to my skills, not generic

7. 30-DAY MILESTONE
   - What does winning look like in 4 weeks?
   - One measurable number that tells me I'm on track by day 30

Be honest. If \$$goal is unrealistic in $hours hours, say so and tell me what IS realistic."

    info "Plan saved to $plan_file"
    note "Read it: cat '$plan_file'"
}

# ── COMMAND: rate ─────────────────────────────────────────────────────────────
cmd_rate() {
    local new_rate="${1:-}"
    if [[ -z "$new_rate" ]]; then
        ask "New hourly rate in USD"
        read -r new_rate
    fi
    RATE="$new_rate"
    if [[ -f "$HUSTLE_ENV" ]]; then
        sed -i "s/^RATE=.*/RATE=$RATE/" "$HUSTLE_ENV"
    else
        echo "RATE=$RATE" > "$HUSTLE_ENV"
    fi
    info "Rate set to \$$RATE/hour"
    run_agent "Update my rate in your memory: I now charge \$$RATE/hour."
}

# ── MAIN ──────────────────────────────────────────────────────────────────────
CMD="${1:-help}"
shift 2>/dev/null || true

case "$CMD" in
    setup)   cmd_setup ;;
    intake)  cmd_intake  "$@" ;;
    build)   cmd_build   "$@" ;;
    apply)   cmd_apply   "$@" ;;
    plan)    cmd_plan ;;
    rate)    cmd_rate    "$@" ;;
    help|--help|-h|"")
        echo ""
        echo -e "${BOLD}${CYAN}ZeroClaw Hustle Mode${RESET} — free AI income accelerator"
        echo ""
        echo -e "  ${GREEN}bash scripts/hustle.sh setup${RESET}            Set skills + rate (run once)"
        echo -e "  ${GREEN}bash scripts/hustle.sh intake [url]${RESET}     Analyze a job, draft a proposal"
        echo -e "  ${GREEN}bash scripts/hustle.sh build [type] [stack]${RESET}  Build a portfolio project"
        echo -e "  ${GREEN}bash scripts/hustle.sh apply [company]${RESET}  Full job application package"
        echo -e "  ${GREEN}bash scripts/hustle.sh plan${RESET}             Weekly income action plan"
        echo -e "  ${GREEN}bash scripts/hustle.sh rate <USD/hr>${RESET}    Update your hourly rate"
        echo ""
        echo "  Workspace: ${WORKSPACE}"
        echo "  Projects:  ${PROJECTS}"
        echo ""
        ;;
    *)
        echo "Unknown command: $CMD"
        echo "Run: bash scripts/hustle.sh help"
        exit 1
        ;;
esac
