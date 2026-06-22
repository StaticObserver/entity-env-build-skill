# entity-env-build-skill

[English](./README.en.md)

---

`entity-env-build` 是一个用于构建 Entity 项目环境与本体的 Codex skill。它把一次 Entity 编译拆成三个阶段：

1. 确认当前构建需求并生成 `requirements.json`。
2. 搜索、选择、检查本地依赖，生成 `entity-deps.local.json` 和 `env.sh`。
3. 根据 `requirements.json + env.sh` 生成并执行 `entity-build.sh`。

## 核心约束

- 默认复用本地/system 依赖，不使用 Spack 或 Docker，除非用户明确要求。
- 所有依赖默认使用一致的编译器/toolchain。
- CUDA 后端使用 Kokkos `nvcc_wrapper`。
- Entity `1.4.0` 之前版本使用 `C++17 + Kokkos 4.x + ADIOS2 2.10.x`。
- Entity `1.4.0` 及更新版本使用 `C++20 + Kokkos 5.x + ADIOS2 2.11.x`。
- Entity **低于 `1.4.3` 与 CUDA 后端 + modern profile (C++20) 不兼容**。NVCC 的 EDG frontend 拒绝 C++20 `requires` 约束（`constraints on a non-templated function`）和 TOML11 的 `std::source_location::current` consteval。Entity `1.4.3` (PR #210) 用 `static_assert` 替换了 `requires`，修复了此问题。
- 只有 `Kokkos 5.x + ADIOS2 2.11.x` profile 启用 ADIOS2 Kokkos 支持。
- `env.sh` 只能在 compatibility check 通过后生成。

## 主要脚本

```text
scripts/entity_checkpoint.py   ← validate + create checkpoint
scripts/entity_checkpoint.py   ← record-install dependency evidence
scripts/entity_compat.py       ← compatibility check
scripts/entity_generate.py     ← deps / env / build 生成
scripts/entity_run.py          ← run build scripts + record results
```

## 典型顺序

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
