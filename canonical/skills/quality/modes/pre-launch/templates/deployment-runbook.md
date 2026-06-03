# Deployment Runbook

**Service:** [SERVICE NAME]
**Last Updated:** [DATE]
**Owner:** [TEAM/PERSON]

## Prerequisites

- [ ] Deployment access to [ENVIRONMENT] configured
- [ ] Required environment variables set (see `.env.example`)
- [ ] Database migrations reviewed and tested in staging
- [ ] Health check URL accessible: [HEALTH_URL]

## Pre-Deployment Checklist

- [ ] All tests passing on `main` branch
- [ ] Security review completed (see `.planning/audits/security-signoff.md`)
- [ ] CHANGELOG updated for this release
- [ ] Release tag created: `git tag v[VERSION]`
- [ ] Notify [STAKEHOLDERS] of upcoming deployment

## Deployment Steps

1. **Pull latest main:**
   ```bash
   git checkout main && git pull
   ```

2. **Deploy to [ENVIRONMENT]:**
   ```bash
   [DEPLOYMENT COMMAND]
   ```

3. **Verify deployment:**
   ```bash
   curl [HEALTH_CHECK_URL]
   # Expected: {"status": "ok"}
   ```

4. **Run smoke tests:**
   ```bash
   [SMOKE TEST COMMAND]
   ```

## Post-Deployment Verification

- [ ] Health endpoint returns 200: `curl [HEALTH_URL]`
- [ ] Key user flow works: [DESCRIBE FLOW]
- [ ] Error rate stable in monitoring: [MONITORING_URL]
- [ ] No spike in error logs

## Rollback Procedure

See [ROLLBACK.md](./ROLLBACK.md) for complete rollback procedure.

Quick rollback:
```bash
[ROLLBACK COMMAND]
```

## Escalation

If deployment fails or issues detected post-deploy:
- Primary on-call: @[USERNAME] (Slack: #ops-alerts)
- Escalation: [EMAIL]

---
*Fill in all [BRACKETED] placeholders before use.*
