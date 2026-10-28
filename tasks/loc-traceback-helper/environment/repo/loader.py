from pathlib import Path
from codec import parse_record


def load_records(path):
    source = Path(path)
    if not source.is_absolute():
        source = Path(__file__).resolve().parent / source
    return [parse_record(line) for line in source.read_text(encoding="utf-8").splitlines() if line.strip()]
