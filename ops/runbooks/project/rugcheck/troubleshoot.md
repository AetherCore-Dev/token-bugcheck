# Runbook: Troubleshoot — Token RugCheck

**Scope**: Project-specific — Token RugCheck diagnostic trees.
**When to use**: When any other runbook encounters a failure and references this document.
**Format**: Symptom-based diagnostic trees -- jump to the matching symptom, follow the diagnosis.

---

## Symptom: Container not starting

### Diagnosis
1. Check container logs -> `ssh root@140.82.49.221 "cd /opt/token-rugcheck && docker compose -f docker-compose.yml -f docker-compose.prod.yml logs --tail=50"` -> if "port already in use" then port conflict
2. Check which container failed -> `ssh root@140.82.49.221 "cd /opt/token-rugcheck && docker compose -f docker-compose.yml -f docker-compose.prod.yml ps -a"` -> identify if `token-rugcheck-audit-server-1` or `token-rugcheck-ag402-gateway-1` or both
3. Check .env file exists -> `ssh root@140.82.49.221 "test -f /opt/token-rugcheck/.env && echo EXISTS || echo MISSING"` -> if MISSING then .env issue
4. Check Docker daemon -> `ssh root@140.82.49.221 "docker info > /dev/null 2>&1 && echo OK || echo FAIL"` -> if FAIL then Docker daemon issue

### Common Causes
- **Port conflict on 8000**: Another process occupying the audit-server port. Check with `ssh root@140.82.49.221 "ss -tlnp | grep 8000"`.
- **Port conflict on 80/8001**: Another process occupying the gateway ports. Check with `ssh root@140.82.49.221 "ss -tlnp | grep -E ':(80|8001)\s'"`.
- **Missing .env**: Containers require environment variables. Regenerate with `scripts/generate-env.sh`.
- **Docker daemon stopped**: systemd service not running. Restart with `systemctl restart docker`.
- **Image build failure cached**: Stale build cache causing repeated failures. Clear with `docker compose build --no-cache`.

### Resolution
- Port conflict -> `ssh root@140.82.49.221 "cd /opt/token-rugcheck && docker compose -f docker-compose.yml -f docker-compose.prod.yml down && docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d"` (releases the ports first)
- Missing .env -> follow 00-preflight.md Step 2 to regenerate
- Docker daemon -> `ssh root@140.82.49.221 "sudo systemctl restart docker"` then retry
- Stale cache -> `ssh root@140.82.49.221 "cd /opt/token-rugcheck && docker compose -f docker-compose.yml -f docker-compose.prod.yml build --no-cache && docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d"`

---

## Symptom: Audit-server port 8000 issues

### Diagnosis
1. Check audit-server container specifically -> `ssh root@140.82.49.221 "docker logs token-rugcheck-audit-server-1 --tail=30"` -> look for startup errors, import failures, or uncaught exceptions
2. Check port binding -> `ssh root@140.82.49.221 "curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/health"` -> if connection refused then process not listening
3. Check if process is inside the container -> `ssh root@140.82.49.221 "docker exec token-rugcheck-audit-server-1 ss -tlnp | grep 8000"` -> if empty then app not binding correctly

### Common Causes
- **Audit engine import error**: Missing Python dependency or incompatible version in the audit-server container.
- **Configuration error**: Missing or invalid environment variables for the audit engine (API keys for DexScreener, GoPlus, RugCheck).
- **Process crashed inside container**: Application exited but container restart policy keeps restarting it. Logs show repeated crash-restart cycle.
- **Wrong port binding**: Application listens on a different port than 8000 inside the container.

### Resolution
- Import error -> check Dockerfile for missing dependencies; rebuild with `docker compose build --no-cache`
- Configuration error -> verify .env has all required API keys; regenerate with `scripts/generate-env.sh` if needed
- Process crash -> fix the root cause from logs; most common: missing env var or upstream API key invalid
- Wrong port -> verify port mapping in docker-compose.yml matches the application's listen port (should be 8000)

---

## Symptom: ag402-gateway port 80/8001 issues

