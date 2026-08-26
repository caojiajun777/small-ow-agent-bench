"""Write Hard-Release-15 (3 per atom). Official Hard set after freeze.

    python scripts/write_hard_release.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from write_hard_dev import (  # noqa: E402
    CANARY,
    DOCKERFILE,
    TASKS,
    TEST_SH,
    bash_solve,
    copy_normalize,
    loc_tests,
    repro_hidden,
    testgen_hidden,
    write,
)


def toml(name: str, ability: str, explain: str) -> str:
    return f"""schema_version = "1.4"

[task]
name = "small-ow-agent-bench/{name}"
version = "1.0.0"
authors = []
keywords = ["agentic-coding", "{ability}", "hard-release"]

[metadata]
author_name = ""
author_email = ""
difficulty = "hard"
category = "software"
subcategory = "{ability}"
tags = ["{ability}", "hard", "hard-release", "agentic-coding", "atomic-skills"]
difficulty_explanation = "{explain}"
expert_time_estimate_hours = 0.3

[verifier]
timeout_sec = 180.0

[agent]
timeout_sec = 180.0

[environment]
build_timeout_sec = 600.0
cpus = 1
memory_mb = 2048
storage_mb = 10240
gpus = 0
mcp_servers = []
"""


LOC_INSTR = """The shop project is at `/app/repo`. {issue}

Identify every file that must be changed to resolve this issue. Write each path relative to `/app/repo` using forward slashes, one path per line, to `/app/answer.txt`. Order does not matter. Do not list test files unless they themselves contain the defect.

