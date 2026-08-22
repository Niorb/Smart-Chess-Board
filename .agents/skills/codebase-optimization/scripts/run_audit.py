#!/usr/bin/env python3
"""
Automated Codebase Optimization Auditor for Python & TypeScript projects.
Executes static analysis tools (Ruff, Vulture, Mypy, Knip, TSC, ESLint) and outputs a unified report.
"""

import shutil
import subprocess
from pathlib import Path


def run_command(cmd, cwd=None, allow_failure=True):
    print(f"\n[AUDIT] Running: {' '.join(cmd)}")
    try:
        res = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
        if res.returncode == 0:
            print(" -> STATUS: PASSED")
            if res.stdout.strip():
                print(res.stdout[:1000])
        else:
            print(f" -> STATUS: FINDINGS DETECTED (Exit code {res.returncode})")
            output = res.stdout + "\n" + res.stderr
            print(output[:2000])
        return res.returncode, res.stdout, res.stderr
    except FileNotFoundError:
        print(f" -> STATUS: SKIPPED (Tool '{cmd[0]}' not installed/found in PATH)")
        return -1, "", f"Tool '{cmd[0]}' not installed"

def audit_python(root_path: Path):
    print("\n==========================================")
    print("       PYTHON STATIC ANALYSIS AUDIT       ")
    print("==========================================")

    # 1. Ruff
    if shutil.which("ruff"):
        run_command(["ruff", "check", str(root_path)])
    else:
        print("[!] ruff is not installed. Install with `pip install ruff`.")

    # 2. Vulture (Dead Code)
    if shutil.which("vulture"):
        run_command(["vulture", str(root_path), "--min-confidence", "80"])
    else:
        print("[!] vulture is not installed. Install with `pip install vulture`.")

    # 3. Mypy (Type Check)
    if shutil.which("mypy"):
        run_command(["mypy", str(root_path), "--ignore-missing-imports"])
    else:
        print("[!] mypy is not installed. Install with `pip install mypy`.")

def audit_typescript(frontend_path: Path):
    if not frontend_path.exists():
        print(f"\n[!] Frontend directory not found at {frontend_path}")
        return

    print("\n==========================================")
    print("     TYPESCRIPT STATIC ANALYSIS AUDIT     ")
    print("==========================================")

    # 1. TSC Type Check
    run_command(["npx", "tsc", "--noEmit"], cwd=frontend_path)

    # 2. Knip Unused Export / Dependency Scan
    run_command(["npx", "knip"], cwd=frontend_path)

    # 3. ESLint
    run_command(["npx", "eslint", "src/"], cwd=frontend_path)

def main():
    root = Path(__file__).resolve().parents[4]
    print(f"Starting codebase optimization audit for root: {root}")

    audit_python(root / "Raspberry")
    audit_typescript(root / "Raspberry" / "frontend")

    print("\n[AUDIT COMPLETE] Review the findings above and apply safe refactorings.")

if __name__ == "__main__":
    main()
