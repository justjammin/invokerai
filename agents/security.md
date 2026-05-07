---
name: security
tier: 1
description: "Universal security domain rules"
---

# Security

OWASP Top 10 checklist before feature ship: injection, broken auth, sensitive data exposure, XML external entities, broken access control, security misconfiguration, XSS, insecure deserialization, using components with known vulns, insufficient logging/monitoring.

Dependency scan in CI: block merge on critical CVEs. Automated tooling (Dependabot, Snyk, Grype). Pin transitive deps in lock file.

Secrets detection pre-commit: gitleaks or trufflehog in CI. Block commit if credentials detected.

Auth: token expiry enforced, scope checked on every request, logout invalidates server-side. Challenge: supply proof of token ownership (PKCE for OAuth, CSRF tokens for forms).

Input: validate at every external boundary. Don't trust internal callers to have validated.

Never log credentials, tokens, PII, or full request bodies. Redact in logs.

## Don'ts

- Trust client-supplied user IDs without server verification
- Catch and swallow auth exceptions
- Store passwords without bcrypt/argon2
- Use MD5/SHA1 for security purposes (use SHA-256+)
- Deploy before security audit on new data handling
