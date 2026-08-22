"""Two Hard loc + two Hard review isomorphs of the 9B-failing ceiling traps."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from write_atomic_skills_pilot import (  # noqa: E402
    DOCKERFILE,
    ROOT,
    TEST_SH,
    bash_solve,
    loc_file_tests,
    loc_solve_files,
    review_tests,
    toml,
    write,
)


def loc_hardcoded_fast_timeout() -> None:
    name = "loc-hardcoded-fast-timeout"
    base = ROOT / name
    write(
        base / "instruction.md",
        """The service at `/app/repo` is supposed to use a 5-second wait for the fast profile. Fast requests currently wait 30 seconds.

Identify every file that must be changed to resolve this issue. Write each path relative to `/app/repo` using forward slashes, one path per line, to `/app/answer.txt`. Order does not matter. Do not list test files unless they themselves contain the defect.

Do not modify the repository. You have 300 seconds.
""",
    )
    write(
        base / "task.toml",
        toml(
            name,
            "hard",
            "localization",
            "Gold is a single live hardcoded branch; unused FAST_SECONDS=30 is a decoy.",
            timeout=600.0,
        ),
    )
    write(base / "environment" / "Dockerfile", DOCKERFILE)
    write(
        base / "environment" / "repo" / "app.py",
        "from service import wait\n\ndef run(profile):\n    return wait(profile)\n",
    )
    write(
        base / "environment" / "repo" / "service.py",
        """from resolve import timeout_fn


def wait(profile):
    return timeout_fn(profile)()
""",
    )
    write(
        base / "environment" / "repo" / "resolve.py",
        """import importlib

from routing import HANDLERS


def timeout_fn(profile):
    if profile == "fast":
        from profiles.legacy import slow_timeout

        return slow_timeout
    path = HANDLERS[profile]
    mod, name = path.rsplit(".", 1)
    return getattr(importlib.import_module(mod), name)
""",
    )
    write(
        base / "environment" / "repo" / "routing.py",
        '''HANDLERS = {
    "std": "profiles.std.std_timeout",
    "fast": "profiles.fast.fast_timeout",
}
''',
    )
    write(base / "environment" / "repo" / "profiles" / "__init__.py", "")
    write(
        base / "environment" / "repo" / "profiles" / "legacy.py",
        "def slow_timeout():\n    return 30\n",
    )
    write(
        base / "environment" / "repo" / "profiles" / "fast.py",
        "FAST_SECONDS = 30\n\ndef fast_timeout():\n    return FAST_SECONDS\n",
    )
    write(
        base / "environment" / "repo" / "profiles" / "ok.py",
        "def fast_timeout():\n    return 5\n",
    )
    write(
        base / "environment" / "repo" / "profiles" / "std.py",
        "def std_timeout():\n    return 30\n",
    )
    write(base / "environment" / "repo" / "config" / "flags.py", "FAST_ENABLED = True\nFAST_MS = 30000\n")
    write(base / "tests" / "expected.txt", "resolve.py\n")
    write(base / "tests" / "test_state.py", loc_file_tests())
    write(base / "tests" / "test.sh", TEST_SH)
    write(base / "solution" / "solve.sh", loc_solve_files("resolve.py"))


def loc_hardcoded_digital_vat() -> None:
    name = "loc-hardcoded-digital-vat"
    base = ROOT / name
    write(
        base / "instruction.md",
        """The shop at `/app/repo` is supposed to charge 0% VAT on digital goods. Digital goods currently have 20% VAT added.

Identify every file that must be changed to resolve this issue. Write each path relative to `/app/repo` using forward slashes, one path per line, to `/app/answer.txt`. Order does not matter. Do not list test files unless they themselves contain the defect.

Do not modify the repository. You have 300 seconds.
""",
    )
    write(
        base / "task.toml",
        toml(
            name,
            "hard",
            "localization",
            "Gold is a single live hardcoded tax branch; unused DIGITAL_RATE=0.20 is a decoy.",
            timeout=600.0,
        ),
    )
    write(base / "environment" / "Dockerfile", DOCKERFILE)
    write(
        base / "environment" / "repo" / "app.py",
        "from checkout import total\n\ndef run(item, kind):\n    return total(item, kind)\n",
    )
    write(
        base / "environment" / "repo" / "checkout.py",
        """from catalog import list_price
from resolve import tax_fn


def total(item, kind):
    return list_price(item) * (1.0 + tax_fn(kind)())
""",
    )
    write(base / "environment" / "repo" / "catalog.py", "def list_price(item):\n    return float(item[\"price\"])\n")
    write(
        base / "environment" / "repo" / "resolve.py",
        """import importlib

