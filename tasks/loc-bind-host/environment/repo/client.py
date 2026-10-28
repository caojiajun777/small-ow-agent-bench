"""JSON request adapter. This application is a synthetic benchmark fixture."""
import json
import sys
from app import process

if __name__ == "__main__":
    print(json.dumps(process(json.load(sys.stdin)), ensure_ascii=True))
