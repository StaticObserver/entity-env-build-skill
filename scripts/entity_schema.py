"""Single source of truth for JSON schemas, field definitions, and profile constants.

All entity-env-build scripts import their schema-level constants from here.
When a requirements.json field changes, this is the only Python file that
needs updating — scripts pick up the change through their imports.

references/json-contracts.md is the human-readable mirror of this file.
"""

from typing import Any, Dict, List

# ---------------------------------------------------------------------------
# Version profiles (moved from _version_profile.py)
# ---------------------------------------------------------------------------

PROFILES: Dict[str, Dict[str, Any]] = {
    "legacy": {
        "cxx_standard": "17",
        "kokkos": "4.",
        "adios2": "2.10.",
        "adios2_uses_kokkos": False,
    },
    "modern": {
        "cxx_standard": "20",
        "kokkos": "5.",
        "adios2": "2.11.",
        "adios2_uses_kokkos": True,
    },
}

DEFAULT_VERSION_PROFILES: Dict[str, Dict[str, Any]] = {
    "legacy": {
        "name": "legacy",
        "cxx_standard": "17",
        "kokkos_family": "4.x",
        "kokkos_default": "",
        "adios2_family": "2.10.x",
        "adios2": "2.10.2",
        "adios2_uses_kokkos": False,
    },
    "modern": {
        "name": "modern",
        "cxx_standard": "20",
        "kokkos_family": "5.x",
        "kokkos_default": "5.0.1",
        "adios2_family": "2.11.x",
        "adios2": "2.11.0",
        "adios2_uses_kokkos": True,
    },
}

DEFAULT_HDF5_VERSION = "1.14.6"


# ---------------------------------------------------------------------------
# requirements.json — Required fields by build phase
# ---------------------------------------------------------------------------

REQUIRED_ALWAYS: List[str] = [
    "entity.checkout_root",
    "entity.workdir",
]

REQUIRED_BUILD: List[str] = [
    "compile.pgen",
    "environment.backend",
]

# ---------------------------------------------------------------------------
# requirements.json — Defaults for optional fields
# ---------------------------------------------------------------------------

OPTIONAL_DEFAULTS: Dict[str, str] = {
    "entity.dependency_profile": "auto-detect from entity.version_bucket",
    "environment.output": "true",
    "environment.mpi": "false",
    "environment.gpu_aware_mpi": "false",
    "compile.precision": "single",
    "compile.deposit": "zigzag",
    "compile.shape_order": "1",
    "compile.debug": "false",
    "compile.tests": "false",
    "compile.build_intent": "unspecified",
    "compile.cxx_standard": "profile-derived",
}

# ---------------------------------------------------------------------------
# requirements.json — Consistency rules
# ---------------------------------------------------------------------------

# (rule_id, condition_tuple, field_pair, message)
ConsistencyRule = tuple  # (str, tuple | None, tuple, str)

CONSISTENCY_RULES: List[ConsistencyRule] = [
    ("pgen.mutex", None, ("compile.pgen", "compile.pgens"),
     "compile.pgen and compile.pgens are mutually exclusive. Use one."),
    ("output.requires_adios2", None, ("environment.output", None),
     "environment.output=true requires ADIOS2 and HDF5 in the dependency plan."),
    ("cuda.requires_nvcc", ("environment.backend", "cuda"), ("compile.cxx_standard", None),
     "CUDA backend requires Kokkos nvcc_wrapper as CXX."),
    ("hip.requires_rocm", ("environment.backend", "hip"), ("compile.cxx_standard", None),
     "HIP backend requires ROCm/hipcc toolchain and HIP-aware Kokkos."),
]

# ---------------------------------------------------------------------------
# entity-deps.local.json — Dependency entry shape
# ---------------------------------------------------------------------------

DEPENDENCY_ENTRY_KEYS: List[str] = [
    "name",
    "version",
    "provider",
    "prefix",
    "bin",
    "include",
    "lib",
    "cmake_config",
    "compiler_signature",
    "mpi_signature",
    "environment",
    "compile_config",
    "validation",
]

# ---------------------------------------------------------------------------
# Compile options → CMake flag mapping
# ---------------------------------------------------------------------------

# Maps requirements.compile field → CMake -D flag.
# Used by entity_generate.py to derive cmake options without hardcoding.
CMAKE_BOOL_MAP: Dict[str, str] = {
    "debug": "DEBUG",
    "tests": "TESTS",
}

CMAKE_VALUE_MAP: Dict[str, str] = {
    "precision": "precision",
    "deposit": "deposit",
    "shape_order": "shape_order",
}

# Environment-level CMake flags (from requirements.environment)
CMAKE_ENV_MAP: Dict[str, str] = {
    "output": "output",
    "mpi": "mpi",
    "gpu_aware_mpi": "gpu_aware_mpi",
}

# Backend → Kokkos CMake flags
KOKKOS_BACKEND_FLAGS: Dict[str, str] = {
    "cuda": "Kokkos_ENABLE_CUDA",
    "hip": "Kokkos_ENABLE_HIP",
    "cpu": "Kokkos_ENABLE_OPENMP",
}

# ---------------------------------------------------------------------------
# source-build dependency list (order matters)
# ---------------------------------------------------------------------------

SOURCE_BUILD_DEPENDENCIES: List[str] = ["kokkos", "hdf5", "adios2"]
OPTIONAL_SOURCE_DEPENDENCIES: List[str] = ["mpi"]
