# Sanitized Demo Fallback Plan

## If The Live Dashboard Is Unavailable

Use the sanitized screenshots and CLI outputs:

- `ds status`
- `ds validate`
- `ds modules`
- `ds router`
- `ds adapters`
- `ds contract-atlas`
- `ds context-packet`
- `ds platform-hardening`
- `ds policy --action secret_sensitive_access`

Message:

> The dashboard is a derived convenience surface. The authority is still visible through installed commands and SQLite-backed read models.

## If Adapter Status Is Unavailable

Use context-packet-only fallback.

Message:

> Unsupported or unavailable adapters do not block the workflow. Dream Studio can still generate scoped context packets and import results manually with evidence refs.

## If Evidence Is Missing

Say:

> This evidence is unavailable in the sanitized demo packet. Dream Studio shows unavailable state instead of inventing confidence.

## If A Policy Action Is Denied

Treat it as a successful operate-mode demo.

Message:

> The policy engine is doing its job. Destructive or sensitive actions are denied or deferred until explicitly approved.

## If Asked For Private Proof

Do not show private operator data in a public demo. Offer a private local walkthrough after a fresh privacy review.

## No-Go Conditions

Stop the public demo if any screen or artifact includes:

- private Work Orders;
- handoffs;
- local runtime paths;
- raw telemetry;
- operator decisions;
- career data;
- application data;
- compensation strategy;
- private external-project details;
- sensitive project details;
- secrets or auth/config values;
- unsanitized security findings.
