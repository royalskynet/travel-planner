#!/usr/bin/env python3
"""Register this repository's skills directory with Hermes."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    source = repo_root / "skills" / "travel-planner-assistant"
    skills_root = source.parent.resolve()

    if not (source / "SKILL.md").is_file():
        print(f"Skill 不存在：{source}", file=sys.stderr)
        return 2
    interpreters = [
        shutil.which(name)
        for name in ("python3.14", "python3.13", "python3.12", "python3.11", "python3.10")
    ]
    interpreter = next((value for value in interpreters if value), None)
    if not interpreter:
        print("V2 需要 Python 3.10+。", file=sys.stderr)
        return 4
    uv = shutil.which("uv")
    if uv:
        installed = subprocess.run([uv, "sync", "--python", interpreter], cwd=repo_root, check=False)
    else:
        venv = repo_root / ".venv"
        installed = subprocess.run([interpreter, "-m", "venv", str(venv)], check=False)
        if installed.returncode == 0:
            installed = subprocess.run(
                [str(venv / "bin" / "python"), "-m", "pip", "install", "-e", str(repo_root)],
                check=False,
            )
    if installed.returncode:
        print("V2 runtime 安裝失敗。", file=sys.stderr)
        return installed.returncode
    hermes = os.environ.get("HERMES_BIN") or shutil.which("hermes")
    if not hermes:
        print("找不到 hermes CLI。", file=sys.stderr)
        return 3

    current = subprocess.run(
        [hermes, "config", "get", "skills.external_dirs", "--json"],
        check=False,
        capture_output=True,
        text=True,
    )
    dirs: list[str] = []
    for line in reversed(current.stdout.splitlines()):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, list):
            dirs = [str(item) for item in value]
            break
    wanted = str(skills_root)
    if wanted not in dirs:
        dirs.append(wanted)
        saved = subprocess.run(
            [hermes, "config", "set", "skills.external_dirs", json.dumps(dirs)],
            check=False,
        )
        if saved.returncode:
            return saved.returncode
    print(f"Hermes 已註冊：{wanted}；V2 runtime：{repo_root / '.venv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
