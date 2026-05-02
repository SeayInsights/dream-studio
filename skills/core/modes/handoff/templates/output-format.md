# Handoff Output Template

**Purpose**: Ensure handoff always prints full absolute paths for easy copy/paste to next session.

## Required Output Format

After writing handoff files, ALWAYS print in this exact format:

```
✅ Handoff complete

📄 Files created:
   - Markdown: {absolute_path_to_md}
   - JSON: {absolute_path_to_json}

📋 Next session resume:
   cat "{absolute_path_to_md}"

🚀 Quick start:
   1. Read handoff: cat "{absolute_path_to_md}"
   2. Execute plan: Read {absolute_path_to_plan} — resume at {phase}, {task_id}
```

## Variables to Resolve

```python
from pathlib import Path
import os

# Get absolute paths
handoff_md = Path(handoff_dir / f"handoff-{topic}.md").resolve()
handoff_json = Path(handoff_dir / f"handoff-{topic}.json").resolve()
plan_path = Path(plan_file).resolve() if plan_file else "N/A"

# Print template
print(f"""
✅ Handoff complete

📄 Files created:
   - Markdown: {handoff_md}
   - JSON: {handoff_json}

📋 Next session resume:
   cat "{handoff_md}"

🚀 Quick start:
   1. Read handoff: cat "{handoff_md}"
   2. Execute plan: Read {plan_path} — resume at {pipeline_phase}, {current_task_id}
""")
```

## Windows Path Handling

For Windows paths, use raw strings or forward slashes:
- ✅ `r"C:\Users\Dannis Seay\builds\..."`
- ✅ `"C:/Users/Dannis Seay/builds/..."`
- ❌ `"C:\Users\Dannis Seay\builds\..."` (escape issues)

## Example Output

```
✅ Handoff complete

📄 Files created:
   - Markdown: C:\Users\Dannis Seay\builds\dream-studio\.sessions\2026-05-02\handoff-realtime-dashboard.md
   - JSON: C:\Users\Dannis Seay\builds\dream-studio\.sessions\2026-05-02\handoff-realtime-dashboard.json

📋 Next session resume:
   cat "C:\Users\Dannis Seay\builds\dream-studio\.sessions\2026-05-02\handoff-realtime-dashboard.md"

🚀 Quick start:
   1. Read handoff: cat "C:\Users\Dannis Seay\builds\dream-studio\.sessions\2026-05-02\handoff-realtime-dashboard.md"
   2. Execute plan: Read .planning/specs/realtime-dashboard/plan.md — resume at build, T001
```

## Anti-Patterns

❌ **Relative paths**:
```
Handoff: .sessions/2026-05-02/handoff-topic.md  # BAD: breaks when pwd changes
```

❌ **No path at all**:
```
Handoff written successfully!  # BAD: user has to hunt for file
```

✅ **Full absolute paths**:
```
Handoff: C:\Users\Dannis Seay\builds\dream-studio\.sessions\2026-05-02\handoff-topic.md
```

## Implementation Checklist

When writing handoff output:
- [ ] Resolve full absolute paths using `Path.resolve()` or `os.path.abspath()`
- [ ] Print both markdown AND JSON paths
- [ ] Include copy/paste ready `cat` command
- [ ] Show next action with full plan path
- [ ] Test on Windows (backslash handling)
- [ ] Test from different working directories (ensure path works everywhere)
