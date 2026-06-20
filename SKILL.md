---
name: entity-env-build
description: Configure, verify, and execute the build environment and source build flow for Entity. Use when the user needs to build Entity, prepare or repair local dependencies, choose CPU/CUDA/HIP/MPI/output support, generate requirements.json, generate or repair entity-deps.local.json, run compatibility checks, generate env.sh, generate entity-build.sh, or execute the verified build script.
---

# entity-env-build

## Mission

Build a reliable local dependency environment for the current Entity build request, then hand off to the Entity source build step.

This skill has three phases:

1. **Requirement phase**: collect the current user request and write `requirements.json`, including both environment requirements and Entity compile options.
2. **Environment phase**: use `requirements.json` to reuse or repair `entity-deps.local.json`, search local dependency candidates, choose a compatible dependency plan, run compatibility checks, and generate `env.sh`.
3. **Entity build phase**: generate `entity-build.sh` from `requirements.json` and `env.sh`, then execute that script to configure and build Entity.

The environment phase is complete only when:

- the JSON checkpoint satisfies the current request;
- compatibility checks pass;
- `env.sh` has been generated from the JSON;
- the JSON records the `env.sh` path and generation status.

The Entity build phase is complete only when `entity-build.sh` has been generated from `requirements.json + env.sh`, executed, and its configure/build result has been recorded. When designing JSON fields, read `references/json-contracts.md`; when designing configure commands, read `references/entity-compile-options.md`.

## Boundaries

Handle:

- CMake, C++ compiler, Kokkos, CUDA/HIP, MPI, ADIOS2, HDF5 dependency planning;
- user confirmation for build-relevant choices;
- local dependency discovery and candidate selection;
- dependency checkpoint JSON creation or repair;
- compatibility checking;
- generation of `env.sh` from the JSON;
- generation and execution of `entity-build.sh` from `requirements.json + env.sh`.

Do not handle:

- TOML or PGen design;
- physics parameter choices;
- output analysis;
- Entity core source changes.

Route those tasks to `entity-case`, `entity-analysis`, or `entity-core-dev`.

## Hard Rules

- Treat the current user request as the first input. Old JSON is reusable only if it satisfies this request.
- Require two explicit locations before writing artifacts: `ENTITY_CHECKOUT` for the Entity source tree and `ENTITY_WORKDIR` for this problem/build workspace. If either is missing or invalid, ask the user to confirm.
- Keep generated control files and build artifacts out of the source checkout by default; write them under `ENTITY_WORKDIR`.
- Write the current request to `requirements.json` before using or repairing environment checkpoints.
- Default dependency policy is local/system reuse first; no Spack or Docker unless the user explicitly asks.
- Core dependencies are always `CMake`, a C++ compiler, and `Kokkos`.
- Use `MPI` only when the current request requires parallel/multi-process or multi-node builds.
- Use output support by default. When `requirements.environment.output=true`, require `ADIOS2 + HDF5`.
- Unless the user explicitly accepts the risk, all dependencies must use one consistent, non-conflicting compiler/toolchain.
- Entity versions newer than `1.4.x` require `C++20`, `Kokkos 5.x`, and `ADIOS2 2.11.x`; Entity `1.4.x` and older use `C++17`, `Kokkos 4.x`, and `ADIOS2 2.10.x`.
- Only the `Kokkos 5.x + ADIOS2 2.11.x` profile builds ADIOS2 with Kokkos support. Other profiles must not add Kokkos as an ADIOS2 dependency unless the user explicitly overrides the profile.
- For CUDA backend builds, use Kokkos `nvcc_wrapper` as the C++ compiler, usually from `Kokkos source/install prefix/bin/nvcc_wrapper`. Record both wrapper path and host compiler.
- For source builds, generate local scripts with `scripts/generate_dependency_build_scripts.py`, using the Entity wiki dependency generator and `dependencies.py` rules as the minimal-options baseline. Record script source and any deviations.
- Do not enter Entity source compilation until compatibility is `pass` and `env.sh` is generated from `entity-deps.local.json`.
- Do not hand-write the Entity configure/build commands. Generate `entity-build.sh` from `requirements.json` and `env.sh`, then execute it.