Do not modify the repository. You have 180 seconds.
"""


def write_foils(base: Path, kind: str, foils: list[dict]) -> None:
    import json

    write(
        base / "foils" / "foils.json",
        json.dumps({"kind": kind, "foils": foils}, indent=2) + "\n",
    )
    lines = [f"- `{item['id']}`: {item.get('why', '')}" for item in foils]
    write(base / "foils" / "README.md", "# Foils (verifier must score 0)\n\n" + "\n".join(lines) + "\n")


def loc_vendor_shadow() -> None:
    name = "loc-vendor-shadow"
    base = TASKS / name
    write(
        base / "instruction.md",
        LOC_INSTR.format(
            issue="Uploads up to 25 MB should be accepted. A 20 MB file is still rejected."
        ),
    )
    write(
        base / "task.toml",
        toml(name, "localization", "Exact set: vendor-shadowed limits, not the unused top-level module."),
    )
    repo = base / "environment" / "repo"
    write(repo / "billing" / "__init__.py", "")
    write(repo / "billing" / "limits.py", "MAX_UPLOAD_MB = 25\n")
    write(repo / "vendor" / "billing" / "__init__.py", "")
    write(repo / "vendor" / "billing" / "limits.py", "MAX_UPLOAD_MB = 5\n")
    write(
        repo / "app.py",
        "import sys\n"
        "from pathlib import Path\n\n"
        "sys.path.insert(0, str(Path(__file__).resolve().parent / 'vendor'))\n"
        "from billing.limits import MAX_UPLOAD_MB\n",
    )
    write(
        repo / "upload.py",
        "from app import MAX_UPLOAD_MB\n\n\n"
        "def allow(size_mb):\n"
        "    return size_mb <= MAX_UPLOAD_MB\n",
    )
    write(repo / "README.md", "Upload limits live in billing/limits.py.\n")
    loc_tests(base, "vendor/billing/limits.py")
    write(
        base / "solution" / "solve.sh",
        bash_solve("printf 'vendor/billing/limits.py\\n' > /app/answer.txt\n"),
    )
    write_foils(
        base,
        "loc",
        [
            {
                "id": "readme-decoy",
                "why": "only the unused top-level module",
                "paths": ["billing/limits.py"],
            },
            {
                "id": "both-copies",
                "why": "gold plus decoy",
                "paths": ["billing/limits.py", "vendor/billing/limits.py"],
            },
            {
                "id": "loader-only",
                "why": "the path insert is not the defect file",
                "paths": ["app.py"],
            },
        ],
    )


def loc_env_wrapper() -> None:
    name = "loc-env-wrapper"
    base = TASKS / name
    write(
        base / "instruction.md",
        LOC_INSTR.format(
            issue="The service should write logs to `/var/log/app.log`. It still writes them somewhere else."
        ),
    )
    write(
        base / "task.toml",
        toml(name, "localization", "Exact set: shell wrapper that exports APP_LOG."),
    )
    repo = base / "environment" / "repo"
    write(
        repo / "bin" / "serve.sh",
        "#!/bin/sh\nexport APP_LOG=/tmp/svc.out\nexec python3 -m app\n",
    )
    write(
        repo / "app.py",
        "import os\n\n\n"
        "def log_path():\n"
        '    return os.environ.get("APP_LOG", "/var/log/app.log")\n',
    )
    write(repo / "config.yaml", "log: /var/log/app.log\n")
    write(repo / "logger.py", 'PATH = "/var/log/app.log"\n')
    loc_tests(base, "bin/serve.sh")
    write(
        base / "solution" / "solve.sh",
        bash_solve("printf 'bin/serve.sh\\n' > /app/answer.txt\n"),
    )
    write_foils(
        base,
        "loc",
        [
            {
                "id": "yaml-decoy",
                "why": "config already has the desired path",
                "paths": ["config.yaml"],
            },
            {
                "id": "python-default",
                "why": "the default in app.py is already correct",
                "paths": ["app.py"],
            },
            {
                "id": "unused-logger",
                "why": "logger.py is never imported",
                "paths": ["logger.py"],
            },
        ],
    )


def loc_hook_plugin() -> None:
    name = "loc-hook-plugin"
    base = TASKS / name
    write(
        base / "instruction.md",
        LOC_INSTR.format(
            issue="Failed jobs should follow the retry policy in `docs/ops.md`. They currently retry fewer times than that policy."
        ),
    )
    write(
        base / "task.toml",
        toml(name, "localization", "Exact set: hooked plugin file, not the unused sibling."),
    )
    repo = base / "environment" / "repo"
    write(repo / "docs" / "ops.md", "Job retry policy: at most five attempts.\n")
    write(repo / "hooks.json", '{"retry": "plugins/retry_v1.py"}\n')
    write(
        repo / "plugins" / "retry.py",
        "ATTEMPTS = 5\n# leftover canary: ATTEMPTS = 2 was never loaded\n",
    )
    write(repo / "plugins" / "retry_v1.py", "ATTEMPTS = 2\n")
    write(
        repo / "loader.py",
        "import importlib.util\n"
        "import json\n"
        "from pathlib import Path\n\n"
        "ROOT = Path(__file__).resolve().parent\n"
        "HOOK = json.loads((ROOT / 'hooks.json').read_text())\n"
        "PLUGIN = ROOT / HOOK['retry']\n\n\n"
        "def attempts():\n"
        "    spec = importlib.util.spec_from_file_location('retry_plugin', PLUGIN)\n"
        "    mod = importlib.util.module_from_spec(spec)\n"
        "    spec.loader.exec_module(mod)\n"
        "    return mod.ATTEMPTS\n",
    )
    write(repo / "worker.py", "from loader import attempts\n\n\ndef max_tries():\n    return attempts()\n")
    loc_tests(base, "plugins/retry_v1.py")
    write(
        base / "solution" / "solve.sh",
        bash_solve("printf 'plugins/retry_v1.py\\n' > /app/answer.txt\n"),
    )
    write_foils(
        base,
        "loc",
        [
            {
                "id": "documented-plugin",
                "why": "unused sibling already has five attempts",
                "paths": ["plugins/retry.py"],
            },
            {
                "id": "registry-only",
                "why": "hooks.json is the pointer, not the live constant",
                "paths": ["hooks.json"],
            },
            {
                "id": "docs-only",
                "why": "the guide is already correct",
                "paths": ["docs/ops.md"],
            },
        ],
    )


def edit_config_beside() -> None:
    name = "edit-config-beside"
    base = TASKS / name
    write(
        base / "instruction.md",
        """In `/app/repo/settings.py`, implement `load()`.

It must read the JSON settings file that ships with this module and return that
object. Callers need at least the `retry` and `mode` fields.

