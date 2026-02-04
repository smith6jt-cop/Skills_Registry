---
name: slurm-concurrent-processing
description: "KINTSUGI SLURM batch processing: Maximize throughput using dual-pool resource calculation and dynamic job promotion. Trigger: SLURM job submission, batch processing, resource maximization, GPU+CPU concurrent, headless processing, resource pool, job promotion."
author: KINTSUGI Team
date: 2026-02-04
---

# SLURM Concurrent GPU+CPU Processing (Dual-Pool Architecture)

## Experiment Overview
| Item | Details |
|------|---------|
| **Date** | 2026-02-04 |
| **Goal** | Maximize SLURM batch throughput using dual-pool resource calculation and dynamic job promotion |
| **Environment** | HiPerGator HPC, SLURM scheduler, 3 GPUs, 104 CPUs, 812GB RAM |
| **Status** | Implemented |

## Context

KINTSUGI has two processing modes with different resource strategies:

| Mode | Context | GPU Policy | CPU Policy |
|------|---------|------------|------------|
| **Notebook** | Interactive | GPU required, no fallback | Not used |
| **SLURM** | Headless batch | GPU + CPU concurrent | CPU concurrent |

**The Problem**: With only 3 GPUs available, limiting concurrency to GPU count (3 jobs) leaves many CPU cores idle. For a 9-cycle dataset, this is inefficient.

**The Solution**: **Dual-pool resource calculation** - calculate total concurrent jobs from both GPU and CPU resource pools. With 3 GPUs + remaining CPU resources, we can run 8 jobs concurrently instead of 3.

## Verified Workflow

### Dual-Pool Resource Calculation

The key innovation is calculating total concurrent jobs from **both** GPU and CPU resource pools:

```bash
# In calculate_max_concurrent() - slurm/submit.sh

# GPU Pool: Limited by allocated GPUs
gpu_slots=$((ALLOC_GPUS / GPUS_PER_NODE))  # e.g., 3/1 = 3

# CPU Pool: Limited by remaining resources after GPU allocation
cpus_used_by_gpu=$((gpu_slots * CPUS_PER_TASK))      # 3 * 8 = 24
cpus_for_cpu_jobs=$((ALLOC_CPUS - cpus_used_by_gpu)) # 104 - 24 = 80
cpu_slots_by_cpu=$((cpus_for_cpu_jobs / CPU_CPUS_PER_TASK))  # 80/8 = 10

mem_used_by_gpu=$((gpu_slots * MEM_DECON))           # 3 * 180 = 540
mem_for_cpu_jobs=$((ALLOC_MEM - mem_used_by_gpu))    # 812 - 540 = 272
cpu_slots_by_mem=$((mem_for_cpu_jobs / CPU_MEM_DECON))  # 272/48 = 5

# CPU slots = minimum of CPU and memory limits
cpu_slots=$((cpu_slots_by_cpu < cpu_slots_by_mem ? cpu_slots_by_cpu : cpu_slots_by_mem))

# Total concurrent = GPU slots + CPU slots
COMPUTED_MAX_CONCURRENT=$((gpu_slots + cpu_slots))  # 3 + 5 = 8
```

**Example Calculation** (104 CPUs, 812GB, 3 GPUs):
| Resource | GPU Jobs | CPU Jobs | Calculation |
|----------|----------|----------|-------------|
| GPUs | 3 | 0 | 3 GPUs / 1 per job |
| CPUs | 24 | 80 | 104 - (3×8) = 80 remaining |
| Memory | 540 GB | 272 GB | 812 - (3×180) = 272 remaining |
| CPU slots | - | 5 | min(80/8, 272/48) = min(10,5) |
| **Total** | **8** | | 3 GPU + 5 CPU concurrent jobs |

### Dynamic Job Promotion

The burst monitor (`burst_monitor.sh`) promotes jobs to better resources when available:

1. **Burst → Allocated**: Preemptible GPU jobs promoted to guaranteed QOS
2. **CPU → GPU**: CPU jobs promoted to GPU when GPUs free up

```bash
# In burst_monitor.sh - promote_cpu_to_gpu() function
# When GPUs become available, cancel CPU job and resubmit as GPU job
if [ "${idle_nodes}" -gt 0 ] && [ -n "${pending_cpu}" ]; then
    promote_cpu_to_gpu "${job_id}" "${job_name}"
fi
```

Promotion priority: Burst jobs first (already GPU-ready), then CPU jobs.

### How Concurrent Processing Works

