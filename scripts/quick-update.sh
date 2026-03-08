#!/usr/bin/env bash
# =============================================================================
# quick-update.sh — 快速更新已部署的 Token RugCheck MCP
#
# 用法:
#   bash scripts/quick-update.sh <server-ip> [domain]
#
# 示例:
#   bash scripts/quick-update.sh 140.82.49.221 rugcheck.aethercore.dev
#   bash scripts/quick-update.sh 140.82.49.221
#
# 功能:
#   1. 拉取最新代码
#   2. 备份 ag402-data (重放保护)
#   3. 重新构建 Docker 镜像
#   4. 重启服务 (零数据丢失)
#   5. 等待健康检查
#   6. 运行 5 层验证
#
# 适用场景:
#   - 代码更新后重新部署
#   - 配置微调后重启
#   - 新项目基于此模板改造后首次部署（.env 已手动配好）
# =============================================================================

set -euo pipefail

# --- Colors ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

info()    { printf "${BLUE}[INFO]${NC}  %s\n" "$1"; }
ok()      { printf "${GREEN}[PASS]${NC}  %s\n" "$1"; }
fail()    { printf "${RED}[FAIL]${NC}  %s\n" "$1"; }
warn()    { printf "${YELLOW}[WARN]${NC}  %s\n" "$1"; }
step()    { printf "\n${BOLD}${CYAN}━━━ Step %s: %s ━━━${NC}\n\n" "$1" "$2"; }

# --- Args ---
SERVER_IP="${1:-}"
DOMAIN="${2:-}"
PROJECT_DIR="/opt/token-rugcheck"
COMPOSE_FILES="-f docker-compose.yml -f docker-compose.prod.yml"

if [[ -z "$SERVER_IP" ]]; then
    echo "用法: bash scripts/quick-update.sh <server-ip> [domain]"
    echo "示例: bash scripts/quick-update.sh 140.82.49.221 rugcheck.aethercore.dev"
    exit 1
fi

remote() {
    ssh -o ConnectTimeout=15 -o StrictHostKeyChecking=accept-new "root@${SERVER_IP}" "$@"
}

printf "\n${BOLD}${CYAN}╔══════════════════════════════════════════════════════════╗${NC}\n"
printf "${BOLD}${CYAN}║           快速更新 — Token RugCheck MCP                  ║${NC}\n"
printf "${BOLD}${CYAN}╚══════════════════════════════════════════════════════════╝${NC}\n\n"

# --- Step 1: 验证 SSH 和当前状态 ---
step "1/6" "检查当前部署状态"

if ! remote "echo SSH_OK" 2>/dev/null | grep -q "SSH_OK"; then
    fail "SSH 连接失败: root@${SERVER_IP}"
    exit 1
fi
ok "SSH 连接正常"

# 检查项目目录和 .env 存在
if ! remote "test -f ${PROJECT_DIR}/.env"; then
    fail ".env 文件不存在。请先运行一键部署: bash scripts/deploy-oneclick.sh"
    exit 1
fi
ok ".env 配置文件存在"

# 当前容器状态
RUNNING=$(remote "docker ps --format '{{.Names}}' | grep token | wc -l" 2>/dev/null) || RUNNING=0
info "当前运行中的容器: $RUNNING"

# --- Step 2: 拉取最新代码 ---
step "2/6" "拉取最新代码"

GIT_OUTPUT=$(remote "cd $PROJECT_DIR && git pull origin main 2>&1") || true
if echo "$GIT_OUTPUT" | grep -qE "Aborting|CONFLICT|error:|fatal:"; then
    warn "git pull 失败，尝试自动 stash 后重试..."
    STASH_OUTPUT=$(remote "cd $PROJECT_DIR && git stash --include-untracked && git pull origin main 2>&1") || true
    if echo "$STASH_OUTPUT" | grep -qE "Aborting|CONFLICT|error:|fatal:"; then
        fail "git pull 重试仍失败！请手动解决："
        fail "  ssh root@${SERVER_IP}"
        fail "  cd $PROJECT_DIR && git status"
        exit 1
    fi
    echo "$STASH_OUTPUT" | tail -5
    ok "git stash + pull 成功"
