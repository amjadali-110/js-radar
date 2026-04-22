# JS Discovery SaaS - Windows Startup Script (PowerShell)

# Ensure UTF-8 output for emoji support
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

# Banner
$lightning = [char]0x26A1  # ⚡
Write-Host ""
Write-Host "    +-==================================================-+" -ForegroundColor Cyan
Write-Host "    |                                                      |" -ForegroundColor Cyan
Write-Host "    |" -ForegroundColor Cyan -NoNewline; Write-Host "            $lightning  J S   R A D A R  $lightning                  " -ForegroundColor Yellow -NoNewline; Write-Host "|" -ForegroundColor Cyan
Write-Host "    |                                                      |" -ForegroundColor Cyan
Write-Host "    |" -ForegroundColor Cyan -NoNewline; Write-Host "        JS Security Analysis Platform            " -ForegroundColor Gray -NoNewline; Write-Host "|" -ForegroundColor Cyan
Write-Host "    |                                                      |" -ForegroundColor Cyan
Write-Host "    |" -ForegroundColor Cyan -NoNewline; Write-Host "             >> Built by Amjad Ali <<                 " -ForegroundColor Green -NoNewline; Write-Host "|" -ForegroundColor Cyan
Write-Host "    |                                                      |" -ForegroundColor Cyan
Write-Host "    +-==================================================-+" -ForegroundColor Cyan
Write-Host ""

$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Definition

# ============ Check required system tools ============
foreach ($tool in @("node", "npm")) {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
        Write-Host "ERROR: '$tool' is required but not found. Please install it and ensure it is in PATH." -ForegroundColor Red
        exit 1
    }
}

# ============ Find Python 3.8+ ============
$PYTHON_BIN = $null
$PYTHON_VERSION = $null
# Save and override ErrorActionPreference so stderr from native commands
# (e.g. the Microsoft Store python3 stub) does not terminate the script.
$savedEAP = $ErrorActionPreference
$ErrorActionPreference = "SilentlyContinue"
foreach ($candidate in @("python", "python3")) {
    $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
    if (-not $cmd) { continue }
    try {
        $verStr = $null
        $output = & $candidate -c "import sys; print(str(sys.version_info.major)+chr(46)+str(sys.version_info.minor))" 2>&1
        foreach ($line in $output) {
            if ($line -is [string] -and $line.Trim() -match '^\d+\.\d+$') {
                $verStr = $line.Trim()
                break
            }
        }
        if ($verStr -and $verStr -match '^(\d+)\.(\d+)$') {
            if ([int]$Matches[1] -ge 3 -and [int]$Matches[2] -ge 8) {
                $PYTHON_BIN = $candidate
                $PYTHON_VERSION = $verStr
                break
            }
        }
    } catch {
        continue
    }
}
$ErrorActionPreference = $savedEAP
if (-not $PYTHON_BIN) {
    Write-Host "ERROR: Python 3.8+ is required but not found." -ForegroundColor Red
    Write-Host "Download from https://www.python.org/downloads/" -ForegroundColor Yellow
    exit 1
}
Write-Host "[+] Using $PYTHON_BIN (Python $PYTHON_VERSION)" -ForegroundColor Green

# Check Node.js
$NODE_VER = & node -v 2>&1 | Where-Object { $_ -is [string] }
$NPM_VER  = & npm -v 2>&1 | Where-Object { $_ -is [string] }
Write-Host "[+] Using node $NODE_VER, npm $NPM_VER" -ForegroundColor Green

# Ensure data directories exist
New-Item -ItemType Directory -Force -Path "$SCRIPT_DIR\data\scans" | Out-Null
New-Item -ItemType Directory -Force -Path "$SCRIPT_DIR\backend\instance" | Out-Null

# ============ Download scanner tool binaries ============
$BIN_DIR = "$SCRIPT_DIR\scanner\bin"
New-Item -ItemType Directory -Force -Path $BIN_DIR | Out-Null

