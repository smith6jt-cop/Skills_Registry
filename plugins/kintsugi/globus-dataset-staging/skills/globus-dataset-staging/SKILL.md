---
name: globus-dataset-staging
description: "Globus CLI workflow for staging HuBMAP CODEX datasets from remote endpoints to HiPerGator"
author: KINTSUGI Team
date: 2026-02-13
---

# globus-dataset-staging - Research Notes

## Experiment Overview
| Item | Details |
|------|---------|
| **Date** | 2026-02-13 |
| **Goal** | Transfer 13 thymus CODEX datasets (~2.4 TB) from PATH lab SMB share to HiPerGator /blue via Globus |
| **Environment** | HiPerGator, `module load globus`, Globus CLI 3.x, Python 3.11 |
| **Status** | Success (7/13 datasets submitted in first batch) |

## Context
Thymus datasets are stored on a PATH lab SMB share (`path.ahc.ufl.edu`) exposed via a Globus Connect Personal endpoint — NOT on HiPerGator orange storage. The existing rsync-based `stage_datasets.sh` only works for orange→blue transfers. Needed a Globus-based alternative for cross-endpoint transfers.

## Verified Workflow

### 1. Load Globus and authenticate
```bash
module load globus
globus login
```

### 2. Complete data_access consent for HiPerGator
The mapped collection requires explicit consent. The scope URL is very long and wraps in terminals, causing errors. Write it to a script:
```bash
cat > /tmp/globus_consent.sh << 'SCRIPT'
globus session consent 'urn:globus:auth:scope:transfer.api.globus.org:all[*https://auth.globus.org/scopes/5dbaf795-8a7e-4dca-91aa-6e10d610c2b3/data_access]'
SCRIPT
bash /tmp/globus_consent.sh
```

### 3. Transfer datasets
```bash
python stage_datasets_globus.py transfer CX_20-005_TH_CC1-A CX_20-005_TH_CC2-B
```

### 4. Check status
```bash
python stage_datasets_globus.py status
globus task list --limit 10
```

## Key Endpoints

| Endpoint | UUID | Description |
|----------|------|-------------|
| PATH lab GCP | `f1b69b9e-f07a-11ef-8c40-0e26ca329435` | Source: Globus Connect Personal on PATH lab workstation |
| UFRC HiPerGator | `5dbaf795-8a7e-4dca-91aa-6e10d610c2b3` | Destination: HiPerGator mapped collection |

Source base path (cifs): `/mnt/ahc_share/SHARE/HuBMAP/`
Source base path (GVFS, DEPRECATED): `/run/user/1001/gvfs/smb-share:server=path.ahc.ufl.edu,share=path$/SHARE/HuBMAP/`

**CRITICAL: Use cifs mount, NOT GVFS.** GVFS SMB mounts (`/run/user/1001/gvfs/...`) cause `Fatal FTP response: end-of-file was reached` errors during bulk transfers (~212 faults per task). GVFS is session-dependent desktop middleware, not suitable for sustained I/O. A proper cifs mount is stable (~7 MB/s per concurrent task, 0 faults).

## Failed Attempts (Critical)

| Attempt | Why it Failed | Lesson Learned |
|---------|---------------|----------------|
| Used endpoint UUID from HiPerGator README (`10f408d9-...`) | That was a guest collection for sharing, not the main mapped collection | Use `globus endpoint search "HiPerGator"` to find `5dbaf795-...` |
| Tried `2123cd72-...` endpoint | "endpoint is non_functional" error | Multiple HiPerGator endpoints exist; only `5dbaf795-...` is active |
| Pasted long consent URL directly in terminal | "client_id must be a valid UUID" or "Query string cannot include newlines" | Terminal wraps the long scope URL. Write to a shell script instead |
| Used `--batch` for dataset with spaces in path (`CX_21-011 L-B_TH_reg1-2`) | Batch format splits on whitespace, corrupting the path | Transfer datasets with spaces as individual `globus transfer` commands, not batch |
| Assumed all datasets have same nesting structure | Some have extra `data/` level (e.g., `CX_21-010_LN_n3/data/src_*/`) | Always verify with `globus ls` before building path mappings |
| Assumed release folder names follow consistent pattern | Release1 uses `Codex_dataset_hubmap_*`, Release2 uses `CODEX_dataset_hubmap_*` (different casing) | Hardcode exact folder names rather than pattern-matching |
| Used GVFS SMB mount (`/run/user/1001/gvfs/...`) as source path | `Fatal FTP response: end-of-file was reached` — 212 faults per task, <0.4% data transferred | GVFS is session-dependent desktop middleware. Use cifs mount (`/mnt/ahc_share/...`) instead |
| Didn't activate endpoint before resubmitting | `Activated: False` despite `GCP Connected: True` — transfers accepted but fail immediately | Run `globus endpoint activate <UUID>` before any transfer. GCP requires periodic credential renewal |

## Final Parameters

### Source path structure (3 release folders)
```
Release1: Codex_dataset_hubmap_Case1-4_Release1_D2019-2020/{dataset}/src_{dataset}/
Release2: CODEX_dataset_hubmap_Case5-9_Release2/{dataset}/src_{dataset}/
Release3: Codex_dataset_HuBMAP_cases10-14_release3/{dataset}/src_{dataset}/
```

### Transfer flags
```bash
globus transfer SRC_EP:src_path DST_EP:dst_path \
  --recursive \
  --sync-level size \
  --preserve-timestamp \
  --notify failed,inactive \
  --label "KINTSUGI: dataset_name"
```

### Path quirks to watch for
```yaml
CX_19-001_thymus_CC2-C:  src dir is "src_CX_19-001_thymus_CC2-C_NBF" (NBF suffix)
CX_20-006_TH_CC2-B:      parent dir is "CX_20-006_TH_CC2-B(NEW)" (parentheses in name)
CX_21-011_L-B_TH_reg1-2: spaces in both parent and src dir names
CX_21-010_LN_n3:         extra data/ nesting: {dataset}/data/src_{dataset}/
```

### Key files
```
stage_datasets_globus.py         - Main transfer script (list/transfer/status/cancel/reset)
globus_transfers.json            - Task log (auto-created by script)
dataset_manifest.csv             - 47 datasets (34 spleen/LN + 13 thymus)
thymus_manifest.csv              - 13 thymus datasets standalone
```

## Key Insights
- **GVFS mounts are unreliable for Globus.** Use `sudo mount -t cifs //path.ahc.ufl.edu/path$ /mnt/ahc_share -o username=...,domain=...` instead. GVFS causes EOF errors under sustained read load.
- Always run `globus endpoint activate <UUID>` before transfers. GCP endpoints deactivate when credentials expire.
- Globus Connect Personal endpoints may go offline when the host machine sleeps/reboots. Check source endpoint is active before starting large transfers.
- `--sync-level size` enables safe re-runs without re-transferring completed files.
- HiPerGator's mapped collection requires periodic consent renewal. If transfers suddenly fail with auth errors, re-run the consent script.
- The `--batch` flag is faster for multiple datasets but incompatible with paths containing spaces. Use a hybrid approach: batch for normal paths, individual commands for space-containing paths.
- Thymus datasets range from 26 GB (3x3 grid) to 350 GB (17x11 grid). Plan storage accordingly.
- Always use `KINTSUGI_Projects/{dataset_name}/data/raw/` as the destination to match project init expectations.

## References
- `stage_datasets_globus.py` in KINTSUGI repo root
- `workflow/CLAUDE.md` — Globus staging section with endpoint details
- Globus CLI docs: https://docs.globus.org/cli/
