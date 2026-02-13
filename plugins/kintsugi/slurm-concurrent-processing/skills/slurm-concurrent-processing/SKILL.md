---
name: slurm-concurrent-processing
description: "KINTSUGI SLURM batch processing: Maximize throughput using multi-account resource calculation with GPU+CPU pools per account. Trigger: SLURM job submission, batch processing, resource maximization, GPU+CPU concurrent, headless processing, resource pool."
author: KINTSUGI Team
date: 2026-02-12
---

# SLURM Concurrent GPU+CPU Processing (Multi-Account Architecture)

## Experiment Overview
| Item | Details |
|------|---------|
| **Date** | 2026-02-12 (updated from 2026-02-11) |
| **Goal** | Maximize SLURM batch throughput using multi-account resource calculation — each account contributes BOTH GPU and CPU slots |
| **Environment** | HiPerGator HPC, SLURM scheduler, clive (3G+11C) + maigan (2G+8C) = 24 total concurrent slots |
| **Status** | Implemented (submit.sh + Snakemake) |

## Context

KINTSUGI has two processing modes with different resource strategies:

| Mode | Context | GPU Policy | CPU Policy |
|------|---------|------------|------------|
| **Notebook** | Interactive | GPU required, no fallback | Not used |
| **SLURM** | Headless batch | GPU + CPU concurrent | CPU concurrent |

**The Problem**: With only 3-5 GPUs available across accounts, limiting concurrency to GPU count leaves many CPU cores idle.

**The Solution**: **Multi-account resource calculation** — each account contributes both GPU slots (from QOS `gres/gpu`) and CPU slots (from `floor(0.85 * cpus / cpus_per_job)`). GPU and CPU partitions are independent pools — GPU jobs on `hpg-b200` do NOT consume CPU allocation on `hpg-default`. With clive (3G+11C) + maigan (2G+8C), we get 24 concurrent jobs instead of 5.

## Verified Workflow

### Multi-Account Resource Calculation

The key innovation is that **every** non-blocked account contributes both GPU and CPU slots. Each account's QOS limits are queried via `sacctmgr show associations`:

```python
# In detect_multi_account_resources() - src/kintsugi/hpc.py
# For EACH account:
gpu_slots = qos_gpu_limit                           # e.g., clive: 3, maigan: 2
cpu_slots = floor(0.85 * qos_cpu_limit / cpus_per_job)  # 85% cap

# Total = sum across all accounts
total_gpu = sum(acct.gpu_slots for acct in accounts)  # 3 + 2 = 5
total_cpu = sum(acct.cpu_slots for acct in accounts)  # 11 + 8 = 19
total_concurrent = total_gpu + total_cpu               # 24
```

**Example Calculation** (both accounts have GPUs AND CPUs):
| Account | CPUs | Memory | GPUs | GPU Slots | CPU Slots | Calculation |
|---------|------|--------|------|-----------|-----------|-------------|
| `clive` | 104 | 812 GB | 3 | 3 | 11 | GPUs: 3/1; CPUs: floor(0.85*104/8) |
| `maigan` | 80 | 625 GB | 2 | 2 | 8 | GPUs: 2/1; CPUs: floor(0.85*80/8) |
| **Total** | | | **5** | **5** | **19** | **24 concurrent jobs** |

**Important**: The old skill version incorrectly showed maigan with 0 GPUs. Both accounts have GPUs AND CPUs. The `brusko` account is permanently blocked (hard-coded in `BLOCKED_ACCOUNTS` frozenset).

### How Concurrent Processing Works

1. **Multi-Account Detection** (`hpc.py` + `submit.sh`):
   - `detect_multi_account_resources()` queries `sacctmgr show associations` for all user accounts
   - Filters burst accounts (`-b` suffix) and blocked accounts (`brusko`)
   - Each account contributes GPU slots + CPU slots independently
   - `detect_live_multi_account()` adds real-time usage data for availability calculation
   - Sets total concurrent = sum(GPU slots) + sum(CPU slots) across accounts

2. **Device Mode Export**:
   ```bash
   # submit.sh sets this based on job type
   export KINTSUGI_DEVICE_MODE=gpu   # For GPU jobs
   export KINTSUGI_DEVICE_MODE=cpu   # For CPU jobs
   ```

3. **Job Submission with Separate Accounts**:
   ```bash
   # GPU jobs: GPU account, GPU partition
   sbatch --account=clive --partition=hpg-b200 --qos=clive ...

   # CPU jobs: CPU account, CPU partition (guaranteed resources)
   sbatch --account=maigan --partition=hpg-default --qos=maigan ...
   ```

