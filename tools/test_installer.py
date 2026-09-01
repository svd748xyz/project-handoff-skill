#!/usr/bin/env python3
"""Exercise the multi-agent installer without touching real user directories."""

from __future__ import annotations

import tempfile
from pathlib import Path

import install


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="project-handoff-installer-test-") as temporary:
        root = Path(temporary)

        expected_claude = root / "home" / ".claude" / "skills" / "project-handoff"
        actual_claude = install.default_destination(
            "claude",
            "user",
            project_root=root / "project",
            home=root / "home",
        )
        assert actual_claude == expected_claude

        legacy_home = root / "legacy-home"
        legacy_codex_skills = legacy_home / ".codex" / "skills"
        legacy_codex_skills.mkdir(parents=True)
        if not install.os.environ.get("CODEX_HOME"):
            assert install.default_destination(
                "codex",
                "user",
                project_root=root / "project",
                home=legacy_home,
            ) == legacy_codex_skills / "project-handoff"

        codex_destination = root / "codex" / "project-handoff"
        install.install_skill(
            agent="codex",
            destination=codex_destination,
            claude_explicit_only=False,
        )
        assert (codex_destination / "agents" / "openai.yaml").is_file()
        codex_skill = (codex_destination / "SKILL.md").read_text(encoding="utf-8")
        assert "disable-model-invocation:" not in codex_skill

        claude_destination = root / "claude" / "project-handoff"
        install.install_skill(
            agent="claude",
            destination=claude_destination,
            claude_explicit_only=True,
        )
        claude_skill = (claude_destination / "SKILL.md").read_text(encoding="utf-8")
        assert "disable-model-invocation: true" in claude_skill
        assert not (claude_destination / "agents").exists()

        copilot_destination = root / "copilot" / "project-handoff"
        install.install_skill(
            agent="copilot",
            destination=copilot_destination,
            claude_explicit_only=False,
        )
        assert (copilot_destination / "scripts" / "validate_handoff.py").is_file()
        assert not (copilot_destination / "agents").exists()

        try:
            install.install_skill(
                agent="codex",
                destination=codex_destination,
                claude_explicit_only=False,
            )
        except FileExistsError:
            pass
        else:
            raise AssertionError("installer must not overwrite an existing destination")

    print("PASS: multi-agent installer")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
