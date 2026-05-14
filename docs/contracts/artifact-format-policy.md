# Artifact Format Authority Policy

## Purpose

This policy defines which artifact formats may act as canonical source, which formats are generated or rendered projections, and how future Work Orders should choose between Markdown, YAML, JSON, SQLite, HTML, and export formats.

Dream Studio should not broadly replace Markdown with HTML. HTML is a rendered projection or export format by default, not operational truth.

## Authority Model

Artifact authority is determined by role, not by file extension alone.

- Canonical source artifacts are the human- or machine-edited records that future Work Orders, contracts, reports, generators, validators, or projections must read as authority.
- Generated or rendered projection artifacts are outputs derived from canonical source artifacts. They may be useful for display, review, export, or dashboards, but they must not replace the source artifacts unless a later contract explicitly promotes them.
- A rendered projection can include enough metadata to trace back to its sources, but traceability metadata does not make the rendered artifact canonical.

## Authoritative Source Formats

Use these formats for source artifacts when they match the artifact role:

| Format | Authority role | Use when |
| --- | --- | --- |
| Markdown | Human-readable narrative source | The artifact is primarily prose, guidance, operations documentation, audit narrative, or a handoff packet. |
| Markdown with YAML frontmatter | Human-readable source with structured metadata | The artifact needs prose plus stable fields such as IDs, phase names, status, taxonomy, dates, or source refs. |
| YAML | Human-edited declarative structured source | The artifact is a workflow declaration, release gate, review report, paused-work record, operator-facing structured artifact, or configuration intended for review and hand editing. |
| JSON | Strict machine contract source | The artifact is an adapter payload, schema example, API payload, projection record, validation target, or exact machine exchange shape. |
| JSONL/NDJSON | Replayable source/export stream | The artifact is an append-only event export, replayable event log, or line-delimited stream snapshot. |
| SQLite | Local operational store | Local runtime or operational state needs indexed local persistence, transactions, and queryable history. |
| JSON Schema and Pydantic | Validation authority | Canonical machine contracts require deterministic validation, typed parsing, or versioned field guarantees. |
| Mermaid | Diffable diagram source | Diagrams should be readable in code review, easy to diff, and renderable without making an image file authoritative. |
| CSV | Simple tabular source or export | Data is flat, small, tabular, and does not require nested structure or strict event replay semantics. |

## Generated And Rendered Projection Formats

Use these formats for derived artifacts unless a specific contract documents and justifies an exception:

| Format | Default role | Use when |
| --- | --- | --- |
| HTML | Rendered projection/export | A dashboard, report, preview, static page, or external review surface renders from Markdown, YAML, JSON, SQLite, or projection data. |
| PDF | Rendered export | A fixed-layout shareable document is needed for human consumption. |
| SVG | Rendered visual output | A rendered diagram, icon, or visual asset is generated from source data or source design instructions. |
| PNG | Rendered visual output | A screenshot, raster export, image preview, or generated bitmap is needed. |
| Parquet | Deferred analytics export | Event or analytics volume justifies columnar storage. Until then, prefer JSONL/NDJSON, SQLite, CSV, or JSON depending on role. |

HTML, PDF, SVG, and PNG are generated/rendered outputs by default. They must link or reference canonical sources when used for reports, dashboards, or exports.

## Format Selection Rules

- Use Markdown for narrative contracts, audit reports, operations docs, and handoff packets.
- Use Markdown with YAML frontmatter when the narrative artifact also needs machine-readable metadata.
- Use YAML for human-edited structured artifacts where readability matters, including release gates, security review reports, paused-work records, workflow declarations, and operator-facing configuration.
- Use JSON for strict machine contracts, projection records, adapter payloads, API examples, validation fixtures, and schema examples.
- Use JSONL or NDJSON for append-only event exports and replayable event streams.
- Use SQLite for local canonical operational stores where indexed, transactional state is appropriate.
- Use JSON Schema or Pydantic models to validate canonical machine contracts before relying on them.
- Use Mermaid for diagrams that should remain text source and diffable.
- Use CSV only for simple tabular exports or small flat tables.
- Defer Parquet until analytics or event volume justifies columnar files.
- Use HTML only as a rendered display/export unless a contract explicitly documents why an HTML file is canonical.
- Use PDF, SVG, and PNG as generated outputs unless a specific exception is documented and justified.

## Generated Reports And Dashboards

