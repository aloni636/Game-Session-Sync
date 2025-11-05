# --- configurations ---
$ADDITIONAL_FILES = @(
  "config.yaml"
  'client_secrets.json',
  'credentials.json',
  'settings.yaml'
)
$TASK_NAME = "Game-Session-Sync"
$DEPLOYMENT_DIR = ".\deployment"
$WAIT_TIMEOUT_SEC = 10


# --- utilities ---
function Write-Deploy {
  param([Parameter(Mandatory)][string] $Message)
  Write-Host "[deploy] $Message"
}

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
  Write-Deploy "Script requires admin to register tasks to the scheduler. Relaunching with sudo..."
  if (Get-Command sudo -ErrorAction SilentlyContinue) {
    sudo powershell -ExecutionPolicy Bypass -File "$($MyInvocation.MyCommand.Path)"
  }
  else {
    Write-Deploy "Command sudo.exe was not found - Relaunching in a new terminal window..."
    Start-Process -FilePath "powershell.exe" -Verb RunAs -ArgumentList "-ExecutionPolicy Bypass -File `"$($MyInvocation.MyCommand.Path)`""
  }
  exit
}


# --- stop previous task ---
Write-Deploy "Stopping existing scheduled task..."
Stop-ScheduledTask -TaskName $TASK_NAME -ErrorAction SilentlyContinue

Write-Deploy "Stopping scheduled task (if running)..."
Stop-ScheduledTask -TaskName $TASK_NAME -ErrorAction SilentlyContinue

$oldPythonw = Join-Path $DEPLOYMENT_DIR ".venv-prod\Scripts\pythonw.exe"
if (Test-Path $oldPythonw) {
  $resolvedOld = (Resolve-Path $oldPythonw).Path
  $deadline = (Get-Date).AddSeconds($WAIT_TIMEOUT_SEC)
  do {
    $running = Get-Process pythonw -ErrorAction SilentlyContinue |
    Where-Object { $_.Path -eq $resolvedOld }
    if (-not $running) { break }
    Start-Sleep -Milliseconds 500
  } while ((Get-Date) -lt $deadline)
  
  if ($running) {
    throw "Timed out waiting for old pythonw.exe to stop - still running from $resolvedOld"
  }
}


# --- remove old deployment ---
Write-Deploy "Removing old deployment from '$DEPLOYMENT_DIR'..."
New-Item -Type Directory $DEPLOYMENT_DIR -ErrorAction SilentlyContinue | Out-Null
Get-ChildItem $DEPLOYMENT_DIR | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue


# --- build wheel and requirements.txt ---
Write-Deploy "Starting build with poetry..."
poetry build
$buildExit = $LASTEXITCODE
if ($buildExit -ne 0) { throw "poetry build failed with exit code $buildExit" }
Write-Deploy "Build complete. Locating latest wheel..."
$wheel = Get-ChildItem dist\*.whl | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $wheel) {
  throw "No wheel found under dist\*.whl. Did 'poetry build' succeed?"
}

Write-Deploy "Exporting locked dependencies from poetry.lock..."
poetry export `
  --format=requirements.txt `
  --without-hashes `
  --only main `
  --output "$DEPLOYMENT_DIR\requirements.txt"

$exportExit = $LASTEXITCODE
if ($exportExit -ne 0) { throw "poetry export failed with exit code $exportExit" }


# --- setting up production environment ----
Write-Deploy "Copying additional files: $($ADDITIONAL_FILES -join ', ')"
foreach ($f in $ADDITIONAL_FILES) {
  Copy-Item $f $DEPLOYMENT_DIR
}

Write-Deploy "Creating production virtual environment..."
python -m venv .\deployment\.venv-prod

$venvPython = (Join-Path $DEPLOYMENT_DIR "\.venv-prod\Scripts\python.exe")

Write-Deploy "Upgrading pip..."
& $venvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed with exit code $LASTEXITCODE" }

$requirementsPath = Join-Path $DEPLOYMENT_DIR "requirements.txt"
Write-Deploy "Installing locked dependencies from ${requirementsPath}"
& $venvPython -m pip install -r $requirementsPath
if ($LASTEXITCODE -ne 0) {
  throw "pip install -r '$requirementsPath' failed with exit code $LASTEXITCODE"
}

Write-Deploy "Installing wheel '$($wheel.Name)' without dependencies..."
& $venvPython -m pip install --no-deps $wheel.FullName
if ($LASTEXITCODE -ne 0) { throw "pip install wheel failed with exit code $LASTEXITCODE" }

Write-Deploy "Dependencies installed. Configuring scheduled task..."


# --- paths ---
$wd = (Resolve-Path $DEPLOYMENT_DIR).Path
$pythonw = (Resolve-Path .\deployment\.venv-prod\Scripts\pythonw.exe).Path
Write-Deploy "Using working directory: '$wd'"
Write-Deploy "Using pythonw: '$pythonw'"
$Action = New-ScheduledTaskAction -Execute $pythonw -Argument ('-m game_session_sync') -WorkingDirectory $wd


# --- triggers ---
Write-Deploy "Creating scheduled task triggers (AtStartup, AtLogOn)..."
$TriggerStartup = New-ScheduledTaskTrigger -AtStartup
$TriggerLogon = New-ScheduledTaskTrigger -AtLogOn


# --- principal ---
Write-Deploy "Configuring principal for user '$env:USERDOMAIN\$env:USERNAME'..."
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
Write-Deploy "Registering scheduled task '$TASK_NAME'..."
Register-ScheduledTask -TaskName $TASK_NAME -Action $Action `
  -Trigger @($TriggerStartup, $TriggerLogon) `
  -Principal $Principal -Settings $Settings `
  -Description "Run Game Session Sync (always-on monitor)" -Force

# restart the task to apply updates now
Write-Deploy "Starting scheduled task with new deployment..."
Start-ScheduledTask -TaskName $TASK_NAME

Write-Deploy @"

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
