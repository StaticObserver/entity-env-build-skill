# entity-env-build-skill

## 中文

`entity-env-build` 是一个用于构建 Entity 项目环境与本体的 Codex skill。它把一次 Entity 编译拆成三个阶段：

1. 确认当前构建需求并生成 `requirements.json`。
2. 搜索、选择、检查本地依赖，生成 `entity-deps.local.json` 和 `env.sh`。
3. 根据 `requirements.json + env.sh` 生成并执行 `entity-build.sh`。

核心约束：

- 默认复用本地/system 依赖，不使用 Spack 或 Docker，除非用户明确要求。
- 所有依赖默认使用一致的编译器/toolchain。
- CUDA 后端使用 Kokkos `nvcc_wrapper`。
- Entity `1.4.0` 之前版本使用 `C++17 + Kokkos 4.x + ADIOS2 2.10.x`。
- Entity `1.4.0` 及更新版本使用 `C++20 + Kokkos 5.x + ADIOS2 2.11.x`。
- 只有 `Kokkos 5.x + ADIOS2 2.11.x` profile 启用 ADIOS2 Kokkos 支持。
- `env.sh` 只能在 compatibility check 通过后生成。

主要脚本：

```text
scripts/entity_checkpoint.py   ← validate + create checkpoint
scripts/entity_checkpoint.py   ← record-install dependency evidence
scripts/entity_compat.py       ← compatibility check
scripts/entity_generate.py     ← deps / env / build 生成
scripts/entity_run.py          ← run build scripts + record results
```

典型顺序：

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

详细契约见 `SKILL.md` 和 `references/`。

## English

`entity-env-build` is a Codex skill for preparing an Entity build environment and building Entity itself. It splits one Entity build into three phases:

1. Confirm the current build requirements and write `requirements.json`.
2. Discover, select, and validate local dependencies, then write `entity-deps.local.json` and `env.sh`.
3. Generate and run `entity-build.sh` from `requirements.json + env.sh`.

Core constraints:

- Reuse local/system dependencies by default; do not use Spack or Docker unless explicitly requested.
- Keep all dependencies on one consistent compiler/toolchain unless the user accepts the risk.
- CUDA builds use Kokkos `nvcc_wrapper`.
- Entity versions before `1.4.0` use `C++17 + Kokkos 4.x + ADIOS2 2.10.x`.
- Entity `1.4.0` and newer use `C++20 + Kokkos 5.x + ADIOS2 2.11.x`.
- Enable ADIOS2 Kokkos support only for the `Kokkos 5.x + ADIOS2 2.11.x` profile.
- Generate `env.sh` only after compatibility checks pass.

Main scripts:

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

Typical sequence:

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
