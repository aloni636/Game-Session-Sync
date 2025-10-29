# --- configurations ---
$ADDITIONAL_FILES = @(
  "config.yaml"
  'client_secrets.json',
  'credentials.json',
  'settings.yaml'
)
$TASK_NAME = "Game-Session-Sync"
$DEPLOYMENT_DIR = ".\deployment"


# --- validation ---
$missingFiles = $ADDITIONAL_FILES | Where-Object { -not (Test-Path $_) }
if ($missingFiles.Count -gt 0) {
  $names = $missingFiles -join "', '"
  throw [System.IO.FileNotFoundException] "Required files missing: '$names'"
}
if (-not (Test-Path $DEPLOYMENT_DIR)) {
  throw [System.IO.DirectoryNotFoundException] "Deployment directory not found: '$DEPLOYMENT_DIR'"
}


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
poetry build
$wheel = Get-ChildItem dist\*.whl | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $wheel) {
  throw "No wheel found under dist\*.whl. Did 'poetry build' succeed?"
}

New-Item -Type Directory $DEPLOYMENT_DIR -ErrorAction SilentlyContinue
Get-ChildItem $DEPLOYMENT_DIR | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

foreach ($f in $ADDITIONAL_FILES) {
  Copy-Item $f $DEPLOYMENT_DIR
}
python -m venv .\deployment\.venv-prod
& (Join-Path $DEPLOYMENT_DIR "\.venv-prod\Scripts\python.exe") -m pip install $wheel.FullName


# --- paths ---
$wd = (Resolve-Path $DEPLOYMENT_DIR).Path
$pythonw = (Resolve-Path .\deployment\.venv-prod\Scripts\pythonw.exe).Path
$Action = New-ScheduledTaskAction -Execute $pythonw -Argument ('-m game_session_sync') -WorkingDirectory $wd


# --- triggers ---
$TriggerStartup = New-ScheduledTaskTrigger -AtStartup
$TriggerLogon = New-ScheduledTaskTrigger -AtLogOn


# --- principal ---
$Principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive


# --- settings ---
# -ExecutionTimeLimit: never time out
# -RestartCount: retry if it fails
# -MultipleInstances: only 1 instance
$Settings = New-ScheduledTaskSettingsSet `
  -StartWhenAvailable `
  -ExecutionTimeLimit ([TimeSpan]::Zero) `
  -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) `
  -MultipleInstances IgnoreNew


# --- register ---
Register-ScheduledTask -TaskName $TASK_NAME -Action $Action `
  -Trigger @($TriggerStartup, $TriggerLogon) `
  -Principal $Principal -Settings $Settings `
  -Description "Run Game Session Sync (always-on monitor)" -Force

# restart the task to apply updates now
Stop-ScheduledTask -TaskName $TASK_NAME -ErrorAction SilentlyContinue
Start-ScheduledTask -TaskName $TASK_NAME

Write-Host @"

Setup complete.

Run once:
  Start-ScheduledTask -TaskName '$TASK_NAME'

Inspect:
  Get-ScheduledTask -TaskName "$TASK_NAME" | Get-ScheduledTaskInfo
  (Get-ScheduledTask -TaskName "$TASK_NAME").Actions
  (Get-ScheduledTask -TaskName "$TASK_NAME").Triggers
  (Get-ScheduledTask -TaskName "$TASK_NAME").Principal
  (Get-ScheduledTask -TaskName "$TASK_NAME").Settings

Disable:
  sudo powershell -Command "Disable-ScheduledTask -TaskName '$TASK_NAME'"

Delete:
  sudo powershell -Command "Unregister-ScheduledTask -TaskName '$TASK_NAME' -Confirm:0"
"@
