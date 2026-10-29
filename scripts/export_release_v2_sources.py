"""Plan the public RC2 source overlay without copying or publishing anything.

Default: print a read-only plan. --output creates a new JSON file exclusively.
Only this module's explicit resources, candidate provenance and the static local
Python import closure are selected. No selected module is imported or executed.
"""
from __future__ import annotations

import argparse
import ast
from collections import defaultdict
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import tokenize
from io import BytesIO

ROOT = Path(__file__).absolute().parents[1]
BANK = "task-banks/rc2/task-bank-v2.manifest.json"
RELEASE = "analysis/v2/release-20261028"
RESOURCE_FILES = (
    "README.md", "README_EN.md", "CITATION.cff", "LICENSE", "NOTICE",
    ".gitattributes", ".gitignore", "STANDARD-v2.md", "agents/__init__.py",
    "analysis/v2/models.route-ready.json",
    RELEASE + "/ROUTES.md", RELEASE + "/RELEASE-NOTES.md",
    RELEASE + "/PUBLICATION-CHECKLIST.md", RELEASE + "/PUBLIC-EVIDENCE.md",
    RELEASE + "/MONETARY-POLICY-AMENDMENT-20261029.md",
    RELEASE + "/CLOSEOUT-PROTOCOL-20261029.md",
    RELEASE + "/RESULTS-PARTIAL-20261029.md",
    RELEASE + "/SCORES-PARTIAL-20261029.json",
    RELEASE + "/RESULTS-COMPLETE-20261029.md",
    RELEASE + "/SCORES-COMPLETE-20261029.json",
    RELEASE + "/route-catalog.json",
    "analysis/v2/provider-recovery-20261029/PROVIDER-REASSESSMENT.md",
    "analysis/v2/provider-recovery-20261029/CANCELLATION-AUDIT-AMENDMENT.md",
    "analysis/v2/provider-recovery-20261029/PUBLIC-ROUTE-FINDINGS-20261029.md",
    "analysis/v2/provider-recovery-20261029/models.qwen35-primeintellect-bf16.json",
    "analysis/v2/provider-recovery-20261029/openrouter-qwen35-9b-endpoints-20261029T054716Z.json",
    "analysis/v2/provider-recovery-20261029/openrouter-qwen35-9b-model-selection-20261029T054716Z.json",
    "analysis/v2/provider-recovery-20261029/public-route-catalog-audit-20261029T054716Z.json",
)
ENTRY_POINTS = (
    "scripts/release_v2_pipeline.py", "scripts/release_v2_executor.py",
    "scripts/run_release_v2.py", "scripts/analyze_release_v2.py",
    "scripts/build_release_v2_images.py", "scripts/rc2_pipeline.py",
    "scripts/prepare_rc2_candidate.py", "scripts/rc2_task_patches.py",
    "scripts/validate_rc2_containers.py", "scripts/export_release_v2_sources.py",
    "scripts/release_v2_fee_waiver_executor.py", "scripts/resume_release_v2.py",
    "scripts/analyze_release_v2_fee_waiver.py", "scripts/audit_v2_capture_supplement.py",
    "scripts/analyze_release_v2_supplement.py", "scripts/retry_v2_single_infra.py",
    "scripts/provider_reassessment_v2.py", "scripts/provider_reassessment_scoring_v2.py",
    "scripts/resume_provider_cancellation_v2.py", "scripts/provider_cancellation_scoring_v2.py",
)
REGRESSION_TESTS = (
    "scripts/test_release_v2_pipeline.py", "scripts/test_release_v2_glue.py",
    "scripts/test_build_release_v2_images.py", "scripts/test_prepare_rc2_candidate.py",
    "scripts/test_rc2_pipeline.py", "scripts/test_rc2_task_patches.py",
    "scripts/test_validate_rc2_containers.py",
    "scripts/test_export_release_v2_sources.py",
    "scripts/test_release_v2_fee_waiver.py", "scripts/test_audit_v2_capture_supplement.py",
    "scripts/test_analyze_release_v2_supplement.py", "scripts/test_retry_v2_single_infra.py",
    "scripts/test_provider_reassessment_v2.py", "scripts/test_provider_reassessment_scoring_v2.py",
    "scripts/test_resume_provider_cancellation_v2.py", "scripts/test_provider_cancellation_scoring_v2.py",
    "agents/test_artifacts_v2.py", "agents/test_compact_shell_v2.py",
    "agents/test_protocol_v2.py",
)
IGNORED = frozenset({"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"})
FORBIDDEN_TOP = frozenset({"experiments", "jobs", "results", "archives", "artifacts", "trials"})
FORBIDDEN_PARTS = frozenset({".git", ".venv", "venv", "node_modules", ".ssh", ".aws"})
FORBIDDEN_NAMES = frozenset({"credentials", "credentials.json", "id_rsa", "id_ed25519", ".netrc", ".npmrc", ".pypirc"})
EXTERNAL_IMPORTS = frozenset({"harbor", "yaml", "pytest", "litellm", "dirhash"})
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
TASK_ID = re.compile(r"(?:loc|edit|testgen|repro|review)-[a-z0-9]+(?:-[a-z0-9]+)*\Z")
# Deliberately provider-specific: placeholders and variable names are not secrets.
# Findings contain only path, line and kind; matched values never leave memory.
SECRET_PATTERNS = (
    ("private_key", re.compile(rb"-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----")),
    ("openrouter_token", re.compile(rb"\bsk-or-v1-[a-fA-F0-9]{64}\b")),
    ("openai_token", re.compile(rb"\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{32,}\b")),
    ("github_token", re.compile(rb"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{50,})\b")),
    ("aws_access_key_id", re.compile(rb"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    ("google_api_key", re.compile(rb"\bAIza[A-Za-z0-9_-]{35}\b")),
    ("slack_token", re.compile(rb"\bxox[baprs]-[A-Za-z0-9-]{24,}\b")),
)
UNBOUND = object()
WINDOWS_DEVICES = frozenset({"con", "prn", "aux", "nul"}
                            | {prefix + str(number) for prefix in ("com", "lpt") for number in range(1, 10)})


class PlanError(ValueError):
    """A safe, non-content-bearing error code."""


def relative_name(value, *, publication=True):
    if (not isinstance(value, str) or not value or "\\" in value
            or ":" in value or "\0" in value or value.startswith("/")):
        raise PlanError("invalid_relative_path")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise PlanError("invalid_relative_path")
    if any(part.endswith((".", " ")) or part.casefold().split(".", 1)[0] in WINDOWS_DEVICES for part in parts):
        raise PlanError("windows_ambiguous_path")
    lowered = [part.casefold() for part in parts]
    if (lowered[0] in FORBIDDEN_TOP or FORBIDDEN_PARTS.intersection(lowered)
            or FORBIDDEN_NAMES.intersection(lowered)
            or any(part.lower().startswith(".env") for part in parts)):
        raise PlanError("excluded_private_path")
    if publication and lowered[0] == "analysis" and value not in RESOURCE_FILES:
        raise PlanError("analysis_resource_not_allowlisted")
    return PurePosixPath(value).as_posix()


def reject_link(path):
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
        raise PlanError("link_or_reparse_point")
    return info


def check_root(root):
    root = Path(root).absolute()
    for part in (*reversed(root.parents), root):
        folded = part.name.casefold().rstrip(" .")
        if (folded in FORBIDDEN_PARTS | FORBIDDEN_NAMES | IGNORED
                or folded.startswith(".env")):
            raise PlanError("private_root_or_ancestor")
        reject_link(part)
    if not root.is_dir():
        raise PlanError("root_not_directory")
    return root


def checked_path(root, name):
    name = relative_name(name)
    path = root / name
    for parent in (*reversed(path.relative_to(root).parents),):
        if parent != Path("."):
            reject_link(root / parent)
    info = reject_link(path)
    if not path.resolve().is_relative_to(root.resolve()):
        raise PlanError("path_outside_root")
    return path, info


def secret_findings(name, data):
    findings = set()
    for kind, pattern in SECRET_PATTERNS:
        for match in pattern.finditer(data):
            findings.add((data.count(b"\n", 0, match.start()) + 1, kind))
    return [{"path": name, "line": line, "kind": kind} for line, kind in sorted(findings)]


class Selection:
    def __init__(self, root):
        self.root = check_root(root)
        self.data = {}
        self.reasons = defaultdict(set)
        self.errors = []

    def error(self, code, name="<plan>"):
        try:
            name = relative_name(name)
        except PlanError:
            name = "<invalid-relative-path>"
        finding = {"path": name, "kind": code}
        if finding not in self.errors:
            self.errors.append(finding)

    def add(self, name, reason, expected=UNBOUND):
        try:
            name = relative_name(name)
            path, info = checked_path(self.root, name)
            if not stat.S_ISREG(info.st_mode):
                raise PlanError("not_regular_file")
            data = path.read_bytes()
            if info.st_size != len(data) or path.stat().st_mtime_ns != info.st_mtime_ns:
                raise PlanError("file_changed_during_read")
            if name in self.data and self.data[name] != data:
                raise PlanError("file_changed_during_plan")
            if expected is not UNBOUND and (not isinstance(expected, str)
                    or not SHA256.fullmatch(expected)
                    or hashlib.sha256(data).hexdigest() != expected):
                raise PlanError("frozen_source_hash_mismatch")
            self.data[name] = data
            self.reasons[name].add(reason)
            return data
        except (OSError, PlanError) as error:
            self.error(str(error) if isinstance(error, PlanError) else "missing_or_unreadable_file", name)
            return None

    def tree(self, name, reason):
        try:
            path, info = checked_path(self.root, name)
            if not stat.S_ISDIR(info.st_mode):
                raise PlanError("not_directory")
            # scandir does not follow links; validate each entry before filtering.
            entries = sorted(os.scandir(path), key=lambda entry: entry.name)
            for entry in entries:
                child = name + "/" + entry.name
                entry_info = reject_link(Path(entry.path))
                if entry.name in IGNORED or Path(entry.name).suffix in {".pyc", ".pyo"}:
                    continue
                if stat.S_ISDIR(entry_info.st_mode):
                    self.tree(child, reason)
                elif stat.S_ISREG(entry_info.st_mode):
                    self.add(child, reason)
                else:
                    self.error("not_regular_file", child)
        except (OSError, PlanError) as error:
            self.error(str(error) if isinstance(error, PlanError) else "missing_or_unreadable_directory", name)

    def document(self, name, reason):
        data = self.add(name, reason)
        if data is None:
            return None
        try:
            def unique_pairs(pairs):
                result = {}
                for key, value in pairs:
                    if key in result:
                        raise ValueError("duplicate key")
                    result[key] = value
                return result
            def reject_constant(_):
                raise ValueError("nonfinite JSON")
            return json.loads(data, object_pairs_hook=unique_pairs, parse_constant=reject_constant)
        except (ValueError, UnicodeError):
            self.error("invalid_json_document", name)
            return None


def task_digest(selection, prefix):
    result = hashlib.sha256()
    # Match the frozen validator's sorted(Path.rglob(...)) ordering exactly.
    # The per-file raw hashes in the plan do not depend on this legacy ordering.
    for name, data in sorted(selection.data.items(), key=lambda row: Path(row[0])):
        if not name.startswith(prefix + "/"):
            continue
        result.update(name[len(prefix) + 1:].encode("utf-8") + b"\0")
        try:
            if b"\0" not in data:
                data = data.decode("utf-8").replace("\r\n", "\n").encode("utf-8")
        except UnicodeDecodeError:
            pass
        result.update(data + b"\0")
    return result.hexdigest()


def select_candidate(selection):
    bank = selection.document(BANK, "candidate_manifest")
    if not isinstance(bank, dict):
        selection.error("missing_candidate_manifest", BANK)
        return []
    body = {key: value for key, value in bank.items() if key != "manifest_sha256"}
    digest = hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    if bank.get("manifest_sha256") != digest:
        selection.error("candidate_manifest_self_hash_mismatch", BANK)
    items = bank.get("items")
    if (bank.get("task_count") != 62 or not isinstance(items, list) or len(items) != 62
            or any(not isinstance(item, dict) or not isinstance(item.get("id"), str)
                   or not TASK_ID.fullmatch(item["id"]) for item in items)):
        selection.error("candidate_must_declare_62_unique_tasks", BANK)
        return []
    ids = [item["id"] for item in items]
    if len(set(ids)) != 62:
        selection.error("candidate_must_declare_62_unique_tasks", BANK)
        return []
    selection.add("task-banks/rc2/VERSION", "candidate_version")
    for item in items:
        prefix = "task-banks/rc2/tasks/" + item["id"]
        selection.tree(prefix, "candidate_task")
        if task_digest(selection, prefix) != item.get("task_sha256"):
            selection.error("candidate_task_hash_mismatch", prefix)
    hashes = bank.get("protected_source_hashes")
    builders = bank.get("builder_sources")
    if not isinstance(hashes, dict) or not hashes or not isinstance(builders, dict) or not builders:
        selection.error("missing_frozen_source_dependencies", BANK)
        return ids
    for reason, mapping in (("protected_source", hashes), ("candidate_builder", builders)):
        for name, expected in sorted(mapping.items()):
            if (not isinstance(name, str) or not (
                    name in {"VERSION", "task-bank-v2.manifest.json"}
                    or name.startswith(("scripts/", "agents/")) and name.endswith(".py")
                    or any(name.startswith("tasks/" + task + "/") for task in ids))):
                selection.error("unexpected_frozen_dependency", name)
                continue
            selection.add(name, reason, expected)
    # The original full task trees are needed by validate_candidate's tree hash.
    for task in ids:
        selection.tree("tasks/" + task, "protected_task_tree")
    selected_original = {name for name in selection.data if name.startswith("tasks/")}
    expected_original = {name for name in hashes if name.startswith("tasks/")}
    if selected_original != expected_original:
        selection.error("protected_task_tree_file_set_mismatch", BANK)
    source = bank.get("source_rc1_manifest", {})
    if not isinstance(source, dict) or source.get("path") != "task-bank-v2.manifest.json":
        selection.error("invalid_source_manifest_binding", BANK)
    else:
        selection.add(source["path"], "source_manifest", source.get("sha256", ""))
    return ids


def module_candidates(module):
    parts = module.split(".")
    if parts[0] in {"scripts", "agents"}:
        stem = "/".join(parts)
        return [stem + ".py", stem + "/__init__.py"]
    stem = "/".join(parts)
    return ["scripts/" + stem + ".py", "scripts/" + stem + "/__init__.py",
            "agents/" + stem + ".py", "agents/" + stem + "/__init__.py"]


def local_module_file(selection, candidates, importer):
    for candidate in candidates:
        try:
            _, info = checked_path(selection.root, candidate)
            if stat.S_ISREG(info.st_mode):
                return candidate
        except FileNotFoundError:
            continue
        except (OSError, PlanError) as error:
            selection.error(str(error) if isinstance(error, PlanError) else "unreadable_local_import", importer)
    return None


def select_import_closure(selection):
    processed = set()
    while True:
        pending = sorted(name for name in selection.data if name.startswith(("scripts/", "agents/"))
                         and name.endswith(".py") and name not in processed)
        if not pending:
            break
        for name in pending:
            processed.add(name)
            try:
                data = selection.data[name]
                encoding, _ = tokenize.detect_encoding(BytesIO(data).readline)
                tree = ast.parse(data.decode(encoding), filename=name)
            except (SyntaxError, UnicodeError, LookupError):
                selection.error("invalid_python_source", name)
                continue
            imports = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.extend((alias.name, True) for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    if node.level:
                        parent = name.split("/")[:-1]
                        if node.level > len(parent):
                            selection.error("relative_import_outside_package", name)
                            continue
                        base = parent[:len(parent) - node.level + 1]
                        module = ".".join(base + ([node.module] if node.module else []))
                    else:
                        module = node.module or ""
                    imports.append((module, True))
                    # from package import submodule also binds the package init.
                    imports.extend((module + "." + alias.name, False) for alias in node.names if alias.name != "*")
            for module, required in imports:
                candidates = module_candidates(module)
                found = local_module_file(selection, candidates, name)
                if found:
                    selection.add(found, "static_import:" + name)
                    parts = found.split("/")[:-1]
                    for count in range(1, len(parts) + 1):
                        init = "/".join(parts[:count]) + "/__init__.py"
                        if local_module_file(selection, [init], name):
                            selection.add(init, "package_initializer")
                elif required and module.split(".")[0] in {"agents", "scripts"}:
                    try:
                        _, info = checked_path(selection.root, module.replace(".", "/"))
                        if not stat.S_ISDIR(info.st_mode):
                            raise PlanError("missing_local_import")
                    except (OSError, PlanError):
                        selection.error("missing_local_import", name)
                elif required and module.split(".")[0] not in sys.stdlib_module_names | EXTERNAL_IMPORTS:
                    selection.error("unresolved_import:" + module, name)
    return sorted(processed)


def tracked_task_deletions(selection, ids):
    """Read only the old task index entries; never change the user's index."""
    if len(ids) != 62:
        return []
    try:
        result = subprocess.run(
            ["git", "--no-optional-locks", "ls-files", "-z", "--", *["tasks/" + task + "/" for task in ids]],
            cwd=selection.root, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False,
        )
    except OSError:
        selection.error("git_task_index_unavailable")
        return []
    if result.returncode:
        selection.error("git_task_index_unavailable")
        return []
    deletions = []
    for raw in result.stdout.split(b"\0"):
        if not raw:
            continue
        try:
            name = relative_name(raw.decode("utf-8"))
            if name not in selection.data and not (selection.root / name).exists():
                deletions.append(name)
        except (PlanError, UnicodeError):
            selection.error("invalid_tracked_task_path")
    return sorted(set(deletions))


def build_plan(root=ROOT, *, include_git=True):
    selection = Selection(root)
    ids = select_candidate(selection)
    for name in RESOURCE_FILES:
        selection.add(name, "explicit_public_resource")
    for name in ENTRY_POINTS:
        selection.add(name, "release_entry_point")
    for name in REGRESSION_TESTS:
        selection.add(name, "release_regression_test")
    selection.tree("vendor/harbor-patches", "licensed_runtime_patch")
    closure = select_import_closure(selection)
    deletions = tracked_task_deletions(selection, ids) if include_git else []
    secrets = [finding for name, data in sorted(selection.data.items())
               for finding in secret_findings(name, data)]
    files = [{"path": name, "size_bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
              "reasons": sorted(selection.reasons[name])}
             for name, data in sorted(selection.data.items())]
    return {
        "schema_version": 1, "kind": "smallowbench_rc2_public_source_overlay_plan",
        "status": "blocked" if selection.errors or secrets else "ready",
        "dry_run": True, "source_bytes_policy": "exact bytes; no newline or encoding conversion",
        "candidate_manifest": BANK, "task_count": len(ids), "files": files,
        "file_count": len(files), "total_size_bytes": sum(row["size_bytes"] for row in files),
        "static_python_closure": closure, "overlay_deletions": deletions,
        "errors": sorted(selection.errors, key=lambda row: (row["path"], row["kind"])),
        "secret_findings": secrets,
        "compatibility_warnings": [{
            "kind": "legacy_task_digest_path_sorting",
            "paths": ["scripts/validate_upgraded_tasks.py", BANK],
            "detail": "Frozen task digests use sorted(Path.rglob). Windows and POSIX order mixed-case names differently. This plan uses the local validator order and preserves all source bytes; raw per-file SHA-256 values are independent of that ordering. Frozen digests are not rewritten.",
        }],
        "removal_policy": {
            "apply_only_listed_files_and_overlay_deletions": True,
            "unlisted_base_files": "retain only after separate base-tree review; this plan does not approve inherited files",
            "private_existing_products": "omit from public source tree and attachments; preserve local originals",
            "excluded_top_level": sorted(FORBIDDEN_TOP),
            "excluded_runtime_and_credentials": sorted(FORBIDDEN_PARTS | FORBIDDEN_NAMES | IGNORED) + [".env*", "*.pyc", "*.pyo", "raw traces", "Docker inventories", "absolute-path runtime reports"],
            "raw_runtime_evidence": "excluded; new installations must generate their own evidence",
            "scores": "no formal results are created or inferred by this source plan",
            "schemas": "submission schema constants in pipelines; task.toml and grader resources in complete task trees",
            "secret_scan_scope": "only selected publication files; high-confidence provider tokens and private-key markers",
            "git_task_index_checked": include_git,
        },
    }


def write_plan(root, output, plan):
    output = Path(output)
    root = check_root(root)
    if output.is_absolute():
        try:
            name = output.absolute().relative_to(root).as_posix()
        except ValueError as error:
            raise PlanError("output_outside_root") from error
    else:
        name = output.as_posix()
    # Output is local audit material, never implicitly an allowlisted resource.
    name = relative_name(name, publication=False)
    destination = root / name
    for part in (*reversed(destination.parent.parents), destination.parent):
        if not part.is_relative_to(root):
            continue
        reject_link(part)
    if destination.exists() or destination.is_symlink():
        raise PlanError("output_already_exists")
    with destination.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(plan, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT, help="source repository (read-only)")
    parser.add_argument("--output", type=Path, help="create a new local plan JSON; never overwrite")
    args = parser.parse_args(argv)
    try:
        plan = build_plan(args.root)
        if args.output is not None:
            write_plan(args.root, args.output, plan)
        else:
            print(json.dumps(plan, ensure_ascii=False, indent=2, allow_nan=False))
        return 2 if plan["status"] == "blocked" else 0
    except (OSError, PlanError) as error:
        # Never expose OS error strings: they can contain host paths or content.
        code = str(error) if isinstance(error, PlanError) else "filesystem_error"
        print(json.dumps({"status": "blocked", "errors": [{"kind": code}]}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
