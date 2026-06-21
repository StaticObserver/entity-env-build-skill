#!/usr/bin/env python3
"""Generate local source-build scripts for Entity dependencies.

The generated scripts are adapted to entity-env-build's layout:
ENTITY_CHECKOUT stays clean, while generated scripts, logs, source trees,
build trees, and install prefixes live under ENTITY_WORKDIR by default.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from _version_profile import (
    DEFAULT_HDF5_VERSION,
    DEFAULT_VERSION_PROFILES as _DEFAULT_VERSION_PROFILES,
    requested_version,
    version_profile,
)


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


# Backwards-compatible aliases for callers within this module
DEFAULT_VERSION_PROFILES = _DEFAULT_VERSION_PROFILES
entity_version_profile = version_profile


def get_workdir(req: dict[str, Any]) -> Path:
    entity = req.get("entity", {})
    if isinstance(entity, dict) and entity.get("workdir"):
        return Path(str(entity["workdir"]))
    env_workdir = os.environ.get("ENTITY_WORKDIR")
    if env_workdir:
        return Path(env_workdir)
    raise SystemExit("requirements.json missing entity.workdir and ENTITY_WORKDIR is unset")


def dep_list(value: str | None, req: dict[str, Any]) -> list[str]:
    if value:
        deps = [item.strip().lower() for item in value.split(",") if item.strip()]
        unknown = [dep for dep in deps if dep not in {"kokkos", "hdf5", "adios2", "mpi"}]
        if unknown:
            raise SystemExit(f"unsupported dependencies: {', '.join(unknown)}")
        return deps
    env = req.get("environment", {})
    deps = ["kokkos"]
    if isinstance(env, dict) and env.get("mpi") and env.get("build_mpi_from_source"):
        deps.insert(0, "mpi")
    if not isinstance(env, dict) or env.get("output", True):
        deps.extend(["hdf5", "adios2"])
    return deps


def compiler_env(checkpoint: dict[str, Any]) -> dict[str, str]:
    selected = checkpoint.get("selected", {})
    compiler = selected.get("compiler", {}) if isinstance(selected, dict) else {}
    mpi = selected.get("mpi", {}) if isinstance(selected, dict) else {}
    out = {
        "CC": str(compiler.get("cc") or os.environ.get("CC", "")),
        "CXX": str(compiler.get("cxx") or os.environ.get("CXX", "")),
        "HOST_CXX": str(compiler.get("host_cxx") or compiler.get("host_compiler") or ""),
        "MPICXX": str(mpi.get("mpicxx") or os.environ.get("MPICXX", "")),
    }
    if not out["HOST_CXX"]:
        out["HOST_CXX"] = out["CXX"]
    return out


def script_header(name: str, workdir: Path, prefix: Path, compilers: dict[str, str]) -> str:
    lines = [
        "#!/usr/bin/env bash",
        f"# Generated dependency build script for {name}. Review before execution.",
        "set -euo pipefail",
        'if [ -z "${ENTITY_WORKDIR:-}" ]; then',
        f"  ENTITY_WORKDIR={q(workdir)}",
        "fi",
        "export ENTITY_WORKDIR",
        'if [ -z "${PREFIX:-}" ]; then',
        f"  PREFIX={q(prefix)}",
        "fi",
        "export PREFIX",
        'SRC_ROOT="${ENTITY_WORKDIR}/generated/source-trees"',
        'BUILD_ROOT="${ENTITY_WORKDIR}/generated/source-builds"',
        'LOG_DIR="${ENTITY_WORKDIR}/logs"',
        "mkdir -p \"$SRC_ROOT\" \"$BUILD_ROOT\" \"$PREFIX\" \"$LOG_DIR\"",
    ]
    for key in ("CC", "CXX", "MPICXX"):
        if compilers.get(key):
            lines.append(f"export {key}={q(compilers[key])}")
    if compilers.get("HOST_CXX") and "nvcc_wrapper" in Path(compilers.get("CXX", "")).name:
        lines.append(f"export NVCC_WRAPPER_DEFAULT_COMPILER={q(compilers['HOST_CXX'])}")
    lines.append("")
    return "\n".join(lines)


def kokkos_script(req: dict[str, Any], checkpoint: dict[str, Any], workdir: Path) -> str:
    env = req.get("environment", {})
    compilers = compiler_env(checkpoint)
    prefix = workdir / "deps" / "kokkos"
    profile = entity_version_profile(req)
    version = requested_version(req, "kokkos", profile)
    backend = str(env.get("backend") or "cpu").lower() if isinstance(env, dict) else "cpu"
    arch = str(env.get("gpu_arch") or "") if isinstance(env, dict) else ""
    opts = [
        "-DCMAKE_INSTALL_PREFIX=\"$PREFIX\"",
        "-DCMAKE_CXX_EXTENSIONS=OFF",
        "-DCMAKE_POSITION_INDEPENDENT_CODE=TRUE",
        "-DKokkos_ENABLE_SERIAL=ON",
        "-DKokkos_ENABLE_OPENMP=ON" if backend == "cpu" else "",
        "-DKokkos_ENABLE_CUDA=ON" if backend == "cuda" else "",
        "-DKokkos_ENABLE_HIP=ON" if backend == "hip" else "",
        "-DKokkos_ENABLE_PIC=ON",
        f"-DCMAKE_CXX_STANDARD={profile['cxx_standard']}",
    ]
    if arch:
        opts.append(f"-DKokkos_ARCH_{arch}=ON" if not arch.startswith("Kokkos_ARCH_") else f"-D{arch}=ON")
    opts = [opt for opt in opts if opt]
    cuda_wrapper_block = ""
    if backend == "cuda":
        host_cxx = compilers.get("HOST_CXX") or compilers.get("CXX") or "c++"
        cuda_wrapper_block = f"""
