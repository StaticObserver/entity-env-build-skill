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

Run the skill in this order. Phase 1 collects all user requirements before touching the environment.

```text
Phase 1 — User requirements (no environment probing yet)
  -> ask user for Entity source and workspace locations
  -> ask user for build choices (pgen, backend, MPI, output, intent, options)
  -> write requirements.json
  -> validate requirements.json

Phase 2 — Environment probing and planning
  -> locate/read dependency checkpoint JSON (if any)
  -> compare checkpoint against requirements.json
  -> search local dependency candidates
  -> plan compatible selected dependencies
  -> user confirmation gate for ambiguous choices
  -> generate source-build scripts when needed
  -> write entity-deps.local.json
  -> compatibility check
  -> generate env.sh

Phase 3 — Entity build
  -> generate entity-build.sh from requirements.json + env.sh
  -> execute entity-build.sh
```

### Phase 1: Collect User Requirements

**Do not probe the environment until the user has answered the questions in this phase.** The goal is to know what the user wants before checking what is available.

#### 1a. Workspace Location

Ask the user to confirm two paths:

- `ENTITY_CHECKOUT`: where the Entity source lives. Check `$ENTITY_CHECKOUT`, then ask.
- `ENTITY_WORKDIR`: where build artifacts go. Check `$ENTITY_WORKDIR`, then ask.

A typical layout:

```text
$ENTITY_HOME/
├── sources/<entity-version>/
└── problems/<problem-name>/<build-name>/
```

Default artifact paths under `ENTITY_WORKDIR`:

```text
$ENTITY_WORKDIR/requirements.json
$ENTITY_WORKDIR/entity-deps.local.json
$ENTITY_WORKDIR/env.sh
$ENTITY_WORKDIR/entity-build.sh
$ENTITY_WORKDIR/build/
$ENTITY_WORKDIR/logs/
$ENTITY_WORKDIR/generated/source-build-scripts/
```

#### 1b. Build Choices

Ask the user these questions. For each, record a decision even if using the default. Do not probe the system to answer them — these are user intent, not environment discovery.

| Question | Options | Default | Notes |
| --- | --- | --- | --- |
| Problem generator (`pgen`) | built-in name, `pgens/...`, or path | *required* | Changing pgen later requires a fresh build dir |
| CPU or GPU backend? | `cpu` / `cuda` / `hip` | prefer GPU if user expects it | CUDA requires `nvcc_wrapper`; HIP requires ROCm/hipcc |
| Enable MPI? | `true` / `false` | `false` | Don't enable just because mpicxx exists |
| GPU-aware MPI? | `true` / `false` | `false` | Only relevant when MPI + GPU both on |
| Enable output? | `true` / `false` | `true` | `true` implies ADIOS2 + HDF5 |
| Build intent | `smoke` / `production` / `debug` / `unspecified` | `unspecified` | Affects optimization level and strictness |
| Precision | `single` / `double` | `single` | |
| Deposit scheme | `zigzag` / `esirkepov` | `zigzag` | |
| Shape order | `1` to `11` | `1` | |
| Debug mode? | `true` / `false` | `false` | |
| Compile tests? | `true` / `false` | `false` | |
| Dependency policy | `reuse-existing` / `allow-local-build` | `reuse-existing` | Source build is last resort |

Additional questions when the answer is not obvious from context:

- Entity version (auto-detect from checkout if possible; otherwise ask)
- GPU architecture (e.g. `AMPERE80`, `AMD_GFX906`) — needed when backend is GPU
- Exact dependency version tags — only if user wants to pin specific versions
- Install prefix — only if user wants `cmake --install`

#### 1c. Write And Validate requirements.json

After collecting all answers, write `requirements.json` following the schema in `references/json-contracts.md`.

Defaults that don't need asking unless the user overrides:

- `entity.dependency_profile`: derived from Entity version — `legacy` for ≤1.4.x, `modern` for >1.4.x
- `compile.cxx_standard`: derived from profile — `17` for legacy, `20` for modern
- `environment.dependency_versions`: leave empty; fill after probing if source builds are needed

Validate before proceeding:

```bash
python3 scripts/validate_requirements.py "$ENTITY_WORKDIR/requirements.json"
```

If validation fails, fix the missing fields or inconsistencies and re-validate. Do not start environment probing until `status=pass`.

### Phase 2: Environment Probing And Planning

Only now — after `requirements.json` is written and validated — begin probing the environment.

#### 2a. Locate And Read Existing Checkpoint

Default checkpoint filename: `entity-deps.local.json`

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

#### 2b. Compare Checkpoint Against requirements.json

Reuse old dependency content only if it satisfies `requirements.json`.

Examples:

- old `backend=cpu`, current `backend=cuda` -> stale for this request;
- old `mpi=false`, current `mpi=true` -> only non-MPI parts may be reused;
- old `output=false`, current default `output=true` -> ADIOS2/HDF5 must be discovered and checked;
- old compiler differs from the current selected MPI wrapper compiler -> stale until confirmed or rebuilt.

Record this comparison under `status.satisfies_requirements_json` and `status.reuse_notes`.

#### 2c. Search Dependency Candidates

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

For each candidate, record following the dependency entry shape in `references/json-contracts.md`.

