#!/bin/bash

############################################################################
#
#    Agno Requirements Generator
#
#    Usage:
#      ./scripts/generate_requirements.sh           # Generate
#      ./scripts/generate_requirements.sh upgrade   # Generate with upgrade
#
############################################################################

set -e

CURR_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "${CURR_DIR}")"

# Colors
ORANGE='\033[38;5;208m'
DIM='\033[2m'
BOLD='\033[1m'
NC='\033[0m'

echo ""
echo -e "    ${ORANGE}▸${NC} ${BOLD}Generating requirements.txt${NC}"
echo ""

if command -v poetry &> /dev/null && poetry export --help >/dev/null 2>&1; then
    if [[ "$1" = "upgrade" ]]; then
        echo -e "    ${DIM}Mode: poetry upgrade${NC}"
        echo -e "    ${DIM}> poetry update${NC}"
        echo ""
        (cd "${REPO_ROOT}" && poetry update)
    else
        echo -e "    ${DIM}Mode: poetry export${NC}"
    fi

    echo -e "    ${DIM}> poetry export -f requirements.txt --without-hashes -o requirements.txt${NC}"
    echo ""
    (cd "${REPO_ROOT}" && poetry export -f requirements.txt --without-hashes -o "${REPO_ROOT}/requirements.txt")
else
    if [[ "$1" = "upgrade" ]]; then
        echo -e "    ${DIM}Mode: uv upgrade fallback${NC}"
        echo -e "    ${DIM}> uv pip compile pyproject.toml --no-cache --upgrade -o requirements.txt${NC}"
        echo ""
        UV_CUSTOM_COMPILE_COMMAND="./scripts/generate_requirements.sh upgrade" \
            uv pip compile ${REPO_ROOT}/pyproject.toml --no-cache --upgrade -o ${REPO_ROOT}/requirements.txt
    else
        echo -e "    ${DIM}Mode: uv standard fallback${NC}"
        echo -e "    ${DIM}> uv pip compile pyproject.toml --no-cache -o requirements.txt${NC}"
        echo ""
        UV_CUSTOM_COMPILE_COMMAND="./scripts/generate_requirements.sh" \
            uv pip compile ${REPO_ROOT}/pyproject.toml --no-cache -o ${REPO_ROOT}/requirements.txt
    fi
fi

echo ""
echo -e "    ${BOLD}Done.${NC}"
echo ""
