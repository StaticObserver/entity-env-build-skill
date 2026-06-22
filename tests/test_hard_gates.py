import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_cmd(*args, env=None):
    proc_env = os.environ.copy()
    if env:
        proc_env.update(env)
    return subprocess.run(
        [sys.executable, *args],
        cwd=ROOT,
        env=proc_env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


class HardGateTests(unittest.TestCase):
    def write_json(self, path: Path, data: dict) -> None:
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    def base_requirements(self, tmp: Path) -> dict:
        checkout = tmp / "entity"
        checkout.mkdir()
        return {
            "schema_version": 1,
            "entity": {
                "checkout_root": str(checkout),
                "workdir": str(tmp),
                "version_bucket": "1.4.0",
                "dependency_profile": "modern",
            },
            "environment": {
                "backend": "cpu",
                "output": False,
                "mpi": False,
                "dependency_policy": "reuse-existing",
            },
            "compile": {
                "pgen": "smoke",
                "cxx_standard": "20",
            },
        }

    def test_validate_blocks_partial_by_default(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            req = self.base_requirements(tmp)
            req["compile"]["pgens"] = ["other"]
            req_path = tmp / "requirements.json"
            self.write_json(req_path, req)

            proc = run_cmd("scripts/entity_checkpoint.py", "validate", str(req_path))

            self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn('"status": "partial"', proc.stdout)

    def test_validate_allow_partial_exits_zero(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            req = self.base_requirements(tmp)
            req["compile"]["pgens"] = ["other"]
            req_path = tmp / "requirements.json"
            self.write_json(req_path, req)

            proc = run_cmd(
                "scripts/entity_checkpoint.py",
                "validate",
                str(req_path),
                "--allow-partial",
            )

            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn('"status": "partial"', proc.stdout)

    def test_env_blocks_warn_by_default(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            deps_path = tmp / "entity-deps.local.json"
            self.write_json(
                deps_path,
                {
                    "schema_version": 1,
                    "compatibility": {"status": "warn"},
                    "selected": {},
                    "env_sh": {"path": str(tmp / "env.sh")},
                },
            )

            proc = run_cmd(
                "scripts/entity_generate.py",
                "env",
                str(deps_path),
                "--output",
                str(tmp / "env.sh"),
            )

            self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertFalse((tmp / "env.sh").exists())
            self.assertIn("must be pass", proc.stderr)

    def test_env_allows_warn_only_with_recorded_decision(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            deps_path = tmp / "entity-deps.local.json"
            self.write_json(
                deps_path,
                {
                    "schema_version": 1,
                    "compatibility": {"status": "warn"},
                    "decisions": {
                        "compatibility_warnings_accepted": {
                            "value": True,
                            "source": "user",
                            "reason": "fixture",
                        }
                    },
                    "selected": {},
                    "env_sh": {"path": str(tmp / "env.sh")},
                },
            )

            proc = run_cmd(
                "scripts/entity_generate.py",
                "env",
                str(deps_path),
                "--output",
                str(tmp / "env.sh"),
                "--allow-warnings",
            )

            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertTrue((tmp / "env.sh").exists())

    def test_build_blocks_warn_by_default(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            req_path = tmp / "requirements.json"
            deps_path = tmp / "entity-deps.local.json"
            env_path = tmp / "env.sh"
            self.write_json(req_path, self.base_requirements(tmp))
            env_path.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
            self.write_json(
                deps_path,
                {
                    "schema_version": 1,
                    "compatibility": {"status": "warn"},
                    "selected": {},
                    "env_sh": {"path": str(env_path)},
                },
            )

            proc = run_cmd(
                "scripts/entity_generate.py",
                "build",
                str(req_path),
                "--env",
                str(env_path),
                "--checkpoint",
                str(deps_path),
                "--output",
                str(tmp / "entity-build.sh"),
            )

            self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertFalse((tmp / "entity-build.sh").exists())
            self.assertIn("must be 'pass'", proc.stderr)

    def test_build_blocks_stale_env_by_default(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            req_path = tmp / "requirements.json"
            deps_path = tmp / "entity-deps.local.json"
            env_path = tmp / "env.sh"
            self.write_json(req_path, self.base_requirements(tmp))
            env_path.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
            self.write_json(
                deps_path,
                {
                    "schema_version": 1,
                    "compatibility": {"status": "pass"},
                    "selected": {},
                    "env_sh": {"path": str(tmp / "old-env.sh")},
                },
            )

            proc = run_cmd(
                "scripts/entity_generate.py",
                "build",
                str(req_path),
                "--env",
                str(env_path),
                "--checkpoint",
                str(deps_path),
                "--output",
                str(tmp / "entity-build.sh"),
            )

            self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertFalse((tmp / "entity-build.sh").exists())
            self.assertIn("may be stale", proc.stderr)

    def test_record_install_requires_real_paths(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            deps_path = tmp / "entity-deps.local.json"
            self.write_json(
                deps_path,
                {
                    "schema_version": 1,
                    "selected": {},
                    "paths": {},
                    "compatibility": {"status": "pass"},
                },
            )

            proc = run_cmd(
                "scripts/entity_checkpoint.py",
                "record-install",
                "--checkpoint",
                str(deps_path),
                "--dep",
                "kokkos",
                "--prefix",
                str(tmp / "missing"),
            )

            self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            data = json.loads(deps_path.read_text(encoding="utf-8"))
            self.assertEqual(data["selected"], {})

    def test_record_install_updates_checkpoint_and_invalidates_compat(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            prefix = tmp / "kokkos"
            config = prefix / "lib64" / "cmake" / "Kokkos" / "KokkosConfig.cmake"
            config.parent.mkdir(parents=True)
            config.write_text("# fixture\n", encoding="utf-8")
            deps_path = tmp / "entity-deps.local.json"
            self.write_json(
                deps_path,
                {
                    "schema_version": 1,
                    "selected": {},
                    "paths": {},
                    "compatibility": {"status": "pass"},
                    "status": {"checkpoint": "complete", "ready_for_entity_build": True},
                },
            )

            proc = run_cmd(
                "scripts/entity_checkpoint.py",
                "record-install",
                "--checkpoint",
                str(deps_path),
                "--dep",
                "kokkos",
                "--prefix",
                str(prefix),
                "--cmake-config",
                str(config),
                "--version",
                "5.0.1",
            )

            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            data = json.loads(deps_path.read_text(encoding="utf-8"))
            self.assertTrue(data["selected"]["kokkos"]["validation"]["installed"])
            self.assertEqual(data["compatibility"]["status"], "unknown")
            self.assertFalse(data["status"]["ready_for_entity_build"])

    def test_create_embeds_requirements_snapshot(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            req_path = tmp / "requirements.json"
            deps_path = tmp / "entity-deps.local.json"
            self.write_json(req_path, self.base_requirements(tmp))

            proc = run_cmd(
                "scripts/entity_checkpoint.py",
                "create",
                str(req_path),
                "--output",
                str(deps_path),
            )

            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            data = json.loads(deps_path.read_text(encoding="utf-8"))
            embedded = data["requirements"]["embedded"]
            self.assertEqual(embedded["environment"]["backend"], "cpu")
            self.assertEqual(embedded["compile"]["pgen"], "smoke")

    def test_compat_fails_when_requirements_snapshot_drifts(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            req = self.base_requirements(tmp)
            deps_path = tmp / "entity-deps.local.json"
            req_path = tmp / "requirements.json"
            self.write_json(req_path, req)

            create_proc = run_cmd(
                "scripts/entity_checkpoint.py",
                "create",
                str(req_path),
                "--output",
                str(deps_path),
            )
            self.assertEqual(create_proc.returncode, 0, create_proc.stdout + create_proc.stderr)

            req["environment"]["backend"] = "cuda"
            req["environment"]["gpu_arch"] = "AMPERE80"
            self.write_json(req_path, req)

            proc = run_cmd(
                "scripts/entity_compat.py",
                str(req_path),
                "--checkpoint",
                str(deps_path),
            )

            self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("consistency.requirements_embedded", proc.stdout)
            self.assertIn("environment.backend", proc.stdout)

    def test_run_build_records_success(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            req = self.base_requirements(tmp)
            req["artifacts"] = {"logs_dir": str(tmp / "logs")}
            req_path = tmp / "requirements.json"
            script = tmp / "entity-build.sh"
            self.write_json(req_path, req)
            script.write_text("#!/usr/bin/env bash\necho ok\n", encoding="utf-8")
            script.chmod(0o755)

            proc = run_cmd(
                "scripts/entity_run.py",
                "build",
                str(req_path),
                "--script",
                str(script),
                "--run-id",
                "testrun",
                "--quiet",
                env={"HOME": str(tmp / "home")},
            )

            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            data = json.loads(req_path.read_text(encoding="utf-8"))
            self.assertEqual(data["build_result"]["status"], "pass")
            self.assertEqual(data["build_result"]["exit_code"], 0)
            self.assertTrue(Path(data["build_result"]["runner_log"]).is_file())

    def test_run_build_records_failure(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            req = self.base_requirements(tmp)
            req["artifacts"] = {"logs_dir": str(tmp / "logs")}
            req_path = tmp / "requirements.json"
            script = tmp / "entity-build.sh"
            self.write_json(req_path, req)
            script.write_text("#!/usr/bin/env bash\necho bad\nexit 3\n", encoding="utf-8")
            script.chmod(0o755)

            proc = run_cmd(
                "scripts/entity_run.py",
                "build",
                str(req_path),
                "--script",
                str(script),
                "--run-id",
                "testrun",
                "--quiet",
                env={"HOME": str(tmp / "home")},
            )

            self.assertEqual(proc.returncode, 3, proc.stdout + proc.stderr)
            data = json.loads(req_path.read_text(encoding="utf-8"))
            self.assertEqual(data["build_result"]["status"], "fail")
            self.assertEqual(data["build_result"]["exit_code"], 3)
            self.assertTrue(Path(data["build_result"]["runner_log"]).is_file())


if __name__ == "__main__":
    unittest.main()
