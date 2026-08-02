# Migration Rollbacks

Reverse migrations live here. A forward migration `NNN_description.sql` in the
parent directory is paired with a reverse `NNN_description.sql` in this folder that
undoes its schema change (drop what it created, restore what it dropped).

**Enforced from migration 154.** Migrations `<= 153` are grandfathered — the
pre-154 chain predates the convention, is anchored by the `142_lean_baseline.sql`
squash, and includes irreversible `DROP` migrations. The pairing gate
(`core/gates/migration_rollback_pairing.py`, wired into the `migration-risk`
pre-push gate) fails a push that adds a forward migration `>= 154` without a paired
reverse here.

See [`docs/migrations.md`](../../../../docs/migrations.md) for the full convention.
