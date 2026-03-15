# Experience: Docker Internal Endpoint Access via verify.sh

**Date**: 2026-03-15
**Project**: Token RugCheck MCP
**Scenario**: Deployment verification — /stats and /metrics check
**Applies to**: Any project with internal-only endpoints running in Docker containers
**Occurrences**: 1
**Occurrence dates**: 2026-03-15

## Problem

verify.sh L5.4 and L5.5 check /stats and /metrics by running `curl http://localhost:8000/stats` on the host via SSH. These endpoints are protected by middleware that only allows access from `GATEWAY_IPS = {"127.0.0.1", "::1"}`. The checks returned 403 "Endpoint restricted to internal access."

## Root Cause

In Docker's bridge networking, when the host accesses a container's mapped port (e.g., `localhost:8000`), the traffic arrives at the container from the Docker bridge IP (typically `172.17.0.1` or similar), not `127.0.0.1`. The internal-access middleware correctly rejects this as a non-loopback request.

## Solution

Changed verify.sh to use `docker exec <container> curl http://127.0.0.1:8000/stats` instead of curling the host-mapped port. Inside the container, the request originates from 127.0.0.1, satisfying the loopback check.

Key pattern:
```bash
CONTAINER=$(run_on_host "docker ps --filter 'name=audit-server' --format '{{.Names}}' | head -1")
HTTP=$(run_on_host "docker exec $CONTAINER curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/stats")
```

## Failed Attempts

1. **curl from host to localhost:8000** — 403 because Docker bridge IP is not in GATEWAY_IPS

## Status

- [x] Root cause identified
- [x] Fix applied to verify.sh
- [ ] Graduated to Runbook (candidate: 03-verify.md "Docker internal endpoints" note)
