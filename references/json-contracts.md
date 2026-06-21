# JSON Contracts

Use this reference when creating, repairing, or validating `requirements.json` and `entity-deps.local.json`.

## File Roles

`requirements.json` is the source of truth for the current Entity build request. It changes when the user changes backend, MPI, output, PGen, debug/test intent, build directory, install choice, or other compile options.

`entity-deps.local.json` is the local dependency checkpoint. It is reusable only when it satisfies the current `requirements.json`.

`env.sh` is derived from `entity-deps.local.json`.

`entity-build.sh` is derived from `requirements.json + env.sh`.

Do not reconstruct state from chat history or transient shell variables when these files exist.

## Path Roles

Require these locations before writing artifacts:

- `ENTITY_CHECKOUT`: Entity source checkout.
- `ENTITY_WORKDIR`: workspace for one problem/build configuration.

Default layout:

```text
$ENTITY_HOME/
├── sources/<entity-version>/
└── problems/<problem-name>/<build-name>/
```

Default artifact paths:

```text
$ENTITY_WORKDIR/requirements.json
$ENTITY_WORKDIR/entity-deps.local.json
$ENTITY_WORKDIR/env.sh
$ENTITY_WORKDIR/entity-build.sh
$ENTITY_WORKDIR/build/
$ENTITY_WORKDIR/logs/
$ENTITY_WORKDIR/generated/source-build-scripts/
```

Keep `ENTITY_CHECKOUT` clean by default. Do not write control JSON, generated scripts, or CMake build directories into the source tree unless the user explicitly asks.

## requirements.json

Required shape:

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
    "gpu_arch": "",
    "mpi": false,
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
    "precision": "single",
    "deposit": "zigzag",
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
    "complete": false,
    "ready_for_dependency_planning": false,
    "ready_for_entity_build_script": false
  },
  "build_result": {}
}
```

Completion rules:

- `entity.checkout_root` is required before generating `entity-build.sh`.
- `entity.workdir` is required before writing artifacts.
- `entity.dependency_profile` is derived from the Entity version unless explicitly set. Use `legacy` for Entity `1.4.x` and older, and `modern` for Entity newer than `1.4.x`.
- `compile.cxx_standard` must be `17` for `legacy` and `20` for `modern`.
- `environment.dependency_versions` may pin exact source-build tags. If omitted, generated source-build scripts must choose and record profile-compatible concrete tags; for `legacy`, Kokkos must be explicitly pinned to a Kokkos 4.x tag.
- `compile.pgen` or `compile.pgens` is required before generating `entity-build.sh`. Use one, not both.
- `compile.build_dir` may be generated if omitted, but must be written back before script generation.
- `environment.output=true` must align with `compile` output option in generated CMake.
- `environment.mpi` and `environment.gpu_aware_mpi` must align with generated CMake.
- `environment.backend` must align with generated Kokkos backend options.
- `modern` profile requires Kokkos `5.x`, ADIOS2 `2.11.x`, and ADIOS2 built with Kokkos support.
- `legacy` profile requires Kokkos `4.x`, ADIOS2 `2.10.x`, and ADIOS2 without Kokkos support unless explicitly overridden.

## entity-deps.local.json

Required shape:

```json
{
  "schema_version": 1,
  "generated_at": "",
  "requirements": {},
  "target": {},
  "entity": {},
  "candidates": {},
  "selected": {
    "cmake": {},
    "compiler": {},
    "gpu_toolkit": {},
    "mpi": {},
    "kokkos": {},
    "hdf5": {},
    "adios2": {}
  },
  "decisions": {},
  "paths": {
    "PATH": [],
    "CMAKE_PREFIX_PATH": [],
    "LD_LIBRARY_PATH": [],
    "DYLD_LIBRARY_PATH": [],
    "extra_env": {}
  },
  "build_scripts": {},
  "compatibility": {
    "status": "unknown|pass|partial|fail",
    "checked_at": "",
    "checks": [],
    "issues": []
  },
  "env_sh": {
    "path": "",
    "status": "missing|generated|failed",
    "generated_at": "",
    "validation": {}
  },
  "status": {
    "checkpoint": "missing|partial|complete|stale|incompatible",
    "satisfies_requirements_json": false,
    "ready_for_entity_build": false,
    "reuse_notes": []
  }
}
```

Selected dependency entries should use this shape when possible:

```json
{
  "name": "",
  "version": "",
  "provider": "module|system|local-prefix|source-build|entity-dependencies|unknown|none",
  "prefix": "",
  "bin": "",
  "include": "",
  "lib": "",
  "cmake_config": "",
  "compiler_signature": "",
  "mpi_signature": "",
  "environment": {},
  "compile_config": {},
  "validation": {}
}
```

## Extra Environment Variables

Site-specific environment variables that `generate_env_sh.py` should write into `env.sh` can be recorded under `paths.extra_env`:

```json
{
  "paths": {
    "extra_env": {
      "ROCM_PATH": "/opt/rocm",
      "OMPI_CC": "hipcc",
      "OMPI_CXX": "hipcc",
      "HSA_OVERRIDE_GFX_VERSION": "9.0.6"
    }
  }
}
```

Each key-value pair becomes `export KEY=VALUE` in the generated `env.sh`. Use this for system-specific variables that the generic path-derivation logic cannot know about (DTK/ROCm paths, MPI wrapper overrides, GPU runtime environment settings).

## CUDA-specific selected fields

```json
{
  "selected": {
    "compiler": {
      "cc": "/path/to/gcc",
      "cxx": "/path/to/kokkos/bin/nvcc_wrapper",
      "host_cxx": "/path/to/g++"
    },
    "kokkos": {
      "nvcc_wrapper": "/path/to/kokkos/bin/nvcc_wrapper",
      "cuda_arch": "AMPERE80"
    }
  }
}
```

MPI-specific selected fields:

```json
{
  "selected": {
    "mpi": {
      "enabled": true,
      "mpicxx": "/path/to/mpicxx",
      "mpirun": "/path/to/mpirun",
      "wrapper_show": "",
      "gpu_aware_mpi": false
    }
  }
}
```

## Compatibility Result

`compatibility.status=pass` requires:

- `scripts/check_compatibility.py` has written the latest compatibility result;
- current `requirements.json` is represented in `entity-deps.local.json.requirements`;
- required dependencies are selected;
- selected C++ standard, Kokkos family, ADIOS2 family, and ADIOS2 Kokkos support match the Entity version profile;
- selected compiler/toolchain is consistent;
- CUDA builds use Kokkos `nvcc_wrapper`;
- MPI-on/off is consistent across selected dependencies;
- ADIOS2/HDF5 serial/MPI mode is consistent with MPI requirement;
- required `*Config.cmake` paths or prefixes exist;
- runtime library paths exist where required.

Use `partial` only for non-blocking issues explicitly safe before Entity build.

Run:

```bash
python scripts/check_compatibility.py requirements.json --checkpoint entity-deps.local.json
```

## Generated Artifacts

After `env.sh` generation, update:

```json
{
  "env_sh": {
    "path": "/abs/path/env.sh",
    "status": "generated",
    "generated_at": "",
    "validation": {
      "bash_syntax": "pass|fail",
      "commands": []
    }
  }
}
```

After `entity-build.sh` generation or execution, update `requirements.json`:

```json
{
  "artifacts": {
    "entity_build_sh": "/abs/path/entity-build.sh"
  },
  "build_result": {
    "status": "not_run|running|pass|fail",
    "started_at": "",
    "finished_at": "",
    "configure_command": "",
    "build_command": "",
    "expected_executable": ""
  }
}
```
