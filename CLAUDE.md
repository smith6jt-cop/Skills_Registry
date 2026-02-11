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

## Trading Skills (v3.9.1)
Key skills for the Alpaca Trading system:

### Reward Function & Training
- `differential-sharpe-ratio` - DSR for risk-adjusted rewards (Moody & Saffell 1998)
- `discounted-thompson-sampling` - Non-stationary bandit with decay
- `reward-function-v330` - Rebalanced weights, removed trading_incentive
- `reward-scaling-calibration` - reward_scale=0.001 calibration
- `agent-validation-experiment` - v2.2: Per-component metrics, adaptive drawdown, rewritten prompts, A/B testing, robust JSON parser, action type validation, API key parsing fix, quick validation speed fix

### Risk Management
- `integrated-risk-manager` - Unified Kelly + GARCH + drawdown sizing
- `adaptive-predator-prey` - Regime-aware Lotka-Volterra dynamics
- `drawdown-guardrails-pattern` - Max drawdown triggers and scaling (v3.9.0: adaptive threshold)

### Data & Infrastructure
- `data-source-priority` - Alpaca API mandatory, yfinance NOT a fallback
- `colab-notebook-development` - Mandatory notebook structure, API key parsing pattern
- `persistent-cache-gap-filling` - gap_fill_threshold_days parameter, 401 troubleshooting