## Build Workflow

Run the skill in this order:

```text
current user requirements
  -> confirm ENTITY_CHECKOUT and ENTITY_WORKDIR
  -> write/repair requirements.json
  -> locate/read local dependency checkpoint JSON
  -> compare dependency checkpoint against requirements.json
  -> repair missing/stale/conflicting JSON parts
  -> search local dependency candidates
  -> plan compatible selected dependencies
  -> user confirmation gate
  -> generate source-build scripts when approved dependencies must be built
  -> write dependency checkpoint JSON
  -> compatibility check
  -> generate env.sh from dependency checkpoint JSON
  -> generate entity-build.sh from requirements.json + env.sh
  -> execute entity-build.sh
```

### 1. Confirm Current Requirements And Write requirements.json

Start from the current user request, not from the old dependency JSON. Write the result to `requirements.json`; this file is the source of truth for the current build request.

Before writing files, resolve:

- `ENTITY_CHECKOUT`: the Entity source checkout to build.
- `ENTITY_WORKDIR`: the workspace for this problem/build configuration.

If these environment variables are unset, invalid, or ambiguous, ask the user. A typical layout is:

```text
$ENTITY_HOME/
├── sources/<entity-version>/
└── problems/<problem-name>/<build-name>/
```

Default artifact paths are:

```text
$ENTITY_WORKDIR/requirements.json
$ENTITY_WORKDIR/entity-deps.local.json
$ENTITY_WORKDIR/env.sh
$ENTITY_WORKDIR/entity-build.sh
$ENTITY_WORKDIR/build/
$ENTITY_WORKDIR/logs/
$ENTITY_WORKDIR/generated/source-build-scripts/
```

Derive or ask for:

```json
{
  "schema_version": 1,
  "generated_at": "",
  "entity": {
    "checkout_root": "",
    "version_bucket": "",
    "dependency_profile": "legacy|modern",
    "workdir": ""
  },
  "environment": {
    "backend": "cuda|hip|cpu|unspecified",
    "mpi": true,
    "gpu_aware_mpi": false,
    "output": true,
    "dependency_versions": {
      "kokkos": "",
      "adios2": "",
      "hdf5": ""
    },
    "dependency_policy": "reuse-existing|allow-local-build|unspecified"
  },
  "compile": {
    "cxx_standard": "17|20",
    "pgen": "",
    "pgens": "",
    "precision": "single|double",
    "deposit": "zigzag|esirkepov",
    "shape_order": 1,
    "debug": false,
    "tests": false,
    "build_intent": "smoke|production|debug|unspecified",
    "build_dir": "",
    "install": false,
    "install_prefix": "",
    "jobs": ""
  },
  "artifacts": {
    "dependency_checkpoint_json": "",
    "env_sh": "",
    "entity_build_sh": "",
    "logs_dir": "",
    "generated_dir": ""
  },
  "decisions": {},
  "status": {
    "complete": false
  }
}
```

Defaults:

- `backend`: prefer GPU when a viable GPU compiler/toolkit is available; if not found, ask before falling back to CPU.
- `mpi`: do not enable just because `mpicxx` exists. Ask unless the user request clearly implies MPI.
- `gpu_aware_mpi`: default `false` unless the user requests it or the environment is known reliable.
- `output`: default `true`; this implies `ADIOS2 + HDF5`.
- `dependency_policy`: prefer existing local/system dependencies; build missing dependencies from source only when needed or approved.
- `entity.dependency_profile`: derive from the Entity version unless the user overrides it. Use `legacy` for `1.4.x` and older, `modern` for newer than `1.4.x`.
- `compile.cxx_standard`: `17` for `legacy`, `20` for `modern`.
- `environment.dependency_versions`: optional exact source-build tags; if omitted, choose a profile-compatible concrete tag and record it.
- For `legacy` source builds, require an exact Kokkos 4.x tag in `environment.dependency_versions.kokkos` before generating the Kokkos build script.
- compile options: use official Entity defaults unless the user or selected build intent says otherwise: `precision=single`, `deposit=zigzag`, `shape_order=1`, `debug=false`, `tests=false`. Use either `pgen` or `pgens`, not both.

