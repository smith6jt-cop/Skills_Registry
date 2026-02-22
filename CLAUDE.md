# Research Skills Registry

A knowledge-sharing system for documenting and retrieving experimental learnings across Claude Code sessions.

## Commands

### /advise
Search the skills registry for relevant experiments before starting new work.
1. Read the user's goal
2. Search plugins/ for related skills by scanning description fields in plugin.json and SKILL.md files
3. Summarize relevant findings: what worked, what failed, recommended parameters
4. If no relevant skills found, inform the user and suggest creating one after completing their task

### /retrospective
Save learnings from the current session as a new skill.
1. Summarize key findings from the conversation
2. Create a new plugin folder using templates/experiment-skill-template/
3. Fill in SKILL.md with: goal, what worked, what failed, final parameters
4. Create a branch and open a PR to main

## Skill Template
Use templates/experiment-skill-template/ as the base for new skills. Copy the entire folder structure and rename TEMPLATE_NAME to your skill name.

## Rules
- Every skill needs a specific description field with trigger conditions
- Always include a "Failed Attempts" table - this is the most valuable section
- Include exact hyperparameters and configurations, not vague advice
- Skills should be specific enough to be actionable but general enough to be reusable
- Document the environment (software versions, hardware) where the skill was verified

## Repository Structure
```
Skills_Registry/
├── plugins/
│   ├── general/              # Cross-project Python/dev skills
│   │   ├── pypi-collision-fix/
│   │   ├── type-checking-pattern/
│   │   ├── conda-multi-account-hipergator/
│   │   ├── dependency-deprecation/
│   │   ├── hpc-dev-testing-workflow/
│   │   ├── optional-dependency-test-mocking/
│   │   ├── python-performance-patterns/
│   │   └── skills-registry-organization/
│   ├── scientific/           # Scientific computing & GPU patterns
│   │   ├── project-data-separation/
│   │   └── windows-cupy-nvrtc/
│   ├── trading/              # Alpaca Trading system skills
│   │   ├── differential-sharpe-ratio/   # v3.8.0 - DSR reward component
│   │   ├── discounted-thompson-sampling/ # v3.8.0 - Non-stationary bandit
│   │   ├── reward-function-v330/        # v3.3.0 - Reward rebalancing
│   │   ├── integrated-risk-manager/     # v3.3.0 - Unified risk sizing
│   │   ├── adaptive-predator-prey/      # v3.3.0 - Regime dynamics
│   │   └── ...                          # 60+ trading skills
│   ├── kintsugi/             # KINTSUGI-specific skills
│   │   ├── basic-caching-evaluation/
│   │   ├── globus-dataset-staging/
│   │   └── gpu-quality-priority/
│   └── templates/            # Skill templates & examples
│       └── example-skill/
├── templates/
│   └── experiment-skill-template/
├── scripts/
│   ├── validate_plugins.py
│   └── generate_marketplace.py
├── marketplace.json
└── CLAUDE.md
```

## Category Guidelines
- **general/**: Skills applicable to any Python project (packaging, linting, environments)
- **scientific/**: Scientific computing patterns (GPU, data pipelines, architecture)
- **trading/**: Alpaca Trading system skills (RL training, risk management, reward functions, signals)
- **kintsugi/**: KINTSUGI-specific image processing skills (won't trigger for other projects)
- **templates/**: Example skills and templates for creating new skills

## Trading Skills (v4.2.0)
Key skills for the Alpaca Trading system:

### Reward Function & Training
- `agent-validation-v420` - **v4.2.0 (CURRENT)**: Reward weight overrides, fitness decline gate, tightened entropy bounds [0.75x,1.25x], pinned data, staged experiments. Supersedes v3.0 experiment skills
- `reward-function-v410` - v4.1.0: DSR decay, direction floor, normalized curriculum, 3x slippage. Fixes overtrading and DSR dominance
- `agent-validation-integration` - v4.1.0: Model health monitoring, live feedback loop, gating recalibration, diagnostic overrides
- `differential-sharpe-ratio` - DSR for risk-adjusted rewards (Moody & Saffell 1998)
- `discounted-thompson-sampling` - Non-stationary bandit with decay
- `reward-function-v330` - ~~v3.3.0~~ (SUPERSEDED by v4.1.0 curriculum): Rebalanced weights, removed trading_incentive
- `reward-scaling-calibration` - reward_scale=0.001 calibration (thresholds superseded by v4.1.0 gating)
- `agent-validation-experiment` - ~~v3.0~~ (SUPERSEDED by v4.2.0): Phase gates, entropy bounds, fitness-gated checkpoints
- `agent-validation-review` - End-to-end audit of training-to-live pipeline. Stale thresholds, broken circuit breaker wiring, missing shutdown hooks

### Risk Management
- `integrated-risk-manager` - Unified Kelly + GARCH + drawdown sizing
- `adaptive-predator-prey` - Regime-aware Lotka-Volterra dynamics
- `drawdown-guardrails-pattern` - Max drawdown triggers and scaling (v3.9.0: adaptive threshold)

### Data & Infrastructure
- `data-source-priority` - Alpaca API mandatory, yfinance NOT a fallback
- `colab-notebook-development` - Mandatory notebook structure, API key parsing pattern
- `persistent-cache-gap-filling` - gap_fill_threshold_days parameter, 401 troubleshooting
- `notebook-config-drift-detection` - Detect/fix config drift between notebooks and GPUEnvConfig defaults. Silent A/B invalidation, agent memory persistence requirements
