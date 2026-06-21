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
- Entity `1.4.x` 及更早版本使用 `C++17 + Kokkos 4.x + ADIOS2 2.10.x`。
- Entity 新于 `1.4.x` 的版本使用 `C++20 + Kokkos 5.x + ADIOS2 2.11.x`。
- 只有 `Kokkos 5.x + ADIOS2 2.11.x` profile 启用 ADIOS2 Kokkos 支持。
- `env.sh` 只能在 compatibility check 通过后生成。

主要脚本：

```text
scripts/check_compatibility.py
scripts/generate_dependency_build_scripts.py
scripts/generate_env_sh.py
scripts/generate_entity_build_sh.py
```

典型顺序：

```bash
python scripts/generate_dependency_build_scripts.py requirements.json \
  --checkpoint entity-deps.local.json

python scripts/check_compatibility.py requirements.json \
  --checkpoint entity-deps.local.json

python scripts/generate_env_sh.py entity-deps.local.json \
  --output "$ENTITY_WORKDIR/env.sh"

python scripts/generate_entity_build_sh.py requirements.json \
  --env "$ENTITY_WORKDIR/env.sh" \
  --output "$ENTITY_WORKDIR/entity-build.sh"
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
- Entity `1.4.x` and older use `C++17 + Kokkos 4.x + ADIOS2 2.10.x`.
- Entity versions newer than `1.4.x` use `C++20 + Kokkos 5.x + ADIOS2 2.11.x`.
- Enable ADIOS2 Kokkos support only for the `Kokkos 5.x + ADIOS2 2.11.x` profile.
- Generate `env.sh` only after compatibility checks pass.

Main scripts:

```text
scripts/check_compatibility.py
scripts/generate_dependency_build_scripts.py
scripts/generate_env_sh.py
scripts/generate_entity_build_sh.py
```

Typical sequence:

```bash
python scripts/generate_dependency_build_scripts.py requirements.json \
  --checkpoint entity-deps.local.json

python scripts/check_compatibility.py requirements.json \
  --checkpoint entity-deps.local.json

python scripts/generate_env_sh.py entity-deps.local.json \
  --output "$ENTITY_WORKDIR/env.sh"

python scripts/generate_entity_build_sh.py requirements.json \
  --env "$ENTITY_WORKDIR/env.sh" \
  --output "$ENTITY_WORKDIR/entity-build.sh"
```

See `SKILL.md` and `references/` for the full contract.
