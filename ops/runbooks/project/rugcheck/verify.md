# Runbook: Verify — Token RugCheck

**Scope**: Project-specific — Token RugCheck post-deploy verification.
**When to use**: After every deploy or upgrade to confirm the service is healthy.
**Prerequisites**: Deploy completed (deploy.md).
**References**: `scripts/verify.sh`

---

## Steps

### Step 1: Container health check
**Do**: Verify both expected containers are running:
```
ssh root@140.82.49.221 "cd /opt/token-rugcheck && docker compose -f docker-compose.yml -f docker-compose.prod.yml ps --format '{{.Name}} {{.Status}}'"
```
**Expect**: Two containers running:
  - `token-rugcheck-audit-server-1` — status "Up"
  - `token-rugcheck-ag402-gateway-1` — status "Up"
**On failure**:
  - One or both containers missing/exited -> **auto-rollback**: execute rollback.md immediately
  - Container in restart loop -> check logs with `docker compose logs --tail=50`, then **auto-rollback**
**Do NOT attempt**: Waiting indefinitely for containers to self-heal -- if not running within 30 seconds of deploy, rollback

### Step 2: Localhost port check — audit-server
**Do**: Verify the audit server is listening on port 8000:
```
ssh root@140.82.49.221 "curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/health"
```
**Expect**: HTTP 200 response.
**On failure**:
  - Connection refused -> **auto-rollback**: audit-server is not listening, service is broken
  - Non-200 status -> **auto-rollback**: audit-server health check failing
**Do NOT attempt**: Testing port 8000 from outside the server -- it may not be exposed externally

### Step 3: Localhost port check — ag402-gateway
**Do**: Verify the gateway is listening on port 80:
```
ssh root@140.82.49.221 "curl -s -o /dev/null -w '%{http_code}' http://localhost:80/health"
```
**Expect**: HTTP 200 response.
**On failure**:
  - Connection refused -> **auto-rollback**: gateway is not listening, service is broken
  - Non-200 status -> **auto-rollback**: gateway health check failing
**Do NOT attempt**: Skipping the gateway check -- the gateway is the public entry point and must be verified

### Step 4: External IP health check
**Do**: Verify the service is reachable via the server's public IP on port 80:
```
curl -s -o /dev/null -w '%{http_code}' http://140.82.49.221:80/health
```
**Expect**: HTTP 200 response.
**On failure**:
  - Connection refused or timeout -> **auto-rollback**: service not reachable externally
  - Non-200 status -> **auto-rollback**: service returning errors on public IP
**Do NOT attempt**: Assuming external reachability from localhost checks alone -- firewall rules can block external access

### Step 5: HTTPS domain health check
**Do**: Verify the service is reachable via HTTPS on the production domain:
```
curl -s -o /dev/null -w '%{http_code}' https://rugcheck.aethercore.dev/health
```
**Expect**: HTTP 200 response.
**On failure**:
  - Connection refused or SSL error -> **degrade-continue**: log warning, do NOT rollback (DNS/Cloudflare external issue -- application itself is healthy if Steps 2-4 passed)
  - Non-200 status -> **degrade-continue**: log warning, investigate Cloudflare configuration
**Do NOT attempt**: Rolling back due to HTTPS failure when HTTP/IP checks pass -- this indicates a DNS or CDN issue, not an application issue

### Step 6: 402 paywall test
**Do**: Confirm the audit endpoint requires payment (returns 402 without payment):
```
curl -s -o /dev/null -w '%{http_code}' https://rugcheck.aethercore.dev/v1/audit/DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263
```
**Expect**: HTTP 402 (Payment Required) response.
**On failure**:
  - HTTP 200 returned (no payment required) -> **auto-rollback**: ag402 paywall middleware is not active, service is giving away audits for free
  - HTTP 5xx returned -> **auto-rollback**: application error on the business endpoint
  - HTTP 402 returned but response body malformed -> **degrade-continue**: paywall is active but payment infrastructure may have issues
  - Request times out -> **degrade-continue**: may be upstream API slowness, log warning
**Do NOT attempt**: Sending actual payment in this step -- this is a paywall presence check only

### Step 7: Stats endpoint check
**Do**: Verify the stats endpoint is responding:
```
curl -s -o /dev/null -w '%{http_code}' https://rugcheck.aethercore.dev/stats
```
**Expect**: HTTP 200 response.
**On failure**:
  - Non-200 status -> **degrade-continue**: stats are non-critical, log warning
  - Connection error -> **degrade-continue**: may be Cloudflare issue if Steps 2-4 passed
**Do NOT attempt**: Treating stats endpoint failure as a rollback trigger -- it is an informational endpoint, not critical path

---

## Auto-Rollback vs Degrade-Continue Decision Table

| # | Condition | Action | Reason |
|---|-----------|--------|--------|
| 1 | Container not running OR health non-200 on localhost | **auto-rollback** | Service is fundamentally broken, no traffic can be served |
| 2 | Business endpoint 5xx (audit returns 500+) | **auto-rollback** | Application error prevents core audit functionality |
| 3 | HTTPS fails but HTTP on IP works | **degrade-continue** | DNS or Cloudflare external issue -- application itself is healthy |
| 4 | 402 paywall test fails but 402 status IS returned | **degrade-continue** | Paywall is active, payment infrastructure has an issue (wallet, RPC, etc.) |
| 5 | Payment test skipped (no buyer key configured) | **degrade-continue** | Payment testing requires a funded buyer wallet; skip is expected in CI or staging |
