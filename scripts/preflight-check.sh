#!/usr/bin/env bash
# =============================================================================
# preflight-check.sh — Pre-deploy verification for Token RugCheck MCP
#
# Reads ops/manifest.yaml and validates the deployment target before pushing.
#
# Usage:
#   bash scripts/preflight-check.sh [--manifest PATH]
#
# Checks (in order):
#   1. SSH connectivity      (BLOCKING — if this fails, skip 2-7 and exit 2)
#   2. DNS resolution        (dig +short must match server.ip)
#   3. HTTPS reachability    (curl https://{domain}/health)
#   4. Disk space            (>2 GB free on server)
#   5. .env completeness     (server .env vs .env.example required fields)
#   6. Port availability     (80, 8000 not occupied by non-project processes)
#   7. Docker availability   (docker and docker compose exist on server)
#
# Output format: CHECK:<name>:PASS|FAIL|WARN:<detail>
# Summary line:  CHECK:SUMMARY:pass=N fail=N warn=N
# Exit codes:
#   0 = all pass
#   1 = fixable issues (AI can auto-fix)
#   2 = blocking failure (needs human intervention)
# =============================================================================
set -euo pipefail

# --- Defaults ---
MANIFEST="ops/manifest.yaml"
BLOCKING=0
EXIT_CODE=0

# --- Counters ---
PASS=0
FAIL=0
WARN=0

# --- Helpers ---
log_ok()   { echo "CHECK:$1:PASS:$2"; PASS=$((PASS + 1)); }
log_fail() { echo "CHECK:$1:FAIL:$2"; FAIL=$((FAIL + 1)); }
log_warn() { echo "CHECK:$1:WARN:$2"; WARN=$((WARN + 1)); }
log_info() { echo "CHECK:$1:INFO:$2"; }

# --- Remote exec helper ---
run_on_host() {
    if [ -n "$SERVER_IP" ]; then
        ssh -o ConnectTimeout=15 -o StrictHostKeyChecking=accept-new "${SSH_USER}@${SERVER_IP}" "$@"
    else
        eval "$@"
    fi
}

# --- Parse CLI args ---
while [[ $# -gt 0 ]]; do
    case "$1" in
        --manifest) MANIFEST="$2"; shift 2 ;;
        -h|--help)
            echo "Usage: bash scripts/preflight-check.sh [--manifest PATH]"
            echo ""
            echo "Pre-deploy verification — reads manifest.yaml and checks:"
            echo "  1. SSH connectivity       (BLOCKING)"
            echo "  2. DNS resolution"
            echo "  3. HTTPS reachability"
            echo "  4. Disk space (>2 GB)"
            echo "  5. .env completeness"
            echo "  6. Port availability (80, 8000)"
            echo "  7. Docker availability"
            echo ""
            echo "Output: CHECK:<name>:PASS|FAIL|WARN:<detail>"
            echo "Exit:   0=all pass  1=fixable  2=blocking"
            exit 0
            ;;
        *) echo "CHECK:ARGS:FAIL:Unknown argument: $1"; exit 1 ;;
    esac
done

# =============================================================================
# Parse manifest
# =============================================================================
if [ ! -f "$MANIFEST" ]; then
    echo "CHECK:MANIFEST:FAIL:Manifest not found at $MANIFEST"
    exit 2
fi

SERVER_IP=$(grep '^\s*ip:' "$MANIFEST" | head -1 | sed 's/.*:[[:space:]]*//' | tr -d '"' | tr -d "'")
SSH_USER=$(grep '^\s*ssh_user:' "$MANIFEST" | head -1 | sed 's/.*:[[:space:]]*//' | tr -d '"' | tr -d "'")
PROJECT_DIR=$(grep '^\s*project_dir:' "$MANIFEST" | head -1 | sed 's/.*:[[:space:]]*//' | tr -d '"' | tr -d "'")
DOMAIN_NAME=$(grep '^\s*name:' "$MANIFEST" | tail -1 | sed 's/.*:[[:space:]]*//' | tr -d '"' | tr -d "'")

