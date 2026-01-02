# Windows Console Unicode Compatibility

## Problem

Python scripts crash with `UnicodeEncodeError` when printing emojis or special Unicode characters on Windows:

```
UnicodeEncodeError: 'charmap' codec can't encode character '\U0001f4ca' in position 2: character maps to <undefined>
```

This happens because Windows cmd.exe and PowerShell use the `cp1252` encoding by default, which cannot represent Unicode emojis.

## Trigger Conditions

1. Script runs fine on Linux/Mac but crashes on Windows
2. Error occurs in `print()` statements containing emojis
3. Error message mentions `charmap`, `cp1252`, or `encoding_table`
4. Characters like: `[EMOJI]`, `[CHECKMARK]`, `[WARNING]`, `[INFO]` etc.

## Solution

Replace emojis with ASCII text equivalents:

```python
# BEFORE (crashes on Windows)
print(f"[EMOJI] PIPELINE BREAKDOWN:")
print(f"   [CHECKMARK] Task completed")
print(f"   [WARNING] Warning message")

# AFTER (works everywhere)
print(f"PIPELINE BREAKDOWN:")
print(f"   [OK] Task completed")
print(f"   [WARN] Warning message")
```

### Common Replacements

| Emoji | Replacement |
|-------|-------------|
| `[EMOJI_CHART]` | `[INFO]` or remove |
| `[EMOJI_CHECKMARK]` | `[OK]` |
| `[EMOJI_X]` | `[XX]` or `[FAIL]` |
| `[EMOJI_WARNING]` | `[WARN]` |
| `[EMOJI_ROCKET]` | remove |
| `[EMOJI_SAVE]` | `[SAVE]` |
| `[EMOJI_STOP]` | `[HALT]` |

### Automated Fix Script

```python
replacements = {
    '\U0001f4ca': '[INFO]',   # chart emoji
    '\u2713': '[OK]',         # checkmark
    '\u2717': '[XX]',         # X mark
    '\u26a0': '[WARN]',       # warning
    '\U0001f680': '',         # rocket
}

for filepath in files_to_fix:
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    for emoji, replacement in replacements.items():
        content = content.replace(emoji, replacement)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
```

## Alternative Solutions (Not Recommended)

1. **Set PYTHONIOENCODING=utf-8** - Only works for some terminals
2. **Use Windows Terminal** - Not available on all systems
3. **Wrap print in try/except** - Hides the output instead of showing it

## Best Practice

Avoid emojis in production code entirely:
- Log files may not render them correctly
- CI/CD systems often have encoding issues
- Cross-platform compatibility is cleaner with ASCII

## Files Fixed in This Project

- `alpaca_trading/selection/universe.py`
- `alpaca_trading/trading/profit_tracker.py`
- `alpaca_trading/gpu/ppo_trainer_native.py`
- `alpaca_trading/training/archive.py`
- `alpaca_trading/gpu/data_pipeline.py`
- `alpaca_trading/strategy/harmonized.py`
