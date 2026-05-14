---
name: kubernetes-expert
description: Production Kubernetes operations -- debug CrashLoopBackOff/OOMKill/Pending pods, design resource requests/limits/probes, author Helm charts, advise on scheduling, RBAC, NetworkPolicy, and HPA. Invoke for any k8s cluster issue or workload design question.
---

## Patterns

- **Resource requests and limits on every container** -- requests are used by the scheduler; limits are enforced at runtime. Missing limits allow memory leaks to OOMKill neighbors.
- **Three-probe strategy**: startupProbe (slow start budget) -> livenessProbe (deadlock detection) -> readinessProbe (traffic readiness). Never share the same endpoint for liveness and readiness.
- **RBAC least-privilege**: one ServiceAccount per workload, scoped Role/RoleBinding, set `automountServiceAccountToken: false` on the ServiceAccount definition.
- **Default-deny NetworkPolicy**: apply deny-all to every namespace, then explicit allow rules per service pair. CNI must support NetworkPolicy (Calico, Cilium, Weave -- not Flannel alone).
- **PodDisruptionBudget on every multi-replica workload**: prevents node drain from taking all replicas simultaneously during cluster upgrades.
- **HPA v2 (autoscaling/v2, k8s 1.23+)**: set both CPU and memory metrics, minReplicas >= 2, stabilizationWindowSeconds: 300 on scaleDown to prevent thrashing.
- **Rolling update with maxUnavailable: 0**: zero-downtime deploys require readiness probes to be correct -- new pods only receive traffic after passing readiness.
- **External Secrets Operator for secret management**: k8s Secrets are base64, not encrypted. ESO syncs from AWS Secrets Manager / Vault and refreshes on a configurable interval.
- **Namespace isolation with ResourceQuota and LimitRange**: prevents a runaway workload from consuming all cluster resources; sets default requests for pods that omit them.

## Anti-Patterns

- **latest image tag** -- mutable, causes split-brain node versions; always pin to digest or immutable semver.
- **No resource limits** -- memory leak OOMKills neighbor pods; CPU starvation causes cluster-wide latency spikes.
- **Same probe endpoint for liveness and readiness** -- overloaded pod triggers restart storm instead of graceful load-shedding.
- **Privileged containers or UID 0** -- set `runAsNonRoot: true`, `readOnlyRootFilesystem: true`, `allowPrivilegeEscalation: false`.
- **cluster-admin bound to application ServiceAccounts** -- compromised pod owns the entire cluster.
- **No PodDisruptionBudget** -- two-replica Deployments go to zero during `kubectl drain`.

## Gotchas

- **OOMKill looks like CrashLoopBackOff**: check `kubectl describe pod <name> | grep -A5 "Last State"` for exit code 137 (OOMKilled) before adjusting probes.
- **HPA shows "unknown" targets**: HPA cannot compute utilization without resource requests on containers. Fix requests, wait 2 scrape intervals.
- **Liveness probe restarts healthy pods**: startupProbe must have `failureThreshold * periodSeconds >= max startup time`; liveness does not start until startup probe passes.
- **Pending pods are not a pod bug**: `kubectl describe pod` Events section shows `Insufficient cpu` / `Insufficient memory` / node affinity mismatch -- fix at cluster/request level, not pod level.
- **RBAC denies are silent by default**: test with `kubectl auth can-i <verb> <resource> --as=system:serviceaccount:<ns>:<sa>` before deploying.
- **Default SA token mounted in every pod**: set `automountServiceAccountToken: false` on ServiceAccount to prevent unauthenticated pods from querying the API server.

## Commands

```bash
# Debug a crashing pod
kubectl describe pod <name> -n <namespace>
kubectl logs <pod> -n <namespace> --previous
kubectl get events -n <namespace> --sort-by=.lastTimestamp

# Check OOMKill vs CrashLoop
kubectl describe pod <name> -n <namespace> | grep -A5 "Last State"

# Test RBAC permissions for a service account
kubectl auth can-i get secrets --as=system:serviceaccount:production:api-server -n production

# Check HPA status and metrics
kubectl describe hpa <name> -n <namespace>
kubectl get hpa -n <namespace> -w

# Drain a node safely (respects PDBs)
kubectl drain <node-name> --ignore-daemonsets --delete-emptydir-data

# Check resource usage per pod
kubectl top pods -n <namespace> --sort-by=memory

# Tail logs from all pods matching a label
kubectl logs -l app=api-server -n production --follow --max-log-requests=10

# Execute into a running container
kubectl exec -it <pod> -n <namespace> -- /bin/sh

# Force-delete a stuck Terminating pod
kubectl delete pod <name> -n <namespace> --grace-period=0 --force

# View applied NetworkPolicies
kubectl get networkpolicy -n <namespace> -o yaml

# Helm -- dry run a chart install
helm install myapp ./chart --dry-run --debug -f values-prod.yaml

# Helm -- diff before upgrade (helm-diff plugin)
helm diff upgrade myapp ./chart -f values-prod.yaml
```

## Version Notes

- **k8s 1.28+**: Native sidecar containers (feature stable in 1.29) -- init containers with `restartPolicy: Always` run as sidekicks that stay alive alongside the main container.
- **k8s 1.27+**: HPA v2 is GA; autoscaling/v2beta2 is removed in 1.26.
- **k8s 1.25+**: PodSecurityPolicy removed; use Pod Security Admission (pod-security.kubernetes.io labels on namespaces).
- **k8s 1.24+**: ServiceAccount tokens are time-limited (bound tokens) by default; legacy long-lived tokens require explicit Secret creation.
- **k8s 1.23+**: autoscaling/v2 (HPA multi-metric) is GA.
- **Helm 3.x**: no Tiller; all state is Helm release Secrets in the target namespace.
- **External Secrets Operator 0.9+**: v1beta1 ExternalSecret API is stable.
