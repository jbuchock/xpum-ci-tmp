#!/usr/bin/env python3
"""
Shared utilities for XPUM build pipeline scripts

Provides common functionality for:
- Logging with safe encoding
- File operations
- Version management
- Path utilities
"""

import io
import sys
import platform
from pathlib import Path
from typing import Optional

# Configure stdout encoding for Windows console compatibility on import
if platform.system() == "Windows":
    if sys.stdout.encoding != 'utf-8':
        if isinstance(sys.stdout, io.TextIOWrapper):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')


class Logger:
    """Thread-safe logger with Unicode support"""
    
    @staticmethod
    def log(message: str, level: str = "INFO") -> None:
        """Log messages with level prefix and safe encoding"""
        try:
            print(f"[{level}] {message}")
        except UnicodeEncodeError:
            message_ascii = message.encode('ascii', errors='replace').decode('ascii')
            print(f"[{level}] {message_ascii}")


class VersionManager:
    """Manages version reading from VERSION file"""
    
    DEFAULT_VERSION = "2.0.0"
    
    @staticmethod
    def read_version(start_dir: Optional[Path] = None) -> str:
        """
        Read version from VERSION file in workspace root
        
        Args:
            start_dir: Directory to start search from. If None, searches from current directory.
        
        Returns:
            Version string or DEFAULT_VERSION if not found
        """
        if start_dir is None:
            start_dir = Path.cwd()
        
        current = Path(start_dir).resolve()
        
        # Search up directory tree for VERSION file
        for _ in range(15):  # Reasonable limit
            version_file = current / 'VERSION'
            if version_file.exists():
                try:
                    version = version_file.read_text().strip()
                    Logger.log(f"Read version from {version_file}: {version}")
                    return version
                except Exception as e:
                    Logger.log(f"Failed to read VERSION file: {e}", "WARNING")
                    break
            
            if current.parent == current:  # Reached filesystem root
                break
            current = current.parent
        
        Logger.log(f"VERSION file not found, using default {VersionManager.DEFAULT_VERSION}", "WARNING")
        return VersionManager.DEFAULT_VERSION


class PathUtils:
    """Utility functions for path operations"""
    
    @staticmethod
    def find_file_upward(start_dir: Path, filename: str, max_depth: int = 15) -> Optional[Path]:
        """
        Search for a file by going up the directory tree
        
        Args:
            start_dir: Directory to start search from
            filename: Name of file to find
            max_depth: Maximum depth to search
            
        Returns:
            Path to file if found, None otherwise
        """
        current = Path(start_dir).resolve()
        
        for _ in range(max_depth):
            target = current / filename
            if target.exists():
                return target
            
            if current.parent == current:  # Reached filesystem root
                break
            current = current.parent
        
        return None


class PathValidator:
    """Validates and safely handles file paths"""
    
    @staticmethod
    def resolve_path(path_str: str) -> Path:
        """
        Resolve a path string to an absolute Path object
        
        Args:
            path_str: Path as string
            
        Returns:
            Resolved Path object
        """
        return Path(path_str).resolve()
    
    @staticmethod
    def ensure_dir_exists(path: Path) -> None:
        """
        Ensure a directory exists, creating it if necessary
        
        Args:
            path: Directory path to create
        """
        path.mkdir(parents=True, exist_ok=True)
    
    @staticmethod
    def ensure_parent_exists(path: Path) -> None:
        """
        Ensure parent directory of a path exists
        
        Args:
            path: File path whose parent should exist
        """
        path.parent.mkdir(parents=True, exist_ok=True)


def get_short_commit(commit_hash: str) -> str:
    """
    Get short form of commit hash
    
    Args:
        commit_hash: Full commit hash
        
    Returns:
        First 8 characters or full hash if shorter
    """
    return commit_hash[:8] if commit_hash else "unknown"
