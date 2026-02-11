#!/bin/bash

############################################################################
#
#    Vault Container Entrypoint
#
############################################################################

CYAN='\033[38;5;45m'
DIM='\033[2m'
BOLD='\033[1m'
NC='\033[0m'

echo ""
echo -e "${CYAN}"
cat << 'BANNER'
    ██╗   ██╗ █████╗ ██╗   ██╗██╗  ████████╗
    ██║   ██║██╔══██╗██║   ██║██║  ╚══██╔══╝
    ██║   ██║███████║██║   ██║██║     ██║
    ╚██╗ ██╔╝██╔══██║██║   ██║██║     ██║
     ╚████╔╝ ██║  ██║╚██████╔╝███████╗██║
      ╚═══╝  ╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝
BANNER
echo -e "${NC}"

if [[ "$WAIT_FOR_DB" = true || "$WAIT_FOR_DB" = True ]]; then
    echo -e "    ${DIM}Waiting for database at ${DB_HOST}:${DB_PORT}...${NC}"
    for i in $(seq 1 60); do
        nc -z "${DB_HOST}" "${DB_PORT}" 2>/dev/null && break
        sleep 1
    done
    echo -e "    ${BOLD}Database ready.${NC}"
    echo ""
fi

case "$1" in
    chill)
        echo -e "    ${DIM}Mode: chill${NC}"
        echo -e "    ${BOLD}Container running.${NC}"
        echo ""
        while true; do sleep 18000; done
        ;;
    *)
        echo -e "    ${DIM}> $@${NC}"
        echo ""
        exec "$@"
        ;;
esac
