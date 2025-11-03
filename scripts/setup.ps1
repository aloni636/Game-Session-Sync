# setup.ps1 - Game Session Sync bootstrap with Poetry + pythonw
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

Write-Host "Installing local development version..."
poetry install
