#!/usr/bin/env python3
"""Generate a SLURM batch script for Entity build.

Reads slurm fields from requirements.json and wraps the
entity-build.sh call with #SBATCH headers.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any


SLURM_FIELD_MAP = {
    "job_name": "job-name",
    "partition": "partition",
    "nodes": "nodes",
    "ntasks_per_node": "ntasks-per-node",
    "cpus_per_task": "cpus-per-task",
    "gres": "gres",
    "time": "time",
    "account": "account",
    "qos": "qos",
    "mem": "mem",
    "constraint": "constraint",
    "exclusive": "exclusive",
    "array": "array",
}


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise SystemExit(f"{path} must contain a JSON object")
    return data


def generate_slurm(
    slurm_cfg: dict[str, Any],
    workdir: str,
    build_script: Path,
    *,
    source_env: bool = False,
    env_sh: Path | None = None,
) -> str:
    """Generate a SLURM batch submission script."""
    lines = ["#!/usr/bin/env bash"]

    # SBATCH headers
    for json_key, sbatch_opt in SLURM_FIELD_MAP.items():
        value = slurm_cfg.get(json_key)
        if value is None:
            continue
        if isinstance(value, bool):
            if value:
                lines.append(f"#SBATCH --{sbatch_opt}")
        else:
            lines.append(f"#SBATCH --{sbatch_opt}={value}")

    # Automatic output/error if not explicitly set
    logs_dir = f"{workdir}/logs"
    if "output" not in slurm_cfg:
        lines.append(f"#SBATCH --output={logs_dir}/slurm-%j.out")
    if "error" not in slurm_cfg:
        lines.append(f"#SBATCH --error={logs_dir}/slurm-%j.err")

    lines.extend([
        "",
        "set -euo pipefail",
        "",
        'echo "===== SLURM Job Info ====="',
        'echo "Job ID:   $SLURM_JOB_ID"',
        'echo "Node:     $SLURMD_NODENAME"',
        'echo "Partition: $SLURM_JOB_PARTITION"',
    ])
    if slurm_cfg.get("gres"):
        lines.append('echo "GPUs:     $SLURM_STEP_GPUS"')

    lines.extend([
        "",
        'echo ""',
        'echo "===== Starting Entity Build ====="',
    ])

    if source_env and env_sh:
        lines.append(f"source {str(env_sh.resolve())}")

    lines.append(f"bash {str(build_script.resolve())}")
    lines.append("EXIT_CODE=$?")
    lines.append("if [ $EXIT_CODE -eq 0 ]; then")
    lines.append('  echo ""')
    lines.append('  echo "===== Job completed successfully ====="')
    lines.append("else")
    lines.append('  echo ""')
    lines.append('  echo "===== Job failed with exit code $EXIT_CODE ====="')
    lines.append("fi")
    lines.append("exit $EXIT_CODE")
    lines.append("")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("requirements_json", type=Path, help="Path to requirements.json")
    parser.add_argument(
        "--build-script", type=Path, required=True, help="Path to entity-build.sh"
    )
    parser.add_argument("--output", type=Path, help="Output path for the SLURM script")
    parser.add_argument(
        "--source-env", action="store_true",
        help="Source env.sh before running entity-build.sh"
    )
    parser.add_argument("--env-sh", type=Path, help="Path to env.sh (needed with --source-env)")
    args = parser.parse_args()

    if not args.requirements_json.exists():
        raise SystemExit(f"requirements.json not found: {args.requirements_json}")

    req = load_json(args.requirements_json)
    slurm_cfg = req.get("slurm", {})
    if not isinstance(slurm_cfg, dict) or not slurm_cfg:
        raise SystemExit(
            "requirements.json missing 'slurm' section. "
            "Add slurm.partition, slurm.gres, etc."
        )

    entity = req.get("entity", {})
    workdir = str(
        entity.get("workdir", "") if isinstance(entity, dict) else ""
    ) or os.environ.get("ENTITY_WORKDIR", "")
    if not workdir:
        raise SystemExit("ENTITY_WORKDIR must be set or in requirements.entity.workdir")

    if not args.build_script.exists():
        raise SystemExit(f"entity-build.sh not found: {args.build_script}")

    if args.output is None:
        args.output = Path(workdir) / "submit_entity.sh"

    script = generate_slurm(
        slurm_cfg, workdir, args.build_script,
        source_env=args.source_env, env_sh=args.env_sh,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(script, encoding="utf-8")
    args.output.chmod(0o755)
    print(f"SLURM script written to {args.output.resolve()}")


if __name__ == "__main__":
    main()
