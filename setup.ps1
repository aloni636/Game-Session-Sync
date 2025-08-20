# setup.ps1 — Game Session Sync bootstrap with Poetry + pythonw

# --- elevation ---
if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
    ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "Script requires admin to register tasks to the scheduler. Relaunching with sudo..."
    if (Get-Command sudo -ErrorAction SilentlyContinue) {
        sudo powershell -ExecutionPolicy Bypass -File "$($MyInvocation.MyCommand.Path)"
    }
    else {
        Write-Host "Command sudo.exe was not found - Relaunching in a new terminal window..."
        Start-Process -FilePath "powershell.exe" -Verb RunAs -ArgumentList "-ExecutionPolicy Bypass -File `"$($MyInvocation.MyCommand.Path)`""
    }
    exit
}

# --- paths ---
$RepoDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$EntryPy = Join-Path $RepoDir "main.py"    # adjust if script has different name
$TaskName = "Game Session Sync"

# --- ensure python and poetry (install poetry via pipx only if missing) ---
function Test-Cmd($name) { Get-Command $name -ErrorAction SilentlyContinue }
$hasPython = (Test-Cmd python) -or (Test-Cmd py)
if (-not $hasPython) {
    winget install -e --id Python.Python.3 --accept-package-agreements --accept-source-agreements
}

# If Poetry exists, use it. Otherwise install pipx then Poetry via pipx.
if (-not (Test-Cmd poetry)) {
    if (-not (Test-Cmd pipx)) {
        Write-Host "Installing pipx with pip --user"
        # If you installed Python using Microsoft Store, replace `py` with `python3` in the next line.
        try { py -m pip install --user pipx } catch { python3 -m pip install --user pipx }
        try { py -m pipx ensurepath } catch { python3 -m pipx ensurepath }
        # Refresh PATH for current session
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
    }
    Write-Host "Installing poetry via pipx..."
    pipx install poetry
}

if (-not (Test-Cmd poetry)) { throw "Poetry not found after installation. Ensure pipx is on PATH and try again." }

# --- install deps into poetry venv (inside repo) ---
Write-Host "Configuring Python environment with poetry..."
Set-Location $RepoDir
poetry env use python
poetry install --no-root

# --- action: run pythonw.exe directly from Poetry venv (no PowerShell shell)
$Pythonw = Join-Path $RepoDir ".venv\Scripts\pythonw.exe"
if (-not (Test-Path $Pythonw)) {
    throw "pythonw not found at $Pythonw. Ensure 'poetry install' completed and virtualenvs.in-project is enabled."
}
$Action = New-ScheduledTaskAction -Execute $Pythonw -Argument ('"' + $EntryPy + '"') -WorkingDirectory $RepoDir

# --- triggers ---
$now = Get-Date
$nextHour = $now.Date.AddHours($now.Hour + 1)
$Trigger1 = New-ScheduledTaskTrigger -Once -At $nextHour `
    -RepetitionInterval (New-TimeSpan -Hours 1) `
    -RepetitionDuration ([TimeSpan]::FromDays(3650))
$Trigger2 = New-ScheduledTaskTrigger -AtLogOn

# --- principal ---
$Principal = New-ScheduledTaskPrincipal -UserId "$env:USERNAME" -LogonType Interactive

# --- settings ---
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30)

# --- register ---
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger @($Trigger1, $Trigger2) `
    -Principal $Principal -Settings $Settings `
    -Description "Run Game Session Sync via Poetry + pythonw (hidden)" -Force

Write-Host @"

Setup complete.

Run once:
  Start-ScheduledTask -TaskName '$TaskName'

Inspect:
  Get-ScheduledTask -TaskName "$TaskName" | Get-ScheduledTaskInfo
  (Get-ScheduledTask -TaskName "$TaskName").Actions
  (Get-ScheduledTask -TaskName "$TaskName").Triggers
  (Get-ScheduledTask -TaskName "$TaskName").Principal
  (Get-ScheduledTask -TaskName "$TaskName").Settings

Disable:
  sudo powershell -Command "Disable-ScheduledTask -TaskName '$TaskName'"

Delete:
  sudo powershell -Command "Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:0"
"@