Do not change tests. You may run `python3 -m pytest /app/repo/tests -q`. You have 180 seconds.
""",
    )
    write(
        base / "task.toml",
        toml(name, "code-editing", "Hidden tests load settings after chdir away from the repo."),
    )
    write(base / "environment" / "Dockerfile", DOCKERFILE)
    write(
        base / "environment" / "repo" / "settings.py",
        "import json\n\n\ndef load():\n    with open('settings.json') as handle:\n        return json.load(handle)\n",
    )
    write(base / "environment" / "repo" / "settings.json", '{"retry": 5, "mode": "prod"}\n')
    write(
        base / "environment" / "repo" / "tests" / "test_settings.py",
        "from settings import load\n\n\n"
        "def test_retry_in_repo():\n"
        "    cfg = load()\n"
        "    assert cfg['retry'] == 5\n"
        "    assert cfg['mode'] == 'prod'\n",
    )
    write(
        base / "tests" / "test_state.py",
        CANARY
        + '''
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, "/app/repo")
from settings import load


def test_retry_in_repo():
    cfg = load()
    assert cfg["retry"] == 5
    assert cfg["mode"] == "prod"


def test_retry_from_other_cwd():
    here = Path.cwd()
    other = Path(tempfile.mkdtemp())
    (other / "settings.json").write_text(
        json.dumps({"retry": 99, "mode": "tmp"}), encoding="utf-8"
    )
    try:
        os.chdir(other)
        cfg = load()
        assert cfg["retry"] == 5
        assert cfg["mode"] == "prod"
    finally:
        os.chdir(here)
''',
    )
    write(base / "tests" / "test.sh", TEST_SH)
    write(
        base / "solution" / "solve.sh",
        bash_solve(
            """python3 - <<'PY'
from pathlib import Path
Path("/app/repo/settings.py").write_text('''import json
from pathlib import Path

def load():
    path = Path(__file__).resolve().parent / "settings.json"
    with open(path) as handle:
        return json.load(handle)
''')
PY
"""
        ),
    )
    write_foils(
        base,
        "edit",
        [
            {
                "id": "cwd-open",
                "why": "open('settings.json') follows the process cwd",
                "body": "import json\n\ndef load():\n    with open('settings.json') as handle:\n        return json.load(handle)\n",
            },
            {
                "id": "hardcoded",
                "why": "returns retry=5 without reading the file (mode missing)",
                "body": "def load():\n    return {'retry': 5}\n",
            },
        ],
    )


def edit_retry_discount() -> None:
    name = "edit-retry-discount"
    base = TASKS / name
    write(
        base / "instruction.md",
        """In `/app/repo/checkout.py`, implement `charge(cart)`.

Member checkout is 10% off the list price. Charging the same cart again must
still be 10% off that original list, not a smaller amount.

Do not change tests. You may run `python3 -m pytest /app/repo/tests -q`. You have 180 seconds.
""",
    )
    write(
        base / "task.toml",
        toml(name, "code-editing", "Hidden tests call charge twice; stacking 0.9 fails."),
    )
    write(base / "environment" / "Dockerfile", DOCKERFILE)
    write(
        base / "environment" / "repo" / "checkout.py",
        "def charge(cart):\n"
        '    cart["total"] = round(cart["total"] * 0.9, 2)\n'
        '    return cart["total"]\n',
    )
    write(
        base / "environment" / "repo" / "tests" / "test_checkout.py",
        "from checkout import charge\n\n\n"
        "def test_once():\n"
        '    assert charge({"list_price": 100, "total": 100}) == 90\n',
    )
    write(
        base / "tests" / "test_state.py",
        CANARY
        + '''
import sys

sys.path.insert(0, "/app/repo")
from checkout import charge


def test_once():
    assert charge({"list_price": 100, "total": 100}) == 90


def test_second_charge_not_stacked():
    cart = {"list_price": 100, "total": 100}
    charge(cart)
    assert charge(cart) == 90


def test_other_list_price():
    assert charge({"list_price": 200, "total": 200}) == 180
''',
    )
    write(base / "tests" / "test.sh", TEST_SH)
    write(
        base / "solution" / "solve.sh",
        bash_solve(
            """python3 - <<'PY'
