"""
AGENTIC Launcher — CLI entry point for the Multi-Agent System.

Provides a unified command-line interface for all common operations.
The .bat wrapper calls this script for advanced functions.

Usage:
    python scripts/launcher.py test          # Run tests
    python scripts/launcher.py cov           # Coverage
    python scripts/launcher.py deploy        # Deploy to projects
    python scripts/launcher.py export        # Export to Drive
    python scripts/launcher.py lint          # Ruff lint
    python scripts/launcher.py gpu           # GPU info
    python scripts/launcher.py menu          # Interactive menu
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def cmd(args: list[str], desc: str = "") -> int:
    """Run a command with nice output."""
    if desc:
        print(f"\n{'='*60}")
        print(f"  {desc}")
        print(f"{'='*60}")
    print(f"  $ {' '.join(args)}\n")
    result = subprocess.run(args, cwd=ROOT)
    if result.returncode != 0:
        print(f"\n  ❌ Failed (exit {result.returncode})")
    else:
        print(f"\n  ✅ OK")
    return result.returncode


def do_test(args: list[str]) -> int:
    """Run tests (fast: exclude slow)."""
    return cmd([
        sys.executable, "-m", "pytest", "harness/tests/",
        "-x", "-q", "--tb=short", "-m", "not slow",
    ] + args, desc="Running Tests (fast)")


def do_cov(args: list[str]) -> int:
    """Run tests with coverage."""
    return cmd([
        sys.executable, "-m", "pytest", "harness/tests/",
        "-q", "--tb=no",
        "--cov=harness", "--cov-config=pyproject.toml",
    ] + args, desc="Running Coverage")


def do_deploy(args: list[str]) -> int:
    """Deploy to all projects."""
    return cmd([
        sys.executable, "scripts/deploy_all.py",
    ] + args, desc="Deploying to Projects")


def do_export(args: list[str]) -> int:
    """Export to Google Drive with ZIP."""
    return cmd([
        sys.executable, "scripts/export_to_drive.py",
    ] + args, desc="Exporting to Google Drive")


def do_lint(args: list[str]) -> int:
    """Run Ruff linter."""
    return cmd([
        sys.executable, "-m", "ruff", "check", "harness/",
        "--select=E,F,W,I,N", "--ignore=E501",
    ] + args, desc="Running Ruff Linter")


def do_gpu() -> int:
    """Show GPU information."""
    from harness.gpu_accel import HAVE_CUDA, DEVICE_NAME, GPU_MEMORY_GB
    print(f"\n{'='*60}")
    print("  GPU Information")
    print(f"{'='*60}")
    print(f"  Available: {HAVE_CUDA}")
    print(f"  Device:    {DEVICE_NAME}")
    print(f"  VRAM:      {GPU_MEMORY_GB:.1f} GB")
    print(f"{'='*60}\n")
    return 0


def do_list_tests() -> int:
    """List all test files."""
    tests = sorted(ROOT.glob("harness/tests/test_*.py"))
    print(f"\n{'='*60}")
    print(f"  Test Files ({len(tests)})")
    print(f"{'='*60}")
    for t in tests:
        name = t.name
        lines = len(t.read_text().splitlines())
        print(f"  {name:45s} {lines:4d} lines")
    print(f"{'='*60}\n")
    return 0


def do_menu() -> int:
    """Launch interactive menu (via .bat on Windows)."""
    import subprocess
    bat = ROOT / "launcher.bat"
    if bat.exists():
        return subprocess.call([str(bat)], cwd=ROOT)
    print("launcher.bat not found")
    return 1


def main():
    parser = argparse.ArgumentParser(
        description="AGENTIC Multi-Agent System Launcher"
    )
    parser.add_argument("command", nargs="?", default="menu",
        choices=["test", "cov", "deploy", "export", "lint", "gpu",
                 "list", "menu", "fast"],
        help="Command to execute")
    parser.add_argument("args", nargs=argparse.REMAINDER,
        help="Additional arguments for the command")

    args = parser.parse_args()

    commands = {
        "test":   lambda: do_test(args.args),
        "cov":    lambda: do_cov(args.args),
        "deploy": lambda: do_deploy(args.args),
        "export": lambda: do_export(args.args),
        "lint":   lambda: do_lint(args.args),
        "gpu":    lambda: do_gpu(),
        "list":   lambda: do_list_tests(),
        "fast":   lambda: do_test([]),
        "menu":   lambda: do_menu(),
    }

    fn = commands.get(args.command)
    if fn:
        sys.exit(fn())

    parser.print_help()


if __name__ == "__main__":
    main()
