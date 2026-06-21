#!/usr/bin/env python3
"""Generate env.sh from entity-deps.local.json."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise SystemExit(f"{path} must contain a JSON object")
    return data


def write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    text = json.dumps(data, indent=2, sort_keys=True) + "\n"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as f:
        f.write(text)
        tmp = Path(f.name)
    tmp.replace(path)


def unique(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value:
            continue
        value = os.path.expanduser(str(value))
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def dep_prefixes(selected: dict[str, Any]) -> list[str]:
    prefixes: list[str] = []
    for dep in selected.values():
        if isinstance(dep, dict):
            prefix = dep.get("prefix") or dep.get("install_prefix")
            if prefix:
                prefixes.append(str(prefix))
    return unique(prefixes)


def dep_bins(selected: dict[str, Any]) -> list[str]:
    bins: list[str] = []
    for dep in selected.values():
        if isinstance(dep, dict):
            bin_path = dep.get("bin")
            if bin_path:
                bins.append(str(bin_path))
            prefix = dep.get("prefix") or dep.get("install_prefix")
            if prefix:
                bins.append(str(Path(str(prefix)) / "bin"))
    return unique(bins)


def dep_libs(selected: dict[str, Any]) -> list[str]:
    libs: list[str] = []
    for dep in selected.values():
        if isinstance(dep, dict):
            lib_path = dep.get("lib")
            if lib_path:
                libs.append(str(lib_path))
            prefix = dep.get("prefix") or dep.get("install_prefix")
            if prefix:
                libs.append(str(Path(str(prefix)) / "lib"))
                libs.append(str(Path(str(prefix)) / "lib64"))
    return unique(libs)


def selected_compiler(selected: dict[str, Any]) -> tuple[str, str, str]:
    compiler = selected.get("compiler", {})
    kokkos = selected.get("kokkos", {})
    mpi = selected.get("mpi", {})
    cc = ""
    cxx = ""
    host_cxx = ""
    if isinstance(compiler, dict):
        cc = str(compiler.get("cc") or compiler.get("c") or "")
        cxx = str(compiler.get("cxx") or compiler.get("cpp") or "")
        host_cxx = str(compiler.get("host_cxx") or compiler.get("host_compiler") or "")
    if not cxx and isinstance(kokkos, dict):
        cxx = str(kokkos.get("nvcc_wrapper") or "")
    if not cc and host_cxx:
        cc = host_cxx
    mpicxx = ""
    if isinstance(mpi, dict):
        mpicxx = str(mpi.get("mpicxx") or "")
    return cc, cxx, host_cxx or cc, mpicxx


def shell_export(name: str, value: str) -> str:
    return f"export {name}={shlex.quote(value)}"


def shell_path_export(name: str, values: list[str]) -> str:
    values = unique(values)
    if not values:
        return f"# {name}: no entries generated"
    joined = ":".join(values)
    return f"export {name}={shlex.quote(joined)}${{{name}:+:${name}}}"


def require_compatibility_pass(data: dict[str, Any], allow_incomplete: bool) -> None:
    if allow_incomplete:
        return
    compatibility = data.get("compatibility", {})
    status = ""
    if isinstance(compatibility, dict):
        status = str(compatibility.get("status") or "")
    if status != "pass":
        raise SystemExit(
            "entity-deps.local.json compatibility.status must be pass before env.sh generation "
            "(use --allow-incomplete only for debugging)"
        )


def generate_env(data: dict[str, Any], json_path: Path) -> str:
    selected = data.get("selected", {})
    if not isinstance(selected, dict):
        selected = {}
    paths = data.get("paths", {})
    if not isinstance(paths, dict):
        paths = {}

    prefixes = unique([str(paths.get("ENTITY_DEPS_ROOT") or "")] + dep_prefixes(selected))
    deps_root = prefixes[0] if prefixes else str(json_path.parent)
    path_entries = unique([*(paths.get("PATH") or []), *dep_bins(selected)])
    cmake_entries = unique([*(paths.get("CMAKE_PREFIX_PATH") or []), *dep_prefixes(selected)])
    ld_entries = unique([*(paths.get("LD_LIBRARY_PATH") or []), *dep_libs(selected)])
    dyld_entries = unique([*(paths.get("DYLD_LIBRARY_PATH") or [])])

    cc, cxx, host_cxx, mpicxx = selected_compiler(selected)

    lines = [
        "#!/usr/bin/env bash",
        "# Generated from entity-deps.local.json. Do not edit by hand.",
        "set -euo pipefail",
        shell_export("ENTITY_DEPS_JSON", str(json_path.resolve())),
        shell_export("ENTITY_DEPS_ROOT", deps_root),
        shell_path_export("PATH", path_entries),
        shell_path_export("CMAKE_PREFIX_PATH", cmake_entries),
        shell_path_export("LD_LIBRARY_PATH", ld_entries),
    ]
    if dyld_entries:
        lines.append(shell_path_export("DYLD_LIBRARY_PATH", dyld_entries))
    if cc:
        lines.append(shell_export("CC", cc))
    if cxx:
        lines.append(shell_export("CXX", cxx))
    if "nvcc_wrapper" in Path(cxx).name and host_cxx:
        lines.append(shell_export("NVCC_WRAPPER_DEFAULT_COMPILER", host_cxx))
    if mpicxx:
        lines.append(shell_export("MPICXX", mpicxx))

    # Extra environment variables (ROCM_PATH, OMPI_CC, HSA_OVERRIDE_GFX_VERSION, etc.)
    extra_env = paths.get("extra_env", {}) if isinstance(paths, dict) else {}
    if isinstance(extra_env, dict) and extra_env:
        lines.append("")
        lines.append("# Site-specific environment overrides from entity-deps.local.json")
        for var, val in extra_env.items():
            if val:
                lines.append(shell_export(str(var), str(val)))

    lines.append("")
    return "\n".join(lines)


def default_output_path(data: dict[str, Any], json_path: Path) -> Path:
    env_sh = data.get("env_sh", {})
    if isinstance(env_sh, dict) and env_sh.get("path"):
        return Path(str(env_sh["path"]))
    artifacts = data.get("artifacts", {})
    if isinstance(artifacts, dict) and artifacts.get("env_sh"):
        return Path(str(artifacts["env_sh"]))
    requirements = data.get("requirements", {})
    if isinstance(requirements, dict):
        entity = requirements.get("entity", {})
        if isinstance(entity, dict) and entity.get("workdir"):
            return Path(str(entity["workdir"])) / "env.sh"
    env_workdir = os.environ.get("ENTITY_WORKDIR")
    if env_workdir:
        return Path(env_workdir) / "env.sh"
    return json_path.parent / "env.sh"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("json_path", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--allow-incomplete", action="store_true")
    parser.add_argument("--no-update-json", action="store_true")
    args = parser.parse_args()

    data = load_json(args.json_path)
    require_compatibility_pass(data, args.allow_incomplete)
    if args.output is None:
        args.output = default_output_path(data, args.json_path)
    script = generate_env(data, args.json_path)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(script, encoding="utf-8")
    args.output.chmod(0o755)

    if not args.no_update_json:
        env_sh = data.setdefault("env_sh", {})
        if not isinstance(env_sh, dict):
            env_sh = {}
            data["env_sh"] = env_sh
        env_sh.update(
            {
                "path": str(args.output.resolve()),
                "status": "generated",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "generated_from_checkpoint": str(args.json_path.resolve()),
                "validation": {"bash_syntax": "not_run", "commands": []},
            }
        )
        write_json_atomic(args.json_path, data)


if __name__ == "__main__":
    main()
