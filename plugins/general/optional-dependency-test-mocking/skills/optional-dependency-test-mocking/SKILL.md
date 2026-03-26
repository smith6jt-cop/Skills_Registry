---
name: optional-dependency-test-mocking
description: "Pattern for testing modules with optional dependencies by mocking at sys.modules level"
author: Claude Code
date: 2026-02-22
version: 1.0.0
---

# Optional Dependency Test Mocking

## Experiment Overview
| Item | Details |
|------|---------|
| **Date** | 2026-02-22 |
| **Goal** | Test modules that depend on optional packages without installing them |
| **Environment** | Python 3.11+, pytest |
| **Status** | Success — validated with 137 tests for CCXT broker |

## The Pattern

When a module uses `try/except ImportError` for optional dependencies, you can't just `unittest.mock.patch` the import — the module-level guard has already run. Instead, inject a mock module into `sys.modules` **before** importing the module under test.

### Step 1: Create Mock Module (top of test file)

```python
import sys
import types
from unittest.mock import MagicMock

# Create mock module BEFORE importing the module under test
_mock_pkg = types.ModuleType('optional_package')

# CRITICAL: Use real exception classes, not MagicMock
# MagicMock exceptions break `except SomeError` clauses
class _BaseError(Exception):
    pass

class _SpecificError(_BaseError):
    pass

_mock_pkg.BaseError = _BaseError
_mock_pkg.SpecificError = _SpecificError

# Mock callable classes (exchange constructors, clients, etc.)
for name in ['ClassA', 'ClassB']:
    setattr(_mock_pkg, name, MagicMock(name=f'pkg.{name}'))

# Inject into sys.modules
sys.modules['optional_package'] = _mock_pkg
```

### Step 2: Import Module Under Test (after mock injection)

```python
# NOW import — the try/except will find our mock
from my_project.module import MyClass, MY_FLAG  # noqa: E402
```

### Step 3: Autouse Fixture for Import-Order Resilience

```python
@pytest.fixture(autouse=True)
def _patch_optional_package():
    """Ensure mock stays in sys.modules even if other tests remove it."""
    prev = sys.modules.get('optional_package')
    sys.modules['optional_package'] = _mock_pkg
    yield
    if prev is not None:
        sys.modules['optional_package'] = prev
    else:
        sys.modules.pop('optional_package', None)
```

### Step 4: Reset Fixture for State Isolation

```python
@pytest.fixture(autouse=True)
def _reset_mock_state():
    """Reset all mocks between tests to prevent cross-test leakage."""
    yield
    for name in ['ClassA', 'ClassB']:
        getattr(_mock_pkg, name).reset_mock()
```

## Why Real Exception Classes Matter

```python
# In production code:
try:
    exchange.fetch_balance()
except ccxt.InsufficientFunds:  # This is an `except` clause
    handle_insufficient()

# If InsufficientFunds is a MagicMock:
#   - `raise MagicMock()` works
#   - But `except MagicMock` FAILS — except needs a real BaseException subclass
#   - Tests pass where they shouldn't, hiding real bugs
```

Always create exception classes as real Python classes inheriting from `Exception` (or the appropriate base), preserving the inheritance hierarchy from the real package.

## Multi-File Test Suites

When multiple test files need the same mock, guard against double-injection:

```python
if 'optional_package' not in sys.modules:
    _mock_pkg = types.ModuleType('optional_package')
    # ... set up mock ...
    sys.modules['optional_package'] = _mock_pkg
```

This prevents conflicts when pytest collects multiple test files that share the dependency.

## Failed Attempts (Critical)

| Attempt | Why it Failed | Lesson Learned |
|---------|---------------|----------------|
| `@patch('module.ccxt')` | Module-level `try/except` already ran at import time | Must inject BEFORE import |
| `MagicMock()` for exceptions | `except MagicMock` is a TypeError | Use real `Exception` subclasses |
| Shared conftest.py mock | Import order depends on pytest collection order | Each file should be self-contained |
| No autouse fixture | Other test files could remove the mock | Always restore in autouse fixture |
| No reset fixture | Mock call counts leaked between tests | Reset mocks after each test |
| `monkeypatch.setitem` in fixture | Only works for existing keys, not pre-import injection | Use direct `sys.modules` assignment at module level |

## Real-World Example

See the Alpaca Trading CCXT test suite:
- `tests/test_ccxt_broker.py` — 102 tests, full mock ccxt with 4 exception classes
- `tests/test_exchange_selector.py` — 35 tests, guard-style injection for second file

## Key Insights

- **Module-level injection is mandatory** — the `try/except ImportError` runs at import time, not call time
- **Exception hierarchy must be real** — `except MockClass` is a TypeError in Python
- **Autouse fixtures provide resilience** — protects against test collection order issues
- **State reset prevents cross-contamination** — MagicMock accumulates calls across tests
- **Each test file should be self-contained** — don't rely on conftest.py for `sys.modules` injection
- **`AVAILABLE` flags work automatically** — if the module checks `PACKAGE_AVAILABLE = True` inside the `try` block, your mock makes it `True`
