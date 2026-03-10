#!/usr/bin/env python3
"""
XPUM Cross-Platform Build Script

This script automates the build process for XPUM on Linux and Windows.
It handles environment setup, dependency installation, and compilation.

Usage:
    python3 build_xpum.py [--build-type BUILD_TYPE] [--run-tests] [--verbose]

Examples:
    python3 build_xpum.py --build-type Release --run-tests
"""

import os
import sys
import subprocess
import platform
import argparse
import io
from pathlib import Path
from typing import List

# Configure stdout encoding for Windows console compatibility
if platform.system() == "Windows":
    if sys.stdout.encoding != 'utf-8':
        if isinstance(sys.stdout, io.TextIOWrapper):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')


class XPUMBuilder:
    """Cross-platform XPUM builder"""

    # Configuration constants
    RECIPES = [("level-zero", "1.27.0"), ("metee", "6.0.0"), ("igsc", "0.9.6")]
    REQUIREMENTS_FILE = "requirements.txt"
    TARGETS = ["xpu-smi", "hal/core/xpum:shared_library"]
    LINUX_PACKAGES = ["python3-venv", "libcurl4-openssl-dev", "meson", "curl", "wget"]
    VS_PATHS = [
        "C:\\Program Files\\Microsoft Visual Studio\\2022\\Enterprise",
        "C:\\Program Files\\Microsoft Visual Studio\\2022\\Professional",
        "C:\\Program Files\\Microsoft Visual Studio\\2022\\Community",
    ]

    def __init__(self, build_type: str = "Release", run_tests: bool = False, verbose: bool = False):
        """Initialize the builder"""
        self.build_type = build_type
        self.build_type_lower = build_type.lower()
        self.run_tests = run_tests
        self.verbose = verbose
        self.current_os = platform.system()

        # Project root is 2 levels up from this script (jenkins/scripts -> jenkins -> root)
        self.script_dir = Path(__file__).parent
        self.project_root = self.script_dir.parent.parent
        self.venv_path = self.script_dir / ".venv"
        self.build_dir = self.project_root / f"build_{self.build_type}"
        self.conan_output_dir = self.project_root

        # Set environment variables (proxy)
        proxy_settings = {
            'https_proxy': 'http://proxy-dmz.intel.com:911',
            'http_proxy': 'http://proxy-dmz.intel.com:911',
            'no_proxy': 'localhost,127.0.0.1,intel.com,.intel.com',
        }
        for key, value in proxy_settings.items():
            os.environ[key] = os.environ[key.upper()] = value

    def log(self, message: str, level: str = "INFO") -> None:
        """Log messages with level prefix"""
        try:
            print(f"[{level}] {message}")
        except UnicodeEncodeError:
            # Fallback to ASCII representation if Unicode fails
            message_ascii = message.encode('ascii', errors='replace').decode('ascii')
            print(f"[{level}] {message_ascii}")

    def run_command(self, cmd: List[str], check: bool = True) -> subprocess.CompletedProcess:
        """Run a command and return the result"""
        self.log(f"Running: {' '.join(cmd)}")
        result = subprocess.run(cmd, check=False, capture_output=not self.verbose, text=True)

        if self.verbose or result.stdout:
            print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)

        if check and result.returncode != 0:
            error_msg = f"Command failed with exit code {result.returncode}"
            if result.stdout:
                error_msg += f"\nStdout: {result.stdout}"
            if result.stderr:
                error_msg += f"\nStderr: {result.stderr}"
            raise RuntimeError(error_msg)

        return result

    def setup_environment(self) -> None:
        """Setup: venv, build tools, and system dependencies"""
        self.log("Setting up Python environment...")

        # Setup venv paths based on OS
        if self.current_os == "Windows":
            self.venv_python = str(self.venv_path / "Scripts" / "python.exe")
            self.venv_pip = str(self.venv_path / "Scripts" / "pip.exe")
            self.venv_conan = str(self.venv_path / "Scripts" / "conan.exe")
            self.venv_meson = str(self.venv_path / "Scripts" / "meson.exe")
        else:
            self.venv_python = str(self.venv_path / "bin" / "python")
            self.venv_pip = str(self.venv_path / "bin" / "pip")
            self.venv_conan = str(self.venv_path / "bin" / "conan")
            self.venv_meson = str(self.venv_path / "bin" / "meson")

        # Create venv if not exists
        if not self.venv_path.exists():
            self.run_command([sys.executable, "-m", "venv", str(self.venv_path)])

        # Install build tools from requirements.txt
        self.log("Installing build tools...")
        requirements_path = self.script_dir / self.REQUIREMENTS_FILE
        if requirements_path.exists():
            self.run_command([self.venv_pip, "install", "-U", "-r", str(requirements_path)])
        else:
            self.log(f"Warning: {self.REQUIREMENTS_FILE} not found, installing default packages", "WARNING")
            self.run_command([self.venv_pip, "install", "-U", "meson", "conan>=2.0", "ninja", "cmake"])

        # Install system dependencies
        if self.current_os == "Linux":
            self.log("Installing system dependencies on Linux...")
            try:
                # Try with sudo first (for non-containerized environments)
                result = subprocess.run(["which", "sudo"], capture_output=True)
                if result.returncode == 0:
                    self.run_command(["sudo", "apt", "update"], check=False)
                    self.run_command(["sudo", "apt", "install", "-y"] + self.LINUX_PACKAGES, check=False)
                else:
                    # No sudo (likely in container), try direct apt commands
                    self.log("sudo not available, attempting direct package installation...", "WARNING")
                    self.run_command(["apt-get", "update"], check=False)
                    self.run_command(["apt-get", "install", "-y"] + self.LINUX_PACKAGES, check=False)
            except Exception as e:
                self.log(f"Warning: Failed to install system dependencies: {e}", "WARNING")
        elif self.current_os == "Windows":
            self.log("Checking Windows build tools...")
            vs_found = any(Path(p).exists() for p in self.VS_PATHS)
            if not vs_found:
                self.log("Visual Studio 2022 not found. Please install it.", "ERROR")
                sys.exit(1)

    def _get_conan_settings(self) -> List[str]:
        """Get platform-specific conan settings"""
        settings = [
            "-s", "arch=x86_64",
            "-s", f"build_type={self.build_type}",
        ]

        if self.current_os == "Windows":
            settings.extend([
                "-s", "compiler=msvc",
                "-s", "compiler.cppstd=20",
                "-s", "compiler.runtime=dynamic",
                "-s", "compiler.version=194",
                "-s", "os=Windows",
            ])
        else:
            settings.extend([
                "-s", "compiler=gcc",
                "-s", "compiler.cppstd=20",
                "-s", "compiler.libcxx=libstdc++11",
                "-s", "compiler.version=13",
                "-s", "os=Linux",
            ])

        return settings

    def setup_dependencies(self) -> None:
        """Setup Conan profile, recipes, and install dependencies"""
        conan_cmd = self.venv_conan
        os.chdir(self.project_root)

        # Detect Conan profile
        self.log("Detecting Conan profile...")
        try:
            self.run_command([conan_cmd, "profile", "detect", "--force"])
        except RuntimeError as e:
            self.log("Conan profile detection failed. Attempting to show conan version...", "WARNING")
            self.run_command([conan_cmd, "--version"], check=False)
            raise

        # Create recipes
        self.log("Creating Conan recipes...")
        conan_settings = self._get_conan_settings()
        for name, version in self.RECIPES:
            recipe_path = self.project_root / "recipes" / name
            if not recipe_path.exists():
                self.log(f"Recipe not found at {recipe_path}", "WARNING")
                continue
            cmd = [
                conan_cmd, "create",
                str(recipe_path),
                f"--name={name}",
                f"--version={version}",
            ] + conan_settings
            self.run_command(cmd, check=False)

        # Install dependencies
        self.log("Installing dependencies via Conan...")
        cmd = [
            conan_cmd, "install", ".",
            "--build=missing",
        ] + conan_settings
        self.run_command(cmd)

    def build_project(self) -> None:
        """Configure, compile, and test the project"""
        meson_cmd = self.venv_meson
        os.chdir(self.project_root)

        meson_options = []
        if self.current_os == "Windows":
            meson_options.extend(["-Dshared_library=true"])

        # Setup Meson
        self.log(f"Setting up Meson build (type={self.build_type})...")
        if self.build_dir.exists():
            self.run_command([
                meson_cmd, "configure",
                str(self.build_dir),
                f"--buildtype={self.build_type_lower}",
            ] + meson_options)
        else:
            setup_cmd = [
                meson_cmd, "setup",
                str(self.build_dir),
                f"--buildtype={self.build_type_lower}",
            ]
            setup_cmd.extend(meson_options)
            # Add dev flag for Linux
            if self.current_os == "Linux":
                setup_cmd.extend(["-D", "dev=true"])
            # Native file is in project root
            setup_cmd.append("--native-file=conan_meson_native.ini")
            self.run_command(setup_cmd)

        # Compile
        self.log("Compiling project...")
        self.run_command([
            meson_cmd, "compile",
            "-C", str(self.build_dir),
        ] + self.TARGETS)
        self.log("[OK] Compilation successful")

        # Run tests (only for Release builds, matching old Jenkinsfile)
        if self.run_tests and self.build_type == "Release":
            self.log("Running tests...")
            self.run_command([
                meson_cmd, "test",
                "-C", str(self.build_dir),
                "--verbose",
            ], check=False)
            logs_dir = self.build_dir / "meson-logs"
            if logs_dir.exists():
                self.log(f"Test logs available at {logs_dir}")

    def build(self) -> int:
        """Execute the full build process"""
        try:
            print("\n" + "="*60)
            print("XPUM Build Summary")
            print("="*60)
            print(f"OS: {self.current_os} | Build: {self.build_type} | Tests: {self.run_tests}")
            print(f"Verbose: {self.verbose}")
            print(f"Root: {self.project_root}\nBuild: {self.build_dir}")
            print(f"Conan: {self.conan_output_dir}")
            exe = f"xpu-smi.exe" if self.current_os == "Windows" else "xpu-smi"
            print(f"Output: {self.build_dir / 'ial' / 'cli' / exe}")
            print("="*60 + "\n")

            self.setup_environment()
            self.setup_dependencies()
            self.build_project()

            self.log("[OK] Build completed successfully!")
            return 0

        except Exception as e:
            self.log(f"[FAILED] Build failed: {e}", "ERROR")
            return 1


def main() -> int:
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="XPUM Cross-Platform Build Script",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Examples:\n  python3 build_xpum.py\n  python3 build_xpum.py --build-type Release --run-tests"
    )
    parser.add_argument("--build-type", choices=["Release", "Debug"], default="Release")
    parser.add_argument("--run-tests", action="store_true")
    parser.add_argument("--verbose", action="store_true")

    args = parser.parse_args()
    return XPUMBuilder(args.build_type, args.run_tests, args.verbose).build()


if __name__ == "__main__":
    sys.exit(main())
