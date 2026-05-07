---
name: php
tier: 2
domain: backend
description: "PHP-specific patterns for backend"
---

# PHP Backend

Strict types declaration in every file: `declare(strict_types=1);` at top.

PHP 8.1+ features: enums over class constants, readonly properties, fibers for concurrency. Don't reach for old patterns.

Type hints: union types (`int|string`), nullable with `?`, return types always declared on public methods.

Composer autoload: PSR-4 always. No manual `require` for app code.

Named arguments for clarity on multi-parameter functions: `myFunc(arg1: value1, arg2: value2)`.

Assertions and validation at boundaries using value objects or DTOs.

## Don'ts

- `extract()`
- `$$variable` variable variables
- `eval()`
- Suppressing errors with `@`
- Mixing PDO and old `mysql_*` functions
- Implicit type coercion: always be explicit
