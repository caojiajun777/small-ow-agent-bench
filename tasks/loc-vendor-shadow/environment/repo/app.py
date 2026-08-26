import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / 'vendor'))
from billing.limits import MAX_UPLOAD_MB
