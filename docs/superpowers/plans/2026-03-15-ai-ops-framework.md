# AI-Driven Ops Framework Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Runbook-based ops framework so AI can autonomously deploy, upgrade, verify, and maintain ag402+FastAPI+Docker services from a project manifest.

**Architecture:** Three-layer system — manifest (config) → Runbooks (knowledge) → scripts (execution). AI reads manifest + Runbooks, auto-detects server state, and follows the appropriate workflow. New scripts (preflight, payment-test, monitor-deps) augment existing scripts (quick-update, verify, deploy-oneclick).

**Tech Stack:** Bash (scripts), Python 3.11+ (payment-test, monitor-deps), YAML (manifest), Markdown (Runbooks/guides)

**Spec:** `docs/superpowers/specs/2026-03-15-ai-ops-framework-design.md`

---

## Chunk 1: Foundation — Directory Structure, Manifest, Schema, CLAUDE.md

### Task 1: Create ops/ directory structure and manifest files

**Files:**
- Create: `ops/manifest.yaml.example`
- Create: `ops/.env.secrets.example`
- Create: `ops/manifest.schema.yaml`
- Modify: `.gitignore` (add ops-specific ignores)

- [ ] **Step 1: Create ops/ directory skeleton**

```bash
mkdir -p ops/guides ops/runbooks/common ops/runbooks/templates ops/runbooks/project/rugcheck ops/experiences ops/reports
```

- [ ] **Step 2: Write manifest.yaml.example**

Create `ops/manifest.yaml.example` — template with placeholder values and inline comments explaining each field. Structure matches spec Section "Layer 1: Project Manifest" exactly:
- `project.*` (name, repo, git_ref)
- `server.*` (ip, ssh_user, ssh_key_path, project_dir)
- `domain.*` (name, cdn, ssl_mode)
- `blockchain.*` (network, seller_address)
- `service.*` (price, free_daily_quota, production_mode, health_endpoint, test_endpoint, test_expect_status, test_expect_fields, test_deposit_amount)
- `secrets_file` reference

Placeholders use `<YOUR_...>` format for human clarity.

- [ ] **Step 3: Write .env.secrets.example**

Create `ops/.env.secrets.example` — template showing required secret fields with descriptions:
```
# Required
SOLANA_RPC_URL=<YOUR_RPC_URL>
BUYER_PRIVATE_KEY=<YOUR_BASE58_KEY>

# Optional
AG402_PREPAID_SIGNING_KEY=
GOPLUS_APP_KEY=
GOPLUS_APP_SECRET=
```

- [ ] **Step 4: Write manifest.schema.yaml**

Create `ops/manifest.schema.yaml` — validation rules from spec (required_fields, ip_format, seller_address_format, enums, formats).

- [ ] **Step 5: Update .gitignore**

Add to `.gitignore`:
```
# Ops secrets & reports (local-only)
ops/.env.secrets
ops/manifest.yaml
ops/reports/

# Un-ignore example templates (overrides .env.* pattern from above)
!ops/.env.secrets.example
!ops/manifest.yaml.example
```

The existing `.env.*` pattern in `.gitignore` would silently block `ops/.env.secrets.example` from being tracked. The `!` prefix explicitly un-ignores it. Verify after committing: `git ls-files ops/` should include both `.example` files.

- [ ] **Step 6: Commit**

```bash
git add ops/ .gitignore
git commit -m "ops: add manifest schema, examples, and directory structure"
```

### Task 2: Create CLAUDE.md with ops instructions

**Files:**
- Create: `CLAUDE.md`

- [ ] **Step 1: Write CLAUDE.md**

