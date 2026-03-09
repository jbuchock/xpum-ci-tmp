#!/usr/bin/env python3
"""
Artifact ZIP Packaging Script - 1.x Compatible Format

Creates versioned ZIP packages matching 1.x build.cmd format:
  Windows: xpu-smi-{VERSION}-{TIMESTAMP}.{COMMIT_SHORT}_win.zip
  Linux:   xpu-smi-{VERSION}-{TIMESTAMP}.{COMMIT_SHORT}_linux.tar.gz

This script replicates the Compress-Archive functionality from build.cmd.

Usage:
    python3 package_artifacts.py --artifact-dir ARTIFACT_DIR \\
                                  --output-dir OUTPUT_DIR \\
                                  --commit COMMIT \\
                                  --timestamp TIMESTAMP \\
                                  --platform Windows|Linux
"""

import sys
import argparse
import zipfile
import tarfile
from pathlib import Path
from xpum_utils import Logger, VersionManager, PathValidator, get_short_commit


class ArtifactPackager:
    """Creates versioned ZIP/TAR.GZ packages in 1.x format"""

    def __init__(self, artifact_dir: str, output_dir: str, 
                 commit: str, timestamp: str, target_platform: str):
        """
        Initialize packager
        
        Args:
            artifact_dir: Directory containing collected artifacts
            output_dir: Output directory for package file
            commit: Full git commit hash
            timestamp: Build timestamp (e.g., "20250127_120000")
            target_platform: Target platform ("Windows" or "Linux")
        """
        self.artifact_dir = PathValidator.resolve_path(artifact_dir)
        self.output_dir = PathValidator.resolve_path(output_dir)
        self.version = VersionManager.read_version(self.artifact_dir)
        self.commit = commit
        self.commit_short = get_short_commit(commit)
        self.timestamp = timestamp
        self.target_platform = target_platform


    def _generate_package_name(self) -> str:
        """Generate 1.x compatible package name"""
        if self.target_platform == "Windows":
            return f"xpu-smi-{self.version}-{self.timestamp}.{self.commit_short}_win.zip"
        else:
            return f"xpu-smi-{self.version}-{self.timestamp}.{self.commit_short}_linux.tar.gz"

    def _create_zip_package(self, zip_path: Path) -> bool:
        """Create ZIP package from artifacts (excludes resources folder)"""
        try:
            Logger.log(f"Creating ZIP package: {zip_path.name}")
            
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for file_path in self.artifact_dir.iterdir():
                    if file_path.is_file():
                        # Add file to zip with just filename (no directories)
                        arcname = file_path.name
                        zipf.write(file_path, arcname=arcname)
                        Logger.log(f"  Added: {arcname}")
                    # Note: resources folder is skipped intentionally (not included in distribution)
            
            file_size_mb = zip_path.stat().st_size / (1024 * 1024)
            Logger.log(f"ZIP package created: {zip_path.name} ({file_size_mb:.2f} MB)")
            return True
        except Exception as e:
            Logger.log(f"Failed to create ZIP package: {e}", "ERROR")
            return False

    def _create_tar_gz_package(self, tar_path: Path) -> bool:
        """Create TAR.GZ package from artifacts (excludes resources folder)"""
        try:
            Logger.log(f"Creating TAR.GZ package: {tar_path.name}")
            
            with tarfile.open(tar_path, 'w:gz') as tar:
                for file_path in self.artifact_dir.iterdir():
                    if file_path.is_file():
                        # Add file to tar with just filename
                        arcname = file_path.name
                        tar.add(file_path, arcname=arcname)
                        Logger.log(f"  Added: {arcname}")
                    # Note: resources folder is skipped intentionally (not included in distribution)
            
            file_size_mb = tar_path.stat().st_size / (1024 * 1024)
            Logger.log(f"TAR.GZ package created: {tar_path.name} ({file_size_mb:.2f} MB)")
            return True
        except Exception as e:
            Logger.log(f"Failed to create TAR.GZ package: {e}", "ERROR")
            return False

    def package(self) -> Path:
        """Create package from artifacts"""
        try:
            # Validate source directory
            if not self.artifact_dir.exists():
                Logger.log(f"Artifact directory not found: {self.artifact_dir}", "ERROR")
                return None

            if not list(self.artifact_dir.iterdir()):
                Logger.log(f"Artifact directory is empty: {self.artifact_dir}", "WARNING")

            # Create output directory
            PathValidator.ensure_dir_exists(self.output_dir)

            # Generate package name in 1.x format
            package_name = self._generate_package_name()
            package_path = self.output_dir / package_name

            # Remove existing package
            if package_path.exists():
                Logger.log(f"Removing existing package: {package_name}")
                package_path.unlink()

            # Log packaging details
            Logger.log(f"Packaging artifacts in 1.x format")
            Logger.log(f"  Version: {self.version}")
            Logger.log(f"  Commit: {self.commit_short}")
            Logger.log(f"  Timestamp: {self.timestamp}")
            Logger.log(f"  Platform: {self.target_platform}")
            Logger.log(f"  Package: {package_name}")

            # Create package based on platform
            if self.target_platform == "Windows":
                success = self._create_zip_package(package_path)
            else:
                success = self._create_tar_gz_package(package_path)

            if not success:
                return None

            # Verify package
            if package_path.exists() and package_path.stat().st_size > 0:
                Logger.log(f"[OK] Package created successfully")
                return package_path
            else:
                Logger.log(f"Package file is empty or missing", "ERROR")
                return None

        except Exception as e:
            Logger.log(f"Failed to package artifacts: {e}", "ERROR")
            return None


def main() -> int:
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Package build artifacts into ZIP/TAR.GZ in 1.x format",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Windows - create ZIP package (reads version from VERSION file)
  python3 package_artifacts.py --artifact-dir artifacts_Windows_Release \\
                                --output-dir packages \\
                                --commit abc123def456 \\
                                --timestamp 20250127_120000 \\
                                --platform Windows

  # Linux - create TAR.GZ package (reads version from VERSION file)
  python3 package_artifacts.py --artifact-dir artifacts_Linux_Release \\
                                --output-dir packages \\
                                --commit abc123def456 \\
                                --timestamp 20250127_120000 \\
                                --platform Linux

Output format:
  Windows: xpu-smi-2.0.0-20250127_120000.abc123de_win.zip
  Linux:   xpu-smi-2.0.0-20250127_120000.abc123de_linux.tar.gz
        """
    )

    parser.add_argument('--artifact-dir', required=True,
                        help='Directory containing collected artifacts')
    parser.add_argument('--output-dir', required=True,
                        help='Output directory for package file')
    parser.add_argument('--commit', required=True,
                        help='Git commit hash (full or short)')
    parser.add_argument('--timestamp', required=True,
                        help='Build timestamp (e.g., 20250127_120000)')
    parser.add_argument('--platform', required=True,
                        choices=['Windows', 'Linux'],
                        help='Target platform')

    args = parser.parse_args()

    packager = ArtifactPackager(
        artifact_dir=args.artifact_dir,
        output_dir=args.output_dir,
        commit=args.commit,
        timestamp=args.timestamp,
        target_platform=args.platform
    )

    package_path = packager.package()
    return 0 if package_path else 1


if __name__ == '__main__':
    sys.exit(main())
