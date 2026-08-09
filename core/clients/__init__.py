"""Client layer (Attribution Coherence Phase 2): a client owns many projects.

Migration 155 adds ``business_clients`` + a nullable ``business_projects.client_id`` FK and seeds
the reference clients. This package holds the client engine; WO-CLIENT-SCHEMA lands the backfill
helper, later work orders add mutations/queries and the client-level project-fit signal.
"""