`requirements.json` may be partial while user confirmation is pending. Do not generate `entity-build.sh` until it is complete.

### 2. Locate And Read JSON Checkpoint

Default checkpoint filename:

```text
entity-deps.local.json
```

Location priority:

1. user-provided path;
2. `requirements.json.artifacts.dependency_checkpoint_json`;
3. `$ENTITY_WORKDIR/entity-deps.local.json`.

If the dependency JSON exists, parse it and check schema. If it does not exist, create a draft checkpoint in memory. Do not let an old complete dependency JSON override `requirements.json`.

Classify checkpoint state:

- `missing`: no usable file;
- `partial`: parseable but missing required sections;
- `stale`: paths, Entity version bucket, target node, or requirements no longer match;
- `complete`: structurally complete for the current requirements;
- `incompatible`: complete enough to evaluate but fails compatibility.

### 3. Compare Dependency JSON Against requirements.json

Reuse old dependency content only if it satisfies `requirements.json`.

Examples:

- old `backend=cpu`, current `backend=cuda` -> stale for this request;
- old `mpi=false`, current `mpi=true` -> only non-MPI parts may be reused;
- old `output=false`, current default `output=true` -> ADIOS2/HDF5 must be discovered and checked;
- old compiler differs from the current selected MPI wrapper compiler -> stale until confirmed or rebuilt.

Record this comparison under `status.satisfies_requirements_json` and `status.reuse_notes`.

### 4. Search Dependency Candidates

Search according to `requirements.json`.

Always search:

- `CMake`;
- C++ compilers;
- `Kokkos`.

Conditional search:

- `environment.backend=cuda`: CUDA toolkit, `nvcc`, Kokkos `nvcc_wrapper`;
- `environment.backend=hip`: HIP/ROCm toolkit, `hipcc`;
- `environment.mpi=true`: `mpicxx`, `mpirun`, MPI modules;
- `environment.output=true`: `ADIOS2`, `HDF5`.

For each candidate, record:

```json
{
  "name": "",
  "version": "",
  "provider": "module|system|local-prefix|source-build|entity-dependencies|unknown",
  "prefix": "",
  "bin": "",
  "include": "",
  "lib": "",
  "cmake_config": "",
  "compiler_signature": "",
  "mpi_signature": "",
  "module_or_env": "",
  "probe_evidence": []
}
```

Do not treat a binary alone as sufficient. For CMake-based dependencies, prefer candidates with a valid `*Config.cmake`.

### 5. Plan Selected Dependencies

Choose a dependency set that satisfies `requirements.json` with the least conflict.

Core selection:

- `cmake`;
- `compiler`;
- `kokkos`.

Conditional selection:

- `gpu_toolkit` for CUDA/HIP;
- `mpi` only when `requirements.environment.mpi=true`;
- `adios2` and `hdf5` when `requirements.environment.output=true`.

Selection rules:

- Prefer one consistent compiler/toolchain across all selected dependencies.
- Reject mixed compiler/toolchain combinations unless the user explicitly approves.
- For CUDA, select Kokkos `nvcc_wrapper` as `compiler.cxx` and record the host compiler.
- Match the Entity version profile: `legacy` means C++17 + Kokkos 4.x + ADIOS2 2.10.x; `modern` means C++20 + Kokkos 5.x + ADIOS2 2.11.x.
- Build ADIOS2 with Kokkos support only for the `modern` profile.
- For MPI, keep `mpicxx`, `mpirun`, Kokkos, ADIOS2, HDF5, and Entity in one MPI/compiler context.
- For output, keep ADIOS2 and HDF5 serial/MPI context consistent with the MPI requirement.
- If local source builds are needed, read `references/dependency-build-scripts.md` and generate scripts with `scripts/generate_dependency_build_scripts.py`.

Record rejected candidates and reasons. This matters for later debugging.

### 6. User Confirmation Gate

Ask only for choices that affect dependency graph, ABI, build output, or installation location.

Confirm when:

