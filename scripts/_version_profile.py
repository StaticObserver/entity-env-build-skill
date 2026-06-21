"""Shared Entity version profile logic.

Used by check_compatibility.py, generate_dependency_build_scripts.py,
and generate_entity_build_sh.py to avoid duplicating the legacy/modern
profile derivation and version-family constants.
"""

from typing import Any, Dict, Tuple


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


def detect_profile_name(req: Dict[str, Any]) -> str:
    """Return 'legacy' or 'modern' based on requirements.entity fields."""
    entity = req.get("entity", {})
    if not isinstance(entity, dict):
        raise ValueError("requirements.entity is missing")

    profile = str(entity.get("dependency_profile") or "").lower()
    if profile in PROFILES:
        return profile

    version = str(entity.get("version_bucket") or entity.get("version") or "").lower()
    if not version:
        raise ValueError(
            "requirements.entity.version_bucket or dependency_profile is required"
        )

    digits = []
    for part in version.removeprefix("v").replace("x", "0").split("."):
        if part.isdigit():
            digits.append(int(part))
        else:
            break

    if len(digits) >= 2 and (digits[0], digits[1]) <= (1, 4):
        return "legacy"
    return "modern"


def profile_for(req: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    """Return (profile_name, profile_dict) suitable for compatibility checks."""
    name = detect_profile_name(req)
    return name, PROFILES[name]


def version_profile(req: Dict[str, Any]) -> Dict[str, Any]:
    """Return the full default-version profile dict (for source-build scripts)."""
    name = detect_profile_name(req)
    return DEFAULT_VERSION_PROFILES[name]


def inferred_cxx_standard(req: Dict[str, Any]) -> str:
    """Derive C++ standard from requirements.compile or entity profile."""
    compile_cfg = req.get("compile", {})
    if isinstance(compile_cfg, dict) and compile_cfg.get("cxx_standard"):
        return str(compile_cfg["cxx_standard"])

    entity = req.get("entity", {})
    if isinstance(entity, dict):
        profile = str(entity.get("dependency_profile") or "").lower()
        if profile in PROFILES:
            return PROFILES[profile]["cxx_standard"]
        version = str(
            entity.get("version_bucket") or entity.get("version") or ""
        ).lower()
        if not version:
            raise SystemExit(
                "requirements.json missing entity.version_bucket or entity.dependency_profile"
            )
        digits = []
        for part in version.removeprefix("v").replace("x", "0").split("."):
            if part.isdigit():
                digits.append(int(part))
            else:
                break
        if len(digits) >= 2 and (digits[0], digits[1]) <= (1, 4):
            return "17"
        if len(digits) >= 2:
            return "20"
    raise SystemExit(
        "requirements.json missing entity.version_bucket or entity.dependency_profile"
    )


def requested_version(req: Dict[str, Any], dep: str, profile: Dict[str, Any]) -> str:
    """Return the concrete source-build tag for *dep*.

    Consults requirements.environment.dependency_versions first, then falls
    back to profile defaults.  Raises SystemExit for legacy kokkos without
    a user-pinned tag.
    """
    env = req.get("environment", {})
    versions = env.get("dependency_versions", {}) if isinstance(env, dict) else {}
    if isinstance(versions, dict) and versions.get(dep):
        return str(versions[dep])

    if dep == "kokkos":
        default = str(profile.get("kokkos_default") or "")
        if default:
            return default
        raise SystemExit(
            "legacy profile requires requirements.environment.dependency_versions.kokkos "
            "to pin an exact Kokkos 4.x source-build tag"
        )
    if dep == "adios2":
        return str(profile["adios2"])
    if dep == "hdf5":
        return DEFAULT_HDF5_VERSION
    raise KeyError(dep)
