"""Create the GitHub Release and set repo About fields.

Uses GH_TOKEN / GITHUB_TOKEN, or the stored git credential for github.com.
Does not print the token. Does not force-push. Does not move tags.

    python scripts/publish_github_surface.py
    python scripts/publish_github_surface.py --run
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from export_hf_catalog import load_env_file  # noqa: E402

OWNER = "caojiajun777"
REPO = "small-ow-agent-bench"
TAG = "benchmark-v1.0.1"
NOTES = ROOT / "results" / "RELEASE-v1.0.1.md"
DESCRIPTION = (
    "Atomic-skill compact-shell benchmark for open-weight coding agents "
    "(API Standard v1.0.1)."
)
HOMEPAGE = "https://huggingface.co/datasets/junjun77/small-ow-agent-bench"
TOPICS = [
    "agents",
    "benchmark",
    "llm",
    "code-generation",
    "evaluation",
    "open-weight",
]


def git_credential_token() -> str | None:
    try:
        proc = subprocess.run(
            ["git", "credential", "fill"],
            input="protocol=https\nhost=github.com\n\n",
            capture_output=True,
            text=True,
            cwd=str(ROOT),
            check=False,
            timeout=10,
        )
    except subprocess.TimeoutExpired:
        return None
    if proc.returncode != 0:
        return None
    password = None
    for line in proc.stdout.splitlines():
        if line.startswith("password="):
            password = line.split("=", 1)[1].strip()
    return password or None


def token() -> str:
    load_env_file()
    value = (
        os.environ.get("GH_TOKEN")
        or os.environ.get("GITHUB_TOKEN")
        or git_credential_token()
    )
    if not value:
        raise SystemExit("missing GitHub token (GH_TOKEN or git credential)")
    return value


def request(method: str, url: str, payload: dict | None, auth: str) -> dict:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {auth}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "small-ow-agent-bench",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"GitHub {method} {url} -> {exc.code}: {detail[:500]}") from exc


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    notes = NOTES.read_text(encoding="utf-8")
    print(f"repo {OWNER}/{REPO}")
    print(f"tag {TAG}")
    print(f"homepage {HOMEPAGE}")
    if not args.run:
        print("dry-run; pass --run to PATCH the repo and create the Release")
        return 0
    auth = token()
    request(
        "PATCH",
        f"https://api.github.com/repos/{OWNER}/{REPO}",
        {
            "description": DESCRIPTION,
            "homepage": HOMEPAGE,
        },
        auth,
    )
    print("updated description + homepage")
    request(
        "PUT",
        f"https://api.github.com/repos/{OWNER}/{REPO}/topics",
        {"names": TOPICS},
        auth,
    )
    print("updated topics")
    existing = None
    try:
        existing = request(
            "GET",
            f"https://api.github.com/repos/{OWNER}/{REPO}/releases/tags/{TAG}",
            None,
            auth,
        )
    except SystemExit as exc:
        if "404" not in str(exc):
            raise
    if existing and existing.get("id"):
        request(
            "PATCH",
            f"https://api.github.com/repos/{OWNER}/{REPO}/releases/{existing['id']}",
            {"name": TAG, "body": notes, "draft": False, "prerelease": False},
            auth,
        )
        print(f"updated release {existing.get('html_url')}")
    else:
        created = request(
            "POST",
            f"https://api.github.com/repos/{OWNER}/{REPO}/releases",
            {
                "tag_name": TAG,
                "name": TAG,
                "body": notes,
                "draft": False,
                "prerelease": False,
            },
            auth,
        )
        print(f"created release {created.get('html_url')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