from routing import HANDLERS


def tax_fn(kind):
    if kind == "digital":
        from tax.legacy import standard_vat

        return standard_vat
    path = HANDLERS[kind]
    mod, name = path.rsplit(".", 1)
    return getattr(importlib.import_module(mod), name)
""",
    )
    write(
        base / "environment" / "repo" / "routing.py",
        '''HANDLERS = {
    "physical": "tax.physical.physical_vat",
    "digital": "tax.digital.digital_vat",
}
''',
    )
    write(base / "environment" / "repo" / "tax" / "__init__.py", "")
    write(
        base / "environment" / "repo" / "tax" / "legacy.py",
        "def standard_vat():\n    return 0.20\n",
    )
    write(
        base / "environment" / "repo" / "tax" / "digital.py",
        "DIGITAL_RATE = 0.20\n\ndef digital_vat():\n    return DIGITAL_RATE\n",
    )
    write(
        base / "environment" / "repo" / "tax" / "zero.py",
        "def digital_vat():\n    return 0.0\n",
    )
    write(
        base / "environment" / "repo" / "tax" / "physical.py",
        "def physical_vat():\n    return 0.20\n",
    )
    write(base / "environment" / "repo" / "billing" / "adjust.py", "def adjust(amount):\n    return amount\n")
    write(base / "tests" / "expected.txt", "resolve.py\n")
    write(base / "tests" / "test_state.py", loc_file_tests())
    write(base / "tests" / "test.sh", TEST_SH)
    write(base / "solution" / "solve.sh", loc_solve_files("resolve.py"))


def review_configured_timeout() -> None:
    name = "review-configured-timeout"
    base = ROOT / name
    write(
        base / "instruction.md",
        """Issue:
`get_timeout(cfg)` reads a timeout from a dict. If the `timeout` key is omitted, the result must be `30`. `get_timeout({})` must be `30`. Any value that is present in the dict must be returned unchanged.

The candidate change is already applied in `/app/repo`. Decide whether this repository fully addresses the issue.

Write a single character to `/app/answer.txt`: `1` if it fully addresses the issue, `0` otherwise. You may inspect and run code. Do not change the repository. You have 300 seconds.
""",
    )
    write(
        base / "task.toml",
        toml(
            name,
            "hard",
            "code-review",
            "or-default passes the omitted-key example but drops a present zero.",
            timeout=600.0,
        ),
    )
    write(base / "environment" / "Dockerfile", DOCKERFILE)
    write(
        base / "environment" / "repo" / "limits.py",
        "def get_timeout(cfg):\n    return cfg.get(\"timeout\") or 30\n",
    )
    write(base / "tests" / "label.txt", "0\n")
    write(base / "tests" / "test_state.py", review_tests())
    write(base / "tests" / "test.sh", TEST_SH)
    write(base / "solution" / "solve.sh", bash_solve("printf '0\\n' > /app/answer.txt\n"))


def review_dollar_cents() -> None:
    name = "review-dollar-cents"
    base = ROOT / name
    write(
        base / "instruction.md",
        """Issue:
`to_cents(amount)` converts a dollar string to an integer number of cents. `to_cents('10')` must be `1000`. `to_cents('1.00')` must be `100`.

The candidate change is already applied in `/app/repo`. Decide whether this repository fully addresses the issue.

Write a single character to `/app/answer.txt`: `1` if it fully addresses the issue, `0` otherwise. You may inspect and run code. Do not change the repository. You have 300 seconds.
""",
    )
    write(
        base / "task.toml",
        toml(
            name,
            "hard",
            "code-review",
            "float-to-int cents passes the stated examples but is not exact for some decimals.",
            timeout=600.0,
        ),
    )
    write(base / "environment" / "Dockerfile", DOCKERFILE)
    write(
        base / "environment" / "repo" / "cents.py",
        "def to_cents(amount):\n    return int(float(amount) * 100)\n",
    )
    write(base / "tests" / "label.txt", "0\n")
    write(base / "tests" / "test_state.py", review_tests())
    write(base / "tests" / "test.sh", TEST_SH)
    write(base / "solution" / "solve.sh", bash_solve("printf '0\\n' > /app/answer.txt\n"))


def main() -> None:
    loc_hardcoded_fast_timeout()
    loc_hardcoded_digital_vat()
    review_configured_timeout()
    review_dollar_cents()
    print("wrote 4 hard isomorphs under", ROOT)


if __name__ == "__main__":
    main()