from pathlib import Path
Path("/app/repo/checkout.py").write_text('''def charge(cart):
    cart["total"] = round(cart["list_price"] * 0.9, 2)
    return cart["total"]
''')
PY
"""
        ),
    )
    write_foils(
        base,
        "edit",
        [
            {
                "id": "stack-total",
                "why": "multiplies the running total",
                "body": "def charge(cart):\n    cart['total'] = round(cart['total'] * 0.9, 2)\n    return cart['total']\n",
            },
            {
                "id": "hardcoded-90",
                "why": "only works for list_price 100",
                "body": "def charge(cart):\n    cart['total'] = 90\n    return 90\n",
            },
        ],
    )


def edit_blank_name() -> None:
    name = "edit-blank-name"
    base = TASKS / name
    write(
        base / "instruction.md",
        """In `/app/repo/profile.py`, implement `display_name(user)`.

If the user has no name field, return `guest`. If they set a name, return that
name even when it is an empty string.

Do not change tests. You may run `python3 -m pytest /app/repo/tests -q`. You have 180 seconds.
""",
    )
    write(
        base / "task.toml",
        toml(name, "code-editing", "Hidden tests: present empty string is not guest."),
    )
    write(base / "environment" / "Dockerfile", DOCKERFILE)
    write(
        base / "environment" / "repo" / "profile.py",
        'def display_name(user):\n    return user.get("name") or "guest"\n',
    )
    write(
        base / "environment" / "repo" / "tests" / "test_profile.py",
        "from profile import display_name\n\n\n"
        "def test_missing():\n"
        '    assert display_name({}) == "guest"\n\n\n'
        "def test_set():\n"
        '    assert display_name({"name": "Ada"}) == "Ada"\n',
    )
    write(
        base / "tests" / "test_state.py",
        CANARY
        + '''
import sys

sys.path.insert(0, "/app/repo")
from profile import display_name


def test_missing():
    assert display_name({}) == "guest"


def test_set():
    assert display_name({"name": "Ada"}) == "Ada"


def test_empty_string_kept():
    assert display_name({"name": ""}) == ""
''',
    )
    write(base / "tests" / "test.sh", TEST_SH)
    write(
        base / "solution" / "solve.sh",
        bash_solve(
            """python3 - <<'PY'
from pathlib import Path
Path("/app/repo/profile.py").write_text('''def display_name(user):
    if "name" not in user:
        return "guest"
    return user["name"]
''')
PY
"""
        ),
    )
    write_foils(
        base,
        "edit",
        [
            {
                "id": "or-guest",
                "why": "empty string is falsy",
                "body": "def display_name(user):\n    return user.get('name') or 'guest'\n",
            },
            {
                "id": "always-guest-if-empty-method",
                "why": "treats missing and empty the same via get default",
                "body": "def display_name(user):\n    name = user.get('name', 'guest')\n    return name or 'guest'\n",
            },
        ],
    )


def testgen_task(
    name: str,
    issue: str,
    module: str,
    gold: str,
    mutants: dict[str, str],
    oracle_tests: str,
    explain: str,
) -> None:
    base = TASKS / name
    write(base / "instruction.md", issue)
    write(base / "task.toml", toml(name, "unit-test-generation", explain))
    write(base / "environment" / "Dockerfile", DOCKERFILE)
    write(base / "environment" / "repo" / f"{module}.py", gold)
    write(base / "environment" / "repo" / "tests" / ".gitkeep", "")
    write(base / "tests" / "gold" / f"{module}.py", gold)
    for mutant_name, body in mutants.items():
        write(base / "tests" / "mutants" / mutant_name, body)
    write(base / "tests" / "test_state.py", testgen_hidden(module))
    write(base / "tests" / "test.sh", TEST_SH)
    write(
        base / "solution" / "solve.sh",
        bash_solve(
            "python3 - <<'PY'\n"
            "from pathlib import Path\n"
            f'p = Path("/app/repo/tests/test_{module}.py")\n'
            "p.parent.mkdir(parents=True, exist_ok=True)\n"
            f"p.write_text({oracle_tests!r})\n"
            "PY\n"
        ),
    )
    write_foils(
        base,
        "testgen",
        [
            {
                "id": "happy-path-only",
                "why": "tests that never hit mutant-killing cases still pass gold",
            },
            {
                "id": "mutant-also-passes",
                "why": "if agent tests match a mutant, hidden test_detect_all_mutants fails",
            },
        ],
    )


def testgen_tie_order() -> None:
    testgen_task(
        "testgen-tie-order",
        """`/app/repo/rank.py` implements `ranked(rows)`.

