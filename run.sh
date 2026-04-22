#!/bin/bash

# JS Discovery SaaS - Startup Script

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

# Banner
echo ""
echo -e "${CYAN}${BOLD}    ╔══════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}${BOLD}    ║                                                  ║${NC}"
echo -e "${CYAN}${BOLD}    ║${NC}${YELLOW}${BOLD}          ⚡  J S   R A D A R  ⚡                ${NC}${CYAN}${BOLD}║${NC}"
echo -e "${CYAN}${BOLD}    ║${NC}                                                  ${CYAN}${BOLD}║${NC}"
echo -e "${CYAN}${BOLD}    ║${NC}${DIM}      JS Security Analysis Platform          ${NC}${CYAN}${BOLD}║${NC}"
echo -e "${CYAN}${BOLD}    ║${NC}                                                  ${CYAN}${BOLD}║${NC}"
echo -e "${CYAN}${BOLD}    ║${NC}${GREEN}           >> Built by Amjad Ali <<               ${NC}${CYAN}${BOLD}║${NC}"
echo -e "${CYAN}${BOLD}    ║                                                  ║${NC}"
echo -e "${CYAN}${BOLD}    ╚══════════════════════════════════════════════════╝${NC}"
echo ""

# ============ Detect distro family for install hints ============
detect_distro_family() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        case "$ID $ID_LIKE" in
            *debian*|*ubuntu*) echo "debian" ;;
            *arch*)            echo "arch" ;;
            *fedora*|*rhel*)   echo "fedora" ;;
            *suse*)            echo "suse" ;;
            *)                 echo "unknown" ;;
        esac
    else
        echo "unknown"
    fi
}
DISTRO_FAMILY=$(detect_distro_family)

# Helper: print distro-specific install command for a package
install_hint() {
    local pkg_desc="$1"
    local deb_pkg="$2"
    local arch_pkg="$3"
    local fed_pkg="$4"
    echo -e "${YELLOW}Install $pkg_desc for your system:${NC}"
    case "$DISTRO_FAMILY" in
        debian)  echo "  sudo apt install $deb_pkg" ;;
        arch)    echo "  sudo pacman -S $arch_pkg" ;;
        fedora)  echo "  sudo dnf install $fed_pkg" ;;
        *)
            echo "  Debian/Ubuntu/Kali/Parrot:  sudo apt install $deb_pkg"
            echo "  Arch/Manjaro:               sudo pacman -S $arch_pkg"
            echo "  Fedora/RHEL:                sudo dnf install $fed_pkg"
            ;;
    esac
}

# ============ Check required system tools ============
MISSING_TOOLS=0
for tool in curl unzip tar; do
    if ! command -v "$tool" &>/dev/null; then
        echo -e "${RED}ERROR: '$tool' is required but not found.${NC}"
        MISSING_TOOLS=1
    fi
done
[ "$MISSING_TOOLS" -eq 1 ] && exit 1

# ============ Find Python 3.8+ ============
PYTHON_BIN=""
for candidate in python3 python python3.13 python3.12 python3.11 python3.10; do
    if command -v "$candidate" &>/dev/null; then
        if "$candidate" -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" 2>/dev/null; then
            PYTHON_BIN="$candidate"
            break
        fi
    fi
done

if [ -z "$PYTHON_BIN" ]; then
    echo -e "${RED}ERROR: Python 3.8+ is required but not found.${NC}"
    install_hint "Python 3" "python3" "python" "python3"
    exit 1
fi
PYTHON_VERSION=$("$PYTHON_BIN" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo -e "${GREEN}[+] Using $PYTHON_BIN (Python $PYTHON_VERSION)${NC}"

# Check for Node.js / npm
if ! command -v node &>/dev/null || ! command -v npm &>/dev/null; then
    echo -e "${RED}ERROR: Node.js and npm are required but not found.${NC}"
    install_hint "Node.js" "nodejs npm" "nodejs npm" "nodejs npm"
    exit 1
fi
echo -e "${GREEN}[+] Using node $(node -v), npm $(npm -v)${NC}"

# Ensure data directories exist
mkdir -p "$SCRIPT_DIR/data/scans"
mkdir -p "$SCRIPT_DIR/backend/instance"

# ============ Download scanner tool binaries ============
BIN_DIR="$SCRIPT_DIR/scanner/bin"
mkdir -p "$BIN_DIR"

# Detect OS
RAW_OS="$(uname -s)"
case "$RAW_OS" in
    Linux*)  OS_LOWER="linux" ;;
    Darwin*) OS_LOWER="darwin" ;;
    *)       echo -e "${RED}Unsupported OS: $RAW_OS${NC}"; exit 1 ;;
