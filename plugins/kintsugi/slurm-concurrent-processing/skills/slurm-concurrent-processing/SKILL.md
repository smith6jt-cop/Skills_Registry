---
name: slurm-concurrent-processing
description: "KINTSUGI SLURM batch processing: Maximize throughput using dual-pool resource calculation with independent GPU and CPU accounts. Trigger: SLURM job submission, batch processing, resource maximization, GPU+CPU concurrent, headless processing, resource pool."
author: KINTSUGI Team
date: 2026-02-11
---

# SLURM Concurrent GPU+CPU Processing (Dual-Pool Architecture)

## Experiment Overview
| Item | Details |
|------|---------|
| **Date** | 2026-02-11 |
| **Goal** | Maximize SLURM batch throughput using dual-pool resource calculation with independent GPU and CPU account pools |
| **Environment** | HiPerGator HPC, SLURM scheduler, 3 GPUs (clive account), 80 CPUs/625GB (maigan account) = 13 total concurrent slots |
| **Status** | Implemented |

## Context

KINTSUGI has two processing modes with different resource strategies:

| Mode | Context | GPU Policy | CPU Policy |
|------|---------|------------|------------|
| **Notebook** | Interactive | GPU required, no fallback | Not used |
| **SLURM** | Headless batch | GPU + CPU concurrent | CPU concurrent |

**The Problem**: With only 3 GPUs available, limiting concurrency to GPU count (3 jobs) leaves many CPU cores idle. For a 9-cycle dataset, this is inefficient.

**The Solution**: **Dual-pool resource calculation** - calculate total concurrent jobs from independent GPU and CPU account pools. With 3 GPU slots (clive account) + 10 CPU slots (maigan account), we can run 13 jobs concurrently instead of 3.

## Verified Workflow

### Dual-Pool Resource Calculation

The key innovation is calculating total concurrent jobs from **independent** GPU and CPU account pools, each with their own QOS limits queried via `sacctmgr`:

```bash
# In calculate_max_concurrent() - slurm/submit.sh

# GPU Pool: From GPU account (ACCOUNT_CHAIN), queried via sacctmgr
# clive QOS: 104 CPUs, 812GB, 3 GPUs
gpu_slots=$((ALLOC_GPUS / GPUS_PER_NODE))  # e.g., 3/1 = 3

# CPU Pool: From CPU account (CPU_ONLY_ACCOUNTS), independent limits
# auto_detect_cpu_allocation() queries maigan QOS via sacctmgr
# maigan QOS: 80 CPUs, 625GB, 0 GPUs
cpu_slots_by_cpu=$((CPU_ALLOC_CPUS / CPU_CPUS_PER_TASK))  # 80/8 = 10
cpu_slots_by_mem=$((CPU_ALLOC_MEM / CPU_MEM_DECON))        # 625/48 = 13
cpu_slots=$((cpu_slots_by_cpu < cpu_slots_by_mem ? cpu_slots_by_cpu : cpu_slots_by_mem))  # min(10,13) = 10

# Total concurrent = GPU slots + CPU slots
COMPUTED_MAX_CONCURRENT=$((gpu_slots + cpu_slots))  # 3 + 10 = 13
```

**Example Calculation** (clive: 3 GPUs, 104 CPUs, 812GB; maigan: 80 CPUs, 625GB):
| Resource | GPU Pool (clive) | CPU Pool (maigan) | Calculation |
|----------|------------------|-------------------|-------------|
| GPUs | 3 | 0 | 3 GPUs / 1 per job |
| CPUs | 104 | 80 | Independent accounts |
| Memory | 812 GB | 625 GB | Independent accounts |
| Slots by CPU | 3 | 10 | 80/8 = 10 |
| Slots by Mem | 3 | 13 | 625/48 = 13 |
| **Slots** | **3** | **10** | min(10,13) = 10 |
| **Total** | **13** | | 3 GPU + 10 CPU concurrent jobs |

### How Concurrent Processing Works

1. **Dual-Pool Calculation** (`submit.sh`):
   - Auto-detects GPU account limits from `ACCOUNT_CHAIN` (clive) via `sacctmgr`
   - Auto-detects CPU account limits from `CPU_ONLY_ACCOUNTS` (maigan) via `auto_detect_cpu_allocation()`
   - Calculates GPU slots from GPU account QOS limits
   - Calculates CPU slots from CPU account QOS limits (independent pool)
   - Sets `EFFECTIVE_MAX_CONCURRENT = GPU_SLOTS + CPU_SLOTS`

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

### Account Chain Configuration

In `slurm/config.sh`:
```bash
# GPU account (for GPU partition)
ACCOUNT_CHAIN="clive"

# CPU account (for CPU partition - guaranteed resources)
CPU_ONLY_ACCOUNTS="maigan"

# CPU partition
PARTITION_CPU="hpg-default"

# Time multiplier for CPU processing (5x slower than GPU)
CPU_TIME_MULTIPLIER=5
```

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

- KINTSUGI CLAUDE.md - "Resource Pool Calculation" section
- KINTSUGI README.md - "Resource Pool Architecture" section
- `gpu-quality-priority` skill - Notebook-specific GPU enforcement
- `slurm-workflow-integration` skill - SLURM setup and submission
- HiPerGator account/QOS limits: https://help.rc.ufl.edu/doc/Account_and_QOS_Limits
