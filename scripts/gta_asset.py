#!/usr/bin/env python3
"""
Minimal GTA asset helper for CI:
- download gta-asset binary
- push package dir using gta-asset
"""

import argparse
import os
import ssl
import stat
import subprocess
import sys
import urllib.request
from pathlib import Path

def _platform() -> str:
    return "win" if sys.platform.startswith("win") else "linux"


def _gta_binary() -> str:
    return "gta-asset.exe" if sys.platform.startswith("win") else "gta-asset"


def default_gta_asset_url() -> str:
    return (
        f"https://gfx-assets.fm.intel.com/artifactory/gta-fm/gta-asset/latest/{_platform()}/artifacts/{_gta_binary()}"
    )


def download_gta_asset(
    asset_path: Path,
    asset_url: str = default_gta_asset_url(),
    insecure: bool = False
) -> int:
    try:
        asset_path.parent.mkdir(parents=True, exist_ok=True)
        print(f"Downloading gta-asset from: {asset_url}")
        context = ssl._create_unverified_context() if insecure else None
        with urllib.request.urlopen(asset_url, context=context) as resp:
            data = resp.read()
        asset_path.write_bytes(data)
        if _platform() == "linux":
            asset_path.chmod(asset_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        print(f"Downloaded gta-asset to: {asset_path}")
        return 0
    except Exception as e:
        print(f"ERROR: download failed: {e}", file=sys.stderr)
        return 1


def push_gta_asset(
    asset_bin: Path,
    asset_path: str,
    asset_name: str,
    asset_version: str,
    asset_src: Path,
    root_url: str,
    user: str,
    password: str,
    archive: bool = False,
) -> int:
    if not asset_bin.exists():
        print(f"Binary not found at {asset_bin}, downloading...")
        rc = download_gta_asset(asset_path=asset_bin,  insecure=True)
        if rc != 0:
            print(f"ERROR: Failed to download gta-asset binary", file=sys.stderr)
            return rc

    if not asset_src.exists():
        msg = f"Asset to push not found: {asset_src}"
        print(f"ERROR: {msg}", file=sys.stderr)
        return 1

    # TODO: If asset_src is a directory, should we require to archive it before pushing?

    cmd = [
        str(asset_bin),
        "push",
        asset_path,
        asset_name,
        asset_version,
        str(asset_src),
        "--root-url",
        root_url,
        "--user",
        user,
        "--password",
        password,
    ]
    if not archive:
        cmd.append("--no-archive")

    print(f"Uploading: {asset_src}")
    print(f"Target: {asset_path}/{asset_name}/{asset_version}")
    # cmd is intentionally not printed to avoid leaking --password in logs
    result = subprocess.run(cmd, check=False)

    if result.returncode != 0:
        print(f"ERROR: gta-asset push failed ({result.returncode})", file=sys.stderr)
        return result.returncode

    print("Upload done")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="GTA asset helper")
    sub = parser.add_subparsers(dest="cmd", required=True)

    _default_bin = str(Path.cwd() / _gta_binary())

    dl = sub.add_parser("download")
    dl.add_argument("--asset-url", default=default_gta_asset_url())
    dl.add_argument("--output", default=_default_bin)
    dl.add_argument("--insecure", action="store_true")

    push = sub.add_parser("push")
    push.add_argument("--asset-bin", default=_default_bin)
    push.add_argument("--asset-path", required=True)
    push.add_argument("--asset-name", required=True)
    push.add_argument("--asset-version", required=True)
    push.add_argument("--asset-src", required=True, help="Local directory, file, or archive to push")
    push.add_argument("--root-url", required=True)
    push.add_argument("--user", default=os.environ.get("ARTIFACTORY_USER", ""))
    push.add_argument("--password", default=os.environ.get("ARTIFACTORY_PASSWORD", ""))
    push.add_argument("--no-archive", action="store_true")

    args = parser.parse_args()

    if args.cmd == "download":
        return download_gta_asset(
            asset_url=args.asset_url,
            asset_path=Path(args.output).resolve(),
            insecure=args.insecure,
        )

    if args.cmd == "push":
        if not args.user:
            print("ERROR: --user or ARTIFACTORY_USER env var is required", file=sys.stderr)
            return 2
        if not args.password:
            print("ERROR: --password or ARTIFACTORY_PASSWORD env var is required", file=sys.stderr)
            return 2
        return push_gta_asset(
            asset_bin=Path(args.asset_bin).resolve(),
            asset_src=Path(args.asset_src).resolve(),
            asset_path=args.asset_path,
            asset_name=args.asset_name,
            asset_version=args.asset_version,
            root_url=args.root_url,
            user=args.user,
            password=args.password,
            archive=not args.no_archive
        )

    return 2


if __name__ == "__main__":
    sys.exit(main())