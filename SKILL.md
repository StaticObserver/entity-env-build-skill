---
name: entity-env-build
description: Configure, verify, and execute the build environment and source build flow for Entity. Use when the user needs to build Entity, prepare or repair local dependencies, choose CPU/CUDA/HIP/MPI/output support, generate requirements.json, generate or repair entity-deps.local.json, run compatibility checks, generate env.sh, generate entity-build.sh, or execute the verified build script.
---

# entity-env-build

## Mission

Build a reliable local dependency environment for the current Entity build request, then generate and run the Entity build script from verified artifacts.

The core chain is:

```text
requirements.json
  -> entity-deps.local.json
  -> entity_compat.py
  -> env.sh
  -> entity-build.sh
  -> entity_run.py build result
```

Do not reconstruct state from chat history when these artifacts exist.

## Boundaries

Handle:

- Entity build requirements, dependency planning, compatibility checks, `env.sh`, `entity-build.sh`, and build-result recording.
- CMake, C++ compiler, Kokkos, CUDA/HIP, MPI, ADIOS2, and HDF5 choices.
- Source-build scripts for dependencies when reuse fails and the user approves local builds.

Do not handle:

- TOML/PGen design, physics choices, output analysis, or Entity source changes. Route those to the relevant Entity skills.

## Hard Rules

- Treat the current user request as the first input. Reuse old JSON only when it satisfies the current request.
- Require `ENTITY_CHECKOUT` and `ENTITY_WORKDIR` before writing artifacts.
- Keep generated control files and build artifacts out of the Entity source checkout by default.
- Do not probe the environment, search modules, inspect old checkpoints, or choose dependencies until the user has confirmed the compile configuration summary.
- Write and validate `requirements.json` before probing or repairing dependencies.
- Default dependency policy: system modules/packages first, then Spack, then source-build. Do not use conda for C++ build tools; conda is fine for Python tools.
- Core dependencies are `CMake`, a C++ compiler, and `Kokkos`.
- Use MPI only when requested or needed by the build intent.
- Use output support by default; `environment.output=true` requires `ADIOS2 + HDF5`.
- Unless the user explicitly accepts risk, all selected dependencies must use a consistent compiler/toolchain.
- Entity `<1.4.0`: `C++17 + Kokkos 4.x + ADIOS2 2.10.x`. Entity `>=1.4.0`: `C++20 + Kokkos 5.x + ADIOS2 2.11.x`.
- CUDA builds use Kokkos `nvcc_wrapper` as `CXX`; record the wrapper and host compiler.
- Do not enter Entity source compilation until compatibility is `pass` and `env.sh` was generated from the checkpoint.
- Do not hand-write Entity configure/build commands. Generate `entity-build.sh`, then run it through `entity_run.py build` unless debugging.

## Artifact Layout

Use pgen/build-run scoped artifacts:

```text
$ENTITY_WORKDIR/
├── entity-<version>/                     # ENTITY_CHECKOUT
├── deps/                                 # shared dependency installs/sources/scripts
└── problems/<pgen>/
    ├── build/                            # Entity CMake build tree
    └── _build/
        ├── requirements.json
        ├── entity-deps.local.json
        ├── .entity-session.json          # optional run state
        ├── env.sh
        ├── entity-build.sh
        ├── build-logs/
        └── generated/
```

`.entity-session.json`, `~/.entity-env-build/run.log`, compat archives, and site notes are auxiliary state. They are useful for recovery and debugging, but the hard completion criteria are the core artifacts above.

## Workflow

### 1. Requirements

Collect user intent before probing the environment:

- `ENTITY_CHECKOUT`
- `ENTITY_WORKDIR`
- pgen or pgens
- backend: `cpu`, `cuda`, or `hip`
- GPU architecture when backend is CUDA/HIP
- MPI and GPU-aware MPI
- output support
- build intent: smoke/debug/production
- precision, deposit scheme, shape order
- debug/tests/install options if relevant
- dependency policy: reuse existing or allow local build

Before writing `requirements.json` or running any environment command, present a compile configuration summary and wait for explicit confirmation. The summary must include at least:

```text
ENTITY_CHECKOUT:
ENTITY_WORKDIR:
BUILD_ARTIFACTS_DIR:
Entity version/profile:
PGen(s):
Backend:
GPU architecture:
MPI / GPU-aware MPI:
Output support:
Build intent:
Precision / deposit / shape order:
Debug / tests / install:
Dependency policy:
Compiler preference, if specified:
Dependency version pins, if specified:
```

If the user says "use defaults", list the defaults in this summary and ask for confirmation. Only after the user confirms may the agent write `requirements.json`, read old checkpoints, search modules/packages, or inspect dependency paths.

Write `requirements.json` under the build-run `_build/` directory, then validate:

```bash
python3 scripts/entity_checkpoint.py validate "$BUILD_ARTIFACTS_DIR/requirements.json"
```

Only `status=pass` proceeds. `partial` is a drafting/debug state and needs explicit `--allow-partial`.

