#!/bin/bash

# setup.sh - Idempotent environment setup for CMA Compiler

set -e

# Colors for output
GREEN='\033[0;32m'
NC='\033[0m' # No Color

echo -e "${GREEN}==> Starting setup...${NC}"

# 1. Check for Python 3
if ! command -v python3 &> /dev/null; then
    echo "Error: python3 is not installed."
    exit 1
fi

# 2. Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo -e "${GREEN}==> Creating virtual environment...${NC}"
    python3 -m venv .venv
else
    echo -e "${GREEN}==> Virtual environment exists.${NC}"
fi

# 3. Install/Update dependencies
echo -e "${GREEN}==> Installing dependencies...${NC}"
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

# 4. Check for system dependencies (optional check)
if ! command -v weasyprint &> /dev/null; then
    echo -e "${GREEN}==> Checking WeasyPrint (via python)...${NC}"
    if ! .venv/bin/python3 -c "import weasyprint" &> /dev/null; then
        echo "Note: weasyprint python package failed to import. System libraries (pango, cairo) might be missing."
        echo "Refer to https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#installation for OS-specific steps."
    fi
fi

echo -e "${GREEN}==> Setup complete! You can now run ./scripts/dev.sh${NC}"
