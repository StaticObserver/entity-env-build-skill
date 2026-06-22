#!/usr/bin/env python3
"""Validate requirements.json and construct entity-deps.local.json.

Subcommands:
  validate <requirements.json>
  create <requirements.json> [--merge <old.json>] [--from-discovery <discovery.json>]
"""

import argparse
import json
import os
import platform
import socket
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from _json_io import (
    add_json_flag,
    derive_paths,
    load_json,
    protocol_error,
    protocol_ok,
    write_json_atomic,
)
from _version_profile import version_profile as detect_version_profile
from entity_schema import CONSISTENCY_RULES, OPTIONAL_DEFAULTS, REQUIRED_ALWAYS, REQUIRED_BUILD


# ===========================================================================
# Shared helpers
# ===========================================================================


def _get(obj: Dict[str, Any], dotted: str) -> Any:
    """Drill into *obj* using dotted path. Returns None when any key is missing."""
    cur: Any = obj
    for part in dotted.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def _has(obj: Dict[str, Any], dotted: str) -> bool:
    val = _get(obj, dotted)
    if val is None:
        return False
    if isinstance(val, str) and val == "":
        return False
    return True


# ===========================================================================
# Subcommand: validate
# ===========================================================================


def check_required(req: Dict[str, Any], fields: List[str], phase: str) -> List[Dict[str, str]]:
    missing: List[Dict[str, str]] = []
    for path in fields:
        if not _has(req, path):
            missing.append({"field": path, "phase": phase})
    return missing


def check_consistency(req: Dict[str, Any]) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []
    for rule_id, condition, pair, msg in CONSISTENCY_RULES:
        if condition:
            cond_field, cond_val = condition
            actual = _get(req, cond_field)
            if actual is None or str(actual).lower() != cond_val:
                continue

        field_a, field_b = pair
        val_a = _get(req, field_a)
        if field_b:
            val_b = _get(req, field_b)
            if rule_id == "pgen.mutex" and val_a is not None and val_b is not None:
                issues.append({"rule": rule_id, "message": msg, "fields": [field_a, field_b]})
        else:
            if val_a is None or (isinstance(val_a, str) and val_a == ""):
                issues.append({"rule": rule_id, "message": msg, "fields": [field_a]})

    return issues


def run_validation(req: Dict[str, Any]) -> Dict[str, Any]:
    always_missing = check_required(req, REQUIRED_ALWAYS, "always")
    build_missing = check_required(req, REQUIRED_BUILD, "build")
    missing_fields = always_missing + build_missing
    consistency_issues = check_consistency(req)

    status = "pass"
    if missing_fields:
        status = "fail"
    elif consistency_issues:
        status = "partial"

    return {
        "status": status,
        "missing_fields": missing_fields,
        "consistency_issues": consistency_issues,
    }


def cmd_validate(args: argparse.Namespace) -> None:
    if not args.requirements_json.exists():
        result = {
            "status": "fail",
            "missing_fields": [{"field": "(file)", "phase": "always"}],
            "consistency_issues": [],
        }
        if args.json:
            protocol_error("checkpoint.validate", "File not found", result=result)
        print(json.dumps(result))
        raise SystemExit(1)

    req = load_json(args.requirements_json)
    result = run_validation(req)

    if args.json:
        if result["status"] == "fail":
            protocol_error("checkpoint.validate", "Validation failed", result=result)
        protocol_ok("checkpoint.validate", result=result)
    else:
        print(json.dumps(result, indent=2, sort_keys=True))
        if result["status"] == "fail":
            raise SystemExit(1)


# ===========================================================================
# Subcommand: create
# ===========================================================================


def detect_target() -> Dict[str, Any]:
    return {
        "hostname": socket.gethostname(),
        "os": platform.system(),
        "arch": platform.machine(),
        "shell": os.environ.get("SHELL", "bash"),
        "context": "login",
    }


