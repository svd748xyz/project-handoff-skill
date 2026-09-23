#!/usr/bin/env python3
"""Safely install project-handoff for a supported Agent Skills directory."""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "skills" / "project-handoff"
AGENTS = ("codex", "claude", "copilot", "agents")
INVOCATIONS = {
    "codex": "$project-handoff",
    "claude": "/project-handoff",
    "copilot": "Ask the coding agent to use project-handoff explicitly.",
    "agents": "Invoke project-handoff using the target agent's skill syntax.",
}


def default_destination(
    agent: str,
    scope: str,
    *,
    project_root: Path,
    home: Path,
) -> Path:
    if scope == "project":
        containers = {
            "codex": project_root / ".agents" / "skills",
            "claude": project_root / ".claude" / "skills",
            "copilot": project_root / ".github" / "skills",
            "agents": project_root / ".agents" / "skills",
        }
    else:
        codex_home = os.environ.get("CODEX_HOME")
        existing_codex_skills = home / ".codex" / "skills"
        if codex_home:
            codex_container = Path(codex_home).expanduser() / "skills"
        elif existing_codex_skills.is_dir():
            codex_container = existing_codex_skills
        else:
            codex_container = home / ".agents" / "skills"
        containers = {
            "codex": codex_container,
            "claude": home / ".claude" / "skills",
            "copilot": home / ".copilot" / "skills",
            "agents": home / ".agents" / "skills",
        }
    return containers[agent] / "project-handoff"


def add_claude_explicit_only(skill_file: Path) -> None:
    text = skill_file.read_text(encoding="utf-8")
    if "disable-model-invocation:" in text:
        return
    lines = text.splitlines()
    try:
        closing = lines.index("---", 1)
    except ValueError as exc:
        raise ValueError("SKILL.md frontmatter is malformed") from exc
    lines.insert(closing, "disable-model-invocation: true")
    skill_file.write_text("\n".join(lines) + "\n", encoding="utf-8")


def install_skill(
    *,
    agent: str,
    destination: Path,
    claude_explicit_only: bool,
) -> Path:
    if agent not in AGENTS:
        raise ValueError(f"unsupported agent: {agent}")
    if claude_explicit_only and agent != "claude":
        raise ValueError("--explicit-only is supported only for Claude Code")
    if not (SOURCE / "SKILL.md").is_file():
        raise FileNotFoundError(f"source skill is incomplete: {SOURCE}")

    destination = destination.expanduser().resolve()
    if destination.exists():
        raise FileExistsError(
            f"destination already exists; no files were changed: {destination}"
        )

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.parent / f".project-handoff-install-{uuid.uuid4().hex}"
    try:
        shutil.copytree(
            SOURCE,
            temporary,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
        )
        if agent != "codex":
            openai_metadata = temporary / "agents"
            if openai_metadata.exists():
                shutil.rmtree(openai_metadata)
        if claude_explicit_only:
            add_claude_explicit_only(temporary / "SKILL.md")
        temporary.replace(destination)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise
    return destination


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Install project-handoff without overwriting an existing skill."
    )
    parser.add_argument("--agent", choices=AGENTS, required=True)
    parser.add_argument("--scope", choices=("user", "project"), default="user")
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path.cwd(),
        help="Project root used for project-scoped installation; defaults to cwd.",
    )
    parser.add_argument(
        "--dest",
        type=Path,
        help="Exact destination skill directory; overrides --scope and --project-root.",
    )
    parser.add_argument(
        "--explicit-only",
        action="store_true",
        help="Add Claude Code's user-only invocation field to the installed copy.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Perform the installation. Without this flag, print a dry-run plan.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.explicit_only and args.agent != "claude":
        print("ERROR: --explicit-only is supported only for Claude Code", file=sys.stderr)
        return 2

    destination = args.dest or default_destination(
        args.agent,
        args.scope,
        project_root=args.project_root.resolve(),
        home=Path.home(),
    )
    destination = destination.expanduser().resolve()

    if not args.apply:
        print("DRY RUN: no files changed")
        print(f"agent: {args.agent}")
        print(f"source: {SOURCE}")
        print(f"destination: {destination}")
        print(f"claude-explicit-only: {str(args.explicit_only).lower()}")
        print("Run again with --apply to install.")
        return 0

    try:
        installed = install_skill(
            agent=args.agent,
            destination=destination,
            claude_explicit_only=args.explicit_only,
        )
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"INSTALLED: {installed}")
    print(f"INVOKE: {INVOCATIONS[args.agent]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