# Detect architecture
$RAW_ARCH = $env:PROCESSOR_ARCHITECTURE
switch ($RAW_ARCH) {
    "AMD64"  { $ARCH_AMD = "amd64"; $ARCH_FULL = "x86_64" }
    "ARM64"  { $ARCH_AMD = "arm64"; $ARCH_FULL = "arm64" }
    default  {
        Write-Host "Unsupported architecture: $RAW_ARCH" -ForegroundColor Red
        exit 1
    }
}
Write-Host "[*] Detected Windows $RAW_ARCH" -ForegroundColor Blue

# Helper: get latest release tag from GitHub API
function Get-LatestTag($repo) {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    try {
        $response = Invoke-RestMethod -Uri "https://api.github.com/repos/$repo/releases/latest"
    } catch {
        Write-Host "[-] Failed to fetch latest release for $repo. Check internet or GitHub API rate limit." -ForegroundColor Red
        Write-Host "    Error: $_" -ForegroundColor Gray
        exit 1
    }
    $tag = $response.tag_name
    if (-not $tag) {
        Write-Host "[-] No tag_name found in release response for $repo." -ForegroundColor Red
        exit 1
    }
    return $tag
}

# Helper: download file
function Download-File($url, $outPath) {
    Write-Host "    Downloading external scanner dependency..." -ForegroundColor Gray
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    try {
        Invoke-WebRequest -Uri $url -OutFile $outPath -UseBasicParsing -ErrorAction Stop
    } catch {
        Write-Host "[-] External scanner dependency download failed" -ForegroundColor Red
        exit 1
    }
}

# --- gospider ---
# Asset: gospider_v{VER}_windows_{arch}.zip -> contains gospider.exe inside a subfolder
if (-not (Test-Path "$BIN_DIR\gospider.exe")) {
    Write-Host "[*] Installing external scanner dependency..." -ForegroundColor Blue
    $TAG = Get-LatestTag "jaeles-project/gospider"
    $URL = "https://github.com/jaeles-project/gospider/releases/download/$TAG/gospider_${TAG}_windows_${ARCH_FULL}.zip"
    Write-Host "[*] Downloading external scanner dependency ..." -ForegroundColor Blue
    $tempZip = [System.IO.Path]::GetTempFileName() + ".zip"
    $tempDir = Join-Path ([System.IO.Path]::GetTempPath()) "gospider_extract"
    try {
        Download-File $URL $tempZip
        if (Test-Path $tempDir) { Remove-Item -Recurse -Force $tempDir }
        Expand-Archive -Path $tempZip -DestinationPath $tempDir -Force
        $exe = Get-ChildItem -Path $tempDir -Filter "gospider.exe" -Recurse | Select-Object -First 1
        if ($exe) {
            Copy-Item $exe.FullName "$BIN_DIR\gospider.exe" -Force
            Write-Host "[+] External scanner dependency ready" -ForegroundColor Green
        } else {
            Write-Host "[-] External scanner dependency archive missing required binary" -ForegroundColor Red
            exit 1
        }
    } finally {
        Remove-Item -Force $tempZip -ErrorAction SilentlyContinue
        Remove-Item -Recurse -Force $tempDir -ErrorAction SilentlyContinue
    }
}

