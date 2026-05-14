# Research Source Contract

## Purpose

Research/source artifacts help Dream Studio users verify claims, compare options, and make better decisions.

Research/source artifacts are advisory evidence, not canonical truth. Research output must never silently mutate architecture, workflow, memory, decision, dashboard, adapter, Docker, cloud, or org authority.

## Authority Principles

- Local canonical runtime state remains authoritative.
- Research artifacts are evidence and recommendations only.
- `research_cache` is an advisory cache.
- `raw_research` is a research evidence and lineage surface.
- Neither `research_cache` nor `raw_research` may become workflow, orchestration, execution, memory, or architecture authority.
- Semantic memory is canonical only after an approved memory ingestion path writes `memory_entries`.
- Decision lineage must go through approved decision/event paths.
- External research providers are optional and must degrade cleanly when unavailable.
- Private local research, memory, session, token, event, and prompt payloads are local/private unless explicitly redacted or classified for export.

## Research Artifact Contract

Every maintained research artifact must define or explicitly mark unavailable:

- `topic_or_query`: the user question, topic, or search phrase.
- `sources`: a list of source records.
- `extraction_notes`: notes, snippets, or summarized evidence extracted from sources.
- `confidence`: confidence in the artifact, including how it was calculated.
- `verification_status`: unverified, partially_verified, verified, stale, or rejected.
- `triangulation`: source count and independence posture.
- `cache_status`: fresh, cached, stale, expired, bypassed, or not_cached.
- `created_at` or `accessed_at`: when the artifact or source was captured.
- `privacy_export_classification`: local_only, exportable_with_redaction, aggregate_only, or non_exportable.

Missing fields must be visible to callers as unavailable or unknown. Missing fields must not be interpreted as proof.

## Source Record Contract

Every maintained source record must define or explicitly mark unavailable:

- `url` or stable local reference.
- `title` or descriptive name.
- `source_type`: official_docs, code_repository, standard, vendor_docs, blog, forum, internal_file, local_memory, generated_summary, or unknown.
- `source_tier`: quality tier or equivalent ranking.
- `accessed_at`: when the source was accessed.
- `extraction_notes`: what was taken from the source.
- `verification_status`: source-level verification posture.

Model-generated summaries are not sources. They may appear only as extraction notes or advisory recommendations tied back to source records.

## Source Quality Rules

Source quality checks must be executable expectations, not only prose:

- Triangulation should prefer at least three independent sources.
- At least one primary or Tier 1 source should be present when practical.
- Shared domains reduce independence confidence.
- Counter-arguments or disconfirming evidence should be recorded when practical.
- Low confidence must remain visible and must not block local runtime execution.

## Cache And Evidence Surfaces

`research_cache` stores advisory report snapshots. It may be read by dashboard/API projection surfaces and may be invalidated by named cache routes. It is not canonical state.

`raw_research` stores research evidence, trust metadata, validation status, and lineage candidates. It does not authorize architecture, workflow, orchestration, execution, or memory mutations by itself.

The file-backed research cache under the local Dream Studio user data directory is an operator-controlled advisory artifact cache. It must not be treated as canonical state or an export-safe dataset by default.

`tool_registry` and `tool_embeddings_cache` are discovery/catalog metadata and performance cache surfaces. Provider, vendor, MCP, or package names in those surfaces are metadata only.

`control.research.engine` is a legacy opt-in lineage engine for `raw_research`
trust scoring. It may use approved research events and decision records when an
operator or test explicitly invokes it, but it is not the maintained dashboard/API
research cache path.

## API And Projection Boundaries

Research API routes may read or invalidate advisory research cache entries. They must not:

- emit unclassified canonical events;
- write workflow, orchestration, execution, memory, or architecture authority tables;
- promote cache entries into semantic memory;
- treat search result confidence as a decision approval;
- require external research providers for base local runtime.

When a projection/API route writes research cache state, event emission must be suppressed or routed through an explicitly contracted advisory event path.

## Memory And Decision Lineage

Research may inform semantic memory only through approved memory ingestion paths such as `MemoryStore.upsert_by_provenance()` or a named `IngestionConsumer`.

Research may inform decisions only through approved decision/event paths. Decision lineage must preserve source IDs, confidence, verification status, and the operator or workflow that accepted the recommendation.

Cache hits, summaries, and recommendations must not become decisions automatically.

`control.research.memory.MemorySearch` owns a local FTS index database under the
explicit memory directory. That index is a rebuildable retrieval aid and must not
write `memory_entries`.

## External Service Optionality

External research services, search APIs, model APIs, embedding models, MCP servers, and local-model tools are optional edge dependencies. If credentials, packages, or network access are unavailable, the research path must degrade to empty results, local cache lookup, local catalog search, or a clear unavailable status. Base local runtime validation must not require an external research service.

## Privacy And Export Rules

Research artifacts may contain private source URLs, local paths, prompts, snippets, code context, session context, or decision context.

Default classification is `local_only` unless a maintained route or export helper explicitly assigns a narrower export class.

Raw/private sources are not exportable by default:

- `memory_entries`
- `raw_sessions`
- `raw_token_usage`
- `validation_failures`
- `canonical_events` payloads
- raw handoff content
- raw session content
- raw research payloads that contain private local context

Exported research must include source references and privacy classification. Redaction must happen before export, not after distribution.

## Legacy Diagnostics

Legacy diagnostics such as `interfaces/cli/test_wave1_research_cache.py` and `interfaces/cli/debug_trust_score.py` are not normal validation. They must stay opt-in or become temp-home/tmp-DB isolated before promotion. They must not run against the native local runtime DB during standard verification.

Current opt-in gate: `DREAM_STUDIO_RUN_LEGACY_RESEARCH_DIAGNOSTICS=1`.

## Violations

The following are contract violations:

- treating `research_cache` or `raw_research` as canonical truth;
- writing workflow, orchestration, execution, architecture, or memory authority from research cache routes;
- exporting private raw research, memory, session, token, or event payloads by default;
- requiring external research providers for base local runtime;
- emitting unclassified canonical events from dashboard/API research surfaces;
- silently promoting model summaries into decisions or memory.

## Schema Posture

This contract does not introduce schema migrations. Existing fields may be incomplete. Missing artifact fields must be classified as gaps until a future migration or compatibility layer is explicitly scoped.