Include the AI Entry Point instructions from spec (Section "AI Entry Point"):
- Project overview (1-2 lines)
- Ops instructions: read manifest → read secrets → scan experiences → SSH detect state → follow Runbooks → write report → check graduation → summarize
- **Secrets Handling Rules** (all 7 rules from spec Section "Secrets Handling Rules") — these MUST be in CLAUDE.md so every AI session enforces them from the first command, before reading any Runbook
- **AI Autonomy Levels** summary (Level 1/2/3 boundaries from spec Section "Human Interaction Model") — so AI knows what it can do without asking
- Reference existing scripts in `scripts/` and their purposes
- Reference test suite in `tests/`

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: add CLAUDE.md with ops instructions for AI sessions"
```

---

## Chunk 2: Scripts — preflight-check.sh, DNS diagnostics enhancement

### Task 3: Create preflight-check.sh

**Files:**
- Create: `scripts/preflight-check.sh`
- Test: manual invocation with `--help` and dry-run

- [ ] **Step 1: Write preflight-check.sh**

Script reads a manifest.yaml path as argument. Performs 7 checks per spec:
1. SSH connectivity (BLOCKING — exit 2 immediately on failure)
2. DNS resolution vs server IP
3. HTTPS reachability (if domain configured)
4. Disk space > 2GB free
5. .env completeness (compare against .env.example)
6. Port availability (80, 8000 — verify non-project processes)
7. Docker and docker compose available

Output: structured `CHECK:<name>:PASS|FAIL|WARN:<detail>` lines.
Exit codes: 0 = all pass, 1 = fixable, 2 = blocking.

Reuse the `run_on_host()` SSH helper pattern from existing `scripts/verify.sh`.
Parse manifest.yaml using grep/sed (no Python dependency for shell scripts — consistent with existing scripts).

- [ ] **Step 2: Make executable and test --help**

```bash
chmod +x scripts/preflight-check.sh
bash scripts/preflight-check.sh --help
```
Expected: usage text printed, exit 0.

- [ ] **Step 3: Commit**

```bash
git add scripts/preflight-check.sh
git commit -m "ops: add preflight-check.sh — 7-point pre-deploy verification"
```

### Task 4: Enhance quick-update.sh with DNS diagnostics and build-before-down

**Files:**
- Modify: `scripts/quick-update.sh`

- [ ] **Step 1: Add DNS diagnostics on HTTPS connection failure**

In `scripts/quick-update.sh`, after the HTTPS domain check (line ~285-292), add DNS diagnostics specifically when `$DOMAIN_HTTP` equals `"000"` (connection failure only — NOT on 403, 502, etc. where DNS is irrelevant). Add the diagnostic block from spec:
- `dig +short $DOMAIN` → if empty: "DNS 未解析"
- If resolved IP != server IP: "DNS 指向 X，期望 Y — 请修正 Cloudflare A 记录"
- If resolved IP correct: "DNS 正确但 HTTPS 连接失败 — 检查 Cloudflare SSL/TLS 设置"

- [ ] **Step 2: Implement build-before-down strategy**

Modify Step 4 (lines ~194-224) to:
1. Run `docker compose build --no-cache` BEFORE `docker compose down`
2. Only if build succeeds → `docker compose down --timeout 30 && docker compose up -d --no-build`
3. If build fails → abort with error, service never interrupted

This means moving the build step before the stop step and adding `--no-build` to the up command.

- [ ] **Step 3: Test script syntax**

```bash
bash -n scripts/quick-update.sh
```
Expected: no syntax errors.

- [ ] **Step 4: Commit**

```bash
git add scripts/quick-update.sh
git commit -m "ops: add DNS diagnostics + build-before-down to quick-update.sh"
```

---

## Chunk 3: Scripts — payment-test.py, monitor-deps.py

### Task 5: Create payment-test.py

**Files:**
- Create: `scripts/payment-test.py`
- Test: `python scripts/payment-test.py --help`

- [ ] **Step 1: Write payment-test.py**

Implements the standardized ag402 payment test from spec. The script:
1. Parses manifest.yaml using simple line-by-line regex parsing (no PyYAML dependency — the manifest is flat enough for `key: value` extraction via Python's `re` module)
2. Reads seller_address, test_endpoint, test_expect_status, test_expect_fields, test_deposit_amount from manifest
3. Initializes AgentWallet ledger if balance is $0 (using test_deposit_amount)
4. Sends request via async httpx to `http://localhost:80{test_endpoint}` (gateway port)
5. Validates response status and required fields
6. Outputs: `PAYMENT_TEST:PASS|FAIL:<detail>`

Include the "Known constraints" docstring from spec (no CLI, no sync httpx, no container execution).

Dependencies: `ag402-core[crypto]`, `httpx`. Script checks for missing deps and outputs clear error.

- [ ] **Step 2: Test --help**

```bash
python3 scripts/payment-test.py --help
```
Expected: usage text printed.

- [ ] **Step 3: Commit**

```bash
git add scripts/payment-test.py
git commit -m "ops: add payment-test.py — standardized ag402 payment verification"
```

### Task 6: Create monitor-deps.py

**Files:**
- Create: `scripts/monitor-deps.py`
- Test: `python scripts/monitor-deps.py --help`

