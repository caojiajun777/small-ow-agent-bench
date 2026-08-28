"""Publisher marks for the public ranking table and chart.

The vendored SVGs live under results/figures/vendors/.  The chart embeds each
complete SVG so multi-path, multicolor, and non-24x24 official marks survive.
"""

from __future__ import annotations

import html
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENDOR_DIR = ROOT / "results" / "figures" / "vendors"
README_VENDOR = "results/figures/vendors"

VENDORS = {
    "qwen": {"file": "qwen.svg", "color": "#111111", "alt": "Qwen"},
    "mistral": {"file": "mistralai.svg", "color": "#FA520F", "alt": "Mistral"},
    "google": {"file": "google.svg", "color": "#4285F4", "alt": "Google"},
    "ibm": {"file": "ibm.svg", "color": "#0F62FE", "alt": "IBM"},
    "meta": {"file": "meta.svg", "color": "#0082FB", "alt": "Meta"},
    "openai": {"file": "openai.svg", "color": "#111111", "alt": "OpenAI"},
    "nvidia": {"file": "nvidia.svg", "color": "#76B900", "alt": "NVIDIA"},
    "zai": {"file": "zai.svg", "color": "#2D2D2D", "alt": "Z.ai"},
}


def vendor_key(lock_id: str = "", display: str = "") -> str:
    name = f"{lock_id} {display}".lower()
    if "qwen" in name:
        return "qwen"
    if "ministral" in name or "mistral" in name:
        return "mistral"
    if "gemma" in name:
        return "google"
    if "granite" in name:
        return "ibm"
    if "llama" in name:
        return "meta"
    if "gpt-oss" in name or "openai" in name:
        return "openai"
    if "nemotron" in name or "nvidia" in name:
        return "nvidia"
    if "glm" in name or "z-ai" in name or "zai" in name:
        return "zai"
    raise KeyError(f"no publisher mark for {lock_id or display}")


def vendor_path(key: str) -> Path:
    return VENDOR_DIR / VENDORS[key]["file"]


def readme_label(display: str, lock_id: str = "") -> str:
    key = vendor_key(lock_id, display)
    spec = VENDORS[key]
    src = f"{README_VENDOR}/{spec['file']}"
    return f'<img src="{src}" width="16" height="16" alt="{spec["alt"]}"> {display}'


def _svg_parts(key: str) -> tuple[str, str]:
    text = vendor_path(key).read_text(encoding="utf-8")
    match = re.search(r"<svg\b(?P<attrs>[^>]*)>(?P<body>.*)</svg>\s*$", text, re.DOTALL)
    if not match:
        raise ValueError(f"no svg root in {vendor_path(key)}")
    view_box_match = re.search(r'viewBox="([^"]+)"', match.group("attrs"))
    if not view_box_match:
        raise ValueError(f"no viewBox in {vendor_path(key)}")
    body = re.sub(
        r"<(?:title|desc)\b[^>]*>.*?</(?:title|desc)>",
        "",
        match.group("body"),
        flags=re.DOTALL,
    )
    body = "\n".join(line.rstrip() for line in body.splitlines())
    return view_box_match.group(1), body.strip()


def icon_svg(lock_id: str, display: str, x: float, y: float, size: float = 16) -> str:
    key = vendor_key(lock_id, display)
    spec = VENDORS[key]
    view_box, body = _svg_parts(key)
    return (
        f'<svg x="{x:.1f}" y="{y:.1f}" width="{size:.1f}" height="{size:.1f}" '
        f'viewBox="{html.escape(view_box, quote=True)}" preserveAspectRatio="xMidYMid meet" '
        f'role="img" aria-label="{html.escape(spec["alt"], quote=True)}">{body}</svg>'
    )
