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
│   └── training/
│       └── your-experiment-name/
│           ├── .claude-plugin/
│           │   └── plugin.json
│           ├── skills/your-experiment-name/
│           │   └── SKILL.md
│           ├── references/
│           └── scripts/
├── templates/
│   └── experiment-skill-template/
├── scripts/
│   ├── validate_plugins.py
│   └── generate_marketplace.py
├── marketplace.json
└── CLAUDE.md
```