### Diagnosis
1. Check gateway container specifically -> `ssh root@140.82.49.221 "docker logs token-rugcheck-ag402-gateway-1 --tail=30"` -> look for startup errors
2. Check port 80 binding -> `ssh root@140.82.49.221 "curl -s -o /dev/null -w '%{http_code}' http://localhost:80/health"` -> if connection refused then gateway not listening on 80
3. Check port 8001 binding -> `ssh root@140.82.49.221 "curl -s -o /dev/null -w '%{http_code}' http://localhost:8001/health"` -> if connection refused then gateway management port not listening
4. Check if port 80 is occupied by another service -> `ssh root@140.82.49.221 "ss -tlnp | grep ':80 '"` -> if another process (nginx, apache) is using port 80

### Common Causes
- **Port 80 occupied by system nginx/apache**: A pre-existing web server is using port 80. The gateway cannot bind.
- **ag402 wallet configuration error**: Missing or invalid wallet private key in .env prevents gateway startup.
- **Upstream audit-server unreachable**: Gateway cannot proxy to audit-server on port 8000 if audit-server is down.
- **ag402 mode mismatch**: `AG402_MODE` in .env does not match the blockchain network (devnet vs mainnet).

### Resolution
- Port 80 occupied -> stop the conflicting service: `ssh root@140.82.49.221 "sudo systemctl stop nginx"` or `sudo systemctl stop apache2`; then restart the gateway
- Wallet config error -> verify wallet-related variables in .env; regenerate with `scripts/generate-env.sh`
- Upstream unreachable -> fix audit-server first (see "Audit-server port 8000 issues" above), then restart gateway
- Mode mismatch -> fix `AG402_MODE` in .env to match manifest blockchain.network, restart containers

---

## Symptom: BONK mint test failures

### Diagnosis
1. Test the BONK endpoint directly -> `ssh root@140.82.49.221 "curl -s -w '\n%{http_code}' http://localhost:8000/v1/audit/DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"` -> check status and response body
2. Check if 402 is returned via gateway -> `curl -s -o /dev/null -w '%{http_code}' https://rugcheck.aethercore.dev/v1/audit/DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263` -> should be 402
3. Check audit-server logs for the request -> `ssh root@140.82.49.221 "docker logs token-rugcheck-audit-server-1 --tail=20"` -> look for errors during BONK audit processing
4. Validate response fields -> check for `action.risk_score`, `action.is_safe`, `metadata.data_sources` in the response body

### Common Causes
- **BONK mint address not recognized**: The audit engine does not support the specific mint address format or the address is invalid.
- **Upstream API timeout**: DexScreener, GoPlus, or RugCheck API is slow or unreachable, causing the audit to fail or return incomplete data.
- **Missing response fields**: Audit engine returns a response but is missing `action.risk_score`, `action.is_safe`, or `metadata.data_sources`.
- **Rate limiting**: Upstream APIs rate-limiting the server's IP address, causing intermittent failures.

### Resolution
- Mint not recognized -> verify the BONK mint address `DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263` is correct; check audit engine logs for parsing errors
- Upstream timeout -> see "Upstream API timeout" symptom below; may need to increase timeout or retry
- Missing fields -> check audit engine logic for field population; one or more data sources may have returned empty data
- Rate limiting -> wait 60 seconds and retry; if persistent, check upstream API quotas

---

## Symptom: Upstream API timeout (DexScreener / GoPlus / RugCheck)

### Diagnosis
1. Test DexScreener directly from server -> `ssh root@140.82.49.221 "curl -s -o /dev/null -w '%{http_code}' --max-time 10 https://api.dexscreener.com/latest/dex/tokens/DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"` -> if timeout or non-200 then DexScreener issue
2. Test GoPlus directly from server -> `ssh root@140.82.49.221 "curl -s -o /dev/null -w '%{http_code}' --max-time 10 https://api.gopluslabs.io/api/v1/token_security/solana?contract_addresses=DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"` -> if timeout or non-200 then GoPlus issue
3. Test RugCheck API directly from server -> `ssh root@140.82.49.221 "curl -s -o /dev/null -w '%{http_code}' --max-time 10 https://api.rugcheck.xyz/v1/tokens/DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263/report"` -> if timeout or non-200 then RugCheck API issue
4. Check DNS resolution from server -> `ssh root@140.82.49.221 "dig +short api.dexscreener.com api.gopluslabs.io api.rugcheck.xyz"` -> if empty then DNS resolution failing on server

