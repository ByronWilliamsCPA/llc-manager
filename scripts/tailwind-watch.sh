#!/bin/bash
# Tailwind CSS development watcher
# Downloads and runs Tailwind standalone CLI in watch mode

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TAILWIND_BIN="$PROJECT_ROOT/tailwindcss"
INPUT_CSS="$PROJECT_ROOT/src/llc_manager/static/css/input.css"
OUTPUT_CSS="$PROJECT_ROOT/src/llc_manager/static/css/output.css"

# Download Tailwind if not present
if [ ! -f "$TAILWIND_BIN" ]; then
    echo "Downloading Tailwind CSS standalone CLI..."
    ARCH=$(uname -m)
    OS=$(uname -s | tr '[:upper:]' '[:lower:]')

    case "$ARCH" in
        x86_64) ARCH_SUFFIX="x64" ;;
        arm64|aarch64) ARCH_SUFFIX="arm64" ;;
        *) echo "Unsupported architecture: $ARCH"; exit 1 ;;
    esac

    case "$OS" in
        linux) OS_SUFFIX="linux" ;;
        darwin) OS_SUFFIX="macos" ;;
        *) echo "Unsupported OS: $OS"; exit 1 ;;
    esac

    DOWNLOAD_URL="https://github.com/tailwindlabs/tailwindcss/releases/latest/download/tailwindcss-${OS_SUFFIX}-${ARCH_SUFFIX}"
    curl -sL "$DOWNLOAD_URL" -o "$TAILWIND_BIN"
    chmod +x "$TAILWIND_BIN"
    echo "Downloaded Tailwind CSS standalone CLI"
fi

# Run in watch mode
echo "Starting Tailwind CSS watcher..."
echo "  Input:  $INPUT_CSS"
echo "  Output: $OUTPUT_CSS"
echo ""
"$TAILWIND_BIN" -i "$INPUT_CSS" -o "$OUTPUT_CSS" --watch