elif echo "$GIT_OUTPUT" | grep -q "Already up to date"; then
    info "代码已是最新版本"
else
    echo "$GIT_OUTPUT" | tail -5
    ok "代码已更新"
fi

# --- Step 3: 备份数据 ---
step "3/6" "备份 ag402-data"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_CMD="
mkdir -p /opt/backups/rugcheck
VOLUME_NAME=\$(docker volume ls --format '{{.Name}}' | grep ag402-data | head -1)
if [[ -n \"\$VOLUME_NAME\" ]]; then
    docker run --rm -v \"\${VOLUME_NAME}:/data:ro\" -v /opt/backups/rugcheck:/backup alpine:3.19 \
        sh -c \"cd /data && tar czf /backup/ag402-data_${TIMESTAMP}.tar.gz .\" 2>/dev/null
    echo \"BACKUP_OK\"
    # 保留最近 30 份
    ls -1t /opt/backups/rugcheck/ag402-data_*.tar.gz 2>/dev/null | tail -n +31 | xargs -r rm -f
else
    echo \"BACKUP_SKIP\"
fi
"
BACKUP_RESULT=$(remote "$BACKUP_CMD" 2>/dev/null) || BACKUP_RESULT="BACKUP_SKIP"
if echo "$BACKUP_RESULT" | grep -q "BACKUP_OK"; then
    ok "数据已备份: /opt/backups/rugcheck/ag402-data_${TIMESTAMP}.tar.gz"
else
    warn "跳过备份 (volume 不存在或服务未运行过)"
fi

# --- Step 4: 重新构建并启动 ---
step "4/6" "重新构建并启动服务"

info "停止当前服务..."
remote "cd $PROJECT_DIR && docker compose $COMPOSE_FILES down --remove-orphans --timeout 30" 2>&1 || true

# 强制清理残留容器和端口占用
remote "docker ps -a --filter 'name=token-rugcheck' -q | xargs -r docker rm -f" 2>&1 || true
for PORT in 80 8000; do
    if remote "ss -tlnp 2>/dev/null | grep -q ':${PORT} '" 2>/dev/null; then
        PID=$(remote "ss -tlnp 2>/dev/null | grep ':${PORT} ' | grep -oP 'pid=\K[0-9]+' | head -1" 2>/dev/null) || PID=""
        if [ -n "$PID" ]; then
            warn "端口 ${PORT} 仍被占用 (PID=$PID)，强制释放..."
            remote "kill -9 $PID" 2>/dev/null || true
            sleep 2
        fi
    fi
done

info "构建 Docker 镜像 (含 ag402 依赖更新)..."
BUILD_START=$(date +%s)
if remote "cd $PROJECT_DIR && docker compose $COMPOSE_FILES build --no-cache" 2>&1 | tail -5; then
    BUILD_END=$(date +%s)
    ok "构建完成 ($(( BUILD_END - BUILD_START ))s)"
else
    fail "构建失败！查看日志: ssh root@${SERVER_IP} 'cd $PROJECT_DIR && docker compose $COMPOSE_FILES build 2>&1 | tail -50'"
    exit 1
fi

info "启动服务..."
remote "cd $PROJECT_DIR && docker compose $COMPOSE_FILES up -d" 2>&1
ok "服务已启动"

# --- Step 5: 等待健康检查 ---
step "5/6" "等待服务就绪"

MAX_WAIT=120
ELAPSED=0
AUDIT_OK=false
GW_OK=false

while [ "$ELAPSED" -lt "$MAX_WAIT" ]; do
    if [ "$AUDIT_OK" = false ]; then
        HTTP=$(remote "curl -s -o /dev/null -w '%{http_code}' --max-time 3 http://localhost:8000/health" 2>/dev/null) || HTTP="000"
        [ "$HTTP" = "200" ] && AUDIT_OK=true && ok "审计服务就绪 (${ELAPSED}s)"
    fi
    if [ "$GW_OK" = false ]; then
        HTTP=$(remote "curl -s -o /dev/null -w '%{http_code}' --max-time 3 http://localhost:80/health" 2>/dev/null) || HTTP="000"
        [ "$HTTP" = "200" ] && GW_OK=true && ok "支付网关就绪 (${ELAPSED}s)"
    fi
    [ "$AUDIT_OK" = true ] && [ "$GW_OK" = true ] && break
    sleep 5
    ELAPSED=$((ELAPSED + 5))
    printf "  ⏳ %ds (审计=%s, 网关=%s)\r" "$ELAPSED" "$AUDIT_OK" "$GW_OK"
done
printf "\n"

if [ "$AUDIT_OK" = false ] || [ "$GW_OK" = false ]; then
    fail "服务启动超时 (${MAX_WAIT}s)"
    warn "容器日志:"
    remote "cd $PROJECT_DIR && docker compose logs --tail 20" 2>&1 | tail -20 || true
    exit 1
fi

# --- Step 6: 验证 ---
step "6/6" "快速验证"

PASS=0
FAIL=0

# 容器状态
CONTAINERS=$(remote "docker ps --format '{{.Names}} {{.Status}}' | grep token" 2>&1) || true
if echo "$CONTAINERS" | grep -q "Up"; then
    ok "容器正常运行"
    PASS=$((PASS + 1))
else
    fail "容器异常"
    FAIL=$((FAIL + 1))
fi

# 外部 IP 访问
EXT_HTTP=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "http://${SERVER_IP}:80/health" 2>/dev/null) || EXT_HTTP="000"
if [ "$EXT_HTTP" = "200" ]; then
    ok "外部访问正常 (IP:80)"
    PASS=$((PASS + 1))
else
    fail "外部访问失败: $EXT_HTTP"
    FAIL=$((FAIL + 1))
fi

# 域名 HTTPS
if [ -n "$DOMAIN" ]; then
    DOMAIN_HTTP=$(curl -s -o /dev/null -w "%{http_code}" --max-time 15 "https://${DOMAIN}/health" 2>/dev/null) || DOMAIN_HTTP="000"
    if [ "$DOMAIN_HTTP" = "200" ]; then
        ok "HTTPS 域名正常: $DOMAIN"
        PASS=$((PASS + 1))
    else
        fail "HTTPS 域名异常: $DOMAIN ($DOMAIN_HTTP)"
        FAIL=$((FAIL + 1))
    fi
fi

# 402 支付墙
GW_URL="${DOMAIN:+https://$DOMAIN}"
GW_URL="${GW_URL:-http://${SERVER_IP}:80}"
MINT="DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"
PW_HTTP=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "$GW_URL/v1/audit/$MINT" 2>/dev/null) || PW_HTTP="000"
if [ "$PW_HTTP" = "402" ] || [ "$PW_HTTP" = "200" ]; then
    ok "功能测试正常 (audit=$PW_HTTP)"
    PASS=$((PASS + 1))