- backend is unclear or GPU compiler is missing;
- MPI requirement is unclear;
- GPU-aware MPI is requested or risky;
- multiple compatible compilers exist;
- compiler/toolchain consistency requires rebuilding or rejecting existing dependencies;
- multiple CUDA/HIP toolkits or GPU architectures are possible;
- multiple Kokkos/ADIOS2/HDF5 candidates exist;
- source build is required;
- local install prefix or checkpoint path is ambiguous.

Do not ask when:

- the current request is explicit;
- the JSON has a matching confirmed decision and paths still validate;
- only one compatible low-risk option exists;
- a default is safe and cheap to reverse.

Write every decision to JSON:

```json
{
  "value": "",
  "source": "user|request|checkpoint|default|auto-detected",
  "reason": "",
  "confirmed_at": "",
  "alternatives": []
}
```

If later probes invalidate a confirmed decision, mark it stale and re-enter this gate.

### 7. Generate Source-Build Scripts When Needed

Only do this after local/system reuse fails and the user has approved source builds. Use:

```bash
python scripts/generate_dependency_build_scripts.py "$ENTITY_WORKDIR/requirements.json" \
  --checkpoint "$ENTITY_WORKDIR/entity-deps.local.json"
```

Generated dependency scripts live under `$ENTITY_WORKDIR/generated/source-build-scripts/` and must not write into `ENTITY_CHECKOUT`. Review the generated script options against `requirements.json`, then execute only the missing dependency builds. After execution, update selected dependency entries with prefixes, CMake config paths, compiler signatures, and validation evidence.

### 8. Write JSON Checkpoint

The JSON is the source of truth for phase 1.

Required top-level shape:

```json
{
  "schema_version": 1,
  "generated_at": "",
  "requirements": {},
  "target": {},
  "entity": {},
  "candidates": {},
  "selected": {},
  "decisions": {},
  "paths": {},
  "build_scripts": {},
  "compatibility": {},
  "env_sh": {},
  "status": {}
}
```

Minimum field intent:

- `requirements`: pointer to or embedded copy of the current `requirements.json` content.
- `target`: host/node context, OS, shell, login vs compute context.
- `entity`: checkout root, branch/commit, version bucket, dependency docs source.
- `candidates`: discovered options, including rejected or incompatible candidates.
- `selected`: chosen dependency set.
- `decisions`: user confirmations, request-derived decisions, defaults, and auto-detections.
- `paths`: `PATH`, `CMAKE_PREFIX_PATH`, `LD_LIBRARY_PATH`, `DYLD_LIBRARY_PATH` entries needed for the selected set.
- `build_scripts`: source-build script source, generated script path, command, options, deviations.
- `compatibility`: independent compatibility check result.
- `env_sh`: generated loader status and path.
- `status`: checkpoint completeness and readiness for Entity build.

Write atomically: temporary file first, then replace the target JSON.

### 9. Compatibility Check

Run compatibility after dependency JSON write/repair, and before `env.sh` generation.

For the detailed checklist and expected evidence shape, read `references/compatibility-check.md`.

Use the bundled checker:

```bash
python scripts/check_compatibility.py "$ENTITY_WORKDIR/requirements.json" \
  --checkpoint "$ENTITY_WORKDIR/entity-deps.local.json"
```

Required checks:

- selected dependencies satisfy `requirements.json`;
- selected C++ standard, Kokkos family, ADIOS2 family, and ADIOS2 Kokkos support match the Entity version profile;
- CMake, compiler, and Kokkos are present;
- `requirements.environment.output=true` implies ADIOS2 and HDF5 are present;
- selected compiler/toolchain is consistent across dependencies;
- CUDA backend uses Kokkos `nvcc_wrapper`;
- `nvcc_wrapper` host compiler is compatible with CUDA and the chosen toolchain;
- GPU architecture matches target run hardware, not merely login node;
- MPI-on/off is consistent across Kokkos, ADIOS2, HDF5, and Entity;
- ADIOS2/HDF5 serial/MPI modes match;
- required `*Config.cmake` files exist and can be discovered through `CMAKE_PREFIX_PATH`;
- runtime library paths exist;
- selected versions match the Entity version bucket.

