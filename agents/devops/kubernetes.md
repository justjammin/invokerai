---
name: kubernetes
tier: 2
domain: devops
description: "Kubernetes-specific patterns"
---

# Kubernetes

Pod disruption budgets (PDB) for every stateful workload. `minAvailable: 1` for high-availability.

Resource requests AND limits on every container. Requests: what the Pod needs. Limits: hard ceiling. Test under load.

Liveness probe ≠ readiness probe. Liveness restarts container (fix hung processes). Readiness removes from load balancer (dependency issue, will recover).

Secrets: external-secrets or sealed-secrets operator—never `kubectl create secret` from plaintext. Rotate regularly.

Rolling updates: `maxUnavailable: 0` for zero-downtime. Test drain sequence.

StatefulSets for ordering guarantees (databases, queues). Deployments for stateless services.

ConfigMap for configuration, Secrets for credentials. Different teams shouldn't read each other's secrets.

## Don'ts

- `hostPath` volumes in prod (node-specific, not portable)
- Privileged containers (use capabilities instead)
- `latest` image tag (use semver)
- NodePort for production traffic (use Ingress/LoadBalancer)
- Skip resource requests (cluster scheduler can't function)