Each row is `{"name": str, "score": int}`. Return names ordered by score from
high to low. The rest of the contract is documented on `ranked`.

Write unit tests in `/app/repo/tests/test_rank.py`. Do not change `rank.py`. You have 180 seconds.
""",
        "rank",
        "def ranked(rows):\n"
        '    """Higher score first. Equal scores keep the input order."""\n'
        '    return [row["name"] for row in sorted(rows, key=lambda row: -row["score"])]\n',
        {
            "by_name.py": "def ranked(rows):\n"
            '    return [row["name"] for row in sorted(rows, key=lambda row: (-row["score"], row["name"]))]\n',
            "last_at_score.py": "def ranked(rows):\n"
            "    best = {}\n"
            "    for row in rows:\n"
            '        best[row["score"]] = row["name"]\n'
            "    return [best[score] for score in sorted(best, reverse=True)]\n",
        },
        """from rank import ranked

def test_scores():
    rows = [{"name": "a", "score": 1}, {"name": "b", "score": 3}]
    assert ranked(rows) == ["b", "a"]

def test_ties_keep_given_order():
    rows = [
        {"name": "bob", "score": 5},
        {"name": "ann", "score": 5},
        {"name": "cal", "score": 1},
    ]
    assert ranked(rows) == ["bob", "ann", "cal"]
""",
        "Must fail name-tiebreak mutant; ties keep input order.",
    )


def testgen_booking_touch() -> None:
    testgen_task(
        "testgen-booking-touch",
        """`/app/repo/booking.py` implements `overlap(a_start, a_end, b_start, b_end)`.

Times are minutes from midnight. Two bookings overlap if they share an instant.
See the docstring on `overlap` for endpoint rules.

Write unit tests in `/app/repo/tests/test_booking.py`. Do not change `booking.py`. You have 180 seconds.
""",
        "booking",
        "def overlap(a_start, a_end, b_start, b_end):\n"
        '    """True iff the half-open intervals share a point. Touching endpoints do not overlap."""\n'
        "    return a_start < b_end and b_start < a_end\n",
        {
            "inclusive.py": "def overlap(a_start, a_end, b_start, b_end):\n"
            "    return a_start <= b_end and b_start <= a_end\n",
            "closed.py": "def overlap(a_start, a_end, b_start, b_end):\n"
            "    return a_start < b_end and b_start <= a_end\n",
        },
        """from booking import overlap

def test_interior():
    assert overlap(0, 60, 30, 90) is True

def test_touching_not_overlap():
    assert overlap(0, 60, 60, 90) is False
""",
        "Must fail inclusive-end mutants; adjacent slots are free.",
    )


def testgen_zero_qty() -> None:
    testgen_task(
        "testgen-zero-qty",
        """`/app/repo/order.py` implements `line_total(qty, price)`.

`qty` is an int or `None`. Quantity must be a non-negative integer when present.
Missing quantity is an error. Line total is quantity times unit price.
Details are on `line_total`.

Write unit tests in `/app/repo/tests/test_order.py`. Do not change `order.py`. You have 180 seconds.
""",
        "order",
        "def line_total(qty, price):\n"
        '    """None is missing (error). 0 is a valid free sample. Negative is an error."""\n'
        "    if qty is None:\n"
        '        raise ValueError("missing")\n'
        "    if qty < 0:\n"
        '        raise ValueError("negative")\n'
        "    return qty * price\n",
        {
            "truthy.py": "def line_total(qty, price):\n"
            "    if not qty:\n"
            '        raise ValueError("missing")\n'
            "    return qty * price\n",
            "default_one.py": "def line_total(qty, price):\n"
            "    n = qty or 1\n"
            "    if n < 0:\n"
            '        raise ValueError("negative")\n'
            "    return n * price\n",
        },
        """from order import line_total

