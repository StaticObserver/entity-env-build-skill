#!/usr/bin/env python3
"""Construct entity-deps.local.json from requirements.json + dependency discovery data.

This formalizes the checkpoint-creation step that was previously done by
hand-written scripts during the initial practice run.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import socket
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from _version_profile import version_profile as detect_version_profile


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise SystemExit(f"{path} must contain a JSON object")
    return data


def write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    text = json.dumps(data, indent=2, sort_keys=True) + "\n"
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as f:
        f.write(text)
        tmp = Path(f.name)
    tmp.replace(path)


# ---------------------------------------------------------------------------
# Auto-detection
# ---------------------------------------------------------------------------


def detect_target() -> dict[str, Any]:
    return {
        "hostname": socket.gethostname(),
        "os": platform.system(),
        "arch": platform.machine(),
        "shell": os.environ.get("SHELL", "bash"),
        "context": "login",
    }


def derive_paths(selected: dict[str, Any]) -> dict[str, Any]:
    """Derive PATH / CMAKE_PREFIX_PATH / LD_LIBRARY_PATH from selected entries."""
    path_entries: list[str] = []
    cmake_entries: list[str] = []
    ld_entries: list[str] = []

    for dep_name, entry in selected.items():
        if not isinstance(entry, dict):
            continue
        prefix = entry.get("prefix", "")

        bin_path = entry.get("bin", "")
        if bin_path:
            path_entries.append(str(bin_path))
        if prefix:
            bin_dir = str(Path(prefix) / "bin")
            if bin_dir not in path_entries:
                path_entries.append(bin_dir)

        if prefix and prefix not in cmake_entries:
            cmake_entries.append(str(prefix))

        lib_path = entry.get("lib", "")
        if lib_path:
            ld_entries.append(str(lib_path))
        if prefix:
            for sub in ("lib64", "lib"):
                lib_dir = str(Path(prefix) / sub)
                if lib_dir not in ld_entries:
                    ld_entries.append(lib_dir)

    # Ensure basic system paths
    if "/usr/bin" not in path_entries:
        path_entries.append("/usr/bin")

    return {
        "PATH": path_entries,
        "CMAKE_PREFIX_PATH": cmake_entries,
        "LD_LIBRARY_PATH": ld_entries,
        "DYLD_LIBRARY_PATH": [],
    }


# ---------------------------------------------------------------------------
# Main construction
# ---------------------------------------------------------------------------


def build_checkpoint(
    req: dict[str, Any],
    discovery: dict[str, Any] | None = None,
    merge_from: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    entity = req.get("entity", {})
    workdir = str(entity.get("workdir", "")) if isinstance(entity, dict) else ""

    if not workdir:
        workdir = os.environ.get("ENTITY_WORKDIR", "")
    if not workdir:
        raise SystemExit("ENTITY_WORKDIR must be set or present in requirements.entity.workdir")

    # Build selected dependencies from discovery data
    selected: dict[str, Any] = {}
    if discovery and isinstance(discovery, dict):
        for dep, entry in discovery.items():
            if isinstance(entry, dict):
                selected[dep] = dict(entry)

    # Merge with existing checkpoint if provided
    if merge_from and isinstance(merge_from, dict):
        merge_selected = merge_from.get("selected", {})
        if isinstance(merge_selected, dict):
            for dep, entry in merge_selected.items():
                if isinstance(entry, dict) and dep not in selected:
                    selected[dep] = dict(entry)
        # Merge decisions
        merge_decisions = merge_from.get("decisions", {})
        if isinstance(merge_decisions, dict) and merge_decisions:
            decisions = merge_decisions
        else:
            decisions = {}
    else:
        decisions = {}

    try:
        profile = detect_version_profile(req)
    except (ValueError, SystemExit):
        profile = {"name": "unknown", "cxx_standard": "17"}

    checkpoint: dict[str, Any] = {
        "schema_version": 1,
        "generated_at": now,
        "requirements": {
            "path": "",
            "embedded": None,
        },
        "target": detect_target(),
        "entity": {
            "checkout_root": str(
                entity.get("checkout_root", "") if isinstance(entity, dict) else ""
            ),
            "version_bucket": str(
                entity.get("version_bucket", "") if isinstance(entity, dict) else ""
            ),
            "dependency_profile": str(
                entity.get("dependency_profile", profile.get("name", ""))
                if isinstance(entity, dict)
                else ""
            ),
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("requirements_json", type=Path, help="Path to requirements.json")
    parser.add_argument(
        "--from-discovery", type=Path, dest="discovery_json",
        help="JSON file with dependency candidate entries (one per dep name)",
    )
    parser.add_argument(
        "--merge", type=Path, dest="merge_json",
        help="Existing entity-deps.local.json to merge selected/decisions from",
    )
    parser.add_argument(
        "--output", type=Path, help="Output path (default: $ENTITY_WORKDIR/entity-deps.local.json)",
    )
    args = parser.parse_args()

    req = load_json(args.requirements_json)

    discovery = None
    if args.discovery_json:
        discovery = load_json(args.discovery_json)

    merge_from = None
    if args.merge_json:
        if args.merge_json.exists():
            merge_from = load_json(args.merge_json)

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
            raise SystemExit("Cannot determine output path: use --output or set ENTITY_WORKDIR")
        output_path = Path(workdir) / "entity-deps.local.json"

    # Record the requirements path in the checkpoint
    checkpoint["requirements"]["path"] = str(args.requirements_json.resolve())

    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(output_path, checkpoint)
    print(f"entity-deps.local.json written to {output_path.resolve()}")


if __name__ == "__main__":
    main()
