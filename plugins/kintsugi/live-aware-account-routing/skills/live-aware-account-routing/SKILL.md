---
name: live-aware-account-routing
description: "KINTSUGI Snakefile + CLI changes that route SLURM jobs around accounts saturated by OTHER users on the same QOS pool. Trigger: QOSGrpMemLimit, jobs stuck pending despite available GPU slots in config, noisy neighbor on shared QOS, multi-user investment pool exhaustion, _build_cycle_assignment static-vs-live."
author: KINTSUGI Team
date: 2026-04-08
---

# Live-Aware SLURM Account Routing (Apr 8, 2026)

## Experiment Overview
| Item | Details |
|------|---------|
| **Date** | 2026-04-08 |
| **Goal** | Stop KINTSUGI jobs getting stuck `PENDING (QOSGrpMemLimit)` when another user saturates a shared QOS investment pool |
| **Environment** | HiPerGator HPC, SLURM, multi-user `clive` and `maigan` group accounts |
| **Status** | Implemented, verified end-to-end with running pipeline |

## Context — what failed before this fix

KINTSUGI's `_build_cycle_assignment()` in `workflow/Snakefile` pre-assigned cycles to accounts at DAG creation, reading static `gpu_slots` from each project's `workflow/config.yaml`. The `_qc_cpu_assignment()` and `_registration_assignment()` helpers always picked the **first account** in config order. None of them queried live SLURM availability, even though the underlying detector (`detect_live_multi_account()` in `src/kintsugi/hpc.py:687`) already counted ALL users on each account's QOS pool via `slurmInfo` / `squeue`.

**Symptom**: 5 SLURM jobs from project `src_CX_19-002_spleen_CC2-A_D200210` stuck `PENDING (QOSGrpMemLimit)` against the `clive` account because user `drew.bloss` was running a 256 GB job in the same investment QOS pool (limit: 312.5 GB total). KINTSUGI's 4 decon jobs (125 GB each) and 1 qc_stitch (62.5 GB) couldn't fit in the 56.5 GB of remaining headroom.

**Verification of static-assignment determinism**: With `clive.gpu_slots=1, maigan.gpu_slots=2`, round-robin pre-assignment for 9 cycles **always** pinned `cyc01, 05, 07, 09 → clive`. The 4 stuck decon jobs matched exactly. The qc_stitch hit clive because clive was first in the config.

## Root cause — feature existed but wasn't wired up

`detect_live_multi_account()` returns per-account `gpu_avail`, `cpu_avail`, `usage` (across all users). The CLI called it (`cli.py:2041`) but only consumed `pool["total_gpu_avail"]` to set `-j`. Per-account live data was thrown away. The Snakefile assignment helpers never saw it.

## Verified workflow

### Step 1 — Inject live data from CLI to Snakemake
`src/kintsugi/cli.py` `_workflow_run()` builds a `live_accounts` list from `pool["accounts"]` and forwards via `--config`:

```python
live_accounts = [
    {
        "name": a["name"],
        "gpu_avail": a.get("gpu_avail", 0),
        "cpu_avail": a.get("cpu_avail", 0),
        "mem_avail_gb": max(0, a["alloc"]["mem_gb"] - a["usage"]["mem_gb"]),
    }
    for a in pool["accounts"]
]
if pool["total_gpu_avail"] == 0 and pool.get("total_cpu_avail", 0) == 0:
    raise SystemExit(1)  # Hard-fail instead of queueing forever
cmd.extend(["--config", f"live_accounts={json.dumps(live_accounts)}"])
```

The actual snakemake invocation includes:
```
--config live_accounts=[{"name": "maigan", "gpu_avail": 2, "cpu_avail": 4, "mem_avail_gb": 593}]
```

### Step 2 — Snakefile reads live data
`workflow/Snakefile`:
```python
_live_raw = config.get("live_accounts", None)
if isinstance(_live_raw, str):
    import json as _json
    LIVE_ACCOUNTS = _json.loads(_live_raw)
elif isinstance(_live_raw, list):
    LIVE_ACCOUNTS = _live_raw
else:
    LIVE_ACCOUNTS = None

def _live_lookup(name):
    if not LIVE_ACCOUNTS:
        return None
    for la in LIVE_ACCOUNTS:
        if la.get("name") == name:
            return la
    return None

def _effective_gpu_slots(acct):
    la = _live_lookup(acct["name"])
    if la is not None:
        return max(0, int(la.get("gpu_avail", 0)))
    return acct.get("gpu_slots", 0)
```