Generated reports and dashboards may render HTML or other visual formats, but they must render from canonical Markdown, YAML, JSON, SQLite, or projection data.

Dashboards and rendered reports must:

- declare their source artifact refs;
- preserve source IDs and version fields where available;
- show stale or missing source evidence instead of inventing authority;
- avoid direct target repo mutation or scan execution unless a later approved Work Order grants that authority;
- avoid replacing Work Order reports, Handoff Packets, operator decisions, release gates, or Security Review artifacts as authority.

Dashboards and rendered reports must not:

- treat HTML as canonical operational truth by default;
- rewrite canonical artifacts through a display surface without an explicit mutation Work Order;
- hide whether content is source, projection, or export;
- make PDF, SVG, PNG, or HTML exports the only record of a decision.

## Artifact-Specific Rules

| Artifact family | Canonical format | Projection/export formats | Authority rule |
| --- | --- | --- | --- |
| Handoff packets | Markdown, optionally Markdown with YAML frontmatter | HTML/PDF only as rendered copies | The Markdown packet is the ready-to-copy source. Rendered copies must not weaken constraints. |
| Audit reports | Markdown, optionally Markdown with YAML frontmatter | HTML/PDF for review packets | The audit report remains source evidence unless a later contract moves the report into YAML/JSON. |
| Security review reports | YAML for structured review reports; Markdown for narrative phase reports | HTML/PDF dashboard/report views | YAML review reports and release gates are authoritative for structured security state. |
| Release gates | YAML | Dashboard cards, HTML/PDF summaries | YAML release-gate artifacts own the decision state until superseded by a later artifact. |
| Paused-work artifacts | YAML | Handoff/report references and dashboard projections | `paused_work.yaml` is the pause/resume continuity source. Narrative prose is not enough. |
| Event exports | JSONL/NDJSON; SQLite for local operational store | CSV/Parquet when justified | Replayability and source classification must be preserved. |
| Projection outputs | JSON for strict projection records; YAML for operator-facing projection inputs | HTML dashboards, PDF summaries, CSV exports | Projections are read-only views over source artifacts unless a later import contract says otherwise. |
| Adapter payloads | JSON plus JSON Schema/Pydantic validation | Logs or rendered diagnostics | Adapter payloads must remain strict machine contracts and must not become canonical runtime state by accident. |

## Decision Table

| Question | Choose | Avoid |
| --- | --- | --- |
| Is this primarily prose for humans? | Markdown | JSON or HTML as the editable source |
| Does prose need stable IDs or status fields? | Markdown with YAML frontmatter | Duplicating metadata only in rendered HTML |
| Is this human-edited structured config or review state? | YAML | HTML, PDF, PNG |
| Is this a strict machine exchange contract? | JSON with JSON Schema or Pydantic | Freeform Markdown parsing |
| Is this an append-only replay/export stream? | JSONL/NDJSON | CSV if nested/replay semantics matter |
| Is this local indexed operational state? | SQLite | Dashboard-only state |
| Is this a diagram that should be reviewed in diffs? | Mermaid | Generated SVG as the only source |
| Is this a simple flat export? | CSV | Parquet before volume justifies it |
| Is this an analytics/event-volume export? | Parquet, after explicit approval | Premature Parquet for small data |
| Is this a dashboard or shareable visual report? | HTML/PDF generated from canonical data | HTML/PDF as the only authority |
| Is this an image or screenshot? | SVG/PNG generated from source | Image file as decision authority without source refs |

## Canonical HTML Exceptions

HTML must not become canonical operational truth by default.

An HTML artifact may be canonical only when a future Work Order documents all of the following:

- why Markdown, YAML, JSON, SQLite, Mermaid, or another source format is insufficient;
- which system treats the HTML file as source;
- which validation or diff strategy protects the HTML source;
- how generated HTML copies are distinguished from canonical HTML source;
- how dashboard/report consumers avoid confusing rendered HTML with authority.

Without that documented exception, HTML is rendered output.

## Markdown-To-HTML Rule

Do not convert Markdown to HTML as canonical source.

Markdown contracts, handoff packets, audit reports, and narrative operations docs may be rendered to HTML for display or export, but the Markdown remains the source unless a later contract explicitly replaces it with a different canonical format.

## Future Work Order Checklist

Every future Work Order that creates or changes artifacts should ask:

> Does this artifact use the correct authority format, and is it clear whether it is canonical source or generated projection?

If the answer is unclear, the Work Order should pause or update the relevant contract before adding new artifact formats.