### Common Causes
- **Upstream API down**: The external data source API is experiencing an outage. This is outside our control.
- **DNS resolution failure on server**: Server cannot resolve upstream API hostnames. Check `/etc/resolv.conf`.
- **Network egress blocked**: Firewall rules on the server or hosting provider blocking outbound HTTPS.
- **Rate limiting by upstream**: Server IP has been rate-limited by one or more upstream APIs.
- **SSL certificate issue**: Server's CA certificates outdated, causing SSL handshake failure with upstream APIs.

### Resolution
- Upstream down -> **degrade-continue**: log which API is down, the audit may still return partial results from other sources. No rollback needed.
- DNS failure -> `ssh root@140.82.49.221 "echo 'nameserver 8.8.8.8' >> /etc/resolv.conf"` (add Google DNS as fallback)
- Network blocked -> escalate-to-human ("outbound HTTPS from 140.82.49.221 appears blocked -- check firewall rules")
- Rate limited -> wait and retry; if persistent, escalate-to-human ("upstream API rate limiting -- may need API key upgrade")
- SSL issue -> `ssh root@140.82.49.221 "apt-get update && apt-get install -y ca-certificates"` then retry

---

## Symptom: ag402 ledger/wallet issues

### Diagnosis
1. Check ledger database exists -> `ssh root@140.82.49.221 "ls -la /opt/token-rugcheck/data/ledger.db"` -> if missing then ledger not initialized
2. Check ledger database integrity -> `ssh root@140.82.49.221 "sqlite3 /opt/token-rugcheck/data/ledger.db 'PRAGMA integrity_check;'"` -> if not "ok" then database corrupted
3. Check wallet balance -> `ssh root@140.82.49.221 "cd /opt/token-rugcheck && python3 -c \"from ag402 import check_balance; print(check_balance())\""` -> if zero or error then wallet issue
4. Check AG402_MODE in .env -> `ssh root@140.82.49.221 "grep AG402_MODE /opt/token-rugcheck/.env"` -> verify matches manifest blockchain.network

### Common Causes
- **Ledger database missing**: First deploy or data directory was cleaned. ag402 will recreate it on first transaction.
- **Ledger database corrupted**: SQLite file is corrupted or locked by a crashed process.
- **Ledger database locked**: Another process or container has a lock on the SQLite file.
- **Wallet unfunded**: Seller wallet has zero USDC balance, or buyer test wallet is unfunded.
- **AG402_MODE mismatch**: Running in devnet mode with mainnet wallet or vice versa.
- **Wallet private key invalid**: The wallet key in .env is malformed or for the wrong network.

### Resolution
- Ledger missing -> non-critical, ag402 will recreate on first transaction. Restart containers to trigger: `ssh root@140.82.49.221 "cd /opt/token-rugcheck && docker compose -f docker-compose.yml -f docker-compose.prod.yml restart"`
- Ledger corrupted -> restore from backup: `bash scripts/backup-data.sh --restore`; if no backup, delete and let ag402 recreate: `ssh root@140.82.49.221 "rm /opt/token-rugcheck/data/ledger.db" && ssh root@140.82.49.221 "cd /opt/token-rugcheck && docker compose -f docker-compose.yml -f docker-compose.prod.yml restart"`
- Ledger locked -> find and kill the locking process: `ssh root@140.82.49.221 "fuser /opt/token-rugcheck/data/ledger.db"` then restart containers
- Wallet unfunded -> escalate-to-human ("wallet needs USDC funding -- Level 3 action required")
- Mode mismatch -> fix `AG402_MODE` in .env, restart containers
- Invalid key -> escalate-to-human ("wallet private key in .env appears invalid -- regenerate or verify")

---

## Symptom: Health check failing

### Diagnosis
1. Check both containers are running -> `ssh root@140.82.49.221 "cd /opt/token-rugcheck && docker compose -f docker-compose.yml -f docker-compose.prod.yml ps"` -> if no containers, see "Container not starting"
2. Check audit-server health -> `ssh root@140.82.49.221 "curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/health"` -> if connection refused then audit-server not listening
3. Check gateway health -> `ssh root@140.82.49.221 "curl -s -o /dev/null -w '%{http_code}' http://localhost:80/health"` -> if connection refused then gateway not listening
4. Check application logs -> `ssh root@140.82.49.221 "cd /opt/token-rugcheck && docker compose -f docker-compose.yml -f docker-compose.prod.yml logs --tail=30"` -> look for startup errors

