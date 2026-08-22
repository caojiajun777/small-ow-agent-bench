"""Retag the main atomic table: Medium = former easy/hard/ceiling that 9B passed."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "tasks"

# name -> (new_difficulty, optional explanation override)
REMAP: dict[str, tuple[str, str | None]] = {
    "loc-member-discount": ("medium", None),
    "loc-vip-two-files": ("medium", None),
    "loc-similar-filenames": ("medium", None),
    "edit-slugify": ("medium", None),
    "edit-covered-length": ("medium", None),
    "edit-deep-merge": ("medium", None),
    "testgen-clip": ("medium", None),
    "testgen-unique-order": ("medium", None),
    "testgen-gregorian": ("medium", None),
    "repro-off-by-one": ("medium", None),
    "repro-end-exclusive": ("medium", None),
    "repro-zero-timeout": ("medium", None),
    "review-clip-incomplete": ("medium", None),
    "review-slug-almost": ("medium", None),
    "review-mean-wrong": ("medium", None),
    "loc-hardcoded-vip-branch": ("hard", None),
    "review-floor-mean": ("hard", None),
}


def retag(text: str, new: str) -> str:
    for old in ("easy", "medium", "hard", "ceiling"):
        text = text.replace(f'difficulty = "{old}"', f'difficulty = "{new}"')
        text = text.replace(f'"{old}", "agentic-coding"', f'"{new}", "agentic-coding"')
    return text


def main() -> None:
    for name, (new, _explain) in REMAP.items():
        path = ROOT / name / "task.toml"
        raw = path.read_text(encoding="utf-8")
        path.write_text(retag(raw, new).replace("\r\n", "\n"), encoding="utf-8", newline="\n")
        print(f"{name} -> {new}")


if __name__ == "__main__":
    main()