def test_plain():
    assert line_total(2, 10) == 20

def test_zero_ok():
    assert line_total(0, 10) == 0

def test_missing_errors():
    try:
        line_total(None, 10)
    except ValueError:
        return
    raise AssertionError("expected ValueError")
""",
        "Must fail not-qty and qty-or-1 mutants.",
    )


def repro_task(
    name: str,
    issue: str,
    target: str,
    buggy: str,
    gold: str,
    oracle: str,
    explain: str,
) -> None:
    base = TASKS / name
    write(
        base / "instruction.md",
        f"""{issue}

Write a minimal Python script to `/app/repro.py` that reproduces this failure: it must exit with a non-zero status on the current repository, and exit 0 after the defect is fixed. Do not modify `/app/repo`. You have 180 seconds.
""",
    )
    write(base / "task.toml", toml(name, "issue-reproduction", explain))
    write(base / "environment" / "Dockerfile", DOCKERFILE)
    write(base / "environment" / "repo" / target, buggy)
    write(base / "tests" / "target.txt", target + "\n")
    write(base / "tests" / "gold.py", gold)
    write(base / "tests" / "test_state.py", repro_hidden())
    write(base / "tests" / "test.sh", TEST_SH)
    body = oracle.lstrip()
    if "sys.path.insert" not in body:
        body = "import sys\nsys.path.insert(0, '/app/repo')\n" + body
    write(base / "solution" / "solve.sh", bash_solve(f"cat > /app/repro.py <<'PY'\n{body}\nPY\n"))


def repro_second_export() -> None:
    repro_task(
        "repro-second-export",
        "In `/app/repo`, `export_rows()` should return the full table every time it is called in a process. A second export currently comes back empty.",
        "export.py",
        "_ROWS = iter([{'id': 1}, {'id': 2}])\n\n\ndef export_rows():\n    return list(_ROWS)\n",
        "_ROWS = [{'id': 1}, {'id': 2}]\n\n\ndef export_rows():\n    return list(_ROWS)\n",
        "from export import export_rows\n"
        "first = export_rows()\n"
        "second = export_rows()\n"
        "assert first == [{'id': 1}, {'id': 2}]\n"
        "assert second == first\n",
        "Repro must fail on a consumed iterator and pass after a reusable sequence.",
    )
    write_foils(
        TASKS / "repro-second-export",
        "repro",
        [
            {"id": "once-only", "why": "asserts the first export only"},
            {"id": "internal-iter", "why": "reaches into _ROWS instead of export_rows"},
        ],
    )


def repro_nested_alias() -> None:
    repro_task(
        "repro-nested-alias",
        "In `/app/repo`, attaching the same customer record to two orders must keep the orders independent. Renaming the customer on one order currently changes the other order too.",
        "orders.py",
        "def new_order():\n    return {}\n\n\n"
        "def attach(order, customer):\n    order['customer'] = customer\n\n\n"
        "def rename(order, name):\n    order['customer']['name'] = name\n",
        "def new_order():\n    return {}\n\n\n"
        "def attach(order, customer):\n    order['customer'] = dict(customer)\n\n\n"
        "def rename(order, name):\n    order['customer']['name'] = name\n",
        "from orders import attach, new_order, rename\n"
        "a, b = new_order(), new_order()\n"
        "customer = {'name': 'Ada'}\n"
        "attach(a, customer)\n"
        "attach(b, customer)\n"
        "rename(a, 'Bea')\n"
        "assert b['customer']['name'] == 'Ada'\n",
        "Repro must fail on shared nested dict and pass after attach copies.",
    )
    write_foils(
        TASKS / "repro-nested-alias",
        "repro",
        [
            {"id": "one-order-only", "why": "never attaches the same customer twice"},
            {"id": "mutate-source", "why": "renames the input dict, not via the order API"},
        ],
    )


def repro_stale_quote() -> None:
    repro_task(
        "repro-stale-quote",
        "In `/app/repo`, `quote(sku)` should follow `set_price`. After a price change in the same process, quotes still show the old amount.",
        "quote.py",
        "from functools import lru_cache\n\n"
        "PRICE = {'a': 10}\n\n\n"
        "@lru_cache(maxsize=None)\n"
        "def quote(sku):\n"
        "    return PRICE[sku]\n\n\n"
        "def set_price(sku, amount):\n"
        "    PRICE[sku] = amount\n",
        "PRICE = {'a': 10}\n\n\n"
        "def quote(sku):\n"
        "    return PRICE[sku]\n\n\n"
        "def set_price(sku, amount):\n"
        "    PRICE[sku] = amount\n",
        "from quote import quote, set_price\n"
        "set_price('a', 10)\n"
        "assert quote('a') == 10\n"
        "set_price('a', 12)\n"
        "assert quote('a') == 12\n",
        "Repro must fail on stale cached quote and pass after live lookup.",
    )
    write_foils(
        TASKS / "repro-stale-quote",
        "repro",
        [
            {"id": "read-once", "why": "never calls set_price after the first quote"},
            {"id": "clear-cache-private", "why": "calls quote.cache_clear instead of the public setter path"},
        ],
    )


def review_task(name: str, issue: str, files: dict[str, str], label: str, explain: str) -> None:
    base = TASKS / name
    write(
        base / "instruction.md",
        f"""Issue:
{issue}

