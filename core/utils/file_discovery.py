import os
from pathlib import Path
from typing import List

def discover_source_files(repo_path: Path) -> List[Path]:
    """
    Discovers source files (.py, .js, .ts) in the given repository path,
    excluding common virtual environment and dependency directories.
    """
    allowed_extensions = {".py", ".js", ".ts"}
    excluded_dirs = {".venv", "venv", "node_modules", ".git", "__pycache__", "dist", "build"}
    
    source_files = []
    
    for root, dirs, files in os.walk(repo_path):
        # Modify dirs in-place to skip excluded directories
        dirs[:] = [d for d in dirs if d not in excluded_dirs and not d.startswith('.')]
        
        for file in files:
            file_path = Path(root) / file
            if file_path.suffix in allowed_extensions:
                source_files.append(file_path)
                
    return source_files