else
    fail "功能测试异常: $PW_HTTP"
    FAIL=$((FAIL + 1))
fi

# 读取当前模式
MODE=$(remote "grep '^X402_MODE=' $PROJECT_DIR/.env | cut -d= -f2" 2>/dev/null) || MODE="unknown"
PRICE=$(remote "grep '^AG402_PRICE=' $PROJECT_DIR/.env | cut -d= -f2" 2>/dev/null) || PRICE="unknown"

# 总结
printf "\n${BOLD}${CYAN}════════════════════════════════════════════════════════════${NC}\n"
if [ "$FAIL" -eq 0 ]; then
    printf "${GREEN}${BOLD}  ✅ 更新成功！所有验证通过 ($PASS/$PASS)${NC}\n"
else
    printf "${YELLOW}${BOLD}  ⚠️  更新完成，$FAIL 项验证未通过${NC}\n"
fi
printf "\n"
printf "  模式: %s | 价格: %s USDC | 服务器: %s\n" "$MODE" "$PRICE" "$SERVER_IP"
if [ -n "$DOMAIN" ]; then
    printf "  入口: https://%s\n" "$DOMAIN"
fi
printf "${BOLD}${CYAN}════════════════════════════════════════════════════════════${NC}\n\n"

exit "$FAIL"