`_build_cycle_assignment()` swaps `acct.get("gpu_slots", 0)` for `_effective_gpu_slots(acct)`. Saturated accounts contribute 0 slots and are skipped entirely. Static fallback path is preserved for bare `snakemake` invocations.

### Step 3 — Live-aware QC and registration
`_qc_cpu_assignment()` sorts CPU candidates by `(mem_avail_gb, cpu_avail)` descending and picks the top one if it has nonzero memory headroom. Falls back to first-account if `LIVE_ACCOUNTS` is None. `_registration_assignment()` sorts GPU candidates by `(gpu_avail, mem_avail_gb)` similarly.

### Step 4 — Permanent block of saturated account
When an account is chronically saturated by other users (clive's QOS was throttled to 1 GPU/312.5 GB and is regularly hammered), add it to `BLOCKED_ACCOUNTS` in `src/kintsugi/hpc.py`:

```python
BLOCKED_ACCOUNTS: frozenset[str] = frozenset({"brusko", "clive"})
```

Future `kintsugi workflow config` invocations will skip blocked accounts entirely.

### Step 5 — Bulk-strip blocked accounts from existing project configs
`kintsugi workflow config` only writes new configs — existing `workflow/config.yaml` files retain stale account lists. Use a Python script to bulk-update:

```python
import yaml
from pathlib import Path
for cfg in Path("/blue/maigan/smith6jt/KINTSUGI_Projects").glob("*/workflow/config.yaml"):
    data = yaml.safe_load(cfg.read_text())
    accts = data["resources"]["accounts"]
    if not any(a["name"] == "clive" for a in accts):
        continue
    new = [a for a in accts if a["name"] != "clive"]
    data["resources"]["accounts"] = new
    data["resources"]["total_gpu_slots"] = sum(a.get("gpu_slots", 0) for a in new)
    data["resources"]["total_cpu_slots"] = sum(a.get("cpu_slots", 0) for a in new)
    data["resources"]["total_slots"] = data["resources"]["total_gpu_slots"] + data["resources"]["total_cpu_slots"]
    cfg.write_text(yaml.safe_dump(data, default_flow_style=False, sort_keys=False))
```

Verified Apr 8 2026: 34/35 project configs updated, 0 remaining clive references.

## Failed attempts (Critical)

| Attempt | Why it Failed | Lesson Learned |
|---------|---------------|----------------|
| Static `gpu_slots` from config.yaml | Doesn't reflect current QOS state — config said clive=3 but live QOS was 1 | Read live availability via `detect_live_multi_account()` |
| Always pick first account in config order (`_qc_cpu_assignment`, `_registration_assignment`) | Hardcodes failures when first account is saturated | Sort by live `(mem_avail_gb, cpu_avail)` or `(gpu_avail, mem_avail_gb)` and prefer top |
| Trust `pool["total_gpu_avail"]` only | Throws away per-account data; can't reroute | Forward the per-account dicts via `--config live_accounts=<json>` |
| Reroute mid-run when QOS frees up | Snakemake's `_CYCLE_ASSIGN` is built once at DAG creation; lambda resources resolve once per submission | Live-aware assignment at *DAG creation* is sufficient — accept the snapshot, accept the hard-fail if everything is full |
| Detect `QOSGrpMemLimit` post-submission and requeue | Fragile, racy, requires background watcher | Prevent the bad assignment in the first place |
| Skip the BLOCKED_ACCOUNTS update because "live routing handles it" | Live routing handles transient saturation but not chronic — when an account is reliably broken, mask it permanently | Use BLOCKED_ACCOUNTS for chronic problems, live routing for transient ones |
| Use `--config` with raw Python literal (not JSON) | Snakemake parses `--config key=value` as YAML; nested lists/dicts need proper JSON quoting | Always `json.dumps(...)` the value |
| Kill snakemake coordinator with SIGTERM | Coordinator ignores it (runs cleanup handlers only on SIGINT) | Use `kill -INT <pid>`; falls back to SIGKILL if needed |
| Cancel pending jobs without killing the snakemake coordinator | Snakemake re-submits failed jobs with the SAME static assignment, recreating the problem | Cancel jobs AND kill the coordinator AND fix the config before relaunching |

## Recognizing the failure mode

| Symptom | Diagnosis | Fix |
|---|---|---|
| `squeue` shows `PENDING (QOSGrpMemLimit)` | Another user saturated the QOS group | `squeue -A <account>` to find them; reroute or wait |
| `squeue` shows `PENDING (QOSGrpCpuLimit)` | Same as Mem but for CPUs | Same |
| `squeue` shows `PENDING (QOSGrpGRES)` | YOUR jobs queueing for a GPU slot from your own QOS | **Normal**, not a problem |
| `squeue` shows `PENDING (BeginTime)` | Scheduled to start later | Not a real wait |
| All your jobs target a single account when config has multiple | Static `_build_cycle_assignment` ran with stale config | Apply live-aware routing |

## Final configuration

### `cli.py` injection point (~line 2041 in `_workflow_run`)
After the existing `pool = detect_live_multi_account(...)` call, add the `live_accounts` list build, hard-fail on zero capacity, and `--config live_accounts=<json>` extension to `cmd`.

### Snakefile parser block (top of multi-account section, ~line 124)
`LIVE_ACCOUNTS`, `_live_lookup()`, `_effective_gpu_slots()` — see Step 2 above.

### Snakefile assignment helpers (~lines 130–230, 369–460)
- `_build_cycle_assignment()`: use `_effective_gpu_slots(acct)` everywhere instead of `acct.get("gpu_slots", 0)`. Add fallback path that re-uses static `gpu_slots` if `LIVE_ACCOUNTS` zeroed everything (so bare `snakemake` runs still work).
- `_registration_assignment()`: sort by live `(gpu_avail, mem_avail_gb)` and pick top when nonzero; fall back to first GPU account otherwise.
- `_qc_cpu_assignment()`: sort by live `(mem_avail_gb, cpu_avail)` and pick top when nonzero; fall back to first CPU-capable account.

### `hpc.py` BLOCKED_ACCOUNTS
Document **why** each account is blocked in a comment block above the frozenset. The "why" is what lets future maintainers re-evaluate.

## Verification checklist

1. **CLI smoke test**: `kintsugi workflow run . --dry-run` should show `--config live_accounts=...` in the printed command.
2. **Snakefile smoke test**: `snakemake --config 'live_accounts=[{"name":"clive","gpu_avail":0,"cpu_avail":0,"mem_avail_gb":0},{"name":"maigan","gpu_avail":2,"cpu_avail":8,"mem_avail_gb":625}]' -np stitch` should route every cycle to maigan.
3. **Live verification**: After launching `kintsugi workflow batch -d <dataset> --detach`, run `scontrol show job <jobid> | grep -E "Account|Comment"` and confirm `Account=maigan` for every submitted job.
4. **Regression**: With both accounts healthy, cycle distribution should still follow proportional `gpu_slots` (preserved in static fallback path).

## Key insights

- **Detection without consumption is worse than no detection** — KINTSUGI had `detect_live_multi_account()` for months before this fix; the data was just thrown away.
- **Static config drifts faster than you think** — clive's QOS was silently throttled from 3 GPU/812 GB → 1 GPU/312.5 GB and the config files weren't reconciled. Always verify against live QOS limits, not docs.
- **First-account bias is a hidden failure mode** — every "pick the first account" loop is a single point of failure when that account misbehaves. Sort by live availability instead.
- **Snakemake `--config` supports JSON** — use `json.dumps()` for nested structures, not Python repr.
- **Hard-fail beats infinite queue** — if all accounts are saturated, abort with an actionable error message. Let the human investigate.
- **Permanent blocks need rationale comments** — `BLOCKED_ACCOUNTS = frozenset({"brusko"})` is opaque. Document **why** so future maintainers can re-evaluate.
- **Bulk config updates need yaml-aware tools** — `sed` is fragile for nested YAML. Use `yaml.safe_load`/`safe_dump` in a small Python script.

## When to apply this pattern

- Multi-tenant SLURM with shared investment QOS pools
- Account-level resource limits that include OTHER users' jobs in the count
- Snakemake DAG creation that pre-assigns jobs to accounts
- Static config files that drift from live cluster state
- Any "pick the first thing in the list" routing logic on multi-account systems

## References

- Plan file: `/home/smith6jt/.claude/plans/velvety-juggling-thimble.md`
- KINTSUGI workflow CLAUDE.md — "Multi-Account Architecture" section
- `slurm-concurrent-processing` skill — original multi-account architecture (now superseded by live-aware variant)
- `src/kintsugi/hpc.py:370` — `detect_current_usage()` (counts ALL users on a QOS, key for noisy-neighbor detection)
- `src/kintsugi/hpc.py:687` — `detect_live_multi_account()` (per-account live availability)
- HiPerGator account/QOS limits: https://help.rc.ufl.edu/doc/Account_and_QOS_Limits
