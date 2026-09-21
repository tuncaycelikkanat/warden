"""Utility functions for discovering source files while respecting ignore patterns."""

import os
from pathlib import Path


def discover_source_files(repo_path: Path) -> list[Path]:
    """
    Discovers source files (.py, .js, .ts) in the given repository path,
    excluding common virtual environment and dependency directories.
    """
    allowed_extensions = {".py", ".js", ".ts"}
    excluded_dirs = {
        ".venv", "venv", "node_modules", ".git", "__pycache__", "dist", "build",
        "fixtures", "test_data", "testdata", ".pytest_cache", ".ruff_cache", ".mypy_cache"
    }
    
    source_files = []
    
    for root, dirs, files in os.walk(repo_path):
        # Modify dirs in-place to skip excluded directories
        dirs[:] = [d for d in dirs if d not in excluded_dirs and not d.startswith('.')]
        
        for file in files:
            # Exclude dummy/scratch test files
            if file.startswith("dummy_"):
                continue
            file_path = Path(root) / file
            if file_path.suffix in allowed_extensions:
                source_files.append(file_path)
                
    return source_files
