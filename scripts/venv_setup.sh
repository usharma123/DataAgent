#!/bin/bash

############################################################################
#
#    Agno Virtual Environment Setup
#
#    Usage: ./scripts/venv_setup.sh
#
############################################################################

set -e

CURR_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "${CURR_DIR}")"
VENV_DIR="${REPO_ROOT}/.venv"

# Colors
ORANGE='\033[38;5;208m'
DIM='\033[2m'
BOLD='\033[1m'
NC='\033[0m'

echo ""
echo -e "${ORANGE}"
cat << 'BANNER'
     █████╗  ██████╗ ███╗   ██╗ ██████╗
    ██╔══██╗██╔════╝ ████╗  ██║██╔═══██╗
    ███████║██║  ███╗██╔██╗ ██║██║   ██║
    ██╔══██║██║   ██║██║╚██╗██║██║   ██║
    ██║  ██║╚██████╔╝██║ ╚████║╚██████╔╝
    ╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═══╝ ╚═════╝
BANNER
echo -e "${NC}"
echo -e "    ${DIM}Virtual Environment Setup${NC}"
echo ""

# Preflight
if [[ -n "$VIRTUAL_ENV" ]]; then
    echo "    Deactivate your current venv first."
    exit 1
fi

if ! command -v poetry &> /dev/null; then
    echo "    poetry not found. Install: https://python-poetry.org/docs/"
    exit 1
fi

# Setup
echo -e "    ${DIM}Removing old environment...${NC}"
echo -e "    ${DIM}> rm -rf ${VENV_DIR}${NC}"
rm -rf ${VENV_DIR}

echo ""
echo -e "    ${DIM}Creating Poetry environment with Python 3.12...${NC}"
echo -e "    ${DIM}> POETRY_VIRTUALENVS_IN_PROJECT=true poetry env use 3.12${NC}"
(cd "${REPO_ROOT}" && POETRY_VIRTUALENVS_IN_PROJECT=true poetry env use 3.12 >/dev/null)

echo ""
echo -e "    ${DIM}Installing project with dev dependencies...${NC}"
echo -e "    ${DIM}> POETRY_VIRTUALENVS_IN_PROJECT=true poetry install --with dev${NC}"
(cd "${REPO_ROOT}" && POETRY_VIRTUALENVS_IN_PROJECT=true poetry install --with dev --no-interaction --sync >/dev/null)

# Copy activation command to clipboard
ACTIVATE_CMD="source .venv/bin/activate"
if command -v pbcopy &> /dev/null; then
    echo -n "${ACTIVATE_CMD}" | pbcopy
    CLIPBOARD_MSG="(Copied to clipboard)"
elif command -v xclip &> /dev/null; then
    echo -n "${ACTIVATE_CMD}" | xclip -selection clipboard
    CLIPBOARD_MSG="(Copied to clipboard)"
else
    CLIPBOARD_MSG=""
fi

echo ""
echo -e "    ${BOLD}Done.${NC}"
echo ""
echo -e "    ${DIM}Activate:${NC}  ${ACTIVATE_CMD} ${DIM}${CLIPBOARD_MSG}${NC}"
echo ""