Read `references/json-contracts.md` when creating or repairing JSON fields. `scripts/entity_schema.py` is the source of truth for schema/default/profile behavior.

### 2. Dependency Checkpoint

Create or repair `entity-deps.local.json` from the current requirements:

```bash
python3 scripts/entity_checkpoint.py create "$BUILD_ARTIFACTS_DIR/requirements.json" \
  --output "$BUILD_ARTIFACTS_DIR/entity-deps.local.json"
```

When merging an old checkpoint, reuse only entries that match the current requirements. Backend, MPI, output, Entity profile, compiler, and pgen drift make the old checkpoint stale until repaired.

For source-built dependencies, generate scripts only after local/system reuse fails and the user approves local builds:

```bash
python3 scripts/entity_generate.py deps "$BUILD_ARTIFACTS_DIR/requirements.json" \
  --checkpoint "$BUILD_ARTIFACTS_DIR/entity-deps.local.json" \
  --deps kokkos,hdf5,adios2
```

Dependency build sub-agents may write only to the approved build tree, install prefix, and log directory. They must not modify `requirements.json`, `entity-deps.local.json`, or Entity source. After a successful dependency build, the main agent records evidence through:

```bash
python3 scripts/entity_checkpoint.py record-install \
  --checkpoint "$BUILD_ARTIFACTS_DIR/entity-deps.local.json" \
  --dep <dep> \
  --prefix <installed-prefix> \
  --cmake-config <Config.cmake-path> \
  --version <version> \
  --compiler-signature <compiler-signature> \
  --log <install-log>
```

### 3. Compatibility

Run compatibility checks against the current files:

```bash
python3 scripts/entity_compat.py "$BUILD_ARTIFACTS_DIR/requirements.json" \
  --checkpoint "$BUILD_ARTIFACTS_DIR/entity-deps.local.json"
```

Only `compatibility.status=pass` proceeds. `warn` and `partial` are blocking by default. Use warning overrides only for explicit, recorded debugging flows.

For isolated verification, generate a compat prompt:

```bash
python3 scripts/entity_generate.py subagent "$BUILD_ARTIFACTS_DIR/requirements.json" \
  --checkpoint "$BUILD_ARTIFACTS_DIR/entity-deps.local.json" \
  --mode compat
```

The sub-agent must read the files from disk and report file hashes. Inline JSON summaries are not a substitute for fresh file reads.

### 4. Generate env.sh

After compatibility passes:

```bash
python3 scripts/entity_generate.py env "$BUILD_ARTIFACTS_DIR/entity-deps.local.json" \
  --output "$BUILD_ARTIFACTS_DIR/env.sh"
```

Do not hand-edit `env.sh`. Put site-specific commands or environment variables into the checkpoint fields described in `references/json-contracts.md`.

### 5. Generate and Run entity-build.sh

Generate the Entity build script:

```bash
python3 scripts/entity_generate.py build "$BUILD_ARTIFACTS_DIR/requirements.json" \
  --env "$BUILD_ARTIFACTS_DIR/env.sh" \
  --checkpoint "$BUILD_ARTIFACTS_DIR/entity-deps.local.json" \
  --output "$BUILD_ARTIFACTS_DIR/entity-build.sh" \
  --run-id "$RUN_ID"
```

Run it through the runner so `requirements.json.build_result` is recorded:

```bash
python3 scripts/entity_run.py build "$BUILD_ARTIFACTS_DIR/requirements.json" \
  --script "$BUILD_ARTIFACTS_DIR/entity-build.sh" \
  --run-id "$RUN_ID"
```

Direct `bash entity-build.sh` is a debugging fallback only.

## Cluster Policy

Separate actions by execution context:

| Action | Login node | Compute node | Notes |
| --- | --- | --- | --- |
| download/materialize | allowed when needed | allowed if network exists | record source and cache paths |
| configure | allowed only when safe and useful | preferred | GPU/tool-linked configure can still fail on login nodes |
| compile/link | default no | preferred/required | use scheduler on clusters |
| run/test | default no | preferred/required | depends on GPU/MPI runtime |

Do not compile on login nodes unless the user explicitly accepts the risk. GPU login-node builds require explicit acknowledgement that GPU runtime libraries may be unavailable and the result may not be runnable there.

## References

- `references/json-contracts.md`: JSON shapes, artifact ownership, and generated-artifact fields.
- `references/compatibility-check.md`: compatibility contract and implemented coverage.
- `references/dependency-build-scripts.md`: generated dependency build scripts.
- `references/entity-compile-options.md`: Entity CMake options.
- `references/dependency-notes/*.md`: dependency-specific build notes.
- `references/site-notes-template.md`: optional machine-local notes.

## Output Contract

Report:

- requirements path and validation status;
- checkpoint path and whether reused, repaired, or created;
- selected dependency set;
- compatibility status and important blocking issues;
- generated `env.sh` path;
- generated `entity-build.sh` path;
- build result status, exit code, and log path;
- any user confirmation still required.