esac

# Detect architecture
RAW_ARCH="$(uname -m)"
case "$RAW_ARCH" in
    x86_64)        ARCH_AMD="amd64"; ARCH_FULL="x86_64" ;;
    aarch64|arm64) ARCH_AMD="arm64"; ARCH_FULL="arm64" ;;
    *)             echo -e "${RED}Unsupported architecture: $RAW_ARCH${NC}"; exit 1 ;;
esac

# Helper: get latest release tag from GitHub API
get_latest_tag() {
    local repo="$1"
    local tag
    tag=$(curl -sfL "https://api.github.com/repos/${repo}/releases/latest" | grep '"tag_name"' | head -1 | sed -E 's/.*"tag_name":\s*"([^"]+)".*/\1/')
    if [ -z "$tag" ]; then
        echo -e "${RED}[-] Failed to fetch latest release tag for ${repo}. Check internet connection or GitHub API rate limit.${NC}" >&2
        exit 1
    fi
    echo "$tag"
}

# --- gospider ---
# Asset pattern: gospider_v{VERSION}_{os}_{arch}.zip (uses x86_64, macos)
if [ ! -f "$BIN_DIR/gospider" ]; then
    echo -e "${BLUE}[*] Installing external scanner dependency...${NC}"
    TAG=$(get_latest_tag "jaeles-project/gospider")
    VERSION="${TAG#v}"
    if [ "$OS_LOWER" = "darwin" ]; then GOSPIDER_OS="macos"; else GOSPIDER_OS="$OS_LOWER"; fi
    GOSPIDER_URL="https://github.com/jaeles-project/gospider/releases/download/${TAG}/gospider_${TAG}_${GOSPIDER_OS}_${ARCH_FULL}.zip"
    echo -e "${BLUE}[*] Downloading external scanner dependency ...${NC}"
    TEMP_FILE=$(mktemp)
    TEMP_EXTRACT=$(mktemp -d)
    if curl -sfL "$GOSPIDER_URL" -o "$TEMP_FILE"; then
        unzip -qo "$TEMP_FILE" -d "$TEMP_EXTRACT" 2>/dev/null
        # Binary may be nested in a subfolder — find and move it
        find "$TEMP_EXTRACT" -name "gospider" -type f -exec mv {} "$BIN_DIR/gospider" \;
        if [ -f "$BIN_DIR/gospider" ]; then
            chmod +x "$BIN_DIR/gospider"
            echo -e "${GREEN}[+] External scanner dependency ready${NC}"
        else
            echo -e "${RED}[-] External scanner dependency binary not found in downloaded archive${NC}"
            exit 1
        fi
    else
        echo -e "${RED}[-] Failed to download external scanner dependency${NC}"
        exit 1
    fi
    rm -rf "$TEMP_FILE" "$TEMP_EXTRACT"
fi

# --- trufflehog ---
# Asset pattern: trufflehog_{VERSION}_{os}_{arch}.tar.gz (uses darwin, amd64)
if [ ! -f "$BIN_DIR/trufflehog" ]; then
    echo -e "${BLUE}[*] Installing external scanner dependency...${NC}"
    TAG=$(get_latest_tag "trufflesecurity/trufflehog")
    VERSION="${TAG#v}"
    TRUFFLEHOG_URL="https://github.com/trufflesecurity/trufflehog/releases/download/${TAG}/trufflehog_${VERSION}_${OS_LOWER}_${ARCH_AMD}.tar.gz"
    echo -e "${BLUE}[*] Downloading external scanner dependency ...${NC}"
    TEMP_FILE=$(mktemp)
    if curl -sfL "$TRUFFLEHOG_URL" -o "$TEMP_FILE"; then
        tar -xzf "$TEMP_FILE" -C "$BIN_DIR" trufflehog 2>/dev/null
        if [ -f "$BIN_DIR/trufflehog" ]; then
            chmod +x "$BIN_DIR/trufflehog"
            echo -e "${GREEN}[+] External scanner dependency ready${NC}"
        else
            echo -e "${RED}[-] External scanner dependency binary not found in downloaded archive${NC}"
            exit 1
        fi
    else
        echo -e "${RED}[-] Failed to download external scanner dependency${NC}"
        exit 1
    fi
    rm -f "$TEMP_FILE"
