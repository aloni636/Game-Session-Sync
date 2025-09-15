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

# --- build into isolated venv ---
New-Item -Type Directory .\deployment -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force .\deployment\* -ErrorAction SilentlyContinue

# Copy optional runtime files if present
$filesToCopy = @(
  '.env',
  'client_secrets.json',
  'credentials.json',
  'settings.yaml'
)
foreach ($f in $filesToCopy) {
  if (Test-Path $f) {
    Copy-Item $f .\deployment\
  }
  else {
    Write-Host "Note: $f not found; skipping copy."
  }
}

poetry build

python -m venv .\deployment\.venv-prod
$wheel = Get-ChildItem dist\*.whl | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $wheel) {
  throw "No wheel found under dist\*.whl. Did 'poetry build' succeed?"
}
.\deployment\.venv-prod\Scripts\python.exe -m pip install $wheel.FullName



# --- paths ---
$TaskName = "Game-Session-Sync"
$wd = (Resolve-Path .\deployment).Path
$pythonw = (Resolve-Path .\deployment\.venv-prod\Scripts\pythonw.exe).Path
$Action = New-ScheduledTaskAction -Execute $pythonw -Argument ('-m game_session_sync') -WorkingDirectory $wd


# --- triggers ---
$now = Get-Date
$nextHour = $now.Date.AddHours($now.Hour + 1)
$Trigger1 = New-ScheduledTaskTrigger -Once -At $nextHour `
  -RepetitionInterval (New-TimeSpan -Hours 1) `
  -RepetitionDuration ([TimeSpan]::FromDays(3650))
$Trigger2 = New-ScheduledTaskTrigger -AtLogOn

# --- principal ---
$Principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive

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
