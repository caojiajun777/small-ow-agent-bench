"""Public, non-generating route inventory for SmallOWBench 2.0.

This module never reads credentials or calls a completion endpoint. Catalog
availability is not a claim of successful inference, parameter semantics, or
provider stability. Recommendations are new draft configurations, never changes
to a frozen run or its legacy roster. All writes are exclusive.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import socket
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


SCHEMA_VERSION = 1
CATALOG_BASE = "https://openrouter.ai/api/v1/models/"
REQUIRED_PARAMETERS = frozenset({"temperature", "top_p", "max_tokens"})
KNOWN_PRECISIONS = frozenset({"bf16", "fp8"})
DEFAULT_EXCLUDED_ROUTES = {
    "gemma-3-4b-it": {"deepinfra/bf16": "observed repeated HTTP 429 shared-pool overload"},
}
DEFAULT_PREFERENCES = {"gemma-3-4b-it": ["parasail/bf16"]}
ROOT = Path(__file__).resolve().parents[1]


class RouteError(ValueError):
    pass


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def canonical_json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                      separators=(",", ":"))


def digest(value):
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def canonical_route(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*", value):
        raise RouteError("invalid provider endpoint tag")
    return value.lower()


def model_slug(value):
    if not isinstance(value, str):
        raise RouteError("model id must be a string")
    value = value.removeprefix("openrouter/")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.:-]+", value):
        raise RouteError("expected an explicit author/model OpenRouter id")
    return value


def load_roster(path=ROOT / "models.lock.yaml"):
    # PyYAML is already a project/runtime dependency. SafeLoader only; never
    # treat historical comments or substitution policies as an execution plan.
    import yaml

    path = Path(path)
    raw = path.read_bytes()
    value = yaml.safe_load(raw)
    models = value.get("models") if isinstance(value, dict) else None
    if not isinstance(models, list) or not models:
        raise RouteError("roster needs a nonempty models list")
    seen = set()
    for model in models:
        if not isinstance(model, dict) or not isinstance(model.get("id"), str):
            raise RouteError("roster contains malformed model")
        if model["id"] in seen:
            raise RouteError("duplicate roster model")
        seen.add(model["id"])
        model_slug(model.get("openrouter_id"))
        canonical_route(model.get("openrouter_provider"))
        quantization = model.get("quantization")
        if quantization not in KNOWN_PRECISIONS | {"mistral-hosted", "alibaba-hosted"}:
            raise RouteError("unrecognized frozen quantization policy")
    return {"source": {"path": str(path.resolve()), "sha256": hashlib.sha256(raw).hexdigest()},
            "models": models}


def fetch_catalog(model_id, *, timeout=30, opener=None):
    """GET one official public metadata endpoint, without a key or retries."""
    slug = model_slug(model_id)
    url = CATALOG_BASE + quote(slug, safe="/") + "/endpoints"
    envelope = {"model_id": slug, "url": url, "retrieved_at": utc_now(),
                "status": None, "http_status": None, "data": None}
    opener = opener or urlopen
    request = Request(url, headers={"Accept": "application/json",
                                   "User-Agent": "SmallOWBench-v2-route-audit/1"})
    try:
        with opener(request, timeout=timeout) as response:
            envelope["http_status"] = response.status
            body = response.read()
            envelope["response_sha256"] = hashlib.sha256(body).hexdigest()
        payload = json.loads(body.decode("utf-8"))
        envelope["payload"] = payload
        if isinstance(payload, dict) and isinstance(payload.get("error"), dict):
            code = payload["error"].get("code")
            envelope["status"] = "not_found" if code == 404 else "transient_error"
            envelope["api_error_code"] = code
        elif (not isinstance(payload, dict) or not isinstance(payload.get("data"), dict)
              or not isinstance(payload["data"].get("endpoints"), list)
              or payload["data"].get("id") != slug):
            envelope["status"] = "schema_error"
        else:
            envelope["status"] = "ok"
            envelope["data"] = payload["data"]
    except HTTPError as exc:
        envelope["http_status"] = exc.code
        envelope["status"] = "not_found" if exc.code == 404 else "transient_error"
        # No request headers, credential values, or user-provided exception text
        # is serialized. The endpoint URL is a validated public model slug.
        envelope["error_type"] = type(exc).__name__
    except (URLError, TimeoutError, socket.timeout, OSError) as exc:
        envelope["status"] = "transient_error"
        envelope["error_type"] = type(exc).__name__
    except (UnicodeError, json.JSONDecodeError) as exc:
        envelope["status"] = "schema_error"
        envelope["error_type"] = type(exc).__name__
    return envelope


def _candidate(model, endpoint, excluded):
    reasons = []
    try:
        route = canonical_route(endpoint.get("tag"))
    except RouteError:
        route = None
        reasons.append("missing_or_invalid_endpoint_tag")
    quantization = endpoint.get("quantization")
    quantization = quantization.lower() if isinstance(quantization, str) else "unknown"
    suffix = route.rsplit("/", 1)[-1] if route else None
    if suffix in {"bf16", "fp16", "fp8", "fp4", "int8", "int4"} and suffix != quantization:
        reasons.append("endpoint_tag_precision_contradicts_metadata")
    declared = model["quantization"]
    old_provider = canonical_route(model["openrouter_provider"]).split("/", 1)[0]
    if declared in KNOWN_PRECISIONS:
        if quantization != declared:
            reasons.append("precision_mismatch_or_unknown")
        precision_scope = "same_advertised_precision"
    else:
        # A provider-hosted legacy label is NOT evidence of BF16. Unknown is
        # acceptable only at the same originally declared hosting provider.
        if route is None or route.split("/", 1)[0] != old_provider:
            reasons.append("hosted_precision_requires_original_provider")
        precision_scope = "same_hosted_provider_precision_" + quantization
    supported = endpoint.get("supported_parameters")
    if not isinstance(supported, list) or not all(isinstance(x, str) for x in supported):
        supported = []
        reasons.append("supported_parameters_unknown")
    missing = sorted(REQUIRED_PARAMETERS - set(supported))
    if missing:
        reasons.append("missing_parameters:" + ",".join(missing))
    if model.get("family") == "qwen" and "reasoning" not in supported:
        reasons.append("reasoning_parameter_not_advertised")
    max_output = endpoint.get("max_completion_tokens")
    if max_output is not None and (not isinstance(max_output, int) or isinstance(max_output, bool)
                                   or max_output < 8192):
        reasons.append("advertised_output_limit_below_8192")
    if endpoint.get("status") != 0 or isinstance(endpoint.get("status"), bool):
        reasons.append("endpoint_status_not_active")
    if route in excluded:
        reasons.append("explicitly_excluded:" + excluded[route])
    return {
        "route": route, "provider_name": endpoint.get("provider_name"),
        "quantization": quantization, "precision_scope": precision_scope,
        "eligible": not reasons, "rejection_reasons": reasons,
        "supported_parameters": sorted(set(supported)),
        "reasoning_parameter_advertised": "reasoning" in supported,
        "reasoning_disable_verified": False,
        "status": endpoint.get("status"), "pricing": endpoint.get("pricing"),
        "context_length": endpoint.get("context_length"),
        "max_completion_tokens": max_output,
        "uptime_last_30m": endpoint.get("uptime_last_30m"),
        "latency_last_30m": endpoint.get("latency_last_30m"),
        "throughput_last_30m": endpoint.get("throughput_last_30m"),
        "endpoint_metadata_sha256": digest(endpoint),
    }


def audit_routes(roster, catalogs, *, overrides=None, excluded_routes=None):
    """Produce explicit draft recommendations; never silently change a run.

    ``catalogs`` maps frozen model ids to fetch_catalog envelopes. An explicit
    invalid override blocks that model rather than falling back elsewhere.
    """
    overrides = overrides or {}
    excluded_routes = DEFAULT_EXCLUDED_ROUTES if excluded_routes is None else excluded_routes
    models = roster["models"]
    ids = {model["id"] for model in models}
    if set(overrides) - ids:
        raise RouteError("route override refers to a model outside the immutable roster")
    rows = []
    for model in models:
        ident = model["id"]
        slug = model_slug(model["openrouter_id"])
        original = canonical_route(model["openrouter_provider"])
        fetch = catalogs.get(ident)
        row = {"model": ident, "runtime_id": "openrouter/" + slug,
               "legacy_route": model["openrouter_provider"], "legacy_quantization": model["quantization"],
               "family": model.get("family"), "catalog": fetch,
               "status": "catalog_not_fetched", "candidates": [], "selected": None,
               "score": None, "inference_probe_verified": False}
        if fetch is None:
            rows.append(row)
            continue
        if fetch.get("model_id") != slug:
            row["status"] = "catalog_identity_mismatch"
        elif fetch.get("status") == "not_found":
            row["status"] = "unavailable_model_404"
        elif fetch.get("status") != "ok":
            row["status"] = "catalog_" + str(fetch.get("status"))
        else:
            data = fetch.get("data")
            endpoints = data.get("endpoints") if isinstance(data, dict) else None
            if not isinstance(endpoints, list) or data.get("id") != slug:
                row["status"] = "catalog_schema_error"
            elif not endpoints:
                row["status"] = "unavailable_zero_endpoints"
            else:
                excluded = {canonical_route(k): v for k, v in excluded_routes.get(ident, {}).items()}
                for endpoint in endpoints:
                    if not isinstance(endpoint, dict):
                        row["candidates"].append({"eligible": False, "route": None,
                                                   "rejection_reasons": ["malformed_endpoint"]})
                    else:
                        row["candidates"].append(_candidate(model, endpoint, excluded))
                eligible = [c for c in row["candidates"] if c["eligible"]]
                tags = [c["route"] for c in eligible]
                if len(tags) != len(set(tags)):
                    row["status"] = "catalog_ambiguous_duplicate_tag"
                    rows.append(row)
                    continue
                if ident in overrides:
                    requested = canonical_route(overrides[ident])
                    chosen = next((c for c in eligible if c["route"] == requested), None)
                    row["selection_reason"] = "explicit_override"
                    row["requested_override"] = requested
                    if chosen is None:
                        row["status"] = "override_rejected"
                else:
                    preferences = DEFAULT_PREFERENCES.get(ident, [])
                    # Base-provider legacy names (e.g. Venice) are canonicalized
                    # to an advertised exact endpoint, never used as broad pins.
                    def priority(candidate):
                        tag = candidate["route"]
                        return (0 if tag in preferences else 1,
                                preferences.index(tag) if tag in preferences else 0,
                                0 if tag == original else 1,
                                0 if tag.split("/", 1)[0] == original else 1,
                                tag)
                    chosen = min(eligible, key=priority) if eligible else None
                    row["selection_reason"] = ("preserve_original" if chosen and chosen["route"] == original
                                               else "explicit_new_draft_recommendation")
                if chosen is not None:
                    row["selected"] = chosen
                    row["status"] = "candidate_requires_inference_probe"
                    row["route_changed_from_legacy"] = chosen["route"] != original
                    row["runtime_model"] = _runtime_model(model, chosen)
                elif row["status"] != "override_rejected":
                    row["status"] = "no_compatible_active_endpoint"
        rows.append(row)
    report = {
        "schema_version": SCHEMA_VERSION, "kind": "public_route_catalog_audit",
        "generated_at": utc_now(), "legacy_roster": roster.get("source"),
        "draft_only": True, "paid_calls": 0, "model_substitution": False,
        "formal_ranking_eligible": False, "frozen_runs_modified": False,
        "required_parameters": sorted(REQUIRED_PARAMETERS),
        "policy": "exact endpoint; no fallback; same advertised precision or same legacy hosted provider; unavailable is missing, never zero",
        "limitations": ["Catalog availability does not verify inference or capacity.",
                        "BF16/FP8 are provider-advertised, not independently measured weight formats.",
                        "Reasoning support does not prove that disabling reasoning is honored.",
                        "Route changes create new configurations; do not mix paired outcomes across providers."],
        "counts": dict(Counter(row["status"] for row in rows)), "rows": rows,
    }
    report["report_sha256"] = digest(report)
    return report


def _runtime_model(model, selected, *, max_tokens=8192):
    provider = {"order": [selected["route"]], "only": [selected["route"]], "allow_fallbacks": False,
                "require_parameters": True}
    if selected["quantization"] in KNOWN_PRECISIONS:
        provider["quantizations"] = [selected["quantization"]]
    extra = {"provider": provider}
    if model.get("family") == "qwen":
        extra["reasoning"] = {"enabled": False}
        extra["enable_thinking"] = False
    return {"runtime_id": model["openrouter_id"], "route": selected["route"],
            "agent_kwargs": {"max_turns": 20, "command_timeout_sec": 60,
                             "observation_limit": 8000, "temperature": 0.0,
                             "llm_call_kwargs": {"max_tokens": max_tokens, "timeout": 180,
                                                 "top_p": 1.0, "extra_body": extra}}}


def config_for_candidate(row, candidate):
    """Return a draft v2 runtime config for an eligible advertised candidate.

    This is suitable for a separately authorized probe or a NEW preparation,
    never an automatic in-run fallback. No network operation is performed.
    """
    if not candidate.get("eligible") or candidate not in row.get("candidates", []):
        raise RouteError("candidate is not eligible in this model's saved catalog")
    if not row.get("runtime_id", "").startswith("openrouter/"):
        raise RouteError("candidate config requires an OpenRouter model identity")
    model_slug(row["runtime_id"])
    model = {"openrouter_id": row["runtime_id"], "family": row.get("family")}
    return _runtime_model(model, candidate)


def active_models_document(report, *, max_tokens=8192):
    """Export candidate models only, as explicitly unverified preparation input."""
    if max_tokens != 8192:
        raise RouteError("this audit validates the declared 8192 output budget only")
    if digest({k: v for k, v in report.items() if k != "report_sha256"}) != report.get("report_sha256"):
        raise RouteError("route audit report digest mismatch")
    models = {row["model"]: row["runtime_model"] for row in report["rows"]
              if row.get("selected") is not None}
    return {"schema_version": 1, "draft_only": True,
            "source_route_report_sha256": report["report_sha256"],
            "inference_probe_verified": False, "models": models}


def write_new_json(path, value):
    path = Path(path)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--roster", type=Path, default=ROOT / "models.lock.yaml")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--fetch", action="store_true", help="GET official public metadata only; no model calls")
    source.add_argument("--catalogs", type=Path, help="offline mapping or report containing saved retrieval envelopes")
    parser.add_argument("--overrides", type=Path, help="explicit model-id -> exact endpoint tag JSON")
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--write", type=Path, help="exclusive NEW audit report; never overwrite")
    parser.add_argument("--models-output", type=Path, help="exclusive NEW draft v2 runtime config")
    args = parser.parse_args(argv)
    if args.timeout <= 0 or args.timeout > 60:
        parser.error("metadata timeout must be > 0 and <= 60 seconds")
    # Fail closed before making even public requests when an output already
    # exists. Frozen/old reports cannot be overwritten as a side effect.
    for path in (args.write, args.models_output):
        if path is not None and path.exists():
            parser.error("output already exists: " + str(path))
    roster = load_roster(args.roster)
    if args.fetch:
        catalogs = {model["id"]: fetch_catalog(model["openrouter_id"], timeout=args.timeout)
                    for model in roster["models"]}
    elif args.catalogs:
        value = json.loads(args.catalogs.read_text(encoding="utf-8"))
        catalogs = ({row["model"]: row["catalog"] for row in value["rows"]}
                    if "rows" in value else value)
    else:
        catalogs = {}
    overrides = json.loads(args.overrides.read_text(encoding="utf-8")) if args.overrides else {}
    report = audit_routes(roster, catalogs, overrides=overrides)
    if args.write:
        write_new_json(args.write, report)
    if args.models_output:
        write_new_json(args.models_output, active_models_document(report))
    print(json.dumps({"kind": report["kind"], "draft_only": True, "paid_calls": 0,
                      "counts": report["counts"], "report_sha256": report["report_sha256"],
                      "models": [{"model": r["model"], "status": r["status"],
                                  "route": r["selected"]["route"] if r["selected"] else None}
                                 for r in report["rows"]]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