# Fall back to root if ssh_user not set
SSH_USER="${SSH_USER:-root}"
PROJECT_DIR="${PROJECT_DIR:-/opt/token-rugcheck}"

log_info "MANIFEST" "server=$SERVER_IP user=$SSH_USER dir=$PROJECT_DIR domain=$DOMAIN_NAME"

# =============================================================================
# 1. SSH connectivity (BLOCKING)
# =============================================================================
log_info "SSH" "Testing SSH connectivity to ${SSH_USER}@${SERVER_IP}"

if ssh -o ConnectTimeout=15 -o StrictHostKeyChecking=accept-new -o BatchMode=yes "${SSH_USER}@${SERVER_IP}" "echo ok" >/dev/null 2>&1; then
    log_ok "SSH" "Connected to ${SSH_USER}@${SERVER_IP}"
else
    log_fail "SSH" "Cannot SSH to ${SSH_USER}@${SERVER_IP} — BLOCKING"
    echo ""
    echo "CHECK:SUMMARY:pass=$PASS fail=$FAIL warn=$WARN"
    exit 2
fi

# =============================================================================
# 2. DNS resolution
# =============================================================================
if [ -n "$DOMAIN_NAME" ]; then
    log_info "DNS" "Resolving $DOMAIN_NAME"

    RESOLVED_IP=$(dig +short "$DOMAIN_NAME" 2>/dev/null | tail -1)

    if [ -z "$RESOLVED_IP" ]; then
        log_fail "DNS" "$DOMAIN_NAME does not resolve"
    elif [ "$RESOLVED_IP" = "$SERVER_IP" ]; then
        log_ok "DNS" "$DOMAIN_NAME resolves to $RESOLVED_IP (matches server.ip)"
    else
        # Could be a CDN proxy (Cloudflare) — warn instead of fail
        log_warn "DNS" "$DOMAIN_NAME resolves to $RESOLVED_IP (server.ip is $SERVER_IP — CDN proxy?)"
    fi
else
    log_warn "DNS" "No domain.name in manifest — skipping DNS check"
fi

# =============================================================================
# 3. HTTPS reachability
# =============================================================================
if [ -n "$DOMAIN_NAME" ]; then
    log_info "HTTPS" "Checking https://$DOMAIN_NAME/health"

    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "https://$DOMAIN_NAME/health" 2>/dev/null) || HTTP_CODE="000"

    if [ "$HTTP_CODE" = "200" ]; then
        log_ok "HTTPS" "https://$DOMAIN_NAME/health returned 200"
    elif [ "$HTTP_CODE" = "000" ]; then
        log_fail "HTTPS" "https://$DOMAIN_NAME/health connection failed (DNS or TLS not configured)"
    else
        log_warn "HTTPS" "https://$DOMAIN_NAME/health returned $HTTP_CODE (expected 200)"
    fi
else
    log_warn "HTTPS" "No domain configured — skipping HTTPS check"
fi

# =============================================================================
# 4. Disk space (>2 GB free)
# =============================================================================
log_info "DISK" "Checking free disk space on server"

# Get available KB on the root partition
AVAIL_KB=$(run_on_host "df / | tail -1 | awk '{print \$4}'" 2>/dev/null) || AVAIL_KB="0"
# Strip non-numeric chars (some df outputs include suffixes)
AVAIL_KB=$(echo "$AVAIL_KB" | tr -dc '0-9')
AVAIL_KB="${AVAIL_KB:-0}"

# 2 GB = 2097152 KB
if [ "$AVAIL_KB" -ge 2097152 ] 2>/dev/null; then
    AVAIL_GB=$(awk "BEGIN {printf \"%.1f\", $AVAIL_KB / 1048576}")
    log_ok "DISK" "${AVAIL_GB} GB free on server"
