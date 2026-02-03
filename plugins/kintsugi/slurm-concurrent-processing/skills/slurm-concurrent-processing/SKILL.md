---
name: slurm-concurrent-processing
description: "KINTSUGI SLURM batch processing: Maximize throughput using concurrent GPU and CPU jobs. Trigger: SLURM job submission, batch processing, resource maximization, GPU+CPU concurrent, headless processing."
author: KINTSUGI Team
date: 2026-02-03
---

# SLURM Concurrent GPU+CPU Processing

## Experiment Overview
| Item | Details |
|------|---------|
| **Date** | 2026-02-03 |
| **Goal** | Maximize SLURM batch throughput by running GPU and CPU jobs concurrently |
| **Environment** | HiPerGator HPC, SLURM scheduler, 2 GPUs max, many CPU cores |
| **Status** | Implemented |

## Context

KINTSUGI has two processing modes with different resource strategies:

| Mode | Context | GPU Policy | CPU Policy |
|------|---------|------------|------------|
| **Notebook** | Interactive | GPU required, no fallback | Not used |
| **SLURM** | Headless batch | GPU preferred | CPU concurrent |

**The Problem**: With only 2 GPUs available on HiperGator, running GPU-only jobs leaves many CPU cores idle. For large datasets with many cycles, this is inefficient.

**The Solution**: Run GPU jobs AND CPU jobs concurrently. GPU accounts process cycles on GPU while CPU-only burst accounts process additional cycles on CPU simultaneously.

## Verified Workflow

### How Concurrent Processing Works

1. **Account Chain Selection** (`submit.sh`):
   - Primary accounts (GPU-enabled): `maigan`, `clive`
   - Overflow accounts (CPU-only): `maigan-b` (burst)
   - Jobs submitted to first available account in chain

2. **Device Mode Export**:
   ```bash
   # submit.sh sets this based on account type
   export KINTSUGI_DEVICE_MODE=gpu   # For GPU accounts
   export KINTSUGI_DEVICE_MODE=cpu   # For CPU-only burst accounts
   ```

3. **Job Script Adaptation** (02_stitching.sh, 03_deconvolution.sh, 04_edf.sh):
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
       print("Running in CPU mode (CPU-only burst account)")

   # Use appropriate backend
   use_gpu = (DEVICE_MODE == 'gpu')
   corrector = KCorrectGPU(use_gpu=use_gpu, ...)
   ```

4. **Resource Allocation**:
   - GPU jobs: Standard time limits, 1 GPU per job
   - CPU jobs: 5x time multiplier (automatic), more CPUs per job
   - Both run simultaneously on different partitions

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
# Account chain: GPU accounts first, burst (CPU-only) as overflow
ACCOUNT_CHAIN="maigan,clive,maigan-b"

# CPU-only accounts (burst accounts without GPU allocation)
CPU_ONLY_ACCOUNTS="maigan-b,clive-b"

# Time multiplier for CPU processing (5x slower than GPU)
CPU_TIME_MULTIPLIER=5

# Burst partition for --use-burst flag
PARTITION_BURST="hpg-default"
```

### Using Burst Resources (`--use-burst`)

Burst QOS provides access to idle cluster resources. Jobs are preemptible but can significantly speed up processing when the cluster has spare capacity.

```bash
# Submit with burst enabled
kintsugi slurm submit . --use-burst

# Burst with specific steps
kintsugi slurm submit . --steps decon,edf --use-burst
```

**How burst works:**
1. Primary jobs submitted to allocated QOS (guaranteed, higher priority)
2. Duplicate jobs submitted to burst QOS (preemptible, lower priority)
3. Burst jobs include `--requeue` flag for automatic requeue if preempted
4. SLURM scheduler prioritizes allocated jobs
5. Burst jobs run on idle/spare cluster capacity

**Burst job characteristics:**
- Use the same job scripts as allocated jobs
- Can request GPUs (preemptible but available when cluster is idle)
- Automatically requeued if preempted by higher-priority jobs
- Run concurrently with allocated jobs when resources permit

**When to use burst:**
- Large datasets with many cycles
- Tight deadlines (need faster processing)
- During off-peak hours when cluster is likely idle
- When some redundant processing is acceptable

## Failed Attempts (Critical)

| Attempt | Why it Failed | Lesson Learned |
|---------|---------------|----------------|
| GPU-only processing for SLURM | CPU cores sit idle with only 2 GPUs | Headless mode should maximize ALL resources |
| CPU fallback only on GPU failure | Doesn't utilize CPU proactively | Need concurrent GPU+CPU, not just fallback |
| Same time limits for GPU and CPU | CPU jobs timeout | Apply 5x time multiplier for CPU jobs |
| Applying notebook GPU-only policy to SLURM | Wastes resources | Different modes need different strategies |

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
| `CUDA_VISIBLE_DEVICES` | GPU IDs | SLURM | CuPy |
| `CPU_TIME_MULTIPLIER` | `5` (default) | `config.sh` | `submit.sh` |

## Key Insights

- **Notebook vs SLURM are different paradigms** - Don't apply interactive policies to batch processing
- **Maximize ALL resources** - With limited GPUs, use CPU cores for overflow
- **Same quality, different speed** - CPU processing takes longer but produces identical results
- **Account chain enables concurrent processing** - GPU accounts + burst accounts = parallel execution
- **5x time multiplier is empirically derived** - CPU processing typically 3-7x slower than GPU

## When to Apply This Pattern

- SLURM batch processing on HPC clusters
- Limited GPU availability (1-2 GPUs)
- Large datasets requiring many cycles
- Need to maximize throughput over wall-clock time
- Processing can run overnight/unattended

## References

- KINTSUGI CLAUDE.md - Processing Modes section
- `gpu-quality-priority` skill - Notebook-specific GPU enforcement
- `slurm-workflow-integration` skill - SLURM setup and submission
- HiPerGator burst accounts: https://help.rc.ufl.edu/doc/Account_and_QOS_Limits
