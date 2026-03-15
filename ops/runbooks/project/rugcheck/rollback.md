# Runbook: Rollback — Token RugCheck

**Scope**: Project-specific — Token RugCheck deployment rollback.
**When to use**: When a deploy or upgrade fails verification and auto-rollback is triggered.
**Prerequisites**: State snapshot from deploy.md Step 0 is available.
**References**: deploy.md (state snapshot), verify.md (post-rollback verify)

---

## Steps

### Step 1: Identify previous commit
**Do**: Retrieve the commit hash to roll back to from the deploy state snapshot or git history:
```
# Option A: Use state snapshot from deploy.md Step 0
ROLLBACK_TO=$COMMIT_BEFORE

# Option B: If no snapshot, use git log
ROLLBACK_TO=$(ssh root@140.82.49.221 "cd /opt/token-rugcheck && git log --oneline -5" | head -2 | tail -1 | awk '{print $1}')

echo "Rolling back to: $ROLLBACK_TO"
```
**Expect**: A valid commit hash identified as the rollback target.
**On failure**:
  - No state snapshot and git log empty -> escalate-to-human ("cannot determine rollback target -- no deploy history available on 140.82.49.221")
  - Commit hash is the same as current -> escalate-to-human ("rollback target is same as current -- manual intervention needed")
**Do NOT attempt**: Rolling back to an arbitrary "known good" commit without verifying it was the immediately previous state

### Step 2: Git checkout previous commit
**Do**: Switch the server's working directory to the rollback target:
```
ssh root@140.82.49.221 "cd /opt/token-rugcheck && git fetch origin && git checkout $ROLLBACK_TO"
```
**Expect**: Git checkout succeeds. `HEAD` now points to `$ROLLBACK_TO`.
**On failure**:
  - Checkout fails due to local changes -> force checkout: `ssh root@140.82.49.221 "cd /opt/token-rugcheck && git checkout -f $ROLLBACK_TO"`
  - Commit not found -> `git fetch origin` first, then retry
**Do NOT attempt**: Using `git reset --hard` on a shared branch -- checkout of a specific commit is safer and preserves branch history

### Step 3: Docker compose rebuild and restart
**Do**: Rebuild and restart both containers with the rolled-back code:
```
ssh root@140.82.49.221 "cd /opt/token-rugcheck && docker compose -f docker-compose.yml -f docker-compose.prod.yml down && docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build"
```
If pre-built images are available for the rollback commit, skip the build:
```
ssh root@140.82.49.221 "cd /opt/token-rugcheck && docker compose -f docker-compose.yml -f docker-compose.prod.yml down && docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --no-build"
```
**Expect**: Both containers start successfully. `docker compose ps` shows:
  - `token-rugcheck-audit-server-1` — status "Up"
  - `token-rugcheck-ag402-gateway-1` — status "Up"
**On failure**:
  - Build fails on old code -> try `--no-build` if images are cached; otherwise escalate-to-human
  - Containers fail to start -> reference troubleshoot.md "Container not starting" symptom
**Do NOT attempt**: Using `docker compose restart` alone -- it does not pick up code changes from the git checkout

### Step 4: Restore .env backup
**Do**: Restore the .env file from the most recent backup:
```
BAK=$(ssh root@140.82.49.221 "ls -1t /opt/token-rugcheck/.env.bak.* 2>/dev/null | head -1")
if [ -n "$BAK" ]; then
  ssh root@140.82.49.221 "cp $BAK /opt/token-rugcheck/.env"
  echo "Restored .env from $BAK"
else
  echo "NO_BACKUP"
fi
```
**Expect**: .env restored from backup, or `NO_BACKUP` reported.
**On failure**:
  - `NO_BACKUP` -> AI must reconstruct .env from manifest + .env.secrets + .env.example using `scripts/generate-env.sh`
  - Backup file corrupted (empty or malformed) -> treat as `NO_BACKUP`, reconstruct .env
**Do NOT attempt**: Proceeding without a valid .env -- the audit-server and ag402-gateway will fail to start or behave incorrectly

### Step 5: Restart containers after .env restore
**Do**: If .env was restored or reconstructed in Step 4, restart containers to pick up the restored environment:
```
ssh root@140.82.49.221 "cd /opt/token-rugcheck && docker compose -f docker-compose.yml -f docker-compose.prod.yml restart"
```
**Expect**: Both `token-rugcheck-audit-server-1` and `token-rugcheck-ag402-gateway-1` restart successfully.
**On failure**:
  - Containers fail to restart -> reference troubleshoot.md "Container not starting" symptom
**Do NOT attempt**: Skipping this step if .env was restored -- containers need to re-read environment variables

### Step 6: Verify after rollback
**Do**: Run the full verification suite on the rolled-back deployment:
```
# Follow verify.md steps in full (all 7 verification points)
bash scripts/verify.sh --server-ip 140.82.49.221 --domain rugcheck.aethercore.dev
```
**Expect**: All verification checks pass. Both `token-rugcheck-audit-server-1` and `token-rugcheck-ag402-gateway-1` healthy on the previous version.
**On failure**:
  - Verification fails after rollback -> escalate-to-human ("rollback did not restore healthy state on 140.82.49.221 -- manual investigation required")
  - Container not running after rollback -> reference troubleshoot.md; likely .env or port conflict issue
**Do NOT attempt**: Triggering another rollback from a failed rollback -- this creates a loop. Escalate to human instead.
