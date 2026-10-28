"""Private reference review; only the report is written to the agent workspace."""
import json
import os
from pathlib import Path

REPO = Path(os.environ.get("BENCH_REPO_ROOT", "/app/repo"))
APP = Path(os.environ.get("BENCH_APP_ROOT", "/app"))
REPORT = json.loads("{\"schema_version\":2,\"reviews\":[{\"candidate\":\"cedar\",\"decision\":\"reject\",\"location\":{\"path\":\"candidates/cedar/scan.py\",\"line\":5},\"behavior\":\"The candidate violates the documented public behavior on the supplied executable counterexample.\",\"cases\":[{\"input\":{\"nums\":[1,2,3]},\"expected\":{\"prefix\":[1,3,6],\"original\":[1,2,3]}},{\"input\":{\"nums\":[2,-3,1],\"start\":10},\"expected\":{\"prefix\":[12,9,10],\"original\":[2,-3,1]}},{\"input\":{\"nums\":[],\"start\":5},\"expected\":{\"prefix\":[],\"original\":[]}},{\"input\":{\"nums\":[0,0],\"start\":-1},\"expected\":{\"prefix\":[-1,-1],\"original\":[0,0]}},{\"input\":{\"nums\":[0.25,0.75]},\"expected\":{\"prefix\":[0.25,1],\"original\":[0.25,0.75]}},{\"input\":{\"nums\":[7]},\"expected\":{\"prefix\":[7],\"original\":[7]}}]},{\"candidate\":\"maple\",\"decision\":\"reject\",\"location\":{\"path\":\"candidates/maple/scan.py\",\"line\":5},\"behavior\":\"The candidate violates the documented public behavior on the supplied executable counterexample.\",\"cases\":[{\"input\":{\"nums\":[1,2,3]},\"expected\":{\"prefix\":[1,3,6],\"original\":[1,2,3]}},{\"input\":{\"nums\":[2,-3,1],\"start\":10},\"expected\":{\"prefix\":[12,9,10],\"original\":[2,-3,1]}},{\"input\":{\"nums\":[],\"start\":5},\"expected\":{\"prefix\":[],\"original\":[]}},{\"input\":{\"nums\":[0,0],\"start\":-1},\"expected\":{\"prefix\":[-1,-1],\"original\":[0,0]}},{\"input\":{\"nums\":[0.25,0.75]},\"expected\":{\"prefix\":[0.25,1],\"original\":[0.25,0.75]}},{\"input\":{\"nums\":[7]},\"expected\":{\"prefix\":[7],\"original\":[7]}}]},{\"candidate\":\"birch\",\"decision\":\"accept\",\"location\":null,\"behavior\":null,\"cases\":[{\"input\":{\"nums\":[1,2,3]},\"expected\":{\"prefix\":[1,3,6],\"original\":[1,2,3]}},{\"input\":{\"nums\":[2,-3,1],\"start\":10},\"expected\":{\"prefix\":[12,9,10],\"original\":[2,-3,1]}},{\"input\":{\"nums\":[],\"start\":5},\"expected\":{\"prefix\":[],\"original\":[]}},{\"input\":{\"nums\":[0,0],\"start\":-1},\"expected\":{\"prefix\":[-1,-1],\"original\":[0,0]}},{\"input\":{\"nums\":[0.25,0.75]},\"expected\":{\"prefix\":[0.25,1],\"original\":[0.25,0.75]}},{\"input\":{\"nums\":[7]},\"expected\":{\"prefix\":[7],\"original\":[7]}}]},{\"candidate\":\"willow\",\"decision\":\"accept\",\"location\":null,\"behavior\":null,\"cases\":[{\"input\":{\"nums\":[1,2,3]},\"expected\":{\"prefix\":[1,3,6],\"original\":[1,2,3]}},{\"input\":{\"nums\":[2,-3,1],\"start\":10},\"expected\":{\"prefix\":[12,9,10],\"original\":[2,-3,1]}},{\"input\":{\"nums\":[],\"start\":5},\"expected\":{\"prefix\":[],\"original\":[]}},{\"input\":{\"nums\":[0,0],\"start\":-1},\"expected\":{\"prefix\":[-1,-1],\"original\":[0,0]}},{\"input\":{\"nums\":[0.25,0.75]},\"expected\":{\"prefix\":[0.25,1],\"original\":[0.25,0.75]}},{\"input\":{\"nums\":[7]},\"expected\":{\"prefix\":[7],\"original\":[7]}}]}]}")

def main():
    candidates = json.loads((REPO / "candidates.json").read_text())["candidates"]
    assert set(candidates) == {row["candidate"] for row in REPORT["reviews"]}
    APP.mkdir(parents=True, exist_ok=True)
    (APP / "review.json").write_text(json.dumps(REPORT, ensure_ascii=False, allow_nan=False, indent=2) + "\n", encoding="utf-8")

if __name__ == "__main__":
    main()

