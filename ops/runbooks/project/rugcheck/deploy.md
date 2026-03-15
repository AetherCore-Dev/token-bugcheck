# Runbook: Deploy — Token RugCheck

**Scope**: Project-specific — Token RugCheck MCP deployment.
**When to use**: Deploy a new version of Token RugCheck to production.
**Prerequisites**: Preflight checks passed (00-preflight.md).
**References**: `scripts/quick-update.sh`, `scripts/deploy-oneclick.sh`

---

## Steps

### Step 0: State snapshot
**Do**: Record the current state of both containers before making any changes:
```
COMMIT_BEFORE=$(ssh root@140.82.49.221 "cd /opt/token-rugcheck && git rev-parse HEAD")
CONTAINERS_BEFORE=$(ssh root@140.82.49.221 "cd /opt/token-rugcheck && docker compose -f docker-compose.yml -f docker-compose.prod.yml ps --format '{{.Name}} {{.Status}}'")
ENV_HASH_BEFORE=$(ssh root@140.82.49.221 "sha256sum /opt/token-rugcheck/.env | cut -d' ' -f1")
echo "commit=$COMMIT_BEFORE"
echo "containers=$CONTAINERS_BEFORE"
echo "env_hash=$ENV_HASH_BEFORE"
```
**Expect**: Three values captured and logged. Expected containers: `token-rugcheck-audit-server-1` and `token-rugcheck-ag402-gateway-1`. These values are required for rollback (rollback.md) if deployment fails.
**On failure**:
  - SSH connection fails -> escalate-to-human ("server 140.82.49.221 unreachable -- check SSH access")
  - .env file missing -> note as `ENV_HASH_BEFORE=NONE`, continue (first deploy scenario)
  - Only one container found -> note the missing container, continue (deploy may fix it)
**Do NOT attempt**: Skipping state snapshot to save time -- rollback depends on this data

### Step 1: Pre-deploy .env backup
**Do**: Create a timestamped backup of the current .env:
```
ssh root@140.82.49.221 "cp /opt/token-rugcheck/.env /opt/token-rugcheck/.env.bak.$(date +%s)"
```
**Expect**: Backup file created at `/opt/token-rugcheck/.env.bak.<timestamp>`.
**On failure**:
  - .env does not exist (first deploy) -> skip this step, proceed to Step 2
  - Permission denied -> escalate-to-human ("file permission issue on server")
**Do NOT attempt**: Backing up .env to a publicly accessible location or logging its contents

### Step 2: Run deploy script
**Do**: Execute the quick-update script with the git ref from manifest:
```
bash scripts/quick-update.sh 140.82.49.221 rugcheck.aethercore.dev {git_ref}
```
**Expect**: Exit code 0. Output contains "所有验证通过" (all verifications passed).
**On failure**:
  - Exit 1 + output contains "构建失败" -> build error, reference troubleshoot.md "Build failing" symptom
  - Exit 1 + output contains "容器未运行" -> container start failure, reference troubleshoot.md "Container not starting" symptom
  - Exit 1 + other error -> capture full output, reference troubleshoot.md for matching symptom
  - SSH timeout during deploy -> retry once after 30 seconds; if still failing, escalate-to-human
**Do NOT attempt**: Running `docker compose up` manually without the deploy script -- the script handles git pull, build, env validation, and restart in the correct order

### Step 3: Parse script output
**Do**: Evaluate the deploy script result:
```
# Success criteria:
# - Exit code 0
# - Output contains "所有验证通过"
#
# Failure criteria:
# - Exit code 1 + "构建失败" = build error
# - Exit code 1 + "容器未运行" = container start failure (check both token-rugcheck-audit-server-1 and token-rugcheck-ag402-gateway-1)
# - Exit code 1 + other = unknown failure
```
**Expect**: Success criteria met. Proceed to verification (verify.md).
**On failure**:
  - Build error -> reference troubleshoot.md "Build failing" symptom
  - Container start failure -> reference troubleshoot.md "Container not starting" symptom
  - Unknown failure -> capture output, escalate-to-human with full error context
**Do NOT attempt**: Ignoring non-zero exit codes and proceeding to verification anyway
