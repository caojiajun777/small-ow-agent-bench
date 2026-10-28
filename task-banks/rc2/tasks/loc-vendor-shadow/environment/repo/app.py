import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "vendor"))
from billing.limits import MAX_UPLOAD_MB


def process(request):
    from upload import validate_batch
    policy = json.loads((ROOT / "policy.json").read_text(encoding="utf-8"))
    return validate_batch(request.get("files", []), policy)
