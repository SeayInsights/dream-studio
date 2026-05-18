import json
import uuid
from pathlib import Path

failed = Path(r"C:\Users\Dannis Seay\.dream-studio\events\failed")
spool = Path(r"C:\Users\Dannis Seay\.dream-studio\events\spool")

for f in sorted(failed.glob("*.json")):
    if ".reason" in f.name:
        continue
    data = json.loads(f.read_text(encoding="utf-8"))
    if "schema_version" not in data:
        data["schema_version"] = 1
    if "event_id" not in data:
        data["event_id"] = str(uuid.uuid4())
    target = spool / f.name
    target.write_text(json.dumps(data), encoding="utf-8")
    f.unlink()
    print("Requeued:", f.name, " (", data["event_type"], ")")
