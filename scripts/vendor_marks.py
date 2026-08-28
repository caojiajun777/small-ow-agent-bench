"""Publisher marks for the public ranking table and chart.

Icons are CC0 Simple Icons copies under results/figures/vendors/.
"""

from __future__ import annotations

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
    "openai": {"file": "openai.svg", "color": "#10A37F", "alt": "OpenAI"},
    "nvidia": {"file": "nvidia.svg", "color": "#76B900", "alt": "NVIDIA"},
    "zai": {"file": "zai.svg", "color": "#5B5BD6", "alt": "Z.ai"},
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


def _path_d(key: str) -> str:
    text = vendor_path(key).read_text(encoding="utf-8")
    match = re.search(r'<path[^>]*\sd="([^"]+)"', text)
    if not match:
        raise ValueError(f"no path in {vendor_path(key)}")
    return match.group(1)


def icon_svg(lock_id: str, display: str, x: float, y: float, size: float = 16) -> str:
    key = vendor_key(lock_id, display)
    spec = VENDORS[key]
    scale = size / 24.0
    d = _path_d(key)
    return (
        f'<g transform="translate({x:.1f},{y:.1f}) scale({scale:.4f})" '
        f'aria-label="{spec["alt"]}">'
        f'<path d="{d}" fill="{spec["color"]}"/></g>'
    )