- [ ] **Step 1: Write monitor-deps.py**

Implements upstream dependency version checker from spec:
1. Reads pinned versions from `pyproject.toml` (parse `ag402-core>=X.Y.Z` lines)
2. Checks PyPI JSON API for latest `ag402-core` and `ag402-mcp` versions
3. Optionally checks server's installed versions via SSH (if manifest provided)
4. Outputs: `DEP:<name>:pinned=X:latest=Y:server=Z:ACTION=<up-to-date|upgrade-available>`

Manual execution mode only for MVP. Cron mode documented but not implemented.

- [ ] **Step 2: Test --help**

```bash
python3 scripts/monitor-deps.py --help
```
Expected: usage text printed.

- [ ] **Step 3: Commit**

```bash
git add scripts/monitor-deps.py
git commit -m "ops: add monitor-deps.py — upstream ag402 version checker"
```

---

## Chunk 4: Runbooks — common/ and templates/

### Task 7: Write common Runbooks (cross-project)

**Files:**
- Create: `ops/runbooks/common/00-preflight.md`
- Create: `ops/runbooks/common/01-server-init.md`

- [ ] **Step 1: Write 00-preflight.md**

Pre-deploy checks Runbook. Each step has the four elements: Do, Expect, On failure, Do NOT attempt.
- Step 1: Run `bash scripts/preflight-check.sh {manifest_path}`
- Step 2: Parse output, categorize as blocking/fixable/pass
- Step 3: For fixable issues, attempt auto-fix (e.g., .env missing vars → generate)
- Step 4: For blocking issues, escalate to human with specific instructions

- [ ] **Step 2: Write 01-server-init.md**

