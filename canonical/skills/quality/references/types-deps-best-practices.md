# Types & Dependencies Best Practices — Canonical Reference

**Source:** Authored for ds-quality:types-deps skill (18.5.2). Content sourced from PEP 484/526
(typing), mypy and pyright documentation, Python Packaging Authority (PyPA), OWASP SCVS, and
pip-audit guidance. No existing LIST-4 section — see authoring notes below.
**Status:** Active reference for ds-quality:types-deps skill (18.5.2)
**Last updated:** 2026-05-30

---

## Authoring notes

Unlike the testing and code-quality reference docs, this document did not exist in any draft form
in the canonical best-practices master. Both sections (M-types and K-deps) are authored here from
primary sources. Where a standard has genuine community consensus (PEP-backed, PyPA-endorsed), it
is cited and stated without qualification. Where there is real variance across the community (e.g.,
license allowlists, lock-file strategy for libraries vs. applications), the spectrum is presented
explicitly rather than a single decree.

---

## Boundary with sibling skills

This document covers two distinct concerns:

**Section M-types — type safety**: annotation coverage, `Any` discipline, `# type: ignore`
hygiene, and type-checker configuration scope. This is distinct from:
- **Code-quality (18.4.3)** — which owns import *ordering* (Section D: "std → third-party →
  internal → relative") and the M-partial item "type checker automated." types-deps owns the
  *coverage* and *discipline* of what the checker enforces once it is automated.
- **ops (18.6.3, future)** — which will own CI tooling setup (adding pyright to the pre-push
  gate, configuring strictness). types-deps *reports* coverage and enforcement gaps; it does not
  apply them.

**Section K-deps — dependency health**: declaration, lock files, CVE-gate enforcement, license
compatibility, and Python circular-import avoidance. This is distinct from:
- **`pr-security-scan:dependency-audit`** — which owns CVE *scan results* (the actual
  vulnerabilities found), version pinning correctness on PRs, and unused packages on PRs.
  types-deps owns the *enforcement-gap finding* (dep-001: CVE gate runs non-blocking), dev-lock
  hygiene, license gate absence, and circular imports.
- **`ds-security` pack** — which owns client-facing security scanning. types-deps is about the
  user's *own project's* dependency health.

**Cross-references:**
- `typ-001` (type-checker scope gap) ↔ `cq-M-partial` (type checker automated): CQ reports
  whether a checker is present at all; types-deps reports whether the checker covers the full
  source tree.
- `dep-007` (circular imports) ↔ `cq-D-import-order` (consistent import ordering): ordering is
  code-quality; cycles are types-deps.

---

## Severity legend

- 🔴 Mandatory — correctness violation, security-adjacent, or gates/CI failure category
- 🟠 De facto standard — every serious project does this; skipping has real maintenance cost
- 🟢 Should have — best practice, judgment-dependent

---

## Section M-types. Type Safety

**Primary sources:**
- PEP 484 — Type Hints (accepted 2015): https://peps.python.org/pep-0484/
- PEP 526 — Syntax for Variable Annotations (accepted 2016): https://peps.python.org/pep-0526/
- mypy documentation: https://mypy.readthedocs.io/en/stable/
- pyright documentation: https://github.com/microsoft/pyright/blob/main/docs/configuration.md
- Google Python Style Guide §3.19: https://google.github.io/styleguide/pyguide.html#319-type-annotations

### The checklist

- 🔴 Type checker configured and covering all production source directories
- 🟠 All public function signatures annotated (parameters + return type)
- 🟠 `Any` confined to system boundaries; not used in interior logic
- 🟠 `# type: ignore` always accompanied by a brief justification comment
- 🟢 `from __future__ import annotations` in files using forward references
- 🟢 `TypedDict` for structured dict shapes rather than `dict[str, Any]`
- 🟢 `Protocol` for structural subtyping (duck typing made explicit)

### Standards, sourced

**Type checker coverage (🔴)**

PEP 484 defines type hints as an optional but analyzable feature of Python. The value is captured
only by static analysis tools (mypy, pyright) that check the hints. A type checker configured
only for part of the codebase is equivalent to a linter with `# noqa` on half the files — the
confidence it provides is proportional to coverage. pyright's own documentation states that the
`include` config directive determines which files are checked; files outside `include` are analyzed
only when imported from included files (https://github.com/microsoft/pyright/blob/main/docs/configuration.md#include).

**Annotation coverage (🟠)**

PEP 484 §2 recommends annotating all public function signatures. mypy documentation recommends
annotating all functions that are part of a module's public API. The mypy `--strict` flag enables
`--disallow-untyped-defs`, which enforces this as an error. This is the community consensus for
mature codebases. Unannotated `__init__` methods returning `None` are exempt (implicitly annotated
by convention per PEP 484 §1).

**`Any` discipline (🟠)**

PEP 484 §4.6 defines `Any` as a special type that is consistent with every other type. Its
intended use is at system boundaries where the type is genuinely unknowable at static-analysis
time: parsed JSON (before validation), plugin return values, deserialized data. Its misuse is in
*interior* code where the type IS known but annotation was omitted for convenience. mypy
documentation describes this as "type erasure" — using `Any` inside a well-typed module defeats
the checker for all code downstream of that point. The community consensus (mypy docs, pyright
docs, Google style guide) is: `Any` at boundaries is legitimate; `Any` as a convenience inside
typed code is a smell.

**CONTESTED POINT — how strict is "too strict"?** mypy's `--strict` mode enables ~10 additional
checks beyond the defaults (e.g., `--disallow-any-generics`, `--warn-return-any`). Teams vary on
whether all of these are appropriate. The baseline consensus is `--disallow-untyped-defs` (annotate
all functions) and avoiding `Any` in interior code. Beyond that, `--strict` is a choice. The skill
reports the *gap* from current config to full coverage; it does not mandate a specific strictness
level.

**`# type: ignore` hygiene (🟠)**

mypy documentation recommends that all `# type: ignore` comments include a brief explanation or
issue reference (e.g., `# type: ignore[assignment]  # mypy bug #1234` or `# type: ignore  # third-party
stubs incomplete`). pyright allows `# type: ignore` but recommends `# pyright: ignore[rule]` for
rule-specific suppression. The community standard is: suppression comments should explain *why*
the checker is wrong, not just silence it. Unexplained suppressions accumulate and erode type
safety without traceable justification.

### Patterns and anti-patterns

**`Any` at boundaries (good):**
```python
# JSON deserialization — type genuinely unknown before validation
def parse_event(raw: dict[str, Any]) -> Event:
    # Validate raw here, then produce a typed Event
    return Event(id=raw["id"], type=raw["event_type"])
```

**`Any` as interior laziness (bad):**
```python
# The type IS known — this erases it for all callers
def get_user_name(user: Any) -> Any:  # should be: user: User) -> str
    return user.name
```

**`TYPE_CHECKING` guard pattern (good — safe forward reference):**
```python
from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from core.projects.models import Project  # safe at runtime; resolved by checker
```
This pattern is not a circular import. It is the standard Python idiom for breaking genuine
circular import cycles at runtime while keeping the type checker informed. Do NOT flag these as
violations of dep-007.

---

## Section K. Dependencies

**Primary sources:**
- Python Packaging User Guide (PyPA): https://packaging.python.org/
- pip-tools / pip-compile: https://pip-tools.readthedocs.io/
- pip-audit (PyPA): https://pypa.github.io/pip-audit/
- OWASP Software Component Verification Standard (SCVS) L1: https://owasp.org/www-project-software-component-verification-standard/
- OWASP Dependency-Check: https://owasp.org/www-project-dependency-check/
- SPDX License List: https://spdx.org/licenses/
- Python Packaging Guide — dependency specifiers: https://packaging.python.org/en/latest/specifications/dependency-specifiers/

### The checklist

- 🔴 CVE scanner is configured AND blocking (not `continue-on-error`)
- 🟠 All dependencies locked to exact versions for reproducible installs
- 🟠 Development dependencies have their own lock file (separate from production)
- 🟠 License compatibility verified for all direct dependencies
- 🟠 No Python runtime circular imports (TYPE_CHECKING-guarded imports are exempt)
- 🟢 Dependency surface minimized — each dependency is justified
- 🟢 Direct dependencies declared; transitive deps not listed directly

### Standards, sourced

**CVE gate enforcement (🔴)**

OWASP SCVS Level 1 (the minimum baseline, applicable to any software handling user data) requires
that "all components, including transitive dependencies, are identified and have no known
exploitable vulnerabilities" (SCVS L1.1 through L1.6). A CVE scanner that runs but does not fail
the build on findings provides false confidence — it is the operational equivalent of a fire alarm
that sounds but does not alert anyone. pip-audit's own documentation states it is designed to be
used as a blocking gate; `continue-on-error: true` in CI defeats this purpose. The difference
between "passes" and "findings suppressed" is not visible to developers when the gate is
non-blocking.

**Dependency locking (🟠)**

PyPA's packaging guide explicitly distinguishes *dependency specifiers* (ranges in `pyproject.toml`
or `requirements.txt`) from *lock files* (exact versions of all direct and transitive deps). The
guide states that for *applications* (not libraries), lock files are the correct mechanism to
ensure reproducible installs across developer machines, CI, and production. pip-compile produces
lock files from range-constrained requirements. poetry.lock serves the same purpose. The principle
is: *specify* your constraints for compatibility with other packages; *lock* for reproducibility
of deployment.

**CONTESTED POINT — library vs. application locking:** Libraries (packages consumed by other
packages) should NOT lock their transitive dependencies, because they need to compose with the
consumer's dep tree. Applications (deployed artifacts with a fixed runtime) SHOULD lock. Most
projects are applications; the rule applies with this caveat. If the project under audit is a
library, dev lock is still appropriate; production lock is not.

**Separate dev dependency lock (🟠)**

Development-only dependencies (test runners, linters, formatters) interact with the production dep
tree but should not appear in the production lock. The standard pattern (PyPA guide, pip-tools
docs) is a separate `requirements-dev.txt` + `requirements-dev.lock` so that:
1. Production environments install only production deps
2. Security audits of production deps are not clouded by dev-only packages
3. Dev dep updates don't touch the production lock

Not having a dev lock means dev environments are not reproducible — different developers may run
tests against different versions of pytest, coverage, etc., introducing environment-dependent
behavior.

**License compatibility (🟠)**

Every package in the dep tree has a license. Whether that license is compatible with the project's
distribution model is a legal obligation, not a suggestion. The SPDX license identifier system
provides machine-readable license identifiers (https://spdx.org/licenses/). The general community
heuristic for open-source projects:
- Permissive licenses (MIT, BSD-2-Clause, BSD-3-Clause, Apache-2.0, ISC): generally compatible
  with both open-source and commercial use.
- Copyleft (GPL-2.0, GPL-3.0, LGPL): compatible with open-source distribution; potentially
  problematic for commercial/SaaS distribution depending on the specific license and legal counsel.
- Non-commercial (CC BY-NC): not compatible with commercial use.

**CONTESTED POINT — license allowlists are organizational, not universal.** The specific set of
"allowed" licenses for a project depends on its distribution model, jurisdictional requirements,
and legal counsel. The skill does NOT prescribe an allowlist. It prescribes that a license gate
EXISTS — a tool (pip-licenses, liccheck) is configured to verify every dep's license against an
operator-defined allowlist before production deployment. The contents of the allowlist are the
operator's decision.

**Circular imports (🟠)**

Python's import system can create circular imports that either (a) fail at runtime with
`ImportError` / `AttributeError` (hard cycle) or (b) succeed at runtime because the import is
deferred until the module attribute is actually needed (soft cycle, often fragile). Neither is
desirable in production code.

The Python community standard for breaking legitimate circular dependencies:
1. **Restructure the dependency graph** — if A needs B and B needs A, extract the shared concept
   into a C that both import.
2. **Use `if TYPE_CHECKING:` guards** — for typing-only imports that would create cycles at
   runtime (PEP 484 recommends this pattern explicitly). These are NOT circular imports; they are
   the standard idiom.
3. **Deferred imports inside functions** — acceptable for rare cases where restructuring is
   impractical, but signals a design issue.

Runtime circular imports (not guarded by `TYPE_CHECKING`) are bugs: they produce environments
where the availability of a symbol depends on module initialization order. The standard is: no
runtime circular imports; TYPE_CHECKING-guarded cycles are expected and correct.

**CONTESTED POINT — depth of cycle detection.** AST-based cycle detection can find all Python
import cycles but requires distinguishing which imports are guarded by `if TYPE_CHECKING:`. Failing
to make this distinction produces large numbers of false positives. The standard approach (used by
tools like `importlab` and `pylint --import-checker`) is to respect TYPE_CHECKING guards. Cycles
that only exist inside a `TYPE_CHECKING` block are not runtime cycles and should not be flagged as
violations.

**Dependency surface (🟢)**

Each dependency is a maintenance liability (updates, CVEs, breaking changes) and a security
surface (supply chain attacks). The PyPA guide recommends declaring only *direct* dependencies —
packages your code explicitly imports — and allowing pip/pip-compile to resolve transitives. This
keeps the intent legible and the maintenance burden proportional to what the project actually uses.
"Dependency bloat" (adding large frameworks for small needs, accumulating abandoned packages) is
a community-recognized antipattern. No specific metric; judgment applies.

### Patterns and anti-patterns

**CVE gate as a blocking check (good):**
```yaml
# .github/workflows/ci.yml
- name: Dependency vulnerability scan
  run: python -m pip_audit -r requirements.txt
  # No continue-on-error — failures block the build
```

**CVE gate silenced (bad):**
```yaml
- name: Dependency vulnerability scan
  continue-on-error: true   # findings are logged but never block merge
  run: python -m pip_audit -r requirements.txt
```

**License gate with pip-licenses (good):**
```bash
pip-licenses --allow-only="MIT;BSD-2-Clause;Apache-2.0;ISC;Python-2.0" --fail-on-violation
```

**TYPE_CHECKING-guarded import (good — NOT a circular import):**
```python
# In core/work_orders/start.py
from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from core.projects.mutations import ProjectContext  # typing-only, no runtime cycle
```

**Runtime circular import (bad):**
```python
# core/a.py
from core.b import B  # B's module imports A — runtime ImportError possible

# core/b.py
from core.a import A  # creates the cycle
```

---

## Relationship to ops (18.6.3)

Several of these standards require tooling changes to *enforce*, not just detect:
- Expanding pyright to cover all source dirs → CI configuration change
- Making pip-audit blocking → remove `continue-on-error` from CI
- Adding a dev lock file → run `pip-compile` on requirements-dev.txt
- Installing a license gate → `pip install pip-licenses` + add CI step

The **types-deps skill** *reports* gaps. It produces findings like "pyright covers 3 of 6 source
directories" and "pip-audit runs non-blocking." The **ops skill (18.6.3)** is the home for the
tooling changes that close those gaps. This mirrors the testing skill's pattern: tst-010 reports
the coverage-enforcement gap; ops (future) is where the `fail_under` threshold gets raised.