Compatibility output:

```json
{
  "status": "pass|fail|partial",
  "checked_at": "",
  "checks": [],
  "issues": []
}
```

Only `status=pass` allows `env.sh` generation for normal Entity build. If compatibility fails, write issues to JSON and stop before Entity build.

### 10. Generate env.sh From JSON

After compatibility passes, generate a local environment loader from `entity-deps.local.json`. The generator must refuse normal execution unless `compatibility.status=pass`.

Use the bundled Python script:

```text
scripts/generate_env_sh.py
```

Expected interface:

```bash
python scripts/generate_env_sh.py entity-deps.local.json --output "$ENTITY_WORKDIR/env.sh"
```

`env.sh` is derived from JSON. Do not hand-edit it as the source of truth.

Generated `env.sh` should include:

```bash
export ENTITY_DEPS_JSON="..."
export ENTITY_DEPS_ROOT="..."
export PATH="..."
export CMAKE_PREFIX_PATH="..."
export LD_LIBRARY_PATH="..."
export DYLD_LIBRARY_PATH="..."
export CC="..."
export CXX="..."
export MPICXX="..."
```

For CUDA backend:

```bash
export CXX="/path/to/kokkos/bin/nvcc_wrapper"
export NVCC_WRAPPER_DEFAULT_COMPILER="/path/to/host/c++"
```

After generation, minimally validate:

```bash
source env.sh
cmake --version
"$CXX" --version
test -f "$ENTITY_DEPS_JSON"
```

Write `env_sh.path`, `env_sh.status`, and validation evidence back to JSON.

### 11. Generate And Execute entity-build.sh

After `env.sh` is generated, create an Entity build script from `requirements.json` and `env.sh`.

Use the bundled Python script:

```text
scripts/generate_entity_build_sh.py
```

Expected interface:

```bash
python scripts/generate_entity_build_sh.py requirements.json --env "$ENTITY_WORKDIR/env.sh" --output "$ENTITY_WORKDIR/entity-build.sh"
```

`entity-build.sh` is derived from `requirements.json` and `env.sh`. Do not hand-edit it as the source of truth.

The generated script must:

1. `source env.sh`;
2. `cd` to the Entity checkout root from `requirements.json`;
3. generate a `cmake -B <build-dir> -D pgen=<...> ...` or `-D pgens=<...>` command from `requirements.compile`;
4. keep `output`, `mpi`, `gpu_aware_mpi`, backend, architecture, `DEBUG`, and `TESTS` consistent with `requirements.json`;
5. run `cmake --build <build-dir> -j <jobs>`;
6. optionally run `ctest` when `requirements.compile.tests=true`;
7. optionally run `cmake --install` when `requirements.compile.install=true`.

The script should fail fast:

```bash
set -euo pipefail
```

After generation, minimally inspect or validate:

```bash
bash -n entity-build.sh
grep -n "source .*env.sh" entity-build.sh
grep -n "cmake -B" entity-build.sh
```

Then execute:

```bash
bash entity-build.sh
```

Record `entity_build_script.path`, `entity_build_script.status`, `entity_build_script.generated_from`, and execution result back to `requirements.json` or a build result section referenced by it.

### 12. Handoff / Completion Criteria

Start and complete Entity source build only when:

```json
{
  "status": {
    "checkpoint": "complete",
    "satisfies_requirements_json": true,
    "ready_for_entity_build": true
  },
  "compatibility": {
    "status": "pass"
  },
  "env_sh": {
    "status": "generated"
  },
  "entity_build_script": {
    "status": "generated"
  }
}
```

Entity build phase must start by executing `entity-build.sh`. It must not reconstruct dependency state from chat history or ad hoc shell variables.

## Output Contract

When this skill runs, report:

- current requirements;
- `requirements.json` path and completeness;
- checkpoint path and state;
- whether old JSON was reused, repaired, or rejected;
- selected dependency set;
- user confirmations still needed, if any;
- compatibility result;
- generated `env.sh` path;
- generated `entity-build.sh` path and execution result;
- handoff readiness for Entity build.