4. **Job Script Adaptation** (02_stitching.sh, 03_deconvolution.sh, 04_edf.sh):
   ```python
   # Read device mode from environment
   DEVICE_MODE = os.environ.get('KINTSUGI_DEVICE_MODE', 'gpu')

   # Initialize GPU with automatic fallback
   if DEVICE_MODE != 'cpu':
       try:
           import cupy as cp
           cp.cuda.Device(0).use()
           _ = cp.zeros(1)  # Test GPU access
           print("CUDA initialized successfully")
       except Exception as e:
           print(f"WARNING: CUDA initialization failed: {e}")
           print("Falling back to CPU processing")
           DEVICE_MODE = 'cpu'
   else:
       print("Running in CPU mode")

   # Use appropriate backend
   use_gpu = (DEVICE_MODE == 'gpu')
   corrector = KCorrectGPU(use_gpu=use_gpu, ...)
   ```

5. **Resource Allocation**:
   - GPU jobs: Standard time limits, 1 GPU per job, clive account
   - CPU jobs: 5x time multiplier (automatic), maigan account with guaranteed resources
   - Both run simultaneously using independent account pools
   - No preemption, no requeue — all jobs have guaranteed resources

### Implementation in Job Scripts

All GPU-capable job scripts follow this pattern:

```python
# 1. Read device mode (set by submit.sh based on account)
DEVICE_MODE = os.environ.get('KINTSUGI_DEVICE_MODE', 'gpu')

# 2. Attempt GPU initialization if not explicitly CPU mode
if DEVICE_MODE != 'cpu':
    try:
        import cupy as cp
        cp.cuda.Device(0).use()
        _ = cp.zeros(1)
        print(f"CUDA initialized successfully")
    except Exception as e:
        print(f"WARNING: CUDA initialization failed: {e}")
        DEVICE_MODE = 'cpu'

# 3. Pass device mode to processing functions
use_gpu = (DEVICE_MODE == 'gpu')
# Functions like KCorrectGPU, stitch_images accept use_gpu parameter
```

### Account Configuration

**submit.sh path** (`slurm/config.sh`):
```bash
ACCOUNT_CHAIN="clive"           # Primary GPU account
CPU_ONLY_ACCOUNTS="maigan"      # Additional CPU account
CPU_TIME_MULTIPLIER=5
```

**Snakemake path** (`workflow/config.yaml`):
```yaml
resources:
  accounts:
    - name: clive
      partition_gpu: "hpg-b200,hpg-turin"
      partition_cpu: hpg-default
      gpu_slots: 3
      cpu_slots: 11
    - name: maigan
      partition_gpu: "hpg-b200,hpg-turin"
      partition_cpu: hpg-default
      gpu_slots: 2
      cpu_slots: 8
```

Both paths use the same `detect_multi_account_resources()` in `hpc.py`.

## Failed Attempts (Critical)

| Attempt | Why it Failed | Lesson Learned |
|---------|---------------|----------------|
| GPU as sole limiting factor | With 3 GPUs, only 3 concurrent jobs even with 104 CPUs | Calculate from BOTH GPU and CPU pools |
| GPU-only processing for SLURM | CPU cores sit idle with only 3 GPUs | Headless mode should maximize ALL resources |
| CPU fallback only on GPU failure | Doesn't utilize CPU proactively | Need concurrent GPU+CPU, not just fallback |
| Same time limits for GPU and CPU | CPU jobs timeout | Apply 5x time multiplier for CPU jobs |
| Applying notebook GPU-only policy to SLURM | Wastes resources | Different modes need different strategies |
| CPU pool from "remaining" GPU account resources | Underestimates CPU capacity — treats GPU and CPU as one shared pool | Use independent account pools with separate QOS limits |
| Burst QOS for CPU jobs | OOM kills — burst nodes are oversubscribed, memory not guaranteed | Use regular account QOS with guaranteed resource allocation |
| `sacctmgr show user USERNAME format=account` | Returns empty pipe on HiPerGator | Use `sacctmgr show associations user=USERNAME format=account -n -P` |
| Treating maigan as CPU-only (0 GPUs) | Wasted 2 GPU slots — maigan has GPUs too | Query every account for BOTH GPU and CPU limits |

## Key Differences from Notebook Mode

| Aspect | Notebook Mode | SLURM Mode |
|--------|---------------|------------|
| User presence | Interactive, watching | Headless, batch |
| GPU policy | Required, fail if unavailable | Preferred, CPU concurrent |
| CPU policy | Not used | Used for overflow/concurrent |
| Error handling | Fail loudly, user intervenes | Log and continue where possible |
| Resource goal | Quality-first | Maximize throughput |
| Quality parameters | Same | Same (unchanged) |