# --- trufflehog ---
# Asset: trufflehog_{VER}_windows_{arch}.tar.gz -> contains trufflehog.exe
if (-not (Test-Path "$BIN_DIR\trufflehog.exe")) {
    Write-Host "[*] Installing external scanner dependency..." -ForegroundColor Blue
    $TAG = Get-LatestTag "trufflesecurity/trufflehog"
    $VERSION = $TAG.TrimStart('v')
    $URL = "https://github.com/trufflesecurity/trufflehog/releases/download/$TAG/trufflehog_${VERSION}_windows_${ARCH_AMD}.tar.gz"
    Write-Host "[*] Downloading external scanner dependency ..." -ForegroundColor Blue
    $tempTarGz = [System.IO.Path]::GetTempFileName() + ".tar.gz"
    $tempDir = Join-Path ([System.IO.Path]::GetTempPath()) "trufflehog_extract"
    try {
        Download-File $URL $tempTarGz
        if (Test-Path $tempDir) { Remove-Item -Recurse -Force $tempDir }
        New-Item -ItemType Directory -Force -Path $tempDir | Out-Null
        # Windows 10+ has native tar support
        & tar -xzf $tempTarGz -C $tempDir 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[-] Failed to extract external scanner dependency archive. Ensure 'tar' is available (Windows 10+)." -ForegroundColor Red
            exit 1
        }
        $exe = Get-ChildItem -Path $tempDir -Filter "trufflehog.exe" -Recurse | Select-Object -First 1
        if ($exe) {
            Copy-Item $exe.FullName "$BIN_DIR\trufflehog.exe" -Force
            Write-Host "[+] External scanner dependency ready" -ForegroundColor Green
        } else {
            Write-Host "[-] External scanner dependency archive missing required binary" -ForegroundColor Red
            exit 1
        }
    } finally {
        Remove-Item -Force $tempTarGz -ErrorAction SilentlyContinue
        Remove-Item -Recurse -Force $tempDir -ErrorAction SilentlyContinue
    }
}

# --- dnsx ---
# Asset: dnsx_{VER}_windows_{arch}.zip -> contains dnsx.exe
if (-not (Test-Path "$BIN_DIR\dnsx.exe")) {
    Write-Host "[*] Installing external scanner dependency..." -ForegroundColor Blue
    $TAG = Get-LatestTag "projectdiscovery/dnsx"
    $VERSION = $TAG.TrimStart('v')
    $URL = "https://github.com/projectdiscovery/dnsx/releases/download/$TAG/dnsx_${VERSION}_windows_${ARCH_AMD}.zip"
    Write-Host "[*] Downloading external scanner dependency ..." -ForegroundColor Blue
    $tempZip = [System.IO.Path]::GetTempFileName() + ".zip"
    $tempDir = Join-Path ([System.IO.Path]::GetTempPath()) "dnsx_extract"
    try {
        Download-File $URL $tempZip
        if (Test-Path $tempDir) { Remove-Item -Recurse -Force $tempDir }
        Expand-Archive -Path $tempZip -DestinationPath $tempDir -Force
        $exe = Get-ChildItem -Path $tempDir -Filter "dnsx.exe" -Recurse | Select-Object -First 1
        if ($exe) {
            Copy-Item $exe.FullName "$BIN_DIR\dnsx.exe" -Force
            Write-Host "[+] External scanner dependency ready" -ForegroundColor Green
        } else {
            Write-Host "[-] External scanner dependency archive missing required binary" -ForegroundColor Red
            exit 1
        }
    } finally {
        Remove-Item -Force $tempZip -ErrorAction SilentlyContinue
        Remove-Item -Recurse -Force $tempDir -ErrorAction SilentlyContinue
    }
}

# Verify all binaries
foreach ($tool in @("gospider.exe", "trufflehog.exe", "dnsx.exe")) {
    if (-not (Test-Path "$BIN_DIR\$tool")) {
        Write-Host "ERROR: Required external scanner dependency missing" -ForegroundColor Red
        exit 1
    }
}
Write-Host "[+] External scanner dependencies ready" -ForegroundColor Green
Write-Host ""

# ============ Python virtual environment ============
$VENV_DIR = "$SCRIPT_DIR\backend\venv"
$VENV_PYTHON = "$VENV_DIR\Scripts\python.exe"
$VENV_OK = $false

if ((Test-Path $VENV_PYTHON)) {
    try {
        $null = & $VENV_PYTHON -c "import sys" 2>&1
        if ($LASTEXITCODE -eq 0) { $VENV_OK = $true }
    } catch {}
}