fi

# --- dnsx ---
# Asset pattern: dnsx_{VERSION}_{os}_{arch}.zip (uses macOS for darwin, amd64)
if [ ! -f "$BIN_DIR/dnsx" ]; then
    echo -e "${BLUE}[*] Installing external scanner dependency...${NC}"
    TAG=$(get_latest_tag "projectdiscovery/dnsx")
    VERSION="${TAG#v}"
    if [ "$OS_LOWER" = "darwin" ]; then DNSX_OS="macOS"; else DNSX_OS="$OS_LOWER"; fi
    DNSX_URL="https://github.com/projectdiscovery/dnsx/releases/download/${TAG}/dnsx_${VERSION}_${DNSX_OS}_${ARCH_AMD}.zip"
    echo -e "${BLUE}[*] Downloading external scanner dependency ...${NC}"
    TEMP_FILE=$(mktemp)
    TEMP_EXTRACT=$(mktemp -d)
    if curl -sfL "$DNSX_URL" -o "$TEMP_FILE"; then
        unzip -qo "$TEMP_FILE" -d "$TEMP_EXTRACT" 2>/dev/null
        find "$TEMP_EXTRACT" -name "dnsx" -type f -exec mv {} "$BIN_DIR/dnsx" \;
        if [ -f "$BIN_DIR/dnsx" ]; then
            chmod +x "$BIN_DIR/dnsx"
            echo -e "${GREEN}[+] External scanner dependency ready${NC}"
        else
            echo -e "${RED}[-] External scanner dependency binary not found in downloaded archive${NC}"
            exit 1
        fi
    else
        echo -e "${RED}[-] Failed to download external scanner dependency${NC}"
        exit 1
    fi
    rm -rf "$TEMP_FILE" "$TEMP_EXTRACT"
fi

echo -e "${GREEN}[+] External scanner dependencies ready${NC}"
echo ""

# Check if virtual environment exists and is functional
VENV_DIR="$SCRIPT_DIR/backend/venv"
VENV_OK=false
if [ -d "$VENV_DIR" ] && [ -f "$VENV_DIR/bin/python" ] && [ -f "$VENV_DIR/bin/pip" ]; then
    # Verify the venv python actually runs (catches stale venvs copied from another machine)
    if "$VENV_DIR/bin/python" -c "import sys" 2>/dev/null; then
        VENV_OK=true
    else
        echo -e "${YELLOW}Existing virtual environment is broken (copied from another machine?). Recreating...${NC}"
        rm -rf "$VENV_DIR"
    fi
fi

if [ "$VENV_OK" = false ]; then
    echo -e "${YELLOW}Creating Python virtual environment...${NC}"
    # Remove broken venv if it exists
    [ -d "$VENV_DIR" ] && rm -rf "$VENV_DIR"

    # Check if venv module is available
    if ! "$PYTHON_BIN" -c "import venv" 2>/dev/null; then
        echo -e "${RED}ERROR: Python venv module is not installed.${NC}"
        install_hint "Python venv" "python${PYTHON_VERSION}-venv" "python" "python3"
        exit 1
    fi

    if ! "$PYTHON_BIN" -m venv "$VENV_DIR"; then
        echo -e "${RED}ERROR: Failed to create virtual environment.${NC}"
        install_hint "Python venv" "python${PYTHON_VERSION}-venv" "python" "python3"
        exit 1
    fi
fi

# Install dependencies using venv python -m pip (avoids PEP 668 and broken shebang issues)
echo -e "${BLUE}Installing backend dependencies...${NC}"
if ! "$VENV_DIR/bin/python" -m pip install -q -r "$SCRIPT_DIR/backend/requirements.txt"; then
    echo -e "${RED}ERROR: Failed to install backend dependencies.${NC}"
    echo -e "${YELLOW}Check your internet connection and try again.${NC}"
    exit 1
