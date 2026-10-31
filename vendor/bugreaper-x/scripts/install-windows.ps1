#Requires -RunAsAdministrator
# BugReaper X v4.0 — Windows Installer
# Kairyx Security Solutions, Fort Saskatchewan, Alberta

param(
    [string]$InstallDir = "C:\BugReaper",
    [string]$ApiPort = "8900",
    [string]$VRPort = "8901"
)

$ErrorActionPreference = "Stop"

function Log { param([string]$msg) Write-Host "[BugReaper] $msg" -ForegroundColor Cyan }
function Ok  { param([string]$msg) Write-Host "[OK] $msg" -ForegroundColor Green }
function Err { param([string]$msg) Write-Host "[ERROR] $msg" -ForegroundColor Red; exit 1 }

Log "BugReaper X v4.0 — Windows Installer"
Log "Kairyx Security Solutions"

if (-not ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")) {
    Err "Run as Administrator"
}

if (-not (Get-Command choco -ErrorAction SilentlyContinue)) {
    Log "Installing Chocolatey..."
    Set-ExecutionPolicy Bypass -Scope Process -Force
    [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
    Invoke-Expression ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
}
Ok "Chocolatey available"

Log "Installing dependencies..."
choco install -y python311 git nmap 7zip curl wget --no-progress | Out-Null
$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine")
Ok "Chocolatey packages installed"

Log "Creating installation directory: $InstallDir"
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
Copy-Item -Recurse -Force ".\*" "$InstallDir\"

Log "Creating Python virtual environment..."
python -m venv "$InstallDir\venv"
& "$InstallDir\venv\Scripts\pip" install --upgrade pip -q
& "$InstallDir\venv\Scripts\pip" install -e "$InstallDir" -q
Ok "Python environment ready"

if (-not (Get-Command nssm -ErrorAction SilentlyContinue)) {
    choco install -y nssm --no-progress | Out-Null
}

Log "Installing Windows service via NSSM..."
$exePath = "$InstallDir\venv\Scripts\bugreaper.exe"
nssm install BugReaperX $exePath "serve --host 0.0.0.0 --port $ApiPort" 2>&1 | Out-Null
nssm set BugReaperX AppDirectory "$InstallDir" 2>&1 | Out-Null
nssm set BugReaperX DisplayName "BugReaper X REAPER Service" 2>&1 | Out-Null
nssm set BugReaperX Description "BugReaper X v4.0 Autonomous Vulnerability Intelligence" 2>&1 | Out-Null
nssm set BugReaperX Start SERVICE_AUTO_START 2>&1 | Out-Null
Start-Service BugReaperX -ErrorAction SilentlyContinue
Ok "Windows service installed and started"

Log "Configuring firewall rules..."
New-NetFirewallRule -DisplayName "BugReaper X API" -Direction Inbound -Protocol TCP -LocalPort $ApiPort -Action Allow -Profile Any -ErrorAction SilentlyContinue | Out-Null
New-NetFirewallRule -DisplayName "BugReaper X VR Bridge" -Direction Inbound -Protocol TCP -LocalPort $VRPort -Action Allow -Profile Any -ErrorAction SilentlyContinue | Out-Null
Ok "Firewall rules configured"

$desktopPath = [Environment]::GetFolderPath("Desktop")
$WshShell = New-Object -comObject WScript.Shell
$shortcut = $WshShell.CreateShortcut("$desktopPath\BugReaper X.lnk")
$shortcut.TargetPath = "cmd.exe"
$shortcut.Arguments = "/k `"$InstallDir\venv\Scripts\bugreaper`" version"
$shortcut.WorkingDirectory = $InstallDir
$shortcut.IconLocation = "powershell.exe,0"
$shortcut.Save()
Ok "Desktop shortcut created"

$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath -notlike "*$InstallDir\venv\Scripts*") {
    [Environment]::SetEnvironmentVariable("Path", "$userPath;$InstallDir\venv\Scripts", "User")
}

Write-Host ""
Ok "BugReaper X v4.0 installed on Windows!"
Write-Host ""
Log "  CLI scan:   bugreaper scan https://target.com"
Log "  API:        http://localhost:$ApiPort"
Log "  Docs:       http://localhost:$ApiPort/docs"
Log "  Configure:  $InstallDir\.env"
Write-Host ""
Log "  Set BUGREAPER_ANTHROPIC_API_KEY in $InstallDir\.env for REAPER AI"
Write-Host ""
Log "  Service management:"
Log "    Start:   Start-Service BugReaperX"
Log "    Stop:    Stop-Service BugReaperX"
Log "    Status:  Get-Service BugReaperX"
