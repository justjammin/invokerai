---
name: python
tier: 2
domain: backend
description: "Python-specific patterns for backend"
---

# Python Backend

Type hints required on all public functions. Python 3.10+ union syntax: `X | Y` instead of `Union[X, Y]`. Private functions: type hints optional if obvious.

Pydantic for data validation at boundaries—not dataclasses for API models. Pydantic v2 preferred.

Async: `asyncio` for IO-bound operations. Avoid mixing sync and async carelessly. Use `asyncio.to_thread()` for CPU-bound work, not in hot loop.

Dependency injection via FastAPI `Depends()` or explicit constructor injection. No global state in functions.

Exception hierarchy: domain exceptions inherit from custom base, never raise raw `Exception` or `BaseException`.

Context managers for resource cleanup: `with`, not try/finally if context manager exists.

## Don'ts

- Mutable default args: `def foo(x=[]):`
- `except: pass` (bare except catches too much)
- `import *` (unclear what's imported)
- `eval()` or `exec()`
- Blocking IO in async context (use `asyncio.to_thread()`)
- `os.system()` instead of `subprocess` with `shell=False`
