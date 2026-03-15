# Experience: macOS BSD sed Incompatibility with \s

**Date**: 2026-03-15
**Project**: Token RugCheck MCP
**Scenario**: Running preflight-check.sh on macOS
**Applies to**: All bash scripts using sed on macOS
**Occurrences**: 1
**Occurrence dates**: 2026-03-15

## Problem

preflight-check.sh used `sed 's/.*:\s*//'` to strip YAML key prefixes when parsing manifest.yaml. On macOS, this silently failed — `\s` was treated as literal characters, not whitespace, leaving leading spaces in parsed values (e.g., ` 140.82.49.221` instead of `140.82.49.221`). This caused SSH to fail with `Cannot SSH to  root@ 140.82.49.221`.

## Root Cause

macOS ships BSD sed, which does NOT support Perl-style character classes like `\s`, `\d`, `\w`. These work only in GNU sed (Linux). BSD sed silently ignores them or treats them as literal characters.

## Solution

Replace Perl-style classes with POSIX character classes:
- `\s` → `[[:space:]]`
- `\d` → `[[:digit:]]`
- `\w` → `[[:alnum:]_]`

```bash
# BEFORE (broken on macOS):
sed 's/.*:\s*//'

# AFTER (cross-platform):
sed 's/.*:[[:space:]]*//'
```

## Failed Attempts

None — root cause was immediately identified from the preflight output showing extra spaces.

## Status

- [x] Root cause identified
- [x] Fix applied to preflight-check.sh
- [ ] Graduated to Runbook (candidate: add to common scripting guidelines)
