#!/usr/bin/env python3
"""
Artifact Collection Helper Script - 1.x Compatible

Collects specific build artifacts from build directory to staging directory.

Usage:
    python3 collect_artifacts.py --platform PLATFORM --build-type BUILD_TYPE \\
                                  --source-dir SOURCE_DIR --output-dir OUTPUT_DIR
"""

import os
import sys
import argparse
import shutil
from pathlib import Path
from xpum_utils import Logger, PathValidator, PathUtils


class ArtifactCollector:
    """Collects build artifacts to staging directory"""
    
    # Windows artifact whitelists
    WINDOWS_EXES = {'xpu-smi.exe'}
    WINDOWS_DLL_PREFIX = 'xpum'
    WINDOWS_LIBS = {'xpu-smi.lib', 'xpum.lib'}
    WINDOWS_HEADERS = {'xpum_api.h', 'xpum_structs.h', 'xpum.h', 'xpum_core_api.h'}

    def __init__(self, platform: str, build_type: str, source_dir: str, output_dir: str):
        """Initialize the collector"""
        self.platform = platform
        self.build_type = build_type
        self.source_dir = PathValidator.resolve_path(source_dir)
        self.output_dir = PathValidator.resolve_path(output_dir)

    def _find_workspace_root(self) -> Path:
        """Find the workspace root by looking for jenkins directory"""
        # Start from source_dir and search up the directory tree
        current = self.source_dir.resolve()
        for _ in range(10):  # Limit search depth
            if (current / 'jenkins' / 'include').exists():
                return current
            if current.parent == current:  # Reached filesystem root
                break
            current = current.parent
        return self.source_dir.parent.parent  # Fallback to original logic

    def _copy_whitelisted_files(self, pattern: str, whitelist: set) -> int:
        """Copy files matching pattern if they're in whitelist"""
        copied = 0
        for file_path in self.source_dir.rglob(f'*{pattern}'):
            if file_path.name in whitelist:
                try:
                    dest = self.output_dir / file_path.name
                    shutil.copy2(file_path, dest)
                    Logger.log(f"Collected: {file_path.name}")
                    copied += 1
                except Exception as e:
                    Logger.log(f"Failed to copy {file_path}: {e}", "WARNING")
        return copied

    def _find_workspace_root(self) -> Path:
        """Find workspace root by searching for jenkins directory"""
        current = self.source_dir.resolve()
        for _ in range(10):
            if (current / 'jenkins' / 'include').exists():
                return current
            if current.parent == current:
                break
            current = current.parent
        return self.source_dir.parent.parent

    def _collect_windows_artifacts(self) -> bool:
        """Collect specific Windows artifacts (1.x compatible format)"""
        Logger.log("Collecting Windows artifacts...")

        if not self.source_dir.exists():
            Logger.log(f"Source directory not found: {self.source_dir}", "WARNING")
            return True

        collected = 0
        
        # Collect by file type using whitelist
        collected += self._copy_whitelisted_files('.exe', self.WINDOWS_EXES)
        # Collect any xpum*.dll
        for file_path in self.source_dir.rglob('*.dll'):
            name_lower = file_path.name.lower()
            if name_lower.startswith(self.WINDOWS_DLL_PREFIX) and name_lower.endswith('.dll'):
                try:
                    dest = self.output_dir / file_path.name
                    shutil.copy2(file_path, dest)
                    Logger.log(f"Collected: {file_path.name}")
                    collected += 1
                except Exception as e:
                    Logger.log(f"Failed to copy {file_path}: {e}", "WARNING")
        collected += self._copy_whitelisted_files('.lib', self.WINDOWS_LIBS)
        collected += self._copy_whitelisted_files('.h', self.WINDOWS_HEADERS)
        
        # Also collect header files from jenkins/include directory
        workspace_root = self._find_workspace_root()
        jenkins_include_dir = workspace_root / 'jenkins' / 'include'
        if jenkins_include_dir.exists():
            Logger.log(f"Collecting from jenkins/include")
            for file_path in jenkins_include_dir.glob('*.h'):
                try:
                    dest = self.output_dir / file_path.name
                    shutil.copy2(file_path, dest)
                    Logger.log(f"Collected from jenkins/include: {file_path.name}")
                    collected += 1
                except Exception as e:
                    Logger.log(f"Failed to copy {file_path}: {e}", "WARNING")
        else:
            Logger.log(f"Jenkins include directory not found at: {jenkins_include_dir}", "WARNING")

        Logger.log(f"Collected {collected} Windows artifacts")
        return True

    def _collect_linux_artifacts(self) -> bool:
        """Collect Linux artifacts (executables, libraries)"""
        Logger.log("Collecting Linux artifacts...")

        if not self.source_dir.exists():
            Logger.log(f"Source directory not found: {self.source_dir}", "WARNING")
            return True

        collected = 0
        for file_path in self.source_dir.rglob('*'):
            if file_path.is_file() and os.access(file_path, os.X_OK):
                name = file_path.name
                if name.endswith('.so') or name.endswith('.a') or name.startswith('xpu'):
                    try:
                        dest = self.output_dir / name
                        shutil.copy2(file_path, dest)
                        Logger.log(f"Collected: {name}")
                        collected += 1
                    except Exception as e:
                        Logger.log(f"Failed to copy {file_path}: {e}", "WARNING")

        Logger.log(f"Collected {collected} Linux artifacts")
        return True

    def collect(self) -> bool:
        """Collect all artifacts"""
        try:
            # Cleanup output directory
            if self.output_dir.exists():
                shutil.rmtree(self.output_dir)
            PathValidator.ensure_dir_exists(self.output_dir)

            Logger.log(f"Collecting artifacts from {self.source_dir} to {self.output_dir}")

            # Collect platform-specific artifacts
            if self.platform == 'Windows':
                if not self._collect_windows_artifacts():
                    return False
            else:
                if not self._collect_linux_artifacts():
                    return False

            # List collected artifacts
            Logger.log("Collected artifacts:")
            for item in self.output_dir.iterdir():
                Logger.log(f"  {item.name}")

            Logger.log("[OK] Artifact collection completed successfully")
            return True

        except Exception as e:
            Logger.log(f"Failed to collect artifacts: {e}", "ERROR")
            return False


def main() -> int:
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Collect build artifacts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 collect_artifacts.py --platform Windows --build-type Release \\
                                --source-dir builddir_release \\
                                --output-dir artifacts_Windows_Release

  python3 collect_artifacts.py --platform Linux --build-type Debug \\
                                --source-dir builddir_debug \\
                                --output-dir artifacts_Linux_Debug
        """
    )

    parser.add_argument('--platform', required=True, choices=['Windows', 'Linux'],
                        help='Target platform')
    parser.add_argument('--build-type', required=True, choices=['Release', 'Debug'],
                        help='Build type')
    parser.add_argument('--source-dir', required=True,
                        help='Source build directory')
    parser.add_argument('--output-dir', required=True,
                        help='Output artifact directory')

    args = parser.parse_args()

    collector = ArtifactCollector(
        platform=args.platform,
        build_type=args.build_type,
        source_dir=args.source_dir,
        output_dir=args.output_dir
    )

    return 0 if collector.collect() else 1


if __name__ == '__main__':
    sys.exit(main())
