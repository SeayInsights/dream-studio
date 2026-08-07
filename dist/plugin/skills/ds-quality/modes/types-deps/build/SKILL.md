# Types-Deps — Build Mode

## What This Mode Does

Provides structured guidance for two build-time activities:
1. **Adding type annotations** to existing unannotated code
2. **Dependency hygiene improvements** (lock files, CVE gate, license gate)

Build mode does NOT:
- Modify CI configuration (ops concern)
- Generate lock files (run pip-compile yourself)
- Install or configure license tools
- Expand pyrightconfig.json coverage
- Reorganize imports (code-quality concern)

## Pre-flight checks (run before any guidance)

Before providing guidance, run static checks on the target code:

1. **Check for existing type errors (if pyright available):**
   Run `pyright <target_file>` on the file to receive annotations. If it reports errors,
   annotating on top of type errors compounds the problem — fix errors first.

2. **Check for high/critical finding in typ-002:**
   If the file has confirmed `Any` leakage in its current unannotated state, note this —
   adding annotations will make the leakage visible to the type checker (good, but expect
   new errors to surface).

3. **Block on critical findings:**
   If any critical finding exists in the file's existing type annotations (confirmed interior
   `Any` leakage, confirmed runtime circular import), block guidance until addressed.
   Providing annotation guidance on top of a critical type issue adds noise.

## Type annotation guidance

When asked to add annotations to a function or module:

### Step 1 — Classify the function

Read the function body to determine annotability:
- **Fully classifiable:** return type and all parameter types are determinable from context.
  Add concrete annotations.
- **Boundary function:** takes external data (JSON, plugin, API response). Use `dict[str, Any]`
  or `TypedDict` for structured input, with a comment noting it's a boundary.
- **Complex return:** multiple possible return types. Use `Union[T1, T2]` or `T1 | T2` (3.10+).
- **Dynamic return:** genuinely unknowable without runtime type information. Use `Any` with a
  `# typ-002: boundary Any — [reason]` suppression comment.

### Step 2 — Annotation forms, by situation

**Simple concrete types:**
```python
def get_user(user_id: str) -> User:
def calculate_total(items: list[Item], tax_rate: float) -> float:
def format_name(first: str, last: str) -> str:
```

**Optional parameters:**
```python
def find_project(project_id: str, include_deleted: bool = False) -> Project | None:
```

**Structured dict input (prefer TypedDict over dict[str, Any]):**
```python
from typing import TypedDict

class EventPayload(TypedDict):
    event_type: str
    timestamp: str
    data: dict[str, Any]  # nested data stays Any at the deepest boundary

def handle_event(payload: EventPayload) -> None:
```

**Boundary deserialization (Any is appropriate):**
```python
def parse_response(raw: dict[str, Any]) -> Response:  # typ-002: boundary — external API
    # Validate and construct Response; type narrows after validation
    return Response(id=raw["id"], status=raw["status"])
```

**Callable parameters:**
```python
from typing import Callable
def retry(fn: Callable[[], T], attempts: int = 3) -> T:
```

**Generator/Iterator:**
```python
from typing import Generator, Iterator
def yield_chunks(data: bytes, size: int) -> Generator[bytes, None, None]:
```

### Step 3 — `from __future__ import annotations`

Add to any file using forward references:
```python
from __future__ import annotations
```
This defers annotation evaluation to strings, allowing forward references without quotes
(e.g., `def get(self) -> MyClass:` even if `MyClass` is defined later in the file).

### Step 4 — Type narrowing at boundaries

For functions that accept `Any` or `dict[str, Any]`, add type narrowing after validation:
```python
def process(raw: dict[str, Any]) -> ProcessedItem:
    # Validate
    if not isinstance(raw.get("id"), str):
        raise ValueError("id must be a string")
    # Narrow — after here, id is str, not Any
    item_id: str = raw["id"]
    return ProcessedItem(id=item_id)
```

## Dependency hygiene guidance

When asked to improve dependency health:

### CVE gate (dep-001 resolution)

If the project has a non-blocking CVE gate, provide this guidance:

1. First, run pip-audit manually and inspect results:
   ```bash
   python -m pip_audit -r requirements.txt
   ```
2. If CVEs are found: upgrade the affected packages or add justified exceptions in
   `.pip-audit-ignore` before making the gate blocking.
3. Remove `continue-on-error: true` from the CI step.
4. Commit the change with message: "fix: make CVE gate blocking in CI"

### Lock file (dep-002 resolution)

Generate lock files with pip-compile:
```bash
pip install pip-tools
# Production lock
pip-compile requirements.txt --output-file requirements.lock
# Dev lock
pip-compile requirements-dev.txt --output-file requirements-dev.lock
```
Commit both lock files. Update them with `pip-compile --upgrade` on dep updates.

### License gate (dep-003 resolution)

This is configuration work, not code. Provide the steps:
1. Install pip-licenses: `pip install pip-licenses` (add to requirements-dev.txt)
2. Run to see current licenses: `pip-licenses`
3. Define your allowlist in your organization's agreed set of acceptable licenses
4. Add to CI: `pip-licenses --allow-only="[your list]" --fail-on-violation`
5. Do NOT let this tool generate the allowlist automatically — human review required.
