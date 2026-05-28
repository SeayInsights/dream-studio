# Code-Quality Skill — Smoke Test

Quick validation after install or update.

## 1. Skill loads

```
ds skill list | grep code-quality
```
Expected: `quality:code-quality` appears.

## 2. Shared utility importable

```python
from canonical.skills.quality.shared.trust_boundary_detection import is_external_entry_point, classify_boundary
```
Expected: No ImportError.

## 3. Dry-run invocation

```
ds skill invoke quality:code-quality --dry-run
```
Expected: No error. Prints skill summary and mode options.

## 4. Static rule on fixture

```
ds skill invoke quality:code-quality:audit tests/fixtures/ --scope tests/fixtures/
```
Expected: Runs without crash. May produce 0-N findings.

## 5. Build mode static smoke

```
ds skill invoke quality:code-quality:build "from os import *"
```
Expected: cq-A-explicit (wildcard import) fires as a medium finding.

## 6. trust_boundary_detection accuracy

```python
import ast
from canonical.skills.quality.shared.trust_boundary_detection import classify_boundary

# FastAPI route — should be external
code = "@router.get('/users')\ndef get_users(user_id: int): pass"
tree = ast.parse(code)
func = tree.body[1]
assert classify_boundary(func) == "external"

# Plain function — should be internal
code2 = "def compute_total(items): pass"
tree2 = ast.parse(code2)
func2 = tree2.body[0]
assert classify_boundary(func2) == "internal"
```
Expected: Both assertions pass.

## Pass criteria

- `quality:code-quality` discoverable
- shared utility importable and correct
- build mode fires on wildcard import
- audit mode runs without crash