fi

# Check if node_modules is properly installed (react-scripts must exist)
if [ ! -d "$SCRIPT_DIR/frontend/node_modules/react-scripts" ]; then
    echo -e "${YELLOW}Installing frontend dependencies...${NC}"
    cd "$SCRIPT_DIR/frontend"
    rm -rf node_modules
    if ! npm install; then
        echo -e "${RED}ERROR: npm install failed. Check your internet connection and try again.${NC}"
        exit 1
    fi
    cd "$SCRIPT_DIR"
fi

# ============ Detect local IPs and set CORS_ORIGINS ============
# Collect all non-loopback IPv4 addresses so the UI works when accessed via
# any local network IP (e.g. http://192.168.x.x:3000), not just localhost.
BACKEND_PORT="${BACKEND_PORT:-3001}"
FRONTEND_PORT=3000

_cors="http://localhost:${FRONTEND_PORT},http://127.0.0.1:${FRONTEND_PORT}"
_network_urls=""

# hostname -I returns space-separated IPs (Linux); skip loopback
if command -v hostname &>/dev/null; then
    for _ip in $(hostname -I 2>/dev/null | tr ' ' '\n' | grep -E '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$' | grep -v '^127\.'); do
        _cors="${_cors},http://${_ip}:${FRONTEND_PORT}"
        _network_urls="${_network_urls}\n  ${BLUE}Network UI:${NC}   http://${_ip}:${FRONTEND_PORT}"
    done
fi

export CORS_ORIGINS="$_cors"
export BACKEND_PORT

# Trap Ctrl+C to cleanup — register early so no process is left orphaned
BACKEND_PID=""
FRONTEND_PID=""
cleanup() {
    echo ""
    echo -e "${YELLOW}Stopping services...${NC}"
    # Kill process groups to ensure child processes (node, scanner) also exit
    [ -n "$FRONTEND_PID" ] && kill -- -$FRONTEND_PID 2>/dev/null
    [ -n "$BACKEND_PID" ]  && kill -- -$BACKEND_PID 2>/dev/null
    # Fallback: kill PIDs directly if process group kill didn't work
    [ -n "$FRONTEND_PID" ] && kill $FRONTEND_PID 2>/dev/null
    [ -n "$BACKEND_PID" ]  && kill $BACKEND_PID 2>/dev/null
    wait 2>/dev/null
    echo -e "${GREEN}Services stopped.${NC}"
    exit 0
}
trap cleanup SIGINT SIGTERM

# Start backend in background
echo -e "${GREEN}Starting Backend API on port 3001...${NC}"
cd "$SCRIPT_DIR"
set -m  # Enable job control so background processes get their own process group
"$VENV_DIR/bin/gunicorn" --config backend/gunicorn.conf.py backend.wsgi:app &
BACKEND_PID=$!

# Wait and verify backend started successfully
sleep 2
if ! kill -0 $BACKEND_PID 2>/dev/null; then
    echo -e "${RED}ERROR: Backend failed to start. Check the error output above.${NC}"
    echo -e "${YELLOW}Common fixes:${NC}"
    echo -e "  - Delete the venv and re-run: rm -rf $VENV_DIR && ./run.sh"
    echo -e "  - Check if port 3001 is already in use: lsof -i :3001"
    exit 1
fi

# Start frontend
echo -e "${YELLOW}Building Frontend UI for production...${NC}"
cd "$SCRIPT_DIR/frontend"
npm run build

echo -e "${GREEN}Starting Frontend UI on port 3000...${NC}"
npx -y serve -s build -l 3000 &
FRONTEND_PID=$!

echo ""
echo -e "${GREEN}${BOLD}  ⚡ JS RADAR — Services Started!${NC}"
echo -e "${DIM}  ──────────────────────────────────${NC}"
echo -e "  ${BLUE}Backend API:${NC}  http://localhost:${BACKEND_PORT}"
echo -e "  ${BLUE}Frontend UI:${NC}  http://localhost:${FRONTEND_PORT}"
if [ -n "$_network_urls" ]; then
    echo -e "$_network_urls"
fi
echo ""
echo -e "  ${DIM}Press Ctrl+C to stop all services${NC}"
echo ""

# Wait for processes
wait