if [ -z "${{NVCC_WRAPPER_DEFAULT_COMPILER:-}}" ]; then
  export NVCC_WRAPPER_DEFAULT_COMPILER={q(host_cxx)}
fi
export CXX="$SRC/bin/nvcc_wrapper"
"""
    return (
        script_header("kokkos", workdir, prefix, compilers)
        + f"""
VERSION="${{KOKKOS_VERSION:-{version}}}"
SRC="$SRC_ROOT/kokkos-$VERSION"
BUILD="$BUILD_ROOT/kokkos-$VERSION"
if [ ! -d "$SRC/.git" ]; then
  git clone --depth 1 --branch "$VERSION" https://github.com/kokkos/kokkos.git "$SRC"
fi
{cuda_wrapper_block}
cmake -S "$SRC" -B "$BUILD" \\
  {' '.join(opts)} 2>&1 | tee "$LOG_DIR/kokkos-configure.log"
cmake --build "$BUILD" -j "${{NCORES:-$(sysctl -n hw.ncpu 2>/dev/null || nproc 2>/dev/null || echo 4)}}" 2>&1 | tee "$LOG_DIR/kokkos-build.log"
cmake --install "$BUILD" 2>&1 | tee "$LOG_DIR/kokkos-install.log"
"""
    )


def hdf5_script(req: dict[str, Any], checkpoint: dict[str, Any], workdir: Path) -> str:
    env = req.get("environment", {})
    compilers = compiler_env(checkpoint)
    prefix = workdir / "deps" / "hdf5"
    version = requested_version(req, "hdf5", entity_version_profile(req))
    mpi_on = bool(env.get("mpi")) if isinstance(env, dict) else False
    parallel = "-DHDF5_ENABLE_PARALLEL=ON" if mpi_on else "-DHDF5_ENABLE_PARALLEL=OFF"
    return (
        script_header("hdf5", workdir, prefix, compilers)
        + f"""
VERSION="${{HDF5_VERSION:-{version}}}"
SRC="$SRC_ROOT/hdf5-$VERSION"
BUILD="$BUILD_ROOT/hdf5-$VERSION"
if [ ! -d "$SRC/.git" ]; then
  git clone --depth 1 --branch "hdf5_$VERSION" https://github.com/HDFGroup/hdf5.git "$SRC"
fi
cmake -S "$SRC" -B "$BUILD" \\
  -DCMAKE_INSTALL_PREFIX="$PREFIX" \\
  -DHDF5_BUILD_CPP_LIB=ON \\
  {parallel} 2>&1 | tee "$LOG_DIR/hdf5-configure.log"
cmake --build "$BUILD" -j "${{NCORES:-$(sysctl -n hw.ncpu 2>/dev/null || nproc 2>/dev/null || echo 4)}}" 2>&1 | tee "$LOG_DIR/hdf5-build.log"
cmake --install "$BUILD" 2>&1 | tee "$LOG_DIR/hdf5-install.log"
"""
    )


def adios2_script(req: dict[str, Any], checkpoint: dict[str, Any], workdir: Path) -> str:
    env = req.get("environment", {})
    compilers = compiler_env(checkpoint)
    prefix = workdir / "deps" / "adios2"
    profile = entity_version_profile(req)
    version = requested_version(req, "adios2", profile)
    mpi_on = bool(env.get("mpi")) if isinstance(env, dict) else False
    backend = str(env.get("backend") or "cpu").lower() if isinstance(env, dict) else "cpu"
    prefix_parts = [str(workdir / "deps" / "hdf5")]
    if profile["adios2_uses_kokkos"]:
        prefix_parts.insert(0, str(workdir / "deps" / "kokkos"))
    cmake_prefix_base = ":".join(prefix_parts)
    opts = [
        "-DCMAKE_INSTALL_PREFIX=\"$PREFIX\"",
        f"-DCMAKE_CXX_STANDARD={profile['cxx_standard']}",
        "-DCMAKE_CXX_EXTENSIONS=OFF",
        "-DCMAKE_POSITION_INDEPENDENT_CODE=TRUE",
        "-DBUILD_SHARED_LIBS=ON",
        "-DADIOS2_USE_Python=OFF",
        "-DADIOS2_USE_Fortran=OFF",
        "-DADIOS2_USE_ZeroMQ=OFF",
        "-DBUILD_TESTING=OFF",
        "-DADIOS2_BUILD_EXAMPLES=OFF",
        f"-DADIOS2_USE_MPI={'ON' if mpi_on else 'OFF'}",
        "-DADIOS2_USE_HDF5=ON",
        f"-DADIOS2_HAVE_HDF5_VOL={'ON' if mpi_on else 'OFF'}",
        f"-DADIOS2_USE_Kokkos={'ON' if profile['adios2_uses_kokkos'] else 'OFF'}",
        "-DADIOS2_USE_CUDA=ON" if backend == "cuda" and not profile["adios2_uses_kokkos"] else "",
    ]
    opts = [opt for opt in opts if opt]
    return (
        script_header("adios2", workdir, prefix, compilers)
        + f"""
