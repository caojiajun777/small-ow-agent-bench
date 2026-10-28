"""Bounded host-only route probes, not benchmark trials or stability guarantees.

Each request is exactly one non-streaming POST, without automatic retries or
redirects. No model-produced shell is executed. Old experiments remain STOP;
their unknown charges are retained in the same aggregate budget envelope.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import sqlite3
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.protocol_v2 import parse_action
from ledger_io import process_lock, write_atomic
from v2_pipeline import ROOT, V2Error, bound_file, digest, file_hash, read_json
from v2_routes import config_for_candidate

PROBE_SOURCES = ("scripts/route_probe_v2.py", "scripts/v2_routes.py",
                 "scripts/v2_pipeline.py", "scripts/ledger_io.py", "agents/protocol_v2.py")
REQUEST_RESERVE = 0.06
PRICE_CAP = {"prompt": 2, "completion": 5, "request": 0}
PROMPT = ("Host-side connectivity/parameter probe. No code will be executed. "
          "Respond with exactly one standalone empty finish fence, without prose:\n"
          "```finish\n```\nProbe number: ")


def now():
    return datetime.now(timezone.utc).isoformat()


def money(value):
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value) and value >= 0


def source_bindings(root=ROOT):
    return {name: file_hash(Path(root) / name) for name in PROBE_SOURCES}


def _parent_identity(row):
    return row.get("manifest", row.get("plan"))["sha256"]


def _envelope_path(root, parents):
    key = digest(sorted(_parent_identity(row) for row in parents))
    return Path(root) / "experiments/smallowbench-v2" / ("route-envelope-" + key[:16] + ".json")


def _parent_rows(paths, seen=None):
    # Share the set across siblings: two parents covering the same ancestor
    # would double-count/respend the same envelope even without a graph cycle.
    seen = set() if seen is None else seen
    return [parent_budget(path, _seen=seen) for path in paths]


def parent_budget(directory, *, _seen=None):
    directory = Path(directory).resolve()
    seen = set() if _seen is None else _seen
    if str(directory) in seen:
        raise V2Error("duplicate budget ancestor or cyclic parent chain")
    seen.add(str(directory))
    if not (directory / "STOP").is_file():
        raise V2Error("historical budget parent must remain STOP")
    if (directory / "plan.json").is_file():
        return _completed_probe_budget(directory, seen)
    manifest = read_json(directory / "manifest.json")
    database = directory / "claims.sqlite3"
    with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as connection:
        stored = connection.execute("SELECT value FROM metadata WHERE key='manifest_sha256'").fetchone()
        visits = connection.execute("SELECT status,charged_usd,reserved_usd FROM visits").fetchall()
    if (stored is None or stored[0] != manifest["manifest_sha256"]
            or any(status not in {"scored", "infra", "aborted"}
                   or not money(reserved) or charged is not None and not money(charged)
                   for status, charged, reserved in visits)):
        raise V2Error("historical parent has unresolved or mismatched budget evidence")
    committed = sum(reserved if charged is None else charged for _, charged, reserved in visits)
    if not money(committed):
        raise V2Error("historical parent has unresolved or mismatched budget evidence")
    return {"directory": str(directory), "manifest": bound_file(directory / "manifest.json"),
            "database": bound_file(database), "committed_usd": committed}


def _validate_audit(audit):
    if audit.get("kind") != "public_route_catalog_audit" or audit.get("report_sha256") != digest(
        {k: v for k, v in audit.items() if k != "report_sha256"}
    ):
        raise V2Error("catalog audit identity/digest mismatch")


def _model_plan(audit, selected_models=None, reasoning_off_style="enabled-false"):
    _validate_audit(audit)
    if reasoning_off_style not in ("enabled-false", "effort-none"):
        raise V2Error("unsupported reasoning-off style")
    names = [row["model"] for row in audit["rows"]]
    if len(set(names)) != len(names):
        raise V2Error("duplicate model in catalog audit")
    if selected_models is not None and (
        not isinstance(selected_models, list) or not selected_models
        or len(set(selected_models)) != len(selected_models)
        or not set(selected_models).issubset(names)
    ):
        raise V2Error("selected models must be a nonempty unique subset of the saved audit")
    result = []
    for row in audit["rows"]:
        if selected_models is not None and row["model"] not in selected_models:
            continue
        if reasoning_off_style == "effort-none" and (
            row.get("family") != "qwen" or not row.get("runtime_id", "").startswith("openrouter/qwen/")
        ):
            raise V2Error("effort-none is restricted to Qwen candidates")
        candidates = [c for c in row["candidates"] if c.get("eligible")]
        selected = row.get("selected")
        if selected is None:
            result.append({"model": row["model"], "catalog_status": row["status"], "candidates": []})
            continue
        candidates = [selected] + [c for c in candidates if c["route"] != selected["route"]]
        configs = []
        for candidate in candidates[:2]:
            config = config_for_candidate(row, candidate)
            if reasoning_off_style == "effort-none":
                config["agent_kwargs"]["llm_call_kwargs"]["extra_body"]["reasoning"] = {"effort": "none"}
            configs.append({"endpoint": candidate, "config": config})
        result.append({"model": row["model"], "catalog_status": row["status"], "candidates": configs})
    return result


def _request_cap(models, selected_models):
    return 60 if selected_models is None else min(60, 3 * sum(len(row["candidates"]) for row in models))


def prepare(directory, audit_path, parents, *, aggregate_cap=4, root=ROOT,
            models=None, reasoning_off_style="enabled-false"):
    directory, root = Path(directory).resolve(), Path(root).resolve()
    if directory.parent != root / "experiments/smallowbench-v2" or directory.exists():
        raise V2Error("probe preparation requires a NEW v2 experiment directory")
    if not money(aggregate_cap) or not 0 < aggregate_cap <= 4:
        raise V2Error("positive aggregate budget no greater than the original US$4 required")
    audit = read_json(audit_path)
    model_rows = _model_plan(audit, models, reasoning_off_style)
    parent_rows = _parent_rows(parents)
    if not parent_rows:
        raise V2Error("at least one historical budget parent is required")
    committed = sum(row["committed_usd"] for row in parent_rows)
    if committed + REQUEST_RESERVE > aggregate_cap:
        raise V2Error("no residual budget for a single route probe")
    plan = {"schema_version": 1, "kind": "smallowbench_route_probe", "directory": str(directory),
            "created_at": now(), "audit": bound_file(audit_path), "source_hashes": source_bindings(root),
            "parents": parent_rows, "historical_committed_usd": committed,
            "aggregate_cap_usd": aggregate_cap, "residual_cap_usd": aggregate_cap - committed,
            "request_reserve_usd": REQUEST_RESERVE, "max_requests": _request_cap(model_rows, models),
            "max_candidates_per_model": 2, "responses_per_candidate": 3,
            "http_timeout_seconds": 45, "http_retries": 0,
            "max_price": PRICE_CAP, "models": model_rows,
            "selected_models": models, "reasoning_off_style": reasoning_off_style,
            "not_benchmark_trial": True, "formal_ranking_eligible": False,
            "stability_certified": False}
    plan["plan_sha256"] = digest(plan)
    return plan


def _validate_plan_document(plan, directory, *, root=None):
    selected = plan.get("selected_models")
    style = plan.get("reasoning_off_style", "enabled-false")
    if (plan.get("plan_sha256") != digest({k: v for k, v in plan.items() if k != "plan_sha256"})
            or plan.get("kind") != "smallowbench_route_probe" or plan.get("directory") != str(directory)
            or root is not None and plan.get("source_hashes") != source_bindings(root)
            or plan.get("request_reserve_usd") != REQUEST_RESERVE or plan.get("max_price") != PRICE_CAP
            or plan.get("http_retries") != 0
            or plan.get("responses_per_candidate") != 3 or plan.get("max_candidates_per_model") != 2
            or plan.get("http_timeout_seconds") != 45
            or not money(plan.get("aggregate_cap_usd")) or not 0 < plan["aggregate_cap_usd"] <= 4):
        raise V2Error("route probe plan/source drifted")
    if bound_file(plan["audit"]["path"]) != plan["audit"]:
        raise V2Error("catalog evidence drifted")
    expected = _model_plan(read_json(plan["audit"]["path"]), selected, style)
    if plan.get("models") != expected or plan.get("max_requests") != _request_cap(expected, selected):
        raise V2Error("frozen model selection, parameter style or audit-derived config drifted")


def validate_plan(directory, *, root=ROOT):
    directory = Path(directory).resolve()
    plan = read_json(directory / "plan.json")
    _validate_plan_document(plan, directory, root=root)
    current_parents = _parent_rows(row["directory"] for row in plan["parents"])
    if current_parents != plan["parents"]:
        raise V2Error("historical budget evidence changed; do not double allocate")
    committed = sum(row["committed_usd"] for row in current_parents)
    if (plan["historical_committed_usd"] != committed
            or plan["residual_cap_usd"] != plan["aggregate_cap_usd"] - committed):
        raise V2Error("historical aggregate budget arithmetic differs")
    approval = read_json(directory / "authorization.json")
    if (approval.get("approved_by_user") is not True
            or approval.get("plan_sha256") != plan["plan_sha256"]
            or approval.get("aggregate_cap_usd") != plan["aggregate_cap_usd"]):
        raise V2Error("explicit all-model probe authorization absent or mismatched")
    return plan


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def post_once(body, key, timeout):
    request = Request("https://openrouter.ai/api/v1/chat/completions",
                      data=json.dumps(body).encode("utf-8"), method="POST",
                      headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    started = time.monotonic()
    try:
        with build_opener(NoRedirect()).open(request, timeout=timeout) as response:
            text = response.read(4_194_305).decode("utf-8", errors="replace")
            status, retry_after = response.status, response.headers.get("Retry-After")
    except HTTPError as exc:
        text = exc.read(4_194_305).decode("utf-8", errors="replace")
        status, retry_after = exc.code, exc.headers.get("Retry-After")
    except (URLError, TimeoutError, OSError) as exc:
        return {"http_status": None, "error_type": type(exc).__name__,
                "elapsed_seconds": time.monotonic() - started, "body": None}
    # Credential values and account IDs are never needed as probe evidence.
    text = text.replace(key, "[REDACTED]")
    try:
        value = json.loads(text)
    except ValueError:
        value = {"unparseable_response": text[:4000]}
    if isinstance(value, dict):
        value.pop("user_id", None)
        if isinstance(value.get("error"), dict):
            value["error"].pop("user_id", None)
    return {"http_status": status, "retry_after": retry_after,
            "elapsed_seconds": time.monotonic() - started, "body": value}


def classify_response(response, expected_provider=None, thinking_off=False, expected_model=None):
    body = response.get("body")
    body = body if isinstance(body, dict) else {}
    choices = body.get("choices")
    choice = choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], dict) else {}
    message = choice.get("message")
    message = message if isinstance(message, dict) else {}
    content = message.get("content")
    usage = body.get("usage")
    usage = usage if isinstance(usage, dict) else {}
    cost = usage.get("cost")
    details = usage.get("completion_tokens_details")
    details = details if isinstance(details, dict) else {}
    reasoning_tokens = details.get("reasoning_tokens")
    success = (response.get("http_status") == 200 and isinstance(body, dict)
               and not body.get("error") and isinstance(choice.get("message"), dict)
               and choice.get("finish_reason") not in (None, "error"))
    provider = body.get("provider")
    response_model = body.get("model")
    provider_matches = (isinstance(provider, str) and bool(provider)
                        and (expected_provider is None or
                             provider.lower().replace(" ", "") == expected_provider.lower().replace(" ", "")))
    model_matches = (isinstance(response_model, str) and bool(response_model)
                     and (expected_model is None or response_model.lower() == expected_model.lower()))
    reasoning_violation = thinking_off and (bool(message.get("reasoning")) or bool(message.get("reasoning_details"))
                                           or money(reasoning_tokens) and reasoning_tokens > 0)
    return {"transport_ok": success, "provider": provider, "provider_matches": provider_matches,
            "response_model": response_model, "model_matches": model_matches,
            "request_contract_ok": success and provider_matches and model_matches and not reasoning_violation,
            "protocol_action": parse_action(content if isinstance(content, str) else "").kind,
            "protocol_is_finish": isinstance(content, str) and parse_action(content).kind == "finish",
            "finish_reason": choice.get("finish_reason"), "reasoning_tokens": reasoning_tokens,
            "thinking_off_violation": reasoning_violation,
            "reported_cost_usd": cost if money(cost) else None,
            "generation_id": body.get("id") if isinstance(body, dict) else None}


def request_body(config, sequence):
    kwargs = config["agent_kwargs"]["llm_call_kwargs"]
    body = {"model": config["runtime_id"].removeprefix("openrouter/"), "stream": False,
            "messages": [{"role": "user", "content": PROMPT + str(sequence)}],
            "max_tokens": kwargs["max_tokens"], "temperature": config["agent_kwargs"]["temperature"],
            "top_p": kwargs["top_p"], **deepcopy(kwargs["extra_body"])}
    body["provider"]["max_price"] = PRICE_CAP
    # The input is short ASCII. Reserve allows 4096 input tokens (including
    # chat-template overhead) at $2/M plus 8192 completion at $5/M = $0.049152.
    if len(json.dumps(body["messages"], ensure_ascii=False).encode("utf-8")) > 1024:
        raise V2Error("probe input exceeded its declared conservative pricing bound")
    return body


def thinking_disabled(body):
    reasoning = body.get("reasoning")
    return isinstance(reasoning, dict) and (
        reasoning.get("enabled") is False or reasoning.get("effort") == "none"
    )


def _same_money(left, right):
    return money(left) and money(right) and math.isclose(left, right, rel_tol=0, abs_tol=1e-9)


def _closure(rows):
    result = set()
    for row in rows:
        result.add(row["directory"])
        result.update(row.get("ancestor_directories", []))
    return result


def _completed_probe_budget(directory, seen):
    """Verify a completed historical probe without authorizing its old source.

    Every charged/unknown request remains covered, including all recursively
    bound parents. Completion is derived from receipts, not a boolean marker.
    """
    plan = read_json(directory / "plan.json")
    _validate_plan_document(plan, directory)  # Old source hashes are historical.
    parents = _parent_rows((row["directory"] for row in plan["parents"]), seen)
    if parents != plan["parents"]:
        raise V2Error("historical probe parent evidence changed")
    historical = sum(row["committed_usd"] for row in parents)
    if (not _same_money(plan.get("historical_committed_usd"), historical)
            or not _same_money(plan.get("residual_cap_usd"), plan["aggregate_cap_usd"] - historical)):
        raise V2Error("historical probe parent budget arithmetic differs")
    report = read_json(directory / "report.json")
    completion = read_json(directory / "completion.json")
    approval = read_json(directory / "authorization.json")
    if (report.get("kind") != "bounded_route_probe_report"
            or report.get("plan_sha256") != plan["plan_sha256"]
            or completion.get("no_expansion") is not True
            or not isinstance(completion.get("completed_at"), str)
            or approval.get("approved_by_user") is not True
            or approval.get("plan_sha256") != plan["plan_sha256"]
            or approval.get("aggregate_cap_usd") != plan["aggregate_cap_usd"]):
        raise V2Error("historical probe report/completion/authorization mismatch")
    paths = sorted((directory / "requests").glob("*.json"))
    receipts = [read_json(path) for path in paths]
    if len(receipts) > plan["max_requests"]:
        raise V2Error("historical probe request count exceeds cap")
    index, new_committed, outcomes = 0, 0.0, []
    for row in plan["models"]:
        outcome = {"model": row["model"], "catalog_status": row["catalog_status"],
                   "status": "not_available", "selected_route": None, "candidate_results": []}
        for candidate in row["candidates"]:
            config, endpoint = candidate["config"], candidate["endpoint"]
            result = {"route": config["route"], "observations": [], "status": "pending"}
            for _ in range(plan["responses_per_candidate"]):
                if index >= len(receipts):
                    raise V2Error("historical probe completion has missing request receipts")
                number, record = index + 1, receipts[index]
                body = request_body(config, number)
                if (paths[index].name != f"r{number:03d}.json"
                        or record.get("status") != "completed"
                        or record.get("sequence") != number
                        or record.get("plan_sha256") != plan["plan_sha256"]
                        or record.get("model") != row["model"]
                        or record.get("route") != config["route"]
                        or record.get("request") != body
                        or record.get("reserved_usd") != REQUEST_RESERVE):
                    raise V2Error("historical probe has unresolved or inconsistent receipt evidence")
                assessment = classify_response(record["response"], endpoint.get("provider_name"),
                                               thinking_disabled(body), expected_model=body["model"])
                cost = assessment["reported_cost_usd"]
                expected_status = "reported_usage_cost" if cost is not None else "unknown_reserve_retained"
                if (record.get("assessment") != assessment or record.get("charged_usd") != cost
                        or record.get("cost_status") != expected_status
                        or cost is not None and cost > REQUEST_RESERVE):
                    raise V2Error("historical probe receipt assessment or accounting differs")
                new_committed += REQUEST_RESERVE if cost is None else cost
                index += 1
                result["observations"].append({"sequence": number, **assessment})
                if not assessment["request_contract_ok"]:
                    result["status"] = "transport_or_parameter_fault"
                    break
            else:
                result["status"] = "short_probe_passed"
            outcome["candidate_results"].append(result)
            if result["status"] == "short_probe_passed":
                outcome.update(status="short_probe_passed", selected_route=config["route"], runtime_model=config)
                break
        if row["candidates"] and outcome["selected_route"] is None:
            outcome["status"] = "no_route_passed_bounded_probe"
        outcomes.append(outcome)
    committed = historical + new_committed
    if (index != len(receipts) or report.get("requests") != len(receipts)
            or report.get("model_outcomes") != outcomes
            or not _same_money(report.get("historical_committed_usd"), historical)
            or not _same_money(report.get("new_committed_usd"), new_committed)
            or not _same_money(report.get("aggregate_committed_usd"), committed)
            or committed > plan["aggregate_cap_usd"] + 1e-12
            or report.get("not_benchmark_trial") is not True
            or report.get("formal_ranking_eligible") is not False
            or report.get("stability_certified") is not False):
        raise V2Error("historical probe report differs from complete receipt evidence")
    ready = read_json(directory / "models.probe-ready.json")
    if ready != {"models": {row["model"]: row["runtime_model"] for row in outcomes
                             if row["status"] == "short_probe_passed"},
                 "probe_plan_sha256": plan["plan_sha256"], "stability_certified": False}:
        raise V2Error("historical probe exported model evidence differs")
    root = directory.parent.parent.parent
    envelope = _envelope_path(root, parents)
    allocation = read_json(envelope)
    if (allocation.get("status") != "completed"
            or allocation.get("plan_sha256") != plan["plan_sha256"]
            or allocation.get("directory") != str(directory)
            or allocation.get("aggregate_cap_usd") != plan["aggregate_cap_usd"]
            or not _same_money(allocation.get("aggregate_committed_usd"), committed)):
        raise V2Error("historical probe envelope is not completed or consistent")
    return {"directory": str(directory), "plan": bound_file(directory / "plan.json"),
            "report": bound_file(directory / "report.json"),
            "completion": bound_file(directory / "completion.json"),
            "authorization": bound_file(directory / "authorization.json"),
            "receipts": [bound_file(path) for path in paths], "envelope": bound_file(envelope),
            "models": bound_file(directory / "models.probe-ready.json"),
            "ancestor_directories": sorted(_closure(parents)), "committed_usd": committed}


def _check_allocation_overlap(root, plan, *, handoff_path=None):
    """A completed parent may advance its envelope; siblings cannot fork it."""
    covered = _closure(plan["parents"])
    for path in (Path(root) / "experiments/smallowbench-v2").glob("route-envelope-*.json"):
        allocation = read_json(path)
        allocated = Path(allocation["directory"]).resolve()
        prior = read_json(allocated / "plan.json")
        if (prior.get("plan_sha256") != allocation.get("plan_sha256")
                or prior.get("plan_sha256") != digest({k: v for k, v in prior.items() if k != "plan_sha256"})
                or prior.get("directory") != str(allocated)):
            raise V2Error("existing route allocation has mismatched evidence")
        intersects = covered.intersection(_closure(prior["parents"]) | {str(allocated)})
        if intersects and not (str(allocated) in covered and allocation.get("status") == "completed"):
            raise V2Error("overlapping historical budget residual already allocated outside the completed parent chain")
    # A split handoff consumes the parent's entire residual allocation right,
    # even if some local ceilings are not spent. Old probe entrypoints must not
    # fork an rt2/ancestor sibling around either bounded consumer.
    from v2_budget_handoff import handoff_documents

    for path, handoff in handoff_documents(root):
        if handoff_path is not None and path.resolve() == Path(handoff_path).resolve():
            continue  # Only validate_share uses this after verifying its hash/rights.
        child_directories = {row["directory"] for row in handoff["shares"].values()}
        if (covered.intersection(handoff["ancestor_directories"])
                or plan.get("directory") in child_directories):
            raise V2Error("overlapping historical budget residual already assigned to immutable budget handoff shares")


def run(directory, *, execute=False, root=ROOT, sender=post_once):
    directory = Path(directory).resolve()
    plan = validate_plan(directory, root=root)
    if not execute:
        return {"execution_started": False, "max_requests": plan["max_requests"],
                "models": len(plan["models"]), "not_benchmark_trial": True}
    if (directory / "STOP").exists():
        raise V2Error("route probe STOP exists")
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise V2Error("operator-supplied OpenRouter process environment key absent")
    if any((directory / "requests").glob("*.json")) or (directory / "report.json").exists():
        raise V2Error("probe cannot be replayed/resumed blindly; preserve original requests")
    outcomes, records = [], []
    committed = plan["historical_committed_usd"]
    envelope = _envelope_path(root, plan["parents"])
    # Allocation serialization and the envelope's atomic writer use distinct
    # sidecars; Windows byte locks are not recursively re-entrant.
    with process_lock(directory / "probe", timeout=1), process_lock(
        Path(root) / "experiments/smallowbench-v2/route-budget-allocation", timeout=1
    ):
        if envelope.exists():
            raise V2Error("historical residual envelope already allocated; do not reuse it in another probe")
        validate_plan(directory, root=root)
        _check_allocation_overlap(root, plan)
        write_atomic(envelope, {"plan_sha256": plan["plan_sha256"], "directory": str(directory),
                     "historical_parent_manifests": [row.get("manifest", row.get("plan")) for row in plan["parents"]],
                     "aggregate_cap_usd": plan["aggregate_cap_usd"], "status": "allocated",
                     "started_at": now()}, overwrite=False)
        for row in plan["models"]:
            outcome = {"model": row["model"], "catalog_status": row["catalog_status"],
                       "status": "not_available", "selected_route": None, "candidate_results": []}
            for candidate in row["candidates"]:
                config, endpoint = candidate["config"], candidate["endpoint"]
                result = {"route": config["route"], "observations": [], "status": "pending"}
                for _ in range(plan["responses_per_candidate"]):
                    validate_plan(directory, root=root)
                    if ((directory / "STOP").exists() or len(records) >= plan["max_requests"]
                            or committed + REQUEST_RESERVE > plan["aggregate_cap_usd"] + 1e-12):
                        raise V2Error("probe stopped by hold, request cap, or aggregate budget admission")
                    number = len(records) + 1
                    body = request_body(config, number)
                    record = {"schema_version": 1, "sequence": number, "model": row["model"],
                              "route": config["route"], "plan_sha256": plan["plan_sha256"],
                              "started_at": now(), "status": "running", "reserved_usd": REQUEST_RESERVE,
                              "request": body}
                    path = directory / "requests" / f"r{number:03d}.json"
                    write_atomic(path, record, overwrite=False)
                    committed += REQUEST_RESERVE
                    response = sender(body, key, plan["http_timeout_seconds"])
                    assessment = classify_response(response, endpoint.get("provider_name"),
                                                   thinking_disabled(body),
                                                   expected_model=body["model"])
                    cost = assessment["reported_cost_usd"]
                    if cost is not None:
                        committed += cost - REQUEST_RESERVE
                    record.update(status="completed", completed_at=now(), response=response,
                                  assessment=assessment, charged_usd=cost,
                                  cost_status="reported_usage_cost" if cost is not None else "unknown_reserve_retained")
                    write_atomic(path, record)
                    records.append(record)
                    result["observations"].append({"sequence": number, **assessment})
                    if cost is not None and cost > REQUEST_RESERVE:
                        raise V2Error("reported charge exceeded conservative request reserve; investigate pricing")
                    error = response.get("body", {})
                    error = error.get("error", {}) if isinstance(error, dict) else {}
                    auth_code = error.get("code") if isinstance(error, dict) else None
                    if (response.get("http_status") in {401, 402, 403}
                            or auth_code in {401, 402, 403, "401", "402", "403"}):
                        try:
                            with (directory / "STOP").open("x", encoding="utf-8") as stream:
                                stream.write("Authentication/credit/permission fault; preserve receipts and stop globally.\n")
                        except FileExistsError:
                            pass
                        raise V2Error("global authentication/credit/permission fault; no provider shopping or further calls")
                    if not assessment["request_contract_ok"]:
                        result["status"] = "transport_or_parameter_fault"
                        break  # New candidate only; no in-request fallback or hidden retries.
                    # Wrong response format is model behavior, NOT a reason to
                    # provider-shop. Keep it separately, without executing it.
                else:
                    result["status"] = "short_probe_passed"
                outcome["candidate_results"].append(result)
                if result["status"] == "short_probe_passed":
                    outcome.update(status="short_probe_passed", selected_route=config["route"], runtime_model=config)
                    break
            if row["candidates"] and outcome["selected_route"] is None:
                outcome["status"] = "no_route_passed_bounded_probe"
            outcomes.append(outcome)
            write_atomic(directory / "progress.json", {"plan_sha256": plan["plan_sha256"],
                         "finished_models": len(outcomes), "requests": len(records), "outcomes": outcomes,
                         "aggregate_committed_usd": committed})
    report = {"schema_version": 1, "kind": "bounded_route_probe_report", "plan_sha256": plan["plan_sha256"],
              "generated_at": now(), "model_outcomes": outcomes, "requests": len(records),
              "aggregate_committed_usd": committed, "historical_committed_usd": plan["historical_committed_usd"],
              "new_committed_usd": committed - plan["historical_committed_usd"],
              "not_benchmark_trial": True, "formal_ranking_eligible": False, "stability_certified": False}
    write_atomic(directory / "report.json", report, overwrite=False)
    write_atomic(directory / "models.probe-ready.json", {"models": {
        row["model"]: row["runtime_model"] for row in outcomes if row["status"] == "short_probe_passed"},
        "probe_plan_sha256": plan["plan_sha256"], "stability_certified": False}, overwrite=False)
    write_atomic(directory / "completion.json", {"completed_at": now(), "no_expansion": True}, overwrite=False)
    write_atomic(envelope, {"plan_sha256": plan["plan_sha256"], "directory": str(directory),
                 "historical_parent_manifests": [row.get("manifest", row.get("plan")) for row in plan["parents"]],
                 "aggregate_cap_usd": plan["aggregate_cap_usd"], "status": "completed",
                 "aggregate_committed_usd": committed, "completed_at": now()})
    (directory / "STOP").write_text("Bounded route probes finished; no matrix execution authorized.\n", encoding="utf-8")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument("--directory", type=Path, required=True)
    prep.add_argument("--audit", type=Path, required=True)
    prep.add_argument("--parent", type=Path, action="append", required=True)
    prep.add_argument("--aggregate-cap", type=float, default=4)
    prep.add_argument("--model", action="append", dest="models")
    prep.add_argument("--reasoning-off-style", choices=("enabled-false", "effort-none"), default="enabled-false")
    prep.add_argument("--write", action="store_true")
    execute = sub.add_parser("execute")
    execute.add_argument("--directory", type=Path, required=True)
    execute.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            plan = prepare(args.directory, args.audit, args.parent, aggregate_cap=args.aggregate_cap,
                           models=args.models, reasoning_off_style=args.reasoning_off_style)
            if args.write:
                args.directory.mkdir(exist_ok=False)
                write_atomic(args.directory / "plan.json", plan, overwrite=False)
                (args.directory / "STOP").write_text("Prepared only; explicit probe approval required.\n", encoding="utf-8")
            result = {"plan_sha256": plan["plan_sha256"], "models": len(plan["models"]),
                      "historical_committed_usd": plan["historical_committed_usd"],
                      "residual_cap_usd": plan["residual_cap_usd"], "max_requests": plan["max_requests"],
                      "written": args.write, "paid_calls": 0}
        else:
            result = run(args.directory, execute=args.execute)
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
        return 0
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as exc:
        if args.command == "execute" and args.execute:
            hold = args.directory / "STOP"
            if not hold.exists():
                hold.write_text("Probe stopped; preserve receipts and unknown reserves.\n", encoding="utf-8")
        print(json.dumps({"blocked": True, "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
