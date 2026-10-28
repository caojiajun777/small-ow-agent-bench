"""JSON stdin/stdout adapter for the application workflow."""
import json
import sys
from workflow import process

if __name__ == "__main__":
    json.dump(process(json.load(sys.stdin)), sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")