Do not treat a binary alone as sufficient. For CMake-based dependencies, prefer candidates with a valid `*Config.cmake`.

#### 2d. Construct Checkpoint JSON

Construct `entity-deps.local.json` from the requirements and dependency selections:

```bash
python3 scripts/write_checkpoint.py "$ENTITY_WORKDIR/requirements.json" \
  --output "$ENTITY_WORKDIR/entity-deps.local.json"
```

To merge with an existing checkpoint:

```bash
python3 scripts/write_checkpoint.py "$ENTITY_WORKDIR/requirements.json" \
  --merge "$ENTITY_WORKDIR/entity-deps.local.json" \
  --output "$ENTITY_WORKDIR/entity-deps.local.json"
```

See `references/json-contracts.md` for the full checkpoint schema. Write atomically: temporary file first, then replace the target JSON.

#### 2e. Plan Selected Dependencies

Choose a dependency set that satisfies `requirements.json` with the least conflict.

Core selection: `cmake`, `compiler`, `kokkos`. Conditional: `gpu_toolkit` for CUDA/HIP; `mpi` only when required; `adios2` + `hdf5` when `output=true`.

Selection rules:

- Prefer one consistent compiler/toolchain across all selected dependencies.
- Reject mixed compiler/toolchain combinations unless the user explicitly approves.
- For CUDA, select Kokkos `nvcc_wrapper` as `compiler.cxx` and record the host compiler.
- Match the Entity version profile: `legacy` means C++17 + Kokkos 4.x + ADIOS2 2.10.x; `modern` means C++20 + Kokkos 5.x + ADIOS2 2.11.x.
- Build ADIOS2 with Kokkos support only for the `modern` profile.
- For MPI, keep `mpicxx`, `mpirun`, Kokkos, ADIOS2, HDF5, and Entity in one MPI/compiler context.
- For output, keep ADIOS2 and HDF5 serial/MPI context consistent with the MPI requirement.
- If local source builds are needed, read `references/dependency-build-scripts.md`.

Record rejected candidates and reasons.

#### 2f. User Confirmation Gate

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

#### 2g. Generate Source-Build Scripts When Needed

Only do this after local/system reuse fails and the user has approved source builds. Use:

```bash
python scripts/generate_dependency_build_scripts.py "$ENTITY_WORKDIR/requirements.json" \
  --checkpoint "$ENTITY_WORKDIR/entity-deps.local.json"
```

Generated dependency scripts live under `$ENTITY_WORKDIR/generated/source-build-scripts/` and must not write into `ENTITY_CHECKOUT`. Review the generated script options against `requirements.json`, then execute only the missing dependency builds. After execution, update selected dependency entries with prefixes, CMake config paths, compiler signatures, and validation evidence.

#### 2h. Compatibility Check

Run compatibility after dependency JSON is written, and before `env.sh` generation.

For the detailed checklist, read `references/compatibility-check.md`.

```bash
python3 scripts/check_compatibility.py "$ENTITY_WORKDIR/requirements.json" \
  --checkpoint "$ENTITY_WORKDIR/entity-deps.local.json"
```

Only `status=pass` allows `env.sh` generation. If compatibility fails, fix issues and re-run.

### Phase 3: Entity Build

#### 3a. Generate env.sh From JSON

After compatibility passes, generate a local environment loader. The generator refuses unless `compatibility.status=pass`.

```bash
python3 scripts/generate_env_sh.py "$ENTITY_WORKDIR/entity-deps.local.json" \
  --output "$ENTITY_WORKDIR/env.sh"
```

`env.sh` is derived from the checkpoint JSON. Do not hand-edit it. For site-specific extra environment variables (e.g. `ROCM_PATH`, `OMPI_CC`), record them in `entity-deps.local.json.paths.extra_env` before generation.

After generation, minimally validate: source it and verify `cmake --version`, `"$CXX" --version`.

#### 3b. Generate And Execute entity-build.sh

After `env.sh` is generated, create an Entity build script:

```bash
python3 scripts/generate_entity_build_sh.py "$ENTITY_WORKDIR/requirements.json" \
  --env "$ENTITY_WORKDIR/env.sh" \
  --checkpoint "$ENTITY_WORKDIR/entity-deps.local.json" \
  --output "$ENTITY_WORKDIR/entity-build.sh"
```

`--checkpoint` enables gate validation: the generator verifies compatibility is `pass` and env.sh matches the checkpoint. Omit `--checkpoint` only for debugging.

The generated script sources `env.sh`, runs `cmake -B` configure then `cmake --build`, respects all `requirements.compile` options, and fails fast with `set -euo pipefail`.

Then execute:

```bash
bash entity-build.sh
```

Record `entity_build_script.path`, `entity_build_script.status`, `entity_build_script.generated_from`, and execution result back to `requirements.json` or a build result section referenced by it.

#### 3c. Handoff / Completion Criteria

Entity build may start only when all are true:

- `status.checkpoint == "complete"` and `satisfies_requirements_json == true`
- `compatibility.status == "pass"`
- `env_sh.status == "generated"`
- `entity_build_script.status == "generated"`

Entity build phase must start by executing `entity-build.sh`. Do not reconstruct state from chat history or transient shell variables.

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