### Common Causes
- **Process crashed inside container**: Application exited but container restart policy keeps restarting it.
- **Wrong port binding**: Application listens on a different port than expected (8000 for audit, 80 for gateway).
- **Application startup error**: Missing dependency or configuration error preventing the app from becoming healthy.

### Resolution
- Process crash -> fix the root cause in application code or configuration; check logs for the specific error
- Wrong port -> verify port mappings in docker-compose.yml and docker-compose.prod.yml
- Startup error -> check .env for required variables; ensure all dependencies are available

---

## Symptom: HTTPS failing

### Diagnosis
1. Check DNS resolution -> `dig +short rugcheck.aethercore.dev` -> if empty or not `140.82.49.221` then DNS issue
2. Check HTTP works on IP -> `curl -s -o /dev/null -w '%{http_code}' http://140.82.49.221:80/health` -> if 200 then app is fine, HTTPS/DNS is the issue
3. Check Cloudflare SSL mode -> Cloudflare dashboard > SSL/TLS > Overview -> should be "flexible" per manifest
4. Check certificate -> `echo | openssl s_client -connect rugcheck.aethercore.dev:443 -servername rugcheck.aethercore.dev 2>/dev/null | openssl x509 -noout -dates` -> if expired or not found then certificate issue

### Common Causes
- **DNS not pointing to server**: `rugcheck.aethercore.dev` resolves to wrong IP. Requires Cloudflare DNS update (Level 3 -- escalate-to-human).
- **Cloudflare SSL mode mismatch**: Mode should be "flexible" per manifest; "Full (strict)" would cause errors since no origin certificate is configured.
- **Certificate expired**: Cloudflare edge certificate needs renewal.
- **Cloudflare proxy not enabled**: DNS record is "DNS only" (grey cloud) instead of "Proxied" (orange cloud).

### Resolution
- DNS wrong -> escalate-to-human ("DNS A record for rugcheck.aethercore.dev does not point to 140.82.49.221 -- update needed in Cloudflare")
- SSL mode -> escalate-to-human ("Cloudflare SSL mode may need adjustment -- current mode causing issues for rugcheck.aethercore.dev")
- Certificate expired -> escalate-to-human ("SSL certificate for rugcheck.aethercore.dev needs renewal")
- Proxy not enabled -> escalate-to-human ("Cloudflare proxy (orange cloud) needs to be enabled for rugcheck.aethercore.dev")

---

## Symptom: Build failing

### Diagnosis
1. Check disk space -> `ssh root@140.82.49.221 "df -h / | tail -1"` -> if less than 2 GB free then disk space issue
2. Check Docker daemon -> `ssh root@140.82.49.221 "docker info > /dev/null 2>&1 && echo OK || echo FAIL"` -> if FAIL then Docker daemon issue
3. Check build logs -> `ssh root@140.82.49.221 "cd /opt/token-rugcheck && docker compose -f docker-compose.yml -f docker-compose.prod.yml build 2>&1 | tail -30"` -> look for specific error messages
4. Check dependency resolution -> look for pip errors in build output indicating version conflicts or missing packages

### Common Causes
- **Disk space exhausted**: Docker images and build cache consume all available space.
- **Docker daemon not running**: systemd service stopped or crashed.
- **Dependency resolution failure**: A Python package version was yanked or version constraints conflict.
- **Dockerfile syntax error**: Recent change introduced a Dockerfile error.
- **Build context too large**: `.dockerignore` missing or incomplete.

### Resolution
- Disk space -> `ssh root@140.82.49.221 "docker system prune -f && docker image prune -a -f --filter 'until=168h'"`
- Docker daemon -> `ssh root@140.82.49.221 "sudo systemctl restart docker"` then retry build
- Dependency failure -> check if the specific package/version is available; update version constraints if needed
- Dockerfile error -> review recent changes to Dockerfile; fix syntax and rebuild
- Build context -> ensure `.dockerignore` excludes `.git/`, `__pycache__/`, and other large directories
