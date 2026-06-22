# entity-env-build-skill

[中文](./README.md) | [English](./README.en.md)

---

`entity-env-build` prepares an Entity build environment and builds Entity itself. It splits one Entity build into three phases:

1. Confirm the current build requirements and write `requirements.json`.
2. Discover, select, and validate local dependencies, then write `entity-deps.local.json` and `env.sh`.
3. Generate and run `entity-build.sh` from `requirements.json + env.sh`.

## Core Constraints

- Reuse local/system dependencies by default; do not use Spack or Docker unless explicitly requested.
- Keep all dependencies on one consistent compiler/toolchain unless the user accepts the risk.
- CUDA builds use Kokkos `nvcc_wrapper`.
- Entity versions before `1.4.0` use `C++17 + Kokkos 4.x + ADIOS2 2.10.x`.
- Entity `1.4.0` and newer use `C++20 + Kokkos 5.x + ADIOS2 2.11.x`.
- Entity versions **before `1.4.3` are incompatible with CUDA backend + modern profile (C++20)**. NVCC's EDG frontend rejects C++20 `requires` constraints (`constraints on a non-templated function`) and TOML11's `std::source_location::current` consteval. Entity `1.4.3` (PR #210) replaced `requires` with `static_assert`, fixing this.
- Enable ADIOS2 Kokkos support only for the `Kokkos 5.x + ADIOS2 2.11.x` profile.
- Generate `env.sh` only after compatibility checks pass.

## Main Scripts

```text
scripts/entity_checkpoint.py   ← validate + create checkpoint
scripts/entity_checkpoint.py   ← record-install dependency evidence
scripts/entity_compat.py       ← compatibility check
scripts/entity_generate.py     ← deps / env / build generation
scripts/entity_run.py          ← run build scripts + record results
```

Before these commands, the agent must present the compile configuration summary
from `SKILL.md` and wait for explicit user confirmation. Environment probing and
old-checkpoint inspection start only after that confirmation.

## Typical Sequence

```bash
# Phase 1: Validate requirements
python3 scripts/entity_checkpoint.py validate "$ENTITY_WORKDIR/requirements.json"

# Phase 2: Create checkpoint
python3 scripts/entity_checkpoint.py create "$ENTITY_WORKDIR/requirements.json" \
  --output "$ENTITY_WORKDIR/entity-deps.local.json"

# Dependency source-build scripts (if needed)
python3 scripts/entity_generate.py deps "$ENTITY_WORKDIR/requirements.json" \
  --checkpoint "$ENTITY_WORKDIR/entity-deps.local.json"

# Record a completed source-build install (example)
python3 scripts/entity_checkpoint.py record-install \
  --checkpoint "$ENTITY_WORKDIR/entity-deps.local.json" \
  --dep kokkos \
  --prefix "$ENTITY_WORKDIR/deps/kokkos/5.0.1" \
  --cmake-config "$ENTITY_WORKDIR/deps/kokkos/5.0.1/lib64/cmake/Kokkos/KokkosConfig.cmake"

# Compatibility check
python3 scripts/entity_compat.py "$ENTITY_WORKDIR/requirements.json" \
  --checkpoint "$ENTITY_WORKDIR/entity-deps.local.json"

# Generate env.sh
python3 scripts/entity_generate.py env "$ENTITY_WORKDIR/entity-deps.local.json" \
  --output "$ENTITY_WORKDIR/env.sh"

# Phase 3: Generate entity-build.sh
python3 scripts/entity_generate.py build "$ENTITY_WORKDIR/requirements.json" \
  --env "$ENTITY_WORKDIR/env.sh" \
  --checkpoint "$ENTITY_WORKDIR/entity-deps.local.json" \
  --output "$ENTITY_WORKDIR/entity-build.sh"

# Run generated build script and update build_result
python3 scripts/entity_run.py build "$ENTITY_WORKDIR/requirements.json" \
  --script "$ENTITY_WORKDIR/entity-build.sh"
```

See `SKILL.md` and `references/` for the full contract.