The candidate change is already applied in `/app/repo`. Decide whether this repository fully addresses the issue.

Write a single character to `/app/answer.txt`: `1` if it fully addresses the issue, `0` otherwise. You may inspect and run code. Do not change the repository. You have 180 seconds.
""",
    )
    write(base / "task.toml", toml(name, "code-review", explain))
    write(base / "environment" / "Dockerfile", DOCKERFILE)
    for rel, body in files.items():
        write(base / "environment" / "repo" / rel, body)
    copy_normalize(base / "tests" / "normalize.py")
    write(base / "tests" / "label.txt", label + "\n")
    write(base / "tests" / "test_state.py", (Path(__file__).resolve().parent / "templates" / "review_test_state.py").read_text(encoding="utf-8"))
    write(base / "tests" / "test.sh", TEST_SH)
    write(base / "solution" / "solve.sh", bash_solve(f"printf '{label}\\n' > /app/answer.txt\n"))
    write_foils(
        base,
        "review",
        [
            {"id": "flip", "why": "the other bit", "label": "1" if label == "0" else "0"},
            {"id": "example-only", "why": "judges only the stated example"},
        ],
    )


def review_bare_except() -> None:
    review_task(
        "review-bare-except",
        "`parse_count(text)` must return the integer count. Invalid text must raise `ValueError`. Example: `parse_count(\"3\")` equals `3`.",
        {
            "parse.py": "def parse_count(text):\n    try:\n        return int(text)\n    except Exception:\n        return 0\n",
        },
        "0",
        "Example passes; bare except swallows invalid input.",
    )


def review_dead_helper() -> None:
    review_task(
        "review-dead-helper",
        "Member checkout should charge 90% of list price. Example: a $100 member checkout is $90.",
        {
            "discount.py": "def member_total(list_price):\n    return round(list_price * 0.9, 2)\n",
            "checkout.py": "def checkout(list_price):\n    return list_price\n",
        },
        "0",
        "Helper matches the example; live checkout ignores it.",
    )


def review_wired_helper() -> None:
    review_task(
        "review-wired-helper",
        "Member checkout should charge 90% of list price. Example: a $100 member checkout is $90.",
        {
            "discount.py": "def member_total(list_price):\n    return round(list_price * 0.9, 2)\n",
            "checkout.py": "from discount import member_total\n\n\ndef checkout(list_price):\n    return member_total(list_price)\n",
        },
        "1",
        "Live checkout calls the helper.",
    )


def main() -> None:
    loc_vendor_shadow()
    loc_env_wrapper()
    loc_hook_plugin()
    edit_config_beside()
    edit_retry_discount()
    edit_blank_name()
    testgen_tie_order()
    testgen_booking_touch()
    testgen_zero_qty()
    repro_second_export()
    repro_nested_alias()
    repro_stale_quote()
    review_bare_except()
    review_dead_helper()
    review_wired_helper()
    print("wrote Hard-Release-15 under", TASKS)


if __name__ == "__main__":
    main()