1. **Dual-Pool Calculation** (`submit.sh`):
   - Calculates GPU slots from `ALLOC_GPUS / GPUS_PER_NODE`
   - Calculates CPU slots from remaining resources after GPU allocation
   - Sets `EFFECTIVE_MAX_CONCURRENT = GPU_SLOTS + CPU_SLOTS`
   - Exports `GPU_SLOTS` and `CPU_SLOTS` for burst_monitor.sh

2. **Device Mode Export**:
   ```bash
   # submit.sh sets this based on job type
   export KINTSUGI_DEVICE_MODE=gpu   # For GPU jobs
   export KINTSUGI_DEVICE_MODE=cpu   # For CPU jobs
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
       print("Running in CPU mode")

   # Use appropriate backend
   use_gpu = (DEVICE_MODE == 'gpu')
   corrector = KCorrectGPU(use_gpu=use_gpu, ...)
   ```

4. **Resource Allocation**:
   - GPU jobs: Standard time limits, 1 GPU per job
   - CPU jobs: 5x time multiplier (automatic), use remaining CPUs/memory
   - Both run simultaneously using different resource pools

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
| GPU as sole limiting factor | With 3 GPUs, only 3 concurrent jobs even with 104 CPUs | Calculate from BOTH GPU and CPU pools |
| GPU-only processing for SLURM | CPU cores sit idle with only 3 GPUs | Headless mode should maximize ALL resources |
| CPU fallback only on GPU failure | Doesn't utilize CPU proactively | Need concurrent GPU+CPU, not just fallback |
| Same time limits for GPU and CPU | CPU jobs timeout | Apply 5x time multiplier for CPU jobs |
| Applying notebook GPU-only policy to SLURM | Wastes resources | Different modes need different strategies |
| No job promotion | CPU jobs stay on CPU even when GPUs free up | Implement dynamic CPU→GPU promotion |

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
| `GPU_SLOTS` | Integer (e.g., 3) | `submit.sh` | `burst_monitor.sh` |
| `CPU_SLOTS` | Integer (e.g., 5) | `submit.sh` | `burst_monitor.sh` |
| `ALLOC_CPUS` | Integer (e.g., 104) | `config.sh` | `submit.sh` |
| `ALLOC_MEM` | Integer GB (e.g., 812) | `config.sh` | `submit.sh` |
| `ALLOC_GPUS` | Integer (e.g., 3) | `config.sh` | `submit.sh` |
| `CPU_CPUS_PER_TASK` | Integer (e.g., 8) | `config.sh` | `submit.sh` |
| `CPU_MEM_DECON` | Integer GB (e.g., 48) | `config.sh` | `submit.sh` |
| `CUDA_VISIBLE_DEVICES` | GPU IDs | SLURM | CuPy |
| `CPU_TIME_MULTIPLIER` | `5` (default) | `config.sh` | `submit.sh` |

## Key Insights

- **Dual-pool calculation is the key innovation** - GPU slots + CPU slots = total concurrent
- **Notebook vs SLURM are different paradigms** - Don't apply interactive policies to batch processing
- **Maximize ALL resources** - With limited GPUs, use CPU cores for overflow
- **Same quality, different speed** - CPU processing takes longer but produces identical results
- **Dynamic promotion improves utilization** - CPU jobs can be promoted to GPU when resources free up
- **5x time multiplier is empirically derived** - CPU processing typically 3-7x slower than GPU

## When to Apply This Pattern

- SLURM batch processing on HPC clusters
- Limited GPU availability (1-3 GPUs) relative to CPU allocation
- Large datasets requiring many cycles (more cycles than GPUs)
- Need to maximize throughput over wall-clock time
- Processing can run overnight/unattended
- Want dynamic resource optimization (jobs move to better resources as they free up)

## CLI Output Example

```
Resource pool calculation:
  GPU job slots: 3 (from 3 GPUs)
  CPU job slots: 5 (from remaining resources)
  Total concurrent jobs: 8
  GPU pool: 3 (3 GPUs), CPU pool: 5 (80 CPUs, 272GB remaining)

Resource Allocation (Dual-Pool Architecture):
  Allocation limits: 104 CPUs, 812GB mem, 3 GPUs
  GPU jobs: 8 CPUs, 180GB mem, 1 GPU each
  CPU jobs: 8 CPUs, 48GB mem each
  GPU slots: 3, CPU slots: 5
  Total concurrent: 8 jobs
```

## References

- KINTSUGI CLAUDE.md - "Resource Pool Calculation" section
- KINTSUGI README.md - "Resource Pool Architecture" section
- `gpu-quality-priority` skill - Notebook-specific GPU enforcement
- `slurm-workflow-integration` skill - SLURM setup and submission
- HiPerGator burst accounts: https://help.rc.ufl.edu/doc/Account_and_QOS_Limits
