"""Private reference review; only the report is written to the agent workspace."""
import json
import os
from pathlib import Path

REPO = Path(os.environ.get("BENCH_REPO_ROOT", "/app/repo"))
APP = Path(os.environ.get("BENCH_APP_ROOT", "/app"))
REPORT = json.loads("{\"schema_version\":2,\"reviews\":[{\"candidate\":\"cedar\",\"decision\":\"accept\",\"location\":null,\"behavior\":null,\"cases\":[{\"input\":{\"texts\":[\"Hello,  World!!\",\"  ABC  \"]},\"expected\":{\"slugs\":[\"hello-world\",\"abc\"]}},{\"input\":{\"texts\":[\"--Hi--\",\"a--b\"]},\"expected\":{\"slugs\":[\"hi\",\"a-b\"]}},{\"input\":{\"texts\":[\"À B\",\"猫\\t狗\"]},\"expected\":{\"slugs\":[\"à-b\",\"猫-狗\"]}},{\"input\":{\"texts\":[\"!!!\",\"\",\" - \"]},\"expected\":{\"slugs\":[\"\",\"\",\"\"]}},{\"input\":{\"texts\":[\"one_two\",\"x.y\"]},\"expected\":{\"slugs\":[\"onetwo\",\"xy\"]}},{\"input\":{\"texts\":[]},\"expected\":{\"slugs\":[]}}]},{\"candidate\":\"maple\",\"decision\":\"reject\",\"location\":{\"path\":\"candidates/maple/slug.py\",\"line\":2},\"behavior\":\"The candidate violates the documented public behavior on the supplied executable counterexample.\",\"cases\":[{\"input\":{\"texts\":[\"Hello,  World!!\",\"  ABC  \"]},\"expected\":{\"slugs\":[\"hello-world\",\"abc\"]}},{\"input\":{\"texts\":[\"--Hi--\",\"a--b\"]},\"expected\":{\"slugs\":[\"hi\",\"a-b\"]}},{\"input\":{\"texts\":[\"À B\",\"猫\\t狗\"]},\"expected\":{\"slugs\":[\"à-b\",\"猫-狗\"]}},{\"input\":{\"texts\":[\"!!!\",\"\",\" - \"]},\"expected\":{\"slugs\":[\"\",\"\",\"\"]}},{\"input\":{\"texts\":[\"one_two\",\"x.y\"]},\"expected\":{\"slugs\":[\"onetwo\",\"xy\"]}},{\"input\":{\"texts\":[]},\"expected\":{\"slugs\":[]}}]},{\"candidate\":\"birch\",\"decision\":\"accept\",\"location\":null,\"behavior\":null,\"cases\":[{\"input\":{\"texts\":[\"Hello,  World!!\",\"  ABC  \"]},\"expected\":{\"slugs\":[\"hello-world\",\"abc\"]}},{\"input\":{\"texts\":[\"--Hi--\",\"a--b\"]},\"expected\":{\"slugs\":[\"hi\",\"a-b\"]}},{\"input\":{\"texts\":[\"À B\",\"猫\\t狗\"]},\"expected\":{\"slugs\":[\"à-b\",\"猫-狗\"]}},{\"input\":{\"texts\":[\"!!!\",\"\",\" - \"]},\"expected\":{\"slugs\":[\"\",\"\",\"\"]}},{\"input\":{\"texts\":[\"one_two\",\"x.y\"]},\"expected\":{\"slugs\":[\"onetwo\",\"xy\"]}},{\"input\":{\"texts\":[]},\"expected\":{\"slugs\":[]}}]},{\"candidate\":\"willow\",\"decision\":\"reject\",\"location\":{\"path\":\"candidates/willow/slug.py\",\"line\":5},\"behavior\":\"The candidate violates the documented public behavior on the supplied executable counterexample.\",\"cases\":[{\"input\":{\"texts\":[\"Hello,  World!!\",\"  ABC  \"]},\"expected\":{\"slugs\":[\"hello-world\",\"abc\"]}},{\"input\":{\"texts\":[\"--Hi--\",\"a--b\"]},\"expected\":{\"slugs\":[\"hi\",\"a-b\"]}},{\"input\":{\"texts\":[\"À B\",\"猫\\t狗\"]},\"expected\":{\"slugs\":[\"à-b\",\"猫-狗\"]}},{\"input\":{\"texts\":[\"!!!\",\"\",\" - \"]},\"expected\":{\"slugs\":[\"\",\"\",\"\"]}},{\"input\":{\"texts\":[\"one_two\",\"x.y\"]},\"expected\":{\"slugs\":[\"onetwo\",\"xy\"]}},{\"input\":{\"texts\":[]},\"expected\":{\"slugs\":[]}}]}]}")

def main():
    candidates = json.loads((REPO / "candidates.json").read_text())["candidates"]
    assert set(candidates) == {row["candidate"] for row in REPORT["reviews"]}
    APP.mkdir(parents=True, exist_ok=True)
    (APP / "review.json").write_text(json.dumps(REPORT, ensure_ascii=False, allow_nan=False, indent=2) + "\n", encoding="utf-8")

if __name__ == "__main__":
    main()

