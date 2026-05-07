---
name: node
tier: 2
domain: backend
description: "Node.js-specific patterns for backend"
---

# Node.js Backend

Async: `async/await` always, never raw callbacks. Handle rejection on every promise: `.catch()` or `try/catch`.

Error-first callbacks only when required by legacy API. Prefer promises/async-await.

`process.env` validation at startup (fail fast on missing required env vars). Validate in config loader, not scattered throughout code.

Stream large files—never load full file into memory. Use `fs.createReadStream()`, not `fs.readFile()`.

ESM over CommonJS. If supporting both, test both.

## Don'ts

- `require()` inside hot loops
- Synchronous fs methods in request handlers
- `process.exit()` without cleanup (no drain)
- `__dirname` in ESM (use `import.meta.url`)
- Unhandled promise rejections (crash process)
- Callback hell (use async/await)
