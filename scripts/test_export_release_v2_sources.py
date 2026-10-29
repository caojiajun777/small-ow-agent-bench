"""Static publication plans: exact provenance, a bounded closure and no secrets."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

import pytest

import export_release_v2_sources as export


def put(root, name, data=b"public\n"):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def freeze(bank):
    bank.pop("manifest_sha256", None)
    bank["manifest_sha256"] = hashlib.sha256(
        json.dumps(bank, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    return bank


@pytest.fixture
def source(tmp_path):
    for name in export.RESOURCE_FILES:
        put(tmp_path, name)
    for name in (*export.ENTRY_POINTS, *export.REGRESSION_TESTS):
        put(tmp_path, name, b"# explicit source\n")
    put(tmp_path, "vendor/harbor-patches/README.md")
    put(tmp_path, "vendor/harbor-patches/HARBOR-LICENSE")
    put(tmp_path, "vendor/harbor-patches/runtime.patch")
    put(tmp_path, "VERSION", b"2.0.0-rc.1\n")
    original = put(tmp_path, "task-bank-v2.manifest.json", b"{}\n")
    put(tmp_path, "task-banks/rc2/VERSION", b"2.0.0-rc.2\n")
    items = []
    protected = {name: hashlib.sha256((tmp_path / name).read_bytes()).hexdigest()
                 for name in ("VERSION", "task-bank-v2.manifest.json")}
    for index in range(62):
        task = "edit-case-" + str(index)
        old = "tasks/" + task + "/task.toml"
        data = b"version = '2'\r\n"
        put(tmp_path, old, data)
        protected[old] = hashlib.sha256(data).hexdigest()
        put(tmp_path, "task-banks/rc2/tasks/" + task + "/task.toml", data)
        digest = hashlib.sha256(b"task.toml\0" + data.replace(b"\r\n", b"\n") + b"\0").hexdigest()
        items.append({"id": task, "task_sha256": digest})
    bank = freeze({
        "task_count": 62, "items": items, "protected_source_hashes": protected,
        "builder_sources": {"scripts/prepare_rc2_candidate.py": hashlib.sha256(
            (tmp_path / "scripts/prepare_rc2_candidate.py").read_bytes()).hexdigest()},
        "source_rc1_manifest": {"path": "task-bank-v2.manifest.json", "sha256": hashlib.sha256(original.read_bytes()).hexdigest()},
    })
    put(tmp_path, export.BANK, (json.dumps(bank) + "\n").encode())
    return tmp_path


def plan(root):
    return export.build_plan(root, include_git=False)


def paths(value):
    return {row["path"] for row in value["files"]}


def rewrite_bank(root, change):
    bank = json.loads((root / export.BANK).read_bytes())
    change(bank)
    put(root, export.BANK, json.dumps(freeze(bank)).encode())


def test_exact_bytes_and_complete_two_bank_sources(source):
    value = plan(source)
    assert value["status"] == "ready", value["errors"]
    assert value["task_count"] == 62
    assert sum(name.startswith("tasks/") for name in paths(value)) == 62
    assert sum(name.startswith("task-banks/rc2/tasks/") for name in paths(value)) == 62
    row = next(row for row in value["files"] if row["path"] == "tasks/edit-case-0/task.toml")
    original = (source / row["path"]).read_bytes()
    assert row["sha256"] == hashlib.sha256(original).hexdigest()
    assert row["size_bytes"] == len(original)
    assert b"\r\n" in original
    assert str(source) not in json.dumps(value)


def test_ast_closure_recurses_local_modules_and_package_initializers(source):
    put(source, "scripts/run_release_v2.py", b"import only_local\nfrom agents import extra\nimport harbor.fake_external\n")
    put(source, "scripts/only_local.py", b"from scripts.nested import helper\n")
    put(source, "scripts/nested.py", b"helper = 1\n")
    put(source, "agents/extra.py", b"from . import protocol\n")
    put(source, "agents/protocol.py", b"import json\n")
    put(source, "scripts/unrelated.py", b"raise RuntimeError('must not import')\n")
    value = plan(source)
    assert value["status"] == "ready", value["errors"]
    assert {"scripts/only_local.py", "scripts/nested.py", "agents/extra.py",
            "agents/protocol.py", "agents/__init__.py"} <= paths(value)
    assert "scripts/unrelated.py" not in paths(value)


@pytest.mark.parametrize("statement", [b"from scripts.missing import value\n", b"import missing_local\n",
                                      b"import missing_local.submodule\n", b"from missing_local.submodule import value\n"])
def test_missing_local_dependency_blocks(source, statement):
    put(source, "scripts/run_release_v2.py", statement)
    assert plan(source)["status"] == "blocked"


def test_protected_source_drift_and_omission_block(source):
    put(source, "tasks/edit-case-0/task.toml", b"changed\n")
    (source / "tasks/edit-case-1/task.toml").unlink()
    value = plan(source)
    assert value["status"] == "blocked"
    assert {"frozen_source_hash_mismatch", "missing_or_unreadable_file"} <= {row["kind"] for row in value["errors"]}


def test_candidate_task_drift_blocks(source):
    put(source, "task-banks/rc2/tasks/edit-case-0/task.toml", b"changed\n")
    assert any(row["kind"] == "candidate_task_hash_mismatch" for row in plan(source)["errors"])


def test_invalid_manifest_and_undeclared_original_task_file_block(source):
    put(source, "tasks/edit-case-0/extra.py", b"pass\n")
    value = plan(source)
    assert value["status"] == "blocked"
    assert any(row["kind"] == "protected_task_tree_file_set_mismatch" for row in value["errors"])
    rewrite_bank(source, lambda bank: bank.update(task_count=61))
    assert any(row["kind"] == "candidate_must_declare_62_unique_tasks" for row in plan(source)["errors"])


def test_excluded_products_are_never_read_or_selected(source, monkeypatch):
    private = {".env", "experiments/private.json", "analysis/v2/runtime.json", "archives/source.zip", ".git/index",
               export.RELEASE + "/CONTINUATION-MEMO-20261029.md",
               export.RELEASE + "/capture-runtime-report.json"}
    for name in private:
        put(source, name, b"private contents\n")
    old_read = Path.read_bytes

    def guarded_read(path):
        assert path.relative_to(source).as_posix() not in private
        return old_read(path)

    monkeypatch.setattr(Path, "read_bytes", guarded_read)
    value = plan(source)
    assert value["status"] == "ready"
    assert not private.intersection(paths(value))


@pytest.mark.parametrize("malicious", ["../outside.py", "X:/outside.py", "scripts/../../.env", "experiments/private.json"])
def test_manifest_cannot_expand_to_private_or_outside_paths(source, malicious):
    rewrite_bank(source, lambda bank: bank["protected_source_hashes"].update({malicious: "a" * 64}))
    value = plan(source)
    assert value["status"] == "blocked"
    assert malicious not in paths(value)


def test_secret_findings_only_report_location_and_kind(source):
    token = "sk-" + "proj-" + "abcdef0123456789" * 4
    put(source, "README.md", ("safe line\n" + token + "\n").encode())
    value = plan(source)
    assert value["status"] == "blocked"
    assert value["secret_findings"] == [{"path": "README.md", "line": 2, "kind": "openai_token"}]
    assert token not in json.dumps(value)


def test_private_key_marker_and_placeholder_policy():
    marker = b"-----BEGIN " + b"PRIVATE KEY-----"
    assert export.secret_findings("test.py", marker)[0]["kind"] == "private_key"
    assert export.secret_findings("test.py", b"api_key = os.environ['API_KEY']; token = 'YOUR_KEY'") == []


def test_reparse_and_symlink_are_rejected_without_reading(source, monkeypatch):
    original = Path.lstat
    target = source / "README.md"

    class ReparseStat:
        st_mode = 0o100644
        st_file_attributes = 0x400

    monkeypatch.setattr(Path, "lstat", lambda path: ReparseStat() if path == target else original(path))
    value = plan(source)
    assert any(row == {"path": "README.md", "kind": "link_or_reparse_point"} for row in value["errors"])


def test_symlink_directory_is_blocked(source):
    link = source / "vendor/harbor-patches/link"
    try:
        link.symlink_to(source / "scripts", target_is_directory=True)
    except OSError:
        pytest.skip("symlinks require platform support")
    assert any(row["kind"] == "link_or_reparse_point" for row in plan(source)["errors"])


def test_overlay_deletions_only_read_task_index(source, monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        assert kwargs["cwd"] == source
        return subprocess.CompletedProcess(command, 0, b"tasks/edit-case-0/deleted.py\0tasks/edit-case-0/task.toml\0")

    monkeypatch.setattr(subprocess, "run", fake_run)
    value = export.build_plan(source)
    assert value["overlay_deletions"] == ["tasks/edit-case-0/deleted.py"]
    assert calls[0][:5] == ["git", "--no-optional-locks", "ls-files", "-z", "--"]
    assert not (source / "tasks/edit-case-0/deleted.py").exists()


def test_default_cli_dry_run_and_explicit_output_never_overwrites(source, monkeypatch, capsys):
    value = plan(source)
    monkeypatch.setattr(export, "build_plan", lambda root: value)
    before = set(source.rglob("*"))
    assert export.main(["--root", str(source)]) == 0
    assert json.loads(capsys.readouterr().out)["dry_run"] is True
    assert before == set(source.rglob("*"))
    output = source / "publication-plan.json"
    assert export.main(["--root", str(source), "--output", str(output)]) == 0
    expected = output.read_bytes()
    assert export.main(["--root", str(source), "--output", str(output)]) == 2
    assert output.read_bytes() == expected
    assert "output_already_exists" in capsys.readouterr().out


def test_output_cannot_escape_or_enter_private_directories(source):
    with pytest.raises(export.PlanError):
        export.write_plan(source, "../escaped.json", {})
    with pytest.raises(export.PlanError):
        export.write_plan(source, source.parent / "escaped.json", {})
    with pytest.raises(export.PlanError):
        export.write_plan(source, ".env.output", {})


@pytest.mark.parametrize("name", [".GIT/new.json", ".git./new.json", ".git /new.json", "NUL.json", "COM1.json", "sub/.ENV.json"])
def test_windows_private_aliases_and_device_names_are_rejected(source, name):
    with pytest.raises(export.PlanError):
        export.write_plan(source, name, {})
    with pytest.raises(export.PlanError):
        export.relative_name(name)


@pytest.mark.parametrize("items", [None, [None] * 62, [{"id": []}] * 62,
                                  [{"id": "edit-case-" + str(index)} for index in range(62)] + [None]])
def test_malformed_candidate_items_block_without_exception(source, items):
    rewrite_bank(source, lambda bank: bank.update(items=items))
    assert plan(source)["status"] == "blocked"


def test_missing_frozen_hash_blocks(source):
    rewrite_bank(source, lambda bank: bank["protected_source_hashes"].update({"VERSION": None}))
    assert any(row["kind"] == "frozen_source_hash_mismatch" for row in plan(source)["errors"])


def test_task_digest_matches_frozen_validator_path_order(source):
    selection = export.Selection(source)
    put(source, "tasks/edit-case-0/README.md", b"README\n")
    put(source, "tasks/edit-case-0/another.txt", b"another\n")
    prefix = "tasks/edit-case-0"
    selection.tree(prefix, "test")
    expected = hashlib.sha256()
    for path in sorted((source / prefix).rglob("*")):
        if path.is_file():
            data = path.read_bytes().replace(b"\r\n", b"\n")
            expected.update(path.relative_to(source / prefix).as_posix().encode() + b"\0" + data + b"\0")
    assert export.task_digest(selection, prefix) == expected.hexdigest()


def test_root_cannot_be_inside_git_metadata(source):
    hidden = source / ".git"
    hidden.mkdir()
    with pytest.raises(export.PlanError, match="private_root_or_ancestor"):
        export.write_plan(hidden, "new.json", {})
    assert not (hidden / "new.json").exists()


def test_scripts_namespace_package_imports_are_supported(source):
    put(source, "scripts/run_release_v2.py", b"from scripts import release_v2_executor\n")
    value = plan(source)
    assert value["status"] == "ready", value["errors"]
