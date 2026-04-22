#!/data/data/com.termux/files/usr/bin/bash

# JS Discovery SaaS - Termux startup script
# This script is intentionally Termux-specific and does not replace run.sh/run.ps1.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/backend/venv"
VENV_PY="$VENV_DIR/bin/python"
BIN_DIR="$SCRIPT_DIR/scanner/bin"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

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
echo -e "${BLUE}[*] Starting JS Discovery in Termux mode${NC}"

# Auto-install python if missing
if ! command -v python >/dev/null 2>&1; then
    echo -e "${YELLOW}[*] Python not found. Installing via pkg...${NC}"
    pkg install python -y
fi

# Auto-install nodejs (provides node + npm) if missing
if ! command -v node >/dev/null 2>&1; then
    echo -e "${YELLOW}[*] Node.js not found. Installing via pkg...${NC}"
    pkg install nodejs -y
fi

# Verify remaining required tools
for tool in curl unzip tar; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        echo -e "${RED}[!] Missing required tool: $tool${NC}"
        echo "    Install with: pkg install $tool"
        exit 1
    fi
done

mkdir -p "$SCRIPT_DIR/data/scans" "$SCRIPT_DIR/backend/instance"
mkdir -p "$BIN_DIR"

get_latest_tag() {
    local repo="$1"
    local tag
    tag="$(curl -sfL "https://api.github.com/repos/${repo}/releases/latest" | sed -n 's/.*"tag_name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n1)"
    if [ -z "$tag" ]; then
        echo -e "${RED}[!] Failed to fetch latest tag for ${repo}${NC}"
        exit 1
    fi
    echo "$tag"
}

ensure_gospider() {
    if [ -x "$BIN_DIR/gospider" ]; then
        return
    fi
    if command -v gospider >/dev/null 2>&1; then
        return
    fi

    echo -e "${BLUE}[*] Building external dependency from source (Termux-native)...${NC}"

    _gospider_cleanup() {
        pkg uninstall golang -y 2>/dev/null || true
        chmod -R +w "$HOME/go" 2>/dev/null || true
        rm -rf "$HOME/go" 2>/dev/null || true
    }

    # Install golang temporarily to compile gospider natively for Termux
    pkg install golang -y

    # Build and install gospider into ~/go/bin (GOPATH pinned so binary always lands at $HOME/go/bin)
    if ! GOPATH="$HOME/go" GO111MODULE=on go install github.com/jaeles-project/gospider@latest; then
        echo -e "${RED}[!] Failed to build external dependency${NC}"
        _gospider_cleanup
        exit 1
    fi

    # Move the compiled binary into scanner/bin
    if [ -x "$HOME/go/bin/gospider" ]; then
        mv "$HOME/go/bin/gospider" "$BIN_DIR/gospider"
        chmod +x "$BIN_DIR/gospider"
    else
        echo -e "${RED}[!] External dependency binary not found after build${NC}"
        _gospider_cleanup
        exit 1
    fi

    # Uninstall golang and remove ~/go — no longer needed after binary is in scanner/bin
    _gospider_cleanup

    echo -e "${GREEN}[+] External dependency ready${NC}"
}

ensure_trufflehog() {
    if [ -x "$BIN_DIR/trufflehog" ]; then
        return
    fi
    if command -v trufflehog >/dev/null 2>&1; then
        return
    fi

    echo -e "${BLUE}[*] Installing external scanner dependency...${NC}"
    local tag version tmp_tgz tmp_extract url
    tag="$(get_latest_tag "trufflesecurity/trufflehog")"
    version="${tag#v}"
    url="https://github.com/trufflesecurity/trufflehog/releases/download/${tag}/trufflehog_${version}_linux_arm64.tar.gz"
    tmp_tgz="$(mktemp)"
    tmp_extract="$(mktemp -d)"
    if ! curl -sfL "$url" -o "$tmp_tgz"; then
        echo -e "${RED}[!] Failed to download external scanner dependency${NC}"
        rm -f "$tmp_tgz"
        rm -rf "$tmp_extract"
        exit 1
    fi
    tar -xzf "$tmp_tgz" -C "$tmp_extract"
    find "$tmp_extract" -name "trufflehog" -type f -exec mv {} "$BIN_DIR/trufflehog" \; 2>/dev/null || true
    rm -f "$tmp_tgz"
    rm -rf "$tmp_extract"
    if [ ! -x "$BIN_DIR/trufflehog" ]; then
        echo -e "${RED}[!] External scanner dependency binary not found in release archive${NC}"
        exit 1
    fi
    chmod +x "$BIN_DIR/trufflehog"
    echo -e "${GREEN}[+] External scanner dependency ready${NC}"
}

