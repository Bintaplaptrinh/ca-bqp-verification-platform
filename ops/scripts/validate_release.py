from __future__ import annotations

import json
import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def calibration_mismatches(expected: object, actual: object, path: str = "$", *, tolerance: float = 1e-12) -> list[str]:
    """Compare calibration JSON while tolerating platform-level float noise."""
    if isinstance(expected, bool) or isinstance(actual, bool):
        return [] if expected is actual else [f"{path}: {expected!r} != {actual!r}"]
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        if math.isclose(float(expected), float(actual), rel_tol=tolerance, abs_tol=tolerance):
            return []
        return [f"{path}: {expected!r} != {actual!r}"]
    if type(expected) is not type(actual):
        return [f"{path}: type {type(expected).__name__} != {type(actual).__name__}"]
    if isinstance(expected, dict):
        differences: list[str] = []
        expected_keys, actual_keys = set(expected), set(actual)
        for key in sorted(expected_keys - actual_keys):
            differences.append(f"{path}.{key}: missing from regenerated artifact")
        for key in sorted(actual_keys - expected_keys):
            differences.append(f"{path}.{key}: unexpected regenerated field")
        for key in sorted(expected_keys & actual_keys):
            differences.extend(calibration_mismatches(expected[key], actual[key], f"{path}.{key}", tolerance=tolerance))
        return differences
    if isinstance(expected, list):
        if len(expected) != len(actual):
            return [f"{path}: list length {len(expected)} != {len(actual)}"]
        differences: list[str] = []
        for index, (expected_item, actual_item) in enumerate(zip(expected, actual)):
            differences.extend(calibration_mismatches(expected_item, actual_item, f"{path}[{index}]", tolerance=tolerance))
        return differences
    return [] if expected == actual else [f"{path}: {expected!r} != {actual!r}"]


def run(label: str, cmd: list[str], cwd: Path | None = None) -> None:
    print(f"[RUN] {label}: {' '.join(cmd)}")
    subprocess.run(cmd, cwd=cwd or ROOT, check=True)
    print(f"[OK ] {label}")


def main() -> int:
    backend = ROOT / "apps/backend"
    run("backend tests", [sys.executable, "-m", "pytest", "-q"], backend)
    run("python compile", [sys.executable, "-m", "compileall", "-q", "src", "tests", "scripts", "migrations"], backend)

    npm = shutil.which("npm")
    web = ROOT / "apps/web"
    legacy = [web / "config.js", web / "src/app.js", web / "src/pages.js", web / "src/api.js", web / "src/auth.js"]
    leftovers = [str(x.relative_to(ROOT)) for x in legacy if x.exists()]
    if leftovers:
        raise SystemExit(f"Legacy static frontend files still present: {leftovers}")
    json.loads((web / "package.json").read_text(encoding="utf-8"))
    print("[OK ] React/TypeScript frontend manifest + legacy-static removal")
    if npm and (web / "node_modules").exists():
        run("frontend typecheck", [npm, "run", "typecheck"], web)
        run("frontend production build", [npm, "run", "build"], web)
    else:
        print("[SKIP] frontend node_modules unavailable; npm typecheck/build are enforced in CI and Docker build")

    json_files = [
        ROOT / "apps/backend/artifacts/resolver_calibration.json",
    ]
    for p in json_files:
        json.loads(p.read_text(encoding="utf-8"))
        print(f"[OK ] JSON {p.relative_to(ROOT)}")

    yaml_files = [
        ROOT / "compose.yaml",
        ROOT / "config.yaml",
        ROOT / ".github/workflows/ci.yml",
        ROOT / ".github/workflows/release.yml",
    ]
    for p in yaml_files:
        yaml.safe_load(p.read_text(encoding="utf-8"))
        print(f"[OK ] YAML {p.relative_to(ROOT)}")

    calibration_check = Path(tempfile.gettempdir()) / "cabqp-resolver-calibration-check.json"
    run(
        "calibration reproducibility",
        [sys.executable, "pipelines/ml/calibrate_resolver.py", "--output", str(calibration_check)],
        ROOT,
    )
    expected = json.loads((ROOT / "apps/backend/artifacts/resolver_calibration.json").read_text(encoding="utf-8"))
    actual = json.loads(calibration_check.read_text(encoding="utf-8"))
    differences = calibration_mismatches(expected, actual)
    if differences:
        preview = "\n".join(f"  - {item}" for item in differences[:20])
        raise SystemExit(f"Calibration artifact is not reproducible:\n{preview}")
    print("[OK ] calibration artifact semantically reproducible (float tolerance 1e-12)")

    docker = shutil.which("docker")
    if docker:
        run("docker compose config", [docker, "compose", "config", "-q"], ROOT)
    else:
        print("[SKIP] docker not installed; image build/Trivy/migration drill are enforced in CI")

    print("Release-local validation PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
