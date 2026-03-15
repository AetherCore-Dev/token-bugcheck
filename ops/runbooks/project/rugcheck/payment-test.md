# Runbook: Payment Test — Token RugCheck

**Scope**: Project-specific — Token RugCheck ag402 payment flow end-to-end test.
**When to use**: After deploy/upgrade to confirm the ag402 payment flow works end-to-end.
**Prerequisites**: Service is running and health check passes (verify.md).
**References**: `scripts/payment-test.py`

---

## Test Parameters

- **Test mint**: `DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263` (BONK)
- **Endpoint**: `/v1/audit/DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263`
- **Price**: $0.02 USDC per audit
- **Expected response fields**: `action.risk_score`, `action.is_safe`, `metadata.data_sources`

---

## Steps

### Step 1: Upload payment test script
**Do**: Copy the payment test script to the server:
```
scp scripts/payment-test.py root@140.82.49.221:/opt/token-rugcheck/scripts/payment-test.py
```
**Expect**: File transferred successfully. Exit code 0.
**On failure**:
  - SCP fails -> check SSH connectivity; reference troubleshoot.md "Container not starting" for SSH diagnostics
  - scripts/ directory missing on server -> create it: `ssh root@140.82.49.221 "mkdir -p /opt/token-rugcheck/scripts"`
**Do NOT attempt**: Pasting the script contents via SSH echo -- risks quoting issues and secret exposure

### Step 2: Install ag402 dependency
**Do**: Ensure the ag402 crypto library is available on the server:
```
ssh root@140.82.49.221 "pip install 'ag402-core[crypto]'"
```
**Expect**: Package installed or already satisfied. Exit code 0.
**On failure**:
  - pip not found -> try `pip3` instead: `ssh root@140.82.49.221 "pip3 install 'ag402-core[crypto]'"`
  - Permission denied -> use `--user` flag: `pip install --user 'ag402-core[crypto]'`
  - Network error -> escalate-to-human ("server cannot reach PyPI -- check outbound network")
**Do NOT attempt**: Installing ag402 inside the Docker container -- the payment test must run on the host to avoid SSRF restrictions

### Step 3: Run payment test
**Do**: Execute the payment test against the BONK token audit endpoint:
```
ssh root@140.82.49.221 "cd /opt/token-rugcheck && python3 scripts/payment-test.py --manifest ops/manifest.yaml"
```
**Expect**: Output contains `PAYMENT_TEST:PASS`. Exit code 0. The test confirms:
  1. GET `/v1/audit/DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263` returns HTTP 402 (paywall active)
  2. Payment of $0.02 USDC is submitted via ag402
  3. Subsequent request returns HTTP 200 with a valid audit response
  4. Response contains `action.risk_score`, `action.is_safe`, and `metadata.data_sources`
**On failure**:
  - Output contains `PAYMENT_TEST:FAIL` -> proceed to Step 4 for diagnostics
  - Script crashes with ImportError -> re-run Step 2 to ensure ag402-core is installed
  - Timeout -> the service may be overloaded or upstream APIs (DexScreener, GoPlus, RugCheck) are slow; wait 10 seconds and retry once
**Do NOT attempt**: Running the payment test without `--manifest` -- it needs the manifest to discover endpoints and payment config

### Step 4: Validate audit response schema
**Do**: Confirm the payment test response includes all required fields:
```
# Expected fields in successful audit response:
# - action.risk_score     (numeric risk score for the BONK token)
# - action.is_safe        (boolean safety determination)
# - metadata.data_sources (list of data sources consulted, e.g. DexScreener, GoPlus, RugCheck)
#
# PASS -> all three fields present with valid types
# FAIL -> one or more fields missing or invalid
```
**Expect**: All three fields present in the response with valid types.
**On failure**:
  - `action.risk_score` missing -> audit engine may not be returning scores; check audit-server logs on port 8000
  - `action.is_safe` missing -> safety determination logic may have errored; check audit-server logs
  - `metadata.data_sources` missing -> upstream data fetchers may have failed; reference troubleshoot.md "Upstream API timeout" symptom
**Do NOT attempt**:
  - `ag402 pay` CLI for localhost targets -- SSRF protection blocks loopback requests
  - `ag402 pay` CLI for HTTP (non-HTTPS) remote targets -- the CLI enforces HTTPS
  - `httpx.Client` (synchronous) for ag402 -- only `httpx.AsyncClient` is patched by ag402
  - Running the payment test inside the Docker container -- wallet DB path is not writable in the container filesystem

### Step 5: Parse payment test result
**Do**: Evaluate the final `PAYMENT_TEST:PASS` or `PAYMENT_TEST:FAIL` output:
```
# PASS -> payment flow works end-to-end:
#   402 -> pay $0.02 USDC -> 200 with valid audit (risk_score, is_safe, data_sources)
#
# FAIL -> check the error detail line following PAYMENT_TEST:FAIL for specific cause
```
**Expect**: `PAYMENT_TEST:PASS` -- the full pay-and-verify cycle succeeded for BONK token.
**On failure**:
  - "402 not returned" -> ag402 paywall middleware not active; check ag402 middleware configuration in the audit-server
  - "payment rejected" -> wallet may be unfunded or ledger has replay-protection issue; reference troubleshoot.md "ag402 ledger/wallet issues"
  - "receipt invalid" -> ag402 version mismatch between client and server; check installed versions
  - "field missing: action.risk_score" -> audit engine issue; check audit-server logs
  - "field missing: metadata.data_sources" -> upstream API issue; reference troubleshoot.md "Upstream API timeout"
**Do NOT attempt**: Treating payment test failure as an auto-rollback trigger unless the 402 paywall itself is broken -- payment infrastructure issues are degrade-continue
