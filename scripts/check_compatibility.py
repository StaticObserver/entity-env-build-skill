#!/usr/bin/env python3
"""Check whether entity-deps.local.json satisfies requirements.json."""

from __future__ import annotations

import argparse
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROFILES = {
    "legacy": {"cxx_standard": "17", "kokkos": "4.", "adios2": "2.10.", "adios2_uses_kokkos": False},
    "modern": {"cxx_standard": "20", "kokkos": "5.", "adios2": "2.11.", "adios2_uses_kokkos": True},
}


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


def profile_for(req: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    entity = req.get("entity", {})
    if not isinstance(entity, dict):
        raise ValueError("requirements.entity is missing")
    profile = str(entity.get("dependency_profile") or "").lower()
    if profile in PROFILES:
        return profile, PROFILES[profile]
    version = str(entity.get("version_bucket") or entity.get("version") or "").lower()
    if not version:
        raise ValueError("requirements.entity.version_bucket or dependency_profile is required")
    digits = []
    for part in version.removeprefix("v").replace("x", "0").split("."):
        if part.isdigit():
            digits.append(int(part))
        else:
            break
    if len(digits) >= 2 and (digits[0], digits[1]) <= (1, 4):
        return "legacy", PROFILES["legacy"]
    return "modern", PROFILES["modern"]


def selected_version(checkpoint: dict[str, Any], dep: str) -> str:
    selected = checkpoint.get("selected", {})
    if isinstance(selected, dict) and isinstance(selected.get(dep), dict):
        version = selected[dep].get("version")
        if version:
            return str(version).lstrip("v")
    scripts = checkpoint.get("build_scripts", {}).get("scripts", {})
    if isinstance(scripts, dict) and isinstance(scripts.get(dep), dict):
        version = scripts[dep].get("version")
        if version:
            return str(version).lstrip("v")
    return ""


def adios2_uses_kokkos(checkpoint: dict[str, Any]) -> bool | None:
    selected = checkpoint.get("selected", {})
    adios2 = selected.get("adios2", {}) if isinstance(selected, dict) else {}
    if isinstance(adios2, dict):
        cfg = adios2.get("compile_config", {})
        if isinstance(cfg, dict):
            value = cfg.get("ADIOS2_USE_Kokkos", cfg.get("adios2_uses_kokkos"))
            if value is not None:
                return str(value).lower() in {"on", "true", "1", "yes"}
    scripts = checkpoint.get("build_scripts", {}).get("scripts", {})
    if isinstance(scripts, dict) and isinstance(scripts.get("adios2"), dict):
        value = scripts["adios2"].get("adios2_uses_kokkos")
        if value is not None:
            return str(value).lower() in {"on", "true", "1", "yes"}
    return None


def add(checks: list[dict[str, Any]], check_id: str, status: str, summary: str, evidence: dict[str, Any] | None = None) -> None:
    checks.append({"id": check_id, "status": status, "summary": summary, "evidence": evidence or {}, "remediation": ""})


def path_exists(value: Any) -> bool:
    return bool(value) and Path(str(value)).exists()


def selected_entry(checkpoint: dict[str, Any], dep: str) -> dict[str, Any]:
    selected = checkpoint.get("selected", {})
    if isinstance(selected, dict) and isinstance(selected.get(dep), dict):
        return selected[dep]
    return {}


def has_installed_dependency(checkpoint: dict[str, Any], dep: str) -> bool:
    entry = selected_entry(checkpoint, dep)
    if not entry:
        return False
    if entry.get("provider") == "source-build" and not entry.get("validation", {}).get("installed"):
        return False
    return bool(entry.get("prefix") or entry.get("cmake_config") or entry.get("bin"))


def run_checks(req: dict[str, Any], checkpoint: dict[str, Any]) -> tuple[str, list[dict[str, Any]], list[str]]:
    checks: list[dict[str, Any]] = []
    issues: list[str] = []

    try:
        profile_name, profile = profile_for(req)
        add(checks, "profile.detect", "pass", f"Using {profile_name} profile", {"profile": profile_name})
    except ValueError as exc:
        add(checks, "profile.detect", "fail", str(exc))
        issues.append(str(exc))
        return "fail", checks, issues

    compile_cfg = req.get("compile", {})
    cxx_standard = str(compile_cfg.get("cxx_standard") or profile["cxx_standard"]) if isinstance(compile_cfg, dict) else str(profile["cxx_standard"])
    if cxx_standard == profile["cxx_standard"]:
        add(checks, "profile.cxx_standard", "pass", "C++ standard matches Entity profile", {"cxx_standard": cxx_standard})
    else:
        add(checks, "profile.cxx_standard", "fail", "C++ standard does not match Entity profile", {"expected": profile["cxx_standard"], "actual": cxx_standard})
        issues.append("C++ standard does not match Entity profile")

    for dep, prefix in (("kokkos", profile["kokkos"]), ("adios2", profile["adios2"])):
        version = selected_version(checkpoint, dep)
        if version and version.startswith(prefix):
            add(checks, f"profile.{dep}_version", "pass", f"{dep} version matches profile", {"version": version})
        else:
            add(checks, f"profile.{dep}_version", "fail", f"{dep} version does not match profile", {"expected_prefix": prefix, "actual": version})
            issues.append(f"{dep} version does not match profile")

    uses_kokkos = adios2_uses_kokkos(checkpoint)
    if uses_kokkos is profile["adios2_uses_kokkos"]:
        add(checks, "profile.adios2_kokkos", "pass", "ADIOS2 Kokkos mode matches profile", {"adios2_uses_kokkos": uses_kokkos})
    else:
        add(checks, "profile.adios2_kokkos", "fail", "ADIOS2 Kokkos mode does not match profile", {"expected": profile["adios2_uses_kokkos"], "actual": uses_kokkos})
        issues.append("ADIOS2 Kokkos mode does not match profile")

    selected = checkpoint.get("selected", {})
    compiler = selected.get("compiler", {}) if isinstance(selected, dict) else {}
    compiler_ok = isinstance(compiler, dict) and bool(compiler.get("cxx"))
    add(checks, "compiler.selected", "pass" if compiler_ok else "fail", "C++ compiler is selected", {"compiler": compiler})
    if not compiler_ok:
        issues.append("C++ compiler is not selected")

    env = req.get("environment", {})
    backend = str(env.get("backend") or "cpu").lower() if isinstance(env, dict) else "cpu"
    if backend == "cuda":
        cxx = str(compiler.get("cxx") or selected_entry(checkpoint, "kokkos").get("nvcc_wrapper") or "")
        ok = "nvcc_wrapper" in Path(cxx).name
        add(checks, "backend.cuda.compiler", "pass" if ok else "fail", "CUDA backend uses Kokkos nvcc_wrapper", {"cxx": cxx})
        if not ok:
            issues.append("CUDA backend requires Kokkos nvcc_wrapper as CXX")
        adios2_script = checkpoint.get("build_scripts", {}).get("scripts", {}).get("adios2", {})
        script_path = adios2_script.get("path") if isinstance(adios2_script, dict) else ""
        if script_path and Path(str(script_path)).exists():
            text = Path(str(script_path)).read_text(encoding="utf-8")
            conflict = "ADIOS2_USE_Kokkos=ON" in text and "ADIOS2_USE_CUDA=ON" in text
            add(checks, "backend.cuda.adios2_flags", "fail" if conflict else "pass", "ADIOS2 Kokkos/CUDA flags are not mutually enabled", {"script": script_path})
            if conflict:
                issues.append("ADIOS2_USE_Kokkos and ADIOS2_USE_CUDA cannot both be ON")

    required = ["kokkos"]
    if isinstance(env, dict) and env.get("output", True):
        required.extend(["hdf5", "adios2"])
    if isinstance(env, dict) and env.get("mpi"):
        required.append("mpi")
    for dep in required:
        ok = has_installed_dependency(checkpoint, dep)
        add(checks, f"dependency.{dep}", "pass" if ok else "fail", f"{dep} has installed/discoverable evidence", selected_entry(checkpoint, dep))
        if not ok:
            issues.append(f"{dep} is missing installed/discoverable evidence")

    source_scripts = checkpoint.get("build_scripts", {}).get("scripts", {})
    if isinstance(source_scripts, dict):
        for dep, script in source_scripts.items():
            if isinstance(script, dict) and script.get("status") == "generated" and not has_installed_dependency(checkpoint, dep):
                add(checks, f"source_build.{dep}", "fail", "Generated source-build script has not produced installed dependency evidence", script)
                issues.append(f"{dep} source-build script has not produced installed dependency evidence")

    return ("pass" if not issues else "fail"), checks, issues


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("requirements_json", type=Path)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--no-update-json", action="store_true")
    args = parser.parse_args()

    req = load_json(args.requirements_json)
    checkpoint = load_json(args.checkpoint)
    status, checks, issues = run_checks(req, checkpoint)
    compatibility = {
        "status": status,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
        "issues": issues,
    }
    if not args.no_update_json:
        checkpoint["compatibility"] = compatibility
        write_json_atomic(args.checkpoint, checkpoint)
    print(json.dumps(compatibility, indent=2, sort_keys=True))
    if status != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
