#!/bin/bash

# dev.sh - One-command development runner for CMA Compiler

set -e

# Configuration
PORT=${PORT:-8000}
HOST=${HOST:-127.0.0.1}
LOG_DIR="./.logs"
LOG_FILE="$LOG_DIR/server.log"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

function usage() {
    echo "Usage: ./scripts/dev.sh [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --setup    Run setup.sh before starting"
    echo "  --help     Show this help message"
}

# Parse arguments
if [[ "$1" == "--setup" ]]; then
    ./scripts/setup.sh
elif [[ "$1" == "--help" ]]; then
    usage
    exit 0
fi

# 1. Check for virtual environment
if [ ! -d ".venv" ]; then
    echo -e "${RED}Error: .venv not found. Run ./scripts/setup.sh first.${NC}"
    exit 1
fi

# 2. Prepare logs
mkdir -p "$LOG_DIR"
touch "$LOG_FILE"

# 3. Start server
echo -e "${GREEN}==> Starting CMA Compiler on http://$HOST:$PORT${NC}"
echo -e "${GREEN}==> Logs: $LOG_FILE${NC}"
echo -e "${GREEN}==> Press Ctrl+C to stop${NC}"

# Define clean exit
trap "echo -e '\n${GREEN}==> Shutting down...${NC}'; exit 0" SIGINT SIGTERM

# Run uvicorn
# We use tee to show logs in console and file
# But uvicorn logs might be noisy, so we just tail the log file in a separate background if needed
# Actually, uvicorn is best run in foreground for Ctrl+C
.venv/bin/python3 -m uvicorn app.main:app \
    --host "$HOST" \
    --port "$PORT" \
    --reload \
    2>&1 | tee -a "$LOG_FILE"
