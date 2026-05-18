# adapter-projections/ — SUPERSEDED

**Superseded by:** `integrations/` (compiler + provisioner) + `emitters/` (event pipeline)  
**Status:** Retained for reference during Slice 1–2 transition. Scheduled for deletion in Slice 3.

This directory contains adapter config projections generated from Dream Studio SQLite authority.
The projection model is replaced by the integration compiler (`integrations/compiler/`) which
generates integration packs from `canonical/` source and installs them via `integrations/installer/`.

Do not add new files here. Do not rely on these files as authoritative config — they are frozen
snapshots. Live config is managed by `ds integrate install`.