Fresh server initialization Runbook:
- Step 1: Install Docker + docker compose via SSH
- Step 2: Configure UFW firewall (ports 22, 80, 443, 8000)
- Step 3: Git clone project repo
- Step 4: Generate .env from manifest + secrets (via scp per spec Rule #6)
- Step 5: Initial docker compose build + up

Reference existing `scripts/setup-server.sh` and `scripts/generate-env.sh`.

- [ ] **Step 3: Commit**

```bash
git add ops/runbooks/common/
git commit -m "ops: add common Runbooks — preflight and server-init"
```

### Task 8: Write template Runbooks

**Files:**
- Create: `ops/runbooks/templates/02-deploy.md`
- Create: `ops/runbooks/templates/03-verify.md`
- Create: `ops/runbooks/templates/04-payment-test.md`
- Create: `ops/runbooks/templates/05-upgrade.md`
- Create: `ops/runbooks/templates/06-rollback.md`
- Create: `ops/runbooks/templates/07-troubleshoot.md`

- [ ] **Step 1: Write 02-deploy.md**

Deploy template with:
- Step 0: State snapshot (git commit, docker ps, .env hash)
- Step 1: Pre-deploy .env backup
- Step 2: Run `bash scripts/quick-update.sh {server.ip} {domain.name} {project.git_ref}`
- Step 3: Parse script output (exit codes, "所有验证通过", "构建失败", etc.)
- On failure entries reference 07-troubleshoot.md

- [ ] **Step 2: Write 03-verify.md**

Verification template:
- Step 1: Run `bash scripts/verify.sh --server-ip {server.ip} --domain {domain.name}`
- Step 2: Parse structured output (OK|FAIL|SKIP lines)
- Step 3: Apply auto-rollback vs degrade-continue rules — encode all 5 conditions from spec table:
  - Container not running OR health non-200 → auto-rollback
  - Business endpoint 5xx → auto-rollback
  - HTTPS fails but HTTP:IP works → degrade-continue
  - Payment test fails but 402 works → degrade-continue
  - Payment test skipped (no buyer key) → degrade-continue

- [ ] **Step 3: Write 04-payment-test.md**

Payment test template:
- Step 1: scp payment-test.py to server
- Step 2: Ensure `ag402-core[crypto]` installed on server
- Step 3: Run `python3 scripts/payment-test.py --manifest {manifest_path}`
- Step 4: Parse PAYMENT_TEST:PASS|FAIL output
- "Do NOT attempt" section: lists all 4 known constraints from spec

- [ ] **Step 4: Write 05-upgrade.md**

Upgrade workflow:
- Run preflight → deploy → verify → payment-test in sequence
- Version comparison logic (current vs target git_ref)

- [ ] **Step 5: Write 06-rollback.md**

Rollback template:
- Step 1: .env snapshot (pre-existing from deploy)
- Step 2: Git checkout previous commit
- Step 3: Docker compose build + restart
- Step 4: .env restore (with NO_BACKUP handling per spec fix)
- Step 5: Verify after rollback

- [ ] **Step 6: Write 07-troubleshoot.md**

Symptom-based diagnostic trees:
- Container not starting → check logs, port conflicts, .env issues
- Health check failing → check process, port binding, application errors
- HTTPS failing → DNS diagnostics, Cloudflare settings
- Payment test failing → ag402 constraints, wallet balance, ledger state
- Build failing → disk space, Docker daemon, dependency issues

- [ ] **Step 7: Commit**

```bash
git add ops/runbooks/templates/
git commit -m "ops: add template Runbooks — deploy, verify, payment-test, upgrade, rollback, troubleshoot"
```

---

## Chunk 5: Runbooks — project/rugcheck/ instantiation

### Task 9: Write Token RugCheck project Runbooks

**Files:**
- Create: `ops/runbooks/project/rugcheck/deploy.md`
- Create: `ops/runbooks/project/rugcheck/verify.md`
- Create: `ops/runbooks/project/rugcheck/payment-test.md`
- Create: `ops/runbooks/project/rugcheck/upgrade.md`
- Create: `ops/runbooks/project/rugcheck/rollback.md`
- Create: `ops/runbooks/project/rugcheck/troubleshoot.md`

- [ ] **Step 1: Write rugcheck deploy.md**

Instantiate 02-deploy.md template with Token RugCheck specifics:
- `quick-update.sh 140.82.49.221 rugcheck.aethercore.dev v0.1.7`
- Docker compose files: `-f docker-compose.yml -f docker-compose.prod.yml`
- Expected containers: `token-rugcheck-audit-server-1`, `token-rugcheck-ag402-gateway-1`

- [ ] **Step 2: Write rugcheck verify.md**

7 verification points specific to this project:
- Container health (2 containers)
- Localhost ports (8000 audit, 80/8001 gateway)
- External IP:80 /health
- HTTPS domain /health
- 402 paywall test (GET /v1/audit/{BONK_MINT} without payment → 402)
- Audit schema validation (action.risk_score, action.is_safe, metadata.data_sources)
- Stats endpoint (/stats)

- [ ] **Step 3: Write rugcheck payment-test.md**

BONK audit test: $0.02 USDC, expect 200, validate score/is_safe/data_sources.
All 4 "Do NOT attempt" constraints included.

- [ ] **Step 4: Write rugcheck upgrade.md**

Project-specific upgrade flow: preflight → deploy → verify → payment-test sequence, referencing rugcheck-specific compose files (`-f docker-compose.yml -f docker-compose.prod.yml`), containers, and endpoints.

- [ ] **Step 5: Write rugcheck rollback.md**

Project-specific rollback: checkout previous commit, .env restore (with NO_BACKUP handling), rebuild with rugcheck compose files, verify 2 containers healthy.

- [ ] **Step 6: Write rugcheck troubleshoot.md**

Project-specific diagnostic trees: audit-server port 8000 issues, ag402-gateway port 80/8001 issues, BONK mint test failures, DexScreener/GoPlus/RugCheck API timeouts.

- [ ] **Step 7: Commit**

```bash
git add ops/runbooks/project/rugcheck/
git commit -m "ops: add Token RugCheck project Runbooks"
```

---

## Chunk 6: Human Setup Guide + Experience Library Bootstrap

### Task 10: Write human setup guide

**Files:**
- Create: `ops/guides/setup-guide.md`

- [ ] **Step 1: Write setup-guide.md**

Step-by-step guide per spec (4 phases):
1. Buy a Server (Vultr/Hetzner/DO, Ubuntu 22.04, min spec, SSH key setup, test: `ssh root@<IP> echo OK`)
2. Domain & Cloudflare (register, create A record, SSL/TLS Flexible, test: `dig +short`)
3. Solana Wallet (Phantom/Solana CLI, seller wallet, Helius RPC, optional buyer test wallet)
4. Fill Manifest (copy examples, fill fields, tell AI "Manifest is ready")

Each phase has estimated time, exact steps, and a completion test.

- [ ] **Step 2: Commit**

```bash
git add ops/guides/
git commit -m "docs: add human setup guide for ops framework"
```

### Task 11: Bootstrap experience library with v0.1.7 lessons

**Files:**
- Create: `ops/experiences/2026-03-14-ag402-payment-test-constraints.md`
- Create: `ops/experiences/2026-03-14-env-secrets-exposure.md`
- Create: `ops/experiences/2026-03-14-dns-cloudflare-mismatch.md`

All experience files MUST follow the exact format from spec Section "Experience File Format": Date, Project, Scenario, Applies to, Occurrences, Occurrence dates, Problem, Root Cause, Solution, Failed Attempts, Status checkboxes.

- [ ] **Step 1: Write ag402 payment test constraints experience**

Captures the 6 failed attempts from v0.1.7 deployment:
- SSRF blocks localhost in `ag402 pay` CLI
- HTTPS required for non-localhost
- Only async httpx patched
- Container wallet DB not writable
- Ledger needs explicit deposit
- Server needs `ag402-core[crypto]`

Status: Graduated to Runbook (04-payment-test.md "Do NOT attempt" section).

- [ ] **Step 2: Write secrets exposure experience**

Private key appeared in tool output during v0.1.7 deployment. Led to Secrets Rules #6 and #7.
Status: Graduated to spec Secrets Handling Rules.

- [ ] **Step 3: Write DNS/Cloudflare mismatch experience**

DNS resolved to wrong IP, only discovered at verification. Led to preflight DNS check.
Status: Graduated to 00-preflight.md Step 2.

- [ ] **Step 4: Commit**

```bash
git add ops/experiences/
git commit -m "ops: bootstrap experience library with v0.1.7 deployment lessons"
```

---

## Chunk 7: Execution Report Template + Final Integration

### Task 12: Create execution report template

**Files:**
- Create: `ops/reports/.gitkeep`
- Create: `ops/runbooks/templates/report-template.md`

- [ ] **Step 1: Write report-template.md**

Create `ops/runbooks/templates/report-template.md` (placed with other templates for consistency).
Template per spec "Execution Report" section with placeholders:
- Header (time, type, result)
- Summary table (phase/status/duration/notes)
- Human Action Required
- Changes Made
- Pre-Operation State
- New Experiences
- Rollback Command

This template is referenced by AI when generating reports — not filled by humans.

- [ ] **Step 2: Add .gitkeep for reports directory**

```bash
touch ops/reports/.gitkeep
```

- [ ] **Step 3: Commit**

```bash
git add ops/runbooks/templates/report-template.md ops/reports/.gitkeep
git commit -m "ops: add execution report template"
```

### Task 13: Final integration and validation

- [ ] **Step 1: Verify all files exist**

```bash
# Check complete directory structure
find ops/ -type f | sort
ls scripts/preflight-check.sh scripts/payment-test.py scripts/monitor-deps.py
cat CLAUDE.md | head -5
```

Expected: all files from spec's Directory Structure section present.

- [ ] **Step 2: Verify .gitignore works**

```bash
# These should be ignored
echo "test" > ops/.env.secrets
echo "test" > ops/manifest.yaml
git status ops/.env.secrets ops/manifest.yaml
# Should show nothing (ignored)
rm ops/.env.secrets ops/manifest.yaml
```

- [ ] **Step 3: Run existing tests to ensure no regressions**

```bash
python -m pytest tests/ -x -q
```

Expected: all existing tests pass (we only added new files, didn't modify source code).

- [ ] **Step 4: Verify script syntax**

```bash
bash -n scripts/preflight-check.sh
python3 -c "import ast; ast.parse(open('scripts/payment-test.py').read())"
python3 -c "import ast; ast.parse(open('scripts/monitor-deps.py').read())"
```

Expected: no syntax errors.

- [ ] **Step 5: Final verification commit (if any uncommitted changes remain)**

```bash
git status
# If any remaining changes:
git add ops/ scripts/preflight-check.sh scripts/payment-test.py scripts/monitor-deps.py CLAUDE.md .gitignore
git commit -m "ops: AI-driven ops framework — final integration"
```

---

## Verification

After all tasks complete:

1. **Structure check**: `find ops/ -type f | sort` matches spec's Directory Structure
2. **Script check**: all 3 new scripts respond to `--help`
3. **Existing tests**: `pytest tests/ -x -q` all pass
4. **CLAUDE.md present**: AI sessions will auto-load ops instructions
5. **Git clean**: `git status` shows clean working tree
6. **Manifest flow**: copy `ops/manifest.yaml.example` → `ops/manifest.yaml`, fill in values — AI can parse it