def build_checkpoint(
    req: Dict[str, Any],
    discovery: Optional[Dict[str, Any]] = None,
    merge_from: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    entity = req.get("entity", {})
    workdir = str(entity.get("workdir", "")) if isinstance(entity, dict) else ""

    if not workdir:
        workdir = os.environ.get("ENTITY_WORKDIR", "")
    if not workdir:
        raise SystemExit("ENTITY_WORKDIR must be set or present in requirements.entity.workdir")

    selected: Dict[str, Any] = {}
    if discovery and isinstance(discovery, dict):
        for dep, entry in discovery.items():
            if isinstance(entry, dict):
                selected[dep] = dict(entry)

    if merge_from and isinstance(merge_from, dict):
        merge_selected = merge_from.get("selected", {})
        if isinstance(merge_selected, dict):
            for dep, entry in merge_selected.items():
                if isinstance(entry, dict) and dep not in selected:
                    selected[dep] = dict(entry)
        merge_decisions = merge_from.get("decisions", {})
        decisions = merge_decisions if isinstance(merge_decisions, dict) and merge_decisions else {}
    else:
        decisions = {}

    try:
        profile = detect_version_profile(req)
    except (ValueError, SystemExit):
        profile = {"name": "unknown", "cxx_standard": "17"}

    checkout_root = str(entity.get("checkout_root", "")) if isinstance(entity, dict) else ""
    version_bucket = str(entity.get("version_bucket", "")) if isinstance(entity, dict) else ""
    dep_profile = (
        str(entity.get("dependency_profile", profile.get("name", "")))
        if isinstance(entity, dict)
        else ""
    )

    checkpoint: Dict[str, Any] = {
        "schema_version": 1,
        "generated_at": now,
        "requirements": {
            "path": "",
            "embedded": None,
        },
        "target": detect_target(),
        "entity": {
            "checkout_root": checkout_root,
            "version_bucket": version_bucket,
            "dependency_profile": dep_profile,
            "workdir": workdir,
        },
        "candidates": {},
        "selected": selected,
        "decisions": decisions,
        "paths": derive_paths(selected),
        "build_scripts": {
            "directory": str(Path(workdir) / "generated" / "source-build-scripts"),
            "generated_at": now,
            "scripts": {},
        },
        "compatibility": {
            "status": "unknown",
            "checked_at": "",
            "checks": [],
            "issues": [],
        },
        "env_sh": {
            "path": str(Path(workdir) / "env.sh"),
            "status": "missing",
            "generated_at": "",
            "validation": {},
        },
        "status": {
            "checkpoint": "partial",
            "satisfies_requirements_json": False,
            "ready_for_entity_build": False,
            "reuse_notes": [],
        },
    }

    return checkpoint


def cmd_create(args: argparse.Namespace) -> None:
    req = load_json(args.requirements_json)

    discovery = None
    if args.from_discovery:
        discovery = load_json(args.from_discovery)

    merge_from = None
    if args.merge:
        if args.merge.exists():
            merge_from = load_json(args.merge)

    checkpoint = build_checkpoint(req, discovery, merge_from)

    if args.output:
        output_path = args.output
    else:
        workdir = str(
            (req.get("entity", {}) if isinstance(req.get("entity"), dict) else {})
            .get("workdir", "")
            or os.environ.get("ENTITY_WORKDIR", "")
        )
        if not workdir:
            msg = "Cannot determine output path: use --output or set ENTITY_WORKDIR"
            if args.json:
                protocol_error("checkpoint.create", msg)
            raise SystemExit(msg)
        output_path = Path(workdir) / "entity-deps.local.json"

    checkpoint["requirements"]["path"] = str(args.requirements_json.resolve())
    write_json_atomic(output_path, checkpoint)

    if args.json:
        protocol_ok("checkpoint.create", output=str(output_path.resolve()))
    else:
        print(f"entity-deps.local.json written to {output_path.resolve()}")


# ===========================================================================
# Main
# ===========================================================================


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="subcommand")

    # --- validate ---
    p_val = sub.add_parser("validate", help="Validate requirements.json completeness and consistency")
    p_val.add_argument("requirements_json", type=Path)
    add_json_flag(p_val)

    # --- create ---
    p_cre = sub.add_parser("create", help="Construct entity-deps.local.json from requirements.json")
    p_cre.add_argument("requirements_json", type=Path, help="Path to requirements.json")
    p_cre.add_argument("--from-discovery", type=Path, dest="from_discovery",
                       help="JSON file with dependency candidate entries")
    p_cre.add_argument("--merge", type=Path, dest="merge",
                       help="Existing entity-deps.local.json to merge selected/decisions from")
    p_cre.add_argument("--output", type=Path,
                       help="Output path (default: $ENTITY_WORKDIR/entity-deps.local.json)")
    add_json_flag(p_cre)

    args = parser.parse_args()
    if args.subcommand is None:
        parser.print_help()
        raise SystemExit(1)
    if args.subcommand == "validate":
        cmd_validate(args)
    elif args.subcommand == "create":
        cmd_create(args)


if __name__ == "__main__":
    main()
