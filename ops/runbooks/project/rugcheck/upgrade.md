# Runbook: Upgrade — Token RugCheck

**Scope**: Project-specific — Token RugCheck version upgrade.
**When to use**: Upgrade a running Token RugCheck deployment to a new version.
**Prerequisites**: Service is currently deployed and running.
**References**: deploy.md, verify.md, payment-test.md, rollback.md

---

## Steps

### Step 1: Compare current version vs target
**Do**: Check whether an upgrade is needed:
```
CURRENT=$(ssh root@140.82.49.221 "cd /opt/token-rugcheck && git rev-parse HEAD")
TARGET={git_ref}
echo "current=$CURRENT target=$TARGET"
```
**Expect**: Two distinct commit hashes indicating an upgrade is needed.
**On failure**:
  - SSH fails -> escalate-to-human ("cannot reach server 140.82.49.221 to check version")
  - git not found on server -> server may not be initialized; run 01-server-init.md first
**Do NOT attempt**: Comparing version strings instead of commit hashes -- tags can be moved, commits are immutable

### Step 2: Skip if already at target
**Do**: If `CURRENT` equals `TARGET`, report and stop:
```
# If CURRENT == TARGET:
echo "Already at target version $TARGET -- skipping upgrade"
# Exit the runbook here. No further steps needed.
```
**Expect**: Either "already at target" (done) or versions differ (continue to Step 3).
**On failure**:
  - N/A -- this step always succeeds
**Do NOT attempt**: Re-deploying the same version "just to be safe" -- it wastes time and risks breaking a working deployment

### Step 3: Run preflight checks
**Do**: Execute the preflight checks to validate the environment:
```
bash scripts/preflight-check.sh --manifest ops/manifest.yaml
```
**Expect**: All preflight checks pass (`fail=0`). Environment is ready for upgrade.
**On failure**:
  - Preflight fails -> follow 00-preflight.md remediation steps before proceeding
  - Blocking issues (SSH/Docker) -> escalate-to-human per 00-preflight.md Step 4
**Do NOT attempt**: Skipping preflight to save time -- upgrades are the most common source of regressions

### Step 4: Run deploy
**Do**: Execute the Token RugCheck deploy runbook (deploy.md) with the target version:
```
# Follow deploy.md steps in full (state snapshot, .env backup, quick-update)
bash scripts/quick-update.sh 140.82.49.221 rugcheck.aethercore.dev {git_ref}
```
**Expect**: Deploy succeeds. Exit code 0 with "所有验证通过" in output. Both `token-rugcheck-audit-server-1` and `token-rugcheck-ag402-gateway-1` running.
**On failure**:
  - Deploy fails -> follow deploy.md failure handling
  - Build error -> reference troubleshoot.md "Build failing" symptom
**Do NOT attempt**: Running `git pull` and `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d` manually -- the deploy script handles the full sequence safely

### Step 5: Run verify
**Do**: Execute the Token RugCheck verification runbook (verify.md) -- all 7 verification points:
```
# Follow verify.md steps in full:
# 1. Container health (audit-server + ag402-gateway)
# 2. Localhost port 8000 (audit-server)
# 3. Localhost port 80 (gateway)
# 4. External IP:80 /health
# 5. HTTPS rugcheck.aethercore.dev/health
# 6. 402 paywall test (BONK mint)
# 7. Stats endpoint
bash scripts/verify.sh --server-ip 140.82.49.221 --domain rugcheck.aethercore.dev
```
**Expect**: All 7 verification points pass or show acceptable degrade-continue per the decision table in verify.md.
**On failure**:
  - Auto-rollback conditions met (container down, health failing, 5xx on business endpoint) -> execute rollback.md immediately
  - Degrade-continue conditions (HTTPS issue, payment infra issue) -> log warnings and proceed to Step 6
**Do NOT attempt**: Skipping verification after upgrade -- version changes are the highest-risk operation

### Step 6: Run payment test
**Do**: Execute the Token RugCheck payment test runbook (payment-test.md) -- BONK audit test:
```
# Follow payment-test.md steps in full:
# Test: /v1/audit/DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263
# Price: $0.02 USDC
# Validate: action.risk_score, action.is_safe, metadata.data_sources
ssh root@140.82.49.221 "cd /opt/token-rugcheck && python3 scripts/payment-test.py --manifest ops/manifest.yaml"
```
**Expect**: `PAYMENT_TEST:PASS` -- payment flow works on the new version with $0.02 USDC BONK audit.
**On failure**:
  - Payment test fails -> follow payment-test.md diagnostics
  - Payment test skipped (no buyer key) -> acceptable, log as degrade-continue
**Do NOT attempt**: Treating payment test failure as a rollback trigger unless the 402 paywall itself is broken -- payment infra issues are degrade-continue
