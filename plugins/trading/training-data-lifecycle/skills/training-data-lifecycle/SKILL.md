# Training Data Lifecycle Management (v5.4.2)

## Context
Colab training runs produce ~20 GB of artifacts (100 checkpoints + models + logs) but only ~400 MB is needed (final models + metadata). The first crypto training run (2026-03-30) produced 15.8 GB across 10 zip files that had to be manually downloaded and extracted. This skill documents the structured lifecycle system that replaced the ad-hoc approach.

## What Worked
- **Run-scoped directories**: `runs/{RUN_ID}/` on Drive with manifest.json, models/, checkpoints/, tensorboard/ — self-contained per run, easy to understand and clean up
- **Checkpoint pruning**: Keep only best + final per symbol (~85% space savings, ~18 GB → ~1.5 GB per run)
- **Deploy zip packaging**: Single `deploy_{RUN_ID}.zip` containing only models + manifest (~400 MB-2 GB instead of 15-35 GB)
- **Local deploy script**: `scripts/deploy_from_archive.py` with stage → promote workflow — clear separation between evaluation and deployment
- **Manifest as lineage source**: SHA-256 hashes, data range, checkpoint selection, gating results all in one JSON
- **Retention policy**: Auto-compress after 30 days, delete after 180 days — prevents unbounded Drive growth

## What Failed / Lessons Learned
1. **Flat `trained_models/` directory**: Models from different runs clobbered each other. No way to tell which run produced which model.
2. **Flat `checkpoints/` directory**: 100+ checkpoints per run accumulated forever. No cleanup mechanism.
3. **Manual zip download**: Downloading entire Colab_Projects/ directory (15-35 GB) when only 2-4 GB of models was needed.
4. **Ad-hoc local archive dirs**: `models_old/`, `checkpoints/mar18/`, `rl_symbols_hold/crypto_drop/` — no metadata, no standard naming.
5. **Crypto symbol `/` in paths** (root cause of first failure): `BTC/USD` treated as directory separator. Always use `sanitize_symbol()`.
6. **Stale verification cell after migration (2026-04-07)**: The notebook's `cf7wloyhe3t` "DISCONNECT COLAB RUNTIME" cell still hard-coded `drive_model_dir = '/content/drive/MyDrive/Colab_Projects/trained_models'` after the v5.4.2 layout migration. After a successful run it printed `[!] WARNING: No models found on Google Drive!` (false alarm) or listed pre-migration leftovers, making the user believe v5.4.2 archival was broken. The actual training and packaging worked correctly — only the verification was lying. **Lesson**: when migrating a folder layout in a long-lived notebook, grep the entire notebook for the old path strings and audit every match — verification/disconnect/cleanup cells are easy to miss because they don't appear to participate in training. The historical comment in cell `jw1po5eou4q` ("# This replaces the old flat trained_models/ and checkpoints/ layout.") is the *only* legitimate remaining reference; everything else is a bug.

## Post-Migration Cleanup Checklist
After v5.4.2 (or any layout migration), the following pre-migration folders may remain on Drive and locally. They are safe to delete after verifying the new `runs/{RUN_ID}/` layout has the data:

**On Drive** (`MyDrive/Colab_Projects/`):
- `trained_models/` — pre-v5.4.2 flat model dump
- `checkpoints/` — pre-v5.4.2 flat checkpoint dump
- `training_archives/` — pre-v5.4.2 archive dir (NOT the same as the local one — see below)

**Locally** (`/home/smith/Alpaca_trading/`):
- `training_archives/*.tar.gz` — pre-v5.4.2 archives. **Keep the folder + `index.json`** (still used by `scripts/deploy_from_archive.py:35` and `alpaca_trading/training/archive.py:67`).
- `checkpoints/` — top-level, usually empty after migration
- `models/checkpoints/{date}/` — old per-run checkpoint dumps
- `models/rl_symbols_staging/{date}/trained_models/` — old nested staging (v5.4.2+ stages flat at `rl_symbols_staging/{file}.pt`)

## Recommended Approach

### Colab Workflow
```python
# Cell 12: Initialize manifest manager
DRIVE_RUNS_DIR = '/content/drive/MyDrive/Colab_Projects/runs'
MANIFEST_MGR = RunManifestManager(runs_dir=DRIVE_RUNS_DIR)

# Cell 32: Create run, train, record per-symbol results
RUN_MANIFEST = MANIFEST_MGR.create(version=..., training_mode=..., ...)
# ... training loop records symbols incrementally ...

# Cell 36: Prune, hash, finalize, package, enforce retention
MANIFEST_MGR.prune_checkpoints(RUN_MANIFEST)
MANIFEST_MGR.compute_model_hashes(RUN_MANIFEST)
MANIFEST_MGR.finalize(RUN_MANIFEST)
MANIFEST_MGR.create_deploy_zip(RUN_MANIFEST)
enforce_retention_policy(runs_dir=DRIVE_RUNS_DIR, archives_dir=...)
```

### Local Deployment
```bash
python scripts/deploy_from_archive.py deploy_20260401_130247.zip     # Stage
python scripts/deploy_from_archive.py --promote --run-id 20260401... # Deploy
python scripts/deploy_from_archive.py --list                          # History
```

### Retention Policy
| Artifact | Active | Archive | Delete |
|----------|--------|---------|--------|
| Run dir (Drive) | 30 days | Compressed | 180 days |
| Held models (local) | 90 days | — | Delete |
| Manifests/metadata | Forever | — | Never |

## Key Files
- `alpaca_trading/training/manifest.py` — RunManifest, RunManifestManager
- `alpaca_trading/training/retention.py` — RetentionPolicy, enforce_retention_policy
- `scripts/deploy_from_archive.py` — Local deploy CLI
- `notebooks/training.ipynb` cells 12, 32, 36 — Colab integration

## Environment
- Verified: v5.4.2, Python 3.12, Colab H100/A100
- Drive quota: ~20 GB/run permanent → ~2 GB for 30 days → ~10 MB permanent
