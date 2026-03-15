# Token RugCheck v0.1.7 Production Deploy + Ops Optimization

**Date**: 2026-03-14
**Status**: Approved
**Scope**: Deploy existing v0.1.7 to production, validate, optimize ops docs

## Context

Production server is running commit `f68a5ce` (approx v0.1.3) with ag402 v0.1.14.
Local main branch is at `b4485ff` (v0.1.7) with ag402 >=0.1.17.
Production is 4 versions behind, missing: prepaid fast-path, security hardening (S13-S16), deploy safety improvements.

### Gap Analysis

| Item | Production (current) | Target (v0.1.7) |
|------|---------------------|------------------|
| Code | f68a5ce | b4485ff (v0.1.7 tag) |
| ag402 | 0.1.14 | >=0.1.17 |
| RUGCHECK_PRODUCTION | not set | true |
| UVLOOP_INSTALL | not set | 0 |
| AG402_PREPAID_SIGNING_KEY | not set | optional |
| Prepaid fast-path | absent | available |
| Branch strategy docs | absent | included |
| Deploy history tracking | absent | included |

## Design

### Phase 1: Pre-deploy .env Fix

SSH to server, add missing variables to `.env`:
- `RUGCHECK_PRODUCTION=true`
- `UVLOOP_INSTALL=0`
- Optionally generate and set `AG402_PREPAID_SIGNING_KEY`

**AI Review**: Verify .env has all required variables before proceeding.

### Phase 2: Deploy v0.1.7

Execute from local machine:
```bash
bash scripts/quick-update.sh 140.82.49.221 rugcheck.aethercore.dev v0.1.7
```

Script handles: git fetch + checkout tag, backup, --no-cache build (upgrades ag402), restart, health check, deploy history, rollback command.

**AI Review**: Check script output for errors, verify containers healthy.

### Phase 3: Multi-layer Verification

1. `docker compose ps` — both containers healthy
2. `curl localhost:80/health` and `localhost:8000/health` — 200
3. `curl https://rugcheck.aethercore.dev/health` — 200, minimal response (no version leak)
4. `curl https://rugcheck.aethercore.dev/v1/audit/<mint>` — 402 (paywall active)
5. `pip show ag402-core ag402-mcp` — version >= 0.1.17
6. `curl https://rugcheck.aethercore.dev/docs` — should fail (production hardened)
7. Verify deploy history file created

**AI Review**: Automated check of all 7 verification points.

### Phase 4: Real Payment Test

Use `ag402 pay` CLI or buyer test script to execute a real mainnet audit:
- Confirm 402 → pay → 200 flow works end-to-end
- Verify audit report structure matches schema
- Check server logs for successful payment verification

**AI Review**: Validate response JSON against expected schema.

### Phase 5: Ops Documentation Update

- Update OPERATIONS.md: add v0.1.7 deploy record, update known issues
- Update README.md: ensure consistency with current state
- Document lessons learned from this deployment

**AI Review**: Check docs for consistency and completeness.

## Rollback Plan

If any phase fails:
```bash
bash scripts/quick-update.sh 140.82.49.221 rugcheck.aethercore.dev f68a5ce
```
This restores the previous commit. The quick-update script prints the exact rollback command.

## Success Criteria

- [ ] Both containers healthy on server
- [ ] ag402 >= 0.1.17 in gateway container
- [ ] /health returns minimal JSON (RUGCHECK_PRODUCTION active)
- [ ] /docs returns 404 or redirect (not API docs)
- [ ] /v1/audit/<mint> returns 402
- [ ] Real payment test passes (if wallet available)
- [ ] OPERATIONS.md and README.md updated
- [ ] Deploy history recorded on server
