"""Execute candidate code only in an immutable, resource-limited Docker container."""

import json
import os
import re
import subprocess
import tempfile
import threading
from pathlib import Path
from uuid import uuid4

from app.contracts.errors import AppError
from app.contracts.training import GradingSpec
from app.routing.ml.graders import Grade


def check_sandbox(image: str) -> None:
    if not re.fullmatch(r"sha256:[a-f0-9]{64}", image):
        raise AppError(
            "CODE_SANDBOX_UNAVAILABLE", 409, "A locally pinned Docker image ID is required"
        )
    try:
        result = subprocess.run(
            ["docker", "image", "inspect", image, "--format", "{{.Id}}"],
            capture_output=True,
            timeout=15,
            check=False,
        )
        if result.returncode or result.stdout.decode().strip() != image:
            raise ValueError("Image unavailable")
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        raise AppError("CODE_SANDBOX_UNAVAILABLE", 409, "Docker sandbox/image unavailable") from exc


def code_grade(spec: GradingSpec, output: str) -> Grade:
    image = spec.docker_image or ""
    check_sandbox(image)
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", output, re.DOTALL)
    code = blocks[0] if len(blocks) == 1 else output
    if len(code.encode()) > 65536:
        return Grade(False, {"tests_passed": 0, "output_limit": 1}, spec.label_source)
    name = "router-grade-" + uuid4().hex
    marker = uuid4().hex
    with tempfile.TemporaryDirectory(prefix="router-code-") as directory:
        path = Path(directory)
        (path / "candidate.py").write_text(code, encoding="utf-8")
        (path / "tests.json").write_text(
            json.dumps([spec.test_setup, *spec.tests]), encoding="utf-8"
        )
        runner = (
            "import json\n"
            "ns={}\n"
            "try:\n"
            " exec(compile(open('/work/candidate.py').read(), '<candidate>', 'exec'), ns)\n"
            " for test in json.load(open('/work/tests.json')): exec(compile(test, '<test>', 'exec'), ns)\n"
            f" print({marker!r})\n"
            "except BaseException:\n"
            " raise SystemExit(1)\n"
        )
        (path / "runner.py").write_text(runner, encoding="utf-8")
        args = [
            "docker",
            "run",
            "--rm",
            "--pull=never",
            "--name",
            name,
            "--network=none",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--pids-limit=32",
            "--memory=128m",
            "--cpus=1",
            "--user=65534:65534",
            "--log-driver=none",
            "--tmpfs=/tmp:rw,noexec,nosuid,size=16m",
            "--mount",
            f"type=bind,source={path.resolve()},target=/work,readonly",
            image,
            "python",
            "-I",
            "-B",
            "-S",
            "/work/runner.py",
        ]
        collected = bytearray()
        too_large = threading.Event()
        try:
            process = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )

            def read_output() -> None:
                assert process.stdout is not None
                while chunk := process.stdout.read(4096):
                    if len(collected) + len(chunk) > 65536:
                        too_large.set()
                        process.kill()
                        break
                    collected.extend(chunk)

            reader = threading.Thread(target=read_output, daemon=True)
            reader.start()
            timed_out = False
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                timed_out = True
                process.kill()
                process.wait(timeout=5)
            reader.join(timeout=2)
            if process.returncode == 125:
                raise AppError("CODE_SANDBOX_UNAVAILABLE", 409, "Docker execution failed")
            passed = (
                not timed_out
                and not too_large.is_set()
                and process.returncode == 0
                and collected.decode(errors="replace").splitlines()[-1:] == [marker]
            )
            return Grade(
                passed,
                {
                    "tests_passed": float(passed),
                    "timeout": float(timed_out),
                    "output_limit": float(too_large.is_set()),
                },
                spec.label_source,
            )
        except OSError as exc:
            raise AppError("CODE_SANDBOX_UNAVAILABLE", 409, "Docker execution unavailable") from exc
        finally:
            subprocess.run(
                ["docker", "rm", "-f", name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=15,
                check=False,
            )