VERSION="${{ADIOS2_VERSION:-v{version}}}"
SRC="$SRC_ROOT/ADIOS2-$VERSION"
BUILD="$BUILD_ROOT/ADIOS2-$VERSION"
CMAKE_PREFIX_PATH_BASE={q(cmake_prefix_base)}
export CMAKE_PREFIX_PATH="${{CMAKE_PREFIX_PATH_BASE}}${{CMAKE_PREFIX_PATH:+:$CMAKE_PREFIX_PATH}}"
if [ ! -d "$SRC/.git" ]; then
  git clone --depth 1 --branch "$VERSION" https://github.com/ornladios/ADIOS2.git "$SRC"
fi
cmake -S "$SRC" -B "$BUILD" \\
  {' '.join(opts)} 2>&1 | tee "$LOG_DIR/adios2-configure.log"
cmake --build "$BUILD" -j "${{NCORES:-$(sysctl -n hw.ncpu 2>/dev/null || nproc 2>/dev/null || echo 4)}}" 2>&1 | tee "$LOG_DIR/adios2-build.log"
cmake --install "$BUILD" 2>&1 | tee "$LOG_DIR/adios2-install.log"
"""
    )


def mpi_script(req: dict[str, Any], checkpoint: dict[str, Any], workdir: Path) -> str:
    compilers = compiler_env(checkpoint)
    prefix = workdir / "deps" / "openmpi"
    return (
        script_header("openmpi", workdir, prefix, compilers)
        + """
cat >&2 <<'MSG'
OpenMPI source build is intentionally not auto-generated yet.
Prefer a system/module MPI. If source MPI is required, add a reviewed
OpenMPI+UCX script here and record the reason in entity-deps.local.json.
MSG
exit 2
"""
    )


SCRIPT_FACTORIES = {
    "kokkos": kokkos_script,
    "hdf5": hdf5_script,
    "adios2": adios2_script,
    "mpi": mpi_script,
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("requirements_json", type=Path)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--deps", help="Comma-separated deps: mpi,kokkos,hdf5,adios2")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--no-update-json", action="store_true")
    args = parser.parse_args()

    req = load_json(args.requirements_json)
    checkpoint = load_json(args.checkpoint)
    workdir = get_workdir(req)
    out_dir = args.output_dir or workdir / "generated" / "source-build-scripts"
    out_dir.mkdir(parents=True, exist_ok=True)
    scripts: dict[str, dict[str, str]] = {}
    profile = entity_version_profile(req)
    for dep in dep_list(args.deps, req):
        text = SCRIPT_FACTORIES[dep](req, checkpoint, workdir)
        path = out_dir / f"build-{dep}.sh"
        path.write_text(text, encoding="utf-8")
        path.chmod(0o755)
        scripts[dep] = {
            "path": str(path.resolve()),
            "status": "generated",
            "source": "entity-env-build/scripts/generate_dependency_build_scripts.py",
            "based_on": "Entity dependencies.py/wiki dependency generator",
            "version_profile": str(profile["name"]),
            "cxx_standard": str(profile["cxx_standard"]),
            "version": requested_version(req, dep, profile),
        }
        if dep == "adios2":
            scripts[dep]["adios2_uses_kokkos"] = "true" if profile["adios2_uses_kokkos"] else "false"

    if not args.no_update_json:
        build_scripts = checkpoint.setdefault("build_scripts", {})
        if not isinstance(build_scripts, dict):
            build_scripts = {}
            checkpoint["build_scripts"] = build_scripts
        build_scripts.update(
            {
                "directory": str(out_dir.resolve()),
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "version_profile": str(profile["name"]),
                "cxx_standard": str(profile["cxx_standard"]),
                "scripts": scripts,
            }
        )
        write_json_atomic(args.checkpoint, checkpoint)


if __name__ == "__main__":
    main()
