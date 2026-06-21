#!/usr/bin/env python3
"""Generate entity-build.sh from requirements.json and env.sh."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from _version_profile import inferred_cxx_standard


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


def q(value: Any) -> str:
    return shlex.quote(str(value))


def bool_on(value: Any) -> str:
    return "ON" if bool(value) else "OFF"


def _verify_checkpoint_gate(checkpoint: dict[str, Any], env_sh: Path) -> None:
    """Verify compatibility and env.sh are consistent before allowing build script generation."""
    compat = checkpoint.get("compatibility", {})
    if not isinstance(compat, dict):
        raise SystemExit("entity-deps.local.json missing compatibility section")
    if compat.get("status") != "pass":
        raise SystemExit(
            f"entity-deps.local.json compatibility.status={compat.get('status')}, must be 'pass'. "
            f"Run check_compatibility.py first."
        )

    checkpoint_env = checkpoint.get("env_sh", {})
    if isinstance(checkpoint_env, dict):
        recorded_path = checkpoint_env.get("path", "")
        if recorded_path and Path(recorded_path).resolve() != env_sh.resolve():
            print(
                f"WARNING: checkpoint env_sh.path ({recorded_path}) differs from "
                f"--env argument ({env_sh}). The env.sh may be stale or from a different "
                f"checkpoint. Proceeding but verify this is intentional.",
                file=sys.stderr,
            )

    ck_status = checkpoint.get("status", {})
    if isinstance(ck_status, dict) and ck_status.get("ready_for_entity_build") is False:
        print(
            "WARNING: checkpoint status.ready_for_entity_build is False. "
            "Proceeding but ensure the environment is ready.",
            file=sys.stderr,
        )


def require_string(obj: dict[str, Any], path: str) -> str:
    cur: Any = obj
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            raise SystemExit(f"requirements.json missing required field: {path}")
        cur = cur[part]
    if cur in (None, ""):
        raise SystemExit(f"requirements.json field is empty: {path}")
    return str(cur)


def default_build_dir(req: dict[str, Any]) -> str:
    compile_cfg = req.get("compile", {})
    env = req.get("environment", {})
    entity = req.get("entity", {})
    workdir = ""
    if isinstance(entity, dict):
        workdir = str(entity.get("workdir") or "")
    if not workdir:
        workdir = os.environ.get("ENTITY_WORKDIR", "")
    if not workdir:
        raise SystemExit("requirements.json missing required field: entity.workdir")
    pgen_value = compile_cfg.get("pgen") or compile_cfg.get("pgens") or "entity"
    if isinstance(pgen_value, list):
        pgen = ",".join(str(item) for item in pgen_value)
    else:
        pgen = str(pgen_value)
    backend = str(env.get("backend") or "cpu")
    mpi = "mpi" if env.get("mpi") else "serial"
    intent = str(compile_cfg.get("build_intent") or "build")
    safe = "-".join([pgen.replace("/", "-"), backend, mpi, intent])
    return str(Path(workdir) / "build" / safe)


def cmake_options(req: dict[str, Any]) -> list[str]:
    env = req.get("environment", {})
    compile_cfg = req.get("compile", {})
    pgen = compile_cfg.get("pgen")
    pgens = compile_cfg.get("pgens")
    if not pgen and not pgens:
        raise SystemExit("requirements.json missing required field: compile.pgen or compile.pgens")
    opts = [
        f"-Dprecision={compile_cfg.get('precision', 'single')}",
        f"-Ddeposit={compile_cfg.get('deposit', 'zigzag')}",
        f"-Dshape_order={compile_cfg.get('shape_order', 1)}",
        f"-Doutput={bool_on(env.get('output', True))}",
        f"-Dmpi={bool_on(env.get('mpi', False))}",
        f"-Dgpu_aware_mpi={bool_on(env.get('gpu_aware_mpi', False))}",
        f"-DDEBUG={bool_on(compile_cfg.get('debug', False))}",
        f"-DTESTS={bool_on(compile_cfg.get('tests', False))}",
        f"-DCMAKE_CXX_STANDARD={inferred_cxx_standard(req)}",
    ]
    if pgen:
        opts.insert(0, f"-Dpgen={pgen}")
    else:
        if isinstance(pgens, list):
            pgens = ",".join(str(item) for item in pgens)
        opts.insert(0, f"-Dpgens={pgens}")
    backend = str(env.get("backend") or "cpu").lower()
    gpu_arch = str(env.get("gpu_arch") or "")
    if backend == "cuda":
        opts.append("-DKokkos_ENABLE_CUDA=ON")
    elif backend == "hip":
        opts.append("-DKokkos_ENABLE_HIP=ON")
    elif backend == "cpu":
        opts.append("-DKokkos_ENABLE_OPENMP=ON")
    if gpu_arch:
        if gpu_arch.startswith("Kokkos_ARCH_"):
            opts.append(f"-D{gpu_arch}=ON")
        else:
            opts.append(f"-DKokkos_ARCH_{gpu_arch}=ON")
    install_prefix = compile_cfg.get("install_prefix")
    if compile_cfg.get("install") and install_prefix:
        opts.append(f"-DCMAKE_INSTALL_PREFIX={install_prefix}")
    for extra in compile_cfg.get("extra_cmake_options") or []:
        opts.append(str(extra))
    return opts


def shell_command(parts: list[str]) -> str:
    return " ".join(q(part) for part in parts)


def generate_script(req: dict[str, Any], req_path: Path, env_sh: Path) -> tuple[str, dict[str, str]]:
    checkout = require_string(req, "entity.checkout_root")
    workdir = require_string(req, "entity.workdir")
    compile_cfg = req.setdefault("compile", {})
    build_dir = str(compile_cfg.get("build_dir") or default_build_dir(req))
    compile_cfg["build_dir"] = build_dir
    compile_cfg["cxx_standard"] = inferred_cxx_standard(req)
    jobs = str(compile_cfg.get("jobs") or "")

    configure_parts = ["cmake", "-B", build_dir, *cmake_options(req)]
    build_parts = ["cmake", "--build", build_dir]
    if jobs:
        build_parts.extend(["-j", jobs])

    lines = [
        "#!/usr/bin/env bash",
        "# Generated from requirements.json and env.sh. Do not edit by hand.",
        "set -euo pipefail",
        f"source {q(env_sh.resolve())}",
        f"mkdir -p {q(Path(workdir) / 'logs')}",
        f"cd {q(checkout)}",
        shell_command(configure_parts),
        shell_command(build_parts),
    ]
    if compile_cfg.get("tests"):
        lines.append(shell_command(["ctest", "--test-dir", build_dir, "--output-on-failure"]))
    if compile_cfg.get("install"):
        lines.append(shell_command(["cmake", "--install", build_dir]))
    lines.append("")
    meta = {
        "configure_command": shell_command(configure_parts),
        "build_command": shell_command(build_parts),
        "expected_executable": str(Path(checkout) / build_dir / "src" / "entity.xc"),
    }
    return "\n".join(lines), meta


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("requirements_json", type=Path)
    parser.add_argument("--env", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, help="entity-deps.local.json for gate validation")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--no-update-json", action="store_true")
    args = parser.parse_args()

    req = load_json(args.requirements_json)
    if not args.env.exists():
        raise SystemExit(f"env.sh not found: {args.env}")

    if args.checkpoint:
        if not args.checkpoint.exists():
            raise SystemExit(f"entity-deps.local.json not found: {args.checkpoint}")
        checkpoint = load_json(args.checkpoint)
        _verify_checkpoint_gate(checkpoint, args.env.resolve())
        env_fingerprint = (
            checkpoint.get("env_sh", {}).get("generated_at", "")
            if isinstance(checkpoint.get("env_sh"), dict)
            else ""
        )
    else:
        print(
            "WARNING: --checkpoint not provided. Skipping compatibility gate validation. "
            "Use --checkpoint for production builds.",
            file=sys.stderr,
        )
        env_fingerprint = ""
    if args.output is None:
        artifacts = req.get("artifacts", {})
        if isinstance(artifacts, dict) and artifacts.get("entity_build_sh"):
            args.output = Path(str(artifacts["entity_build_sh"]))
        else:
            workdir = require_string(req, "entity.workdir")
            args.output = Path(workdir) / "entity-build.sh"
    script, meta = generate_script(req, args.requirements_json, args.env)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(script, encoding="utf-8")
    args.output.chmod(0o755)

    if not args.no_update_json:
        artifacts = req.setdefault("artifacts", {})
        if not isinstance(artifacts, dict):
            artifacts = {}
            req["artifacts"] = artifacts
        artifacts["entity_build_sh"] = str(args.output.resolve())
        build_script = req.setdefault("entity_build_script", {})
        if not isinstance(build_script, dict):
            build_script = {}
            req["entity_build_script"] = build_script
        build_script.update(
            {
                "path": str(args.output.resolve()),
                "status": "generated",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "generated_from": {
                    "requirements_json": str(args.requirements_json.resolve()),
                    "env_sh": str(args.env.resolve()),
                    "env_fingerprint": env_fingerprint,
                    "checkpoint_json": str(args.checkpoint.resolve()) if args.checkpoint else "",
                },
            }
        )
        result = req.setdefault("build_result", {})
        if not isinstance(result, dict):
            result = {}
            req["build_result"] = result
        result.update({"status": "not_run", **meta})
        write_json_atomic(args.requirements_json, req)


if __name__ == "__main__":
    main()
