"""WARDEN Command Line Interface (CLI) package."""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from core.cli.dispatcher import dispatch_cli
from core.cli.parser import build_argument_parser


def ensure_venv_path() -> None:
    """Ensures virtualenv bin directory containing bundled analyzers is in PATH."""
    bin_dir = str(Path(sys.executable).parent)
    if bin_dir not in os.environ.get("PATH", "").split(os.pathsep):
        os.environ["PATH"] = f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"


def cli() -> None:
    """Main CLI entry point for WARDEN."""
    ensure_venv_path()
    load_dotenv()

    parser = build_argument_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    dispatch_cli(args)


__all__ = ["build_argument_parser", "cli", "dispatch_cli", "ensure_venv_path"]
