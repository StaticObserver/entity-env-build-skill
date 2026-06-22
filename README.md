# entity-env-build-skill

`entity-env-build` prepares and verifies an Entity build environment, then generates and runs the Entity build script from structured artifacts.

Core chain:

```text
requirements.json
  -> entity-deps.local.json
  -> entity_compat.py
  -> env.sh
  -> entity-build.sh
  -> entity_run.py build result
```

Authoritative behavior lives in:

- `SKILL.md` for agent workflow and hard rules.
- `scripts/entity_schema.py` for schema constants, defaults, version profiles, and CMake option maps.
- `references/json-contracts.md` for human-readable artifact contracts.
- `references/compatibility-check.md` for compatibility coverage.

## Main Commands

Use a pgen/build-run artifact directory such as:

```bash
BUILD_ARTIFACTS_DIR="$ENTITY_WORKDIR/problems/<pgen>/_build"
```

Typical sequence:

```bash
python3 scripts/entity_checkpoint.py validate "$BUILD_ARTIFACTS_DIR/requirements.json"

python3 scripts/entity_checkpoint.py create "$BUILD_ARTIFACTS_DIR/requirements.json" \
  --output "$BUILD_ARTIFACTS_DIR/entity-deps.local.json"

python3 scripts/entity_compat.py "$BUILD_ARTIFACTS_DIR/requirements.json" \
  --checkpoint "$BUILD_ARTIFACTS_DIR/entity-deps.local.json"

python3 scripts/entity_generate.py env "$BUILD_ARTIFACTS_DIR/entity-deps.local.json" \
  --output "$BUILD_ARTIFACTS_DIR/env.sh"

python3 scripts/entity_generate.py build "$BUILD_ARTIFACTS_DIR/requirements.json" \
  --env "$BUILD_ARTIFACTS_DIR/env.sh" \
  --checkpoint "$BUILD_ARTIFACTS_DIR/entity-deps.local.json" \
  --output "$BUILD_ARTIFACTS_DIR/entity-build.sh"

python3 scripts/entity_run.py build "$BUILD_ARTIFACTS_DIR/requirements.json" \
  --script "$BUILD_ARTIFACTS_DIR/entity-build.sh"
```

If a dependency must be source-built, generate the script and record install evidence:

```bash
python3 scripts/entity_generate.py deps "$BUILD_ARTIFACTS_DIR/requirements.json" \
  --checkpoint "$BUILD_ARTIFACTS_DIR/entity-deps.local.json" \
  --deps kokkos

python3 scripts/entity_checkpoint.py record-install \
  --checkpoint "$BUILD_ARTIFACTS_DIR/entity-deps.local.json" \
  --dep kokkos \
  --prefix /path/to/kokkos \
  --cmake-config /path/to/KokkosConfig.cmake
```

## 中文简述

这个 skill 的目标不是做大型远程构建框架，而是维护一条短而硬的 Entity 构建主链路：先写需求 JSON，再写依赖 checkpoint，通过兼容性检查后生成 `env.sh` 和 `entity-build.sh`，最后用 runner 执行并记录结果。

详细规则以 `SKILL.md`、`scripts/entity_schema.py` 和 `references/` 为准。
