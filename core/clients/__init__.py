"""Client layer engine (Attribution Coherence Phase 2): a client owns many projects.

Event-sourced, mirroring the project engine:
  - mutations.py  — create_client / archive_client / assign_project_client emit canonical events
    (client.created / client.archived / project.client_assigned); never write read models directly.
  - queries.py    — list/get clients, projects-by-client, the SeayInsights default, and
    candidate_projects_for_work (the client-level project-fit signal, twin of milestone_fit).
  - backfill.py   — classify existing projects into clients by emitting project.client_assigned
    events; wired into `ds migrate activate` so activating migration 155 populates client_id.

Read models: business_clients (ClientProjection) + business_projects.client_id
(ProjectProjection.project.client_assigned). Migration 155 seeds the three reference clients.
"""