ensure_dnsx() {
    if [ -x "$BIN_DIR/dnsx" ]; then
        return
    fi
    if command -v dnsx >/dev/null 2>&1; then
        return
    fi

    echo -e "${BLUE}[*] Installing external scanner dependency...${NC}"
    local tag version tmp_zip tmp_extract url
    tag="$(get_latest_tag "projectdiscovery/dnsx")"
    version="${tag#v}"
    url="https://github.com/projectdiscovery/dnsx/releases/download/${tag}/dnsx_${version}_linux_arm64.zip"
    tmp_zip="$(mktemp)"
    tmp_extract="$(mktemp -d)"
    if ! curl -sfL "$url" -o "$tmp_zip"; then
        echo -e "${RED}[!] Failed to download external scanner dependency${NC}"
        rm -f "$tmp_zip"
        rm -rf "$tmp_extract"
        exit 1
    fi
    unzip -qo "$tmp_zip" -d "$tmp_extract"
    find "$tmp_extract" -name "dnsx" -type f -exec mv {} "$BIN_DIR/dnsx" \; 2>/dev/null || true
    rm -f "$tmp_zip"
    rm -rf "$tmp_extract"
    if [ ! -x "$BIN_DIR/dnsx" ]; then
        echo -e "${RED}[!] External scanner dependency binary not found in release archive${NC}"
        exit 1
    fi
    chmod +x "$BIN_DIR/dnsx"
    echo -e "${GREEN}[+] External scanner dependency ready${NC}"
}

echo -e "${BLUE}[*] Ensuring scanner binaries (Termux)...${NC}"
ensure_gospider
ensure_trufflehog
ensure_dnsx
echo -e "${GREEN}[+] All scanner binaries ready${NC}"

# Virtual environment
if [ ! -x "$VENV_PY" ]; then
    echo -e "${YELLOW}[*] Creating backend virtual environment...${NC}"
    rm -rf "$VENV_DIR"
    python -m venv "$VENV_DIR"
fi

echo -e "${BLUE}[*] Installing backend dependencies...${NC}"
"$VENV_PY" -m pip install --upgrade pip setuptools wheel
# Termux: psutil does not support Android build targets in many versions.
# Install all backend deps except psutil, then try psutil separately (non-fatal).
TERMUX_REQ_FILE="$SCRIPT_DIR/backend/requirements.termux.txt"
grep -viE '^\s*psutil([<=>!~].*)?\s*$' "$SCRIPT_DIR/backend/requirements.txt" > "$TERMUX_REQ_FILE"
"$VENV_PY" -m pip install -r "$TERMUX_REQ_FILE"

# psutil is optional on Termux; do not fail startup if it cannot build/install.
echo -e "${BLUE}[*] Trying to install optional psutil (non-fatal in Termux)...${NC}"
if ! "$VENV_PY" -m pip install psutil >/dev/null 2>&1; then
    echo -e "${YELLOW}[!] psutil install failed; continuing without RAM metrics.${NC}"
fi
rm -f "$TERMUX_REQ_FILE"

# Frontend dependencies/build
if [ ! -d "$SCRIPT_DIR/frontend/node_modules/react-scripts" ]; then
    echo -e "${YELLOW}[*] Installing frontend dependencies...${NC}"
    cd "$SCRIPT_DIR/frontend"
    npm install
fi

echo -e "${BLUE}[*] Building frontend...${NC}"
cd "$SCRIPT_DIR/frontend"
npm run build

# Ensure scanner binaries are available (either PATH or scanner/bin)
if ! command -v gospider >/dev/null 2>&1 && [ ! -x "$BIN_DIR/gospider" ]; then
    echo -e "${RED}[!] Required external scanner dependency missing${NC}"
    exit 1
fi
if ! command -v trufflehog >/dev/null 2>&1 && [ ! -x "$BIN_DIR/trufflehog" ]; then
    echo -e "${RED}[!] Required external scanner dependency missing${NC}"
    exit 1
fi

BACKEND_PID=""
FRONTEND_PID=""
cleanup() {
    echo ""
    echo -e "${YELLOW}[*] Stopping services...${NC}"
    [ -n "$FRONTEND_PID" ] && kill "$FRONTEND_PID" 2>/dev/null || true
    [ -n "$BACKEND_PID" ] && kill "$BACKEND_PID" 2>/dev/null || true
    wait 2>/dev/null || true
    echo -e "${GREEN}[+] Services stopped.${NC}"
}
trap cleanup INT TERM

echo -e "${GREEN}[*] Starting backend on :3001...${NC}"
cd "$SCRIPT_DIR"
# APP_ENV=development enables wildcard CORS so the app works when accessed via IP
APP_ENV=development "$VENV_PY" -m waitress --listen=0.0.0.0:3001 backend.wsgi:app &
BACKEND_PID=$!

echo -e "${GREEN}[*] Starting frontend on :3000...${NC}"
cd "$SCRIPT_DIR/frontend"
npx -y serve -s build -l 3000 &
FRONTEND_PID=$!

echo ""
echo -e "${GREEN}${BOLD}[+] JS Discovery services started${NC}"
echo "    Backend:  http://localhost:3001"
echo "    Frontend: http://localhost:3000"
echo "    Press Ctrl+C to stop"
echo ""

wait
