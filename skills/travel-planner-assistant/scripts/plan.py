#!/usr/bin/env python3
"""Portable entry point for the bundled travel planner."""

import os
import sys
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parents[3]
    venv_python = repo_root / ".venv" / "bin" / "python"
    if venv_python.is_file() and Path(sys.executable).resolve() != venv_python.resolve():
        os.execv(str(venv_python), [str(venv_python), str(Path(__file__).resolve()), *sys.argv[1:]])
    source = repo_root / "src"
    if not (source / "travel_assistant" / "cli.py").is_file():
        raise SystemExit(
            "找不到 travel_assistant 核心。請保留 Skill 在原 repo，或重新執行 scripts/install_hermes_skill.py。"
        )
    sys.path.insert(0, str(source))
    from travel_assistant.cli import main as cli_main

    return cli_main()


if __name__ == "__main__":
    raise SystemExit(main())