elif [ "$AVAIL_KB" -gt 0 ] 2>/dev/null; then
    AVAIL_GB=$(awk "BEGIN {printf \"%.1f\", $AVAIL_KB / 1048576}")
    log_fail "DISK" "Only ${AVAIL_GB} GB free (need >2 GB)"
else
    log_fail "DISK" "Could not determine free disk space"
fi

# =============================================================================
# 5. .env completeness
# =============================================================================
log_info "ENV" "Comparing server .env against .env.example"

ENV_EXAMPLE=".env.example"
if [ ! -f "$ENV_EXAMPLE" ]; then
    log_warn "ENV" ".env.example not found locally — skipping .env check"
else
    # Extract required variable names from .env.example (non-comment, non-empty lines with =)
    REQUIRED_VARS=$(grep -E '^[A-Z_]+=' "$ENV_EXAMPLE" | sed 's/=.*//' | sort)

    # Get variable names from server .env
    SERVER_VARS=$(run_on_host "grep -E '^[A-Z_]+=' ${PROJECT_DIR}/.env 2>/dev/null | sed 's/=.*//' | sort" 2>/dev/null) || SERVER_VARS=""

    if [ -z "$SERVER_VARS" ]; then
        log_fail "ENV" "No .env found at ${PROJECT_DIR}/.env on server"
    else
        MISSING=""
        for var in $REQUIRED_VARS; do
            if ! echo "$SERVER_VARS" | grep -qx "$var"; then
                MISSING="$MISSING $var"
            fi
        done

        if [ -z "$MISSING" ]; then
            log_ok "ENV" "All required .env variables present on server"
        else
            MISSING_TRIMMED=$(echo "$MISSING" | xargs)
            log_fail "ENV" "Missing .env variables: $MISSING_TRIMMED"
        fi
    fi
fi

# =============================================================================
# 6. Port availability (80, 8000)
# =============================================================================
log_info "PORTS" "Checking ports 80 and 8000 on server"

for PORT in 80 8000; do
    # Get the process listening on the port (if any)
    LISTENER=$(run_on_host "ss -tlnp 2>/dev/null | grep ':${PORT} ' | head -1" 2>/dev/null) || LISTENER=""

    if [ -z "$LISTENER" ]; then
        log_ok "PORTS" "Port $PORT is free"
    elif echo "$LISTENER" | grep -qiE 'docker|caddy|nginx|ag402|uvicorn|node'; then
        log_ok "PORTS" "Port $PORT in use by project process"
    else
        log_warn "PORTS" "Port $PORT occupied by non-project process: $(echo "$LISTENER" | awk '{print $NF}')"
    fi
done

# =============================================================================
# 7. Docker availability
# =============================================================================
log_info "DOCKER" "Checking Docker availability on server"

DOCKER_OK=true

if run_on_host "command -v docker" >/dev/null 2>&1; then
    DOCKER_VER=$(run_on_host "docker --version 2>/dev/null" || echo "unknown")
    log_ok "DOCKER" "docker found ($DOCKER_VER)"
else
    log_fail "DOCKER" "docker command not found on server"
    DOCKER_OK=false
fi

if run_on_host "docker compose version" >/dev/null 2>&1; then
    COMPOSE_VER=$(run_on_host "docker compose version 2>/dev/null" || echo "unknown")
    log_ok "DOCKER" "docker compose found ($COMPOSE_VER)"
elif run_on_host "command -v docker-compose" >/dev/null 2>&1; then
    COMPOSE_VER=$(run_on_host "docker-compose --version 2>/dev/null" || echo "unknown")
    log_warn "DOCKER" "Only legacy docker-compose found ($COMPOSE_VER) — consider upgrading"
else
    log_fail "DOCKER" "docker compose not available on server"
    DOCKER_OK=false
fi

# =============================================================================
# Summary
# =============================================================================
echo ""
echo "CHECK:SUMMARY:pass=$PASS fail=$FAIL warn=$WARN"

if [ "$FAIL" -gt 0 ]; then
    exit 1
else
    exit 0
fi