**Important**: Quality parameters (BaSiC iterations, tolerances, etc.) remain **unchanged** between modes. Only the compute device differs - GPU is faster, CPU is slower but utilizes idle resources.

## Final Configuration

### Job Scripts with GPU/CPU Support

| Script | GPU Support | CPU Support | Device Mode Variable |
|--------|-------------|-------------|---------------------|
| `02_stitching.sh` | Yes (CuPy) | Yes (NumPy) | `KINTSUGI_DEVICE_MODE` |
| `03_deconvolution.sh` | Yes (CuPy) | Yes (SciPy) | `KINTSUGI_DEVICE_MODE` |
| `04_edf.sh` | Yes (CuPy) | Yes (NumPy) | `KINTSUGI_DEVICE_MODE` |

### Environment Variables

| Variable | Values | Set By | Used By |
|----------|--------|--------|---------|
| `KINTSUGI_DEVICE_MODE` | `gpu`, `cpu` | `submit.sh` | All job scripts |
| `GPU_SLOTS` | Integer (e.g., 3) | `submit.sh` | Resource logging |
| `CPU_SLOTS` | Integer (e.g., 10) | `submit.sh` | Resource logging |
| `ALLOC_CPUS` | Integer (e.g., 104) | `sacctmgr` (GPU account) | `submit.sh` |
| `ALLOC_MEM` | Integer GB (e.g., 812) | `sacctmgr` (GPU account) | `submit.sh` |
| `ALLOC_GPUS` | Integer (e.g., 3) | `sacctmgr` (GPU account) | `submit.sh` |
| `CPU_ALLOC_CPUS` | Integer (e.g., 80) | `sacctmgr` (CPU account) | `submit.sh` |
| `CPU_ALLOC_MEM` | Integer GB (e.g., 625) | `sacctmgr` (CPU account) | `submit.sh` |
| `CPU_CPUS_PER_TASK` | Integer (e.g., 8) | `config.sh` | `submit.sh` |
| `CPU_MEM_DECON` | Integer GB (e.g., 48) | `config.sh` | `submit.sh` |
| `CUDA_VISIBLE_DEVICES` | GPU IDs | SLURM | CuPy |
| `CPU_TIME_MULTIPLIER` | `5` (default) | `config.sh` | `submit.sh` |

## Key Insights

- **Independent account pools are the key innovation** - GPU and CPU accounts have separate QOS limits, giving truly additive concurrency
- **Guaranteed resources prevent OOM kills** - Burst QOS has unreliable memory enforcement; regular QOS gives each job its full allocation
- **Regular QOS gives predictable performance** - No preemption, no requeue overhead, no wasted compute from killed jobs
- **Notebook vs SLURM are different paradigms** - Don't apply interactive policies to batch processing
- **Maximize ALL resources** - With limited GPUs, use CPU cores from a separate account for overflow
- **Same quality, different speed** - CPU processing takes longer but produces identical results
- **5x time multiplier is empirically derived** - CPU processing typically 3-7x slower than GPU

## When to Apply This Pattern

- SLURM batch processing on HPC clusters
- Limited GPU availability (1-3 GPUs) relative to CPU allocation
- Large datasets requiring many cycles (more cycles than GPUs)
- Need to maximize throughput over wall-clock time
- Processing can run overnight/unattended
- Multiple SLURM accounts available with different resource types

## CLI Output Example

```
Resource pool calculation:
  GPU job slots: 3 (from GPU account: 3 GPUs)
  CPU job slots: 10 (from CPU account: 80 CPUs, 625GB mem)
  Total concurrent jobs: 13
  GPU pool: 3 (3 GPUs on GPU account), CPU pool: 10 (80 CPUs, 625GB on CPU account)

Resource Allocation (Dual-Pool Architecture):
  GPU account (clive): 104 CPUs, 812GB mem, 3 GPUs
  CPU account (maigan): 80 CPUs, 625GB mem
  GPU jobs: 8 CPUs, 180GB mem, 1 GPU each (account: clive)
  CPU jobs: 8 CPUs, 48GB mem each (account: maigan)
  GPU slots: 3, CPU slots: 10
  Total concurrent: 13 jobs
```

## References

- KINTSUGI CLAUDE.md - "Multi-Account Architecture" and "Snakemake Workflow" sections
- `snakemake-workflow-architecture` skill - Snakemake-specific design (lambda resources, cycle pre-assignment)
- `gpu-quality-priority` skill - Notebook-specific GPU enforcement
- `slurm-workflow-integration` skill - SLURM setup and submission
- `src/kintsugi/hpc.py` - `detect_multi_account_resources()`, `detect_live_multi_account()`
- HiPerGator account/QOS limits: https://help.rc.ufl.edu/doc/Account_and_QOS_Limits
