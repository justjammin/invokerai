---
name: security
tier: 1
description: "Universal security domain rules"
---

# Roleplay Notes

- OWASP Top 10: checklist before feature ship
  - Injection, broken auth, sensitive data exposure
  - XML external entities, broken access control, misconfiguration
  - XSS, insecure deserialization, known vulnerabilities, insufficient logging/monitoring
- CVEs: block merge on critical (automated scan: Dependabot, Snyk, Grype)
- Lock files: pin transitive deps
- Secrets detection: pre-commit (gitleaks or trufflehog in CI)
- Detected credentials: block commit
- Token expiry: enforced
- Scope: checked on every request
- Logout: invalidates server-side
- Proof of ownership: PKCE for OAuth, CSRF tokens for forms
- Input validation: at every external boundary
- Internal callers: don't trust — validate anyway
- Logging: never log credentials, tokens, PII, full request bodies
- Redaction: in logs

## Don'ts

- Trust client-supplied user IDs without server verification
- Catch and swallow auth exceptions
- Store passwords without bcrypt/argon2
- Use MD5/SHA1 for security (use SHA-256+)
- Deploy before security audit on new data handling
