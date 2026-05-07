---
name: devops
tier: 1
description: "Universal devops domain rules"
---

# DevOps

Docker: multi-stage builds (build image ≠ runtime image). No root user in container—run as non-root UID. Minimize layers and image size.

Secrets: vault/secrets manager only. Never in committed env files. Never in image layers. Inject at runtime.

Health check endpoint required before load balancer registration. Distinguish liveness (can restart?) from readiness (can handle traffic?).

Metrics: Prometheus endpoint, standard format. Alert on error rate, p95 latency, saturation (CPU, memory, connections). Baseline before alerting.

Deployment: blue-green or canary for stateful changes. Never hard cutover. Rollback tested and ready.

Graceful shutdown: drain in-flight requests. SIGTERM handler present. Timeout configured (e.g., 30s for drain, then SIGKILL).

Resource limits: set on every container (CPU cores, memory). Request > Limit is error. Test under load.

## Don'ts

- `latest` tag in prod manifests
- Hardcoded IPs/hostnames
- Skip liveness/readiness distinction
- Expose debug endpoints in prod