if (-not $VENV_OK) {
    if (Test-Path $VENV_DIR) {
        Write-Host "Existing virtual environment is broken. Recreating..." -ForegroundColor Yellow
        Remove-Item -Recurse -Force $VENV_DIR
    }
    Write-Host "Creating Python virtual environment..." -ForegroundColor Yellow
    & $PYTHON_BIN -m venv $VENV_DIR 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: Failed to create virtual environment." -ForegroundColor Red
        exit 1
    }
}

Write-Host "Installing backend dependencies..." -ForegroundColor Blue
& $VENV_PYTHON -m pip install -q -r "$SCRIPT_DIR\backend\requirements.txt" 2>&1 | ForEach-Object { if ($_ -is [string]) { Write-Host $_ } }
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Failed to install backend dependencies." -ForegroundColor Red
    exit 1
}

# ============ Frontend dependencies ============
if (-not (Test-Path "$SCRIPT_DIR\frontend\node_modules\react-scripts")) {
    Write-Host "Installing frontend dependencies..." -ForegroundColor Yellow
    Push-Location "$SCRIPT_DIR\frontend"
    & npm install 2>&1 | ForEach-Object { if ($_ -is [string]) { Write-Host $_ } }
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: npm install failed." -ForegroundColor Red
        Pop-Location
        exit 1
    }
    Pop-Location
}

# ============ Start services ============
Write-Host "Starting Backend API on port 3001..." -ForegroundColor Green
$backendProc = Start-Process -FilePath $VENV_PYTHON -ArgumentList "-m waitress --listen=0.0.0.0:3001 backend.wsgi:app" -WorkingDirectory $SCRIPT_DIR -PassThru -NoNewWindow

Start-Sleep -Seconds 2
if ($backendProc.HasExited) {
    Write-Host "ERROR: Backend failed to start." -ForegroundColor Red
    Write-Host "Common fixes:" -ForegroundColor Yellow
    Write-Host "  - Delete the venv and re-run: Remove-Item -Recurse backend\venv; .\run.ps1"
    Write-Host "  - Check if port 3001 is already in use: netstat -ano | findstr :3001"
    exit 1
}

Write-Host "Building Frontend UI for production..." -ForegroundColor Yellow
Push-Location "$SCRIPT_DIR\frontend"
& npm run build 2>&1 | ForEach-Object { if ($_ -is [string]) { Write-Host $_ } }
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Frontend build failed." -ForegroundColor Red
    Pop-Location
    exit 1
}
Pop-Location

Write-Host "Starting Frontend UI on port 3000..." -ForegroundColor Green
$frontendProc = Start-Process -FilePath "cmd.exe" -ArgumentList "/c npx -y serve -s build -l 3000" -WorkingDirectory "$SCRIPT_DIR\frontend" -PassThru -NoNewWindow

Write-Host ""
Write-Host "  $lightning JS RADAR - Services Started!" -ForegroundColor Green
Write-Host "  ----------------------------------" -ForegroundColor DarkGray
Write-Host "  Backend API:  http://localhost:3001" -ForegroundColor Blue
Write-Host "  Frontend UI:  http://localhost:3000" -ForegroundColor Blue
Write-Host ""
Write-Host "  Press Ctrl+C to stop all services" -ForegroundColor DarkGray
Write-Host ""

try {
    # Wait for either process to exit, or Ctrl+C
    while ($true) {
        if ($backendProc.HasExited -and $frontendProc.HasExited) {
            Write-Host "Both services have stopped." -ForegroundColor Yellow
            break
        }
        Start-Sleep -Seconds 1
    }
} finally {
    Write-Host "`nStopping services..." -ForegroundColor Yellow
    # Kill process trees (the processes may have spawned children)
    foreach ($proc in @($backendProc, $frontendProc)) {
        if (-not $proc.HasExited) {
            try {
                # Kill child processes first
                Get-CimInstance Win32_Process -Filter "ParentProcessId=$($proc.Id)" -ErrorAction SilentlyContinue |
                    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
                Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
            } catch {}
        }
    }
    Write-Host "Services stopped." -ForegroundColor Green
}
