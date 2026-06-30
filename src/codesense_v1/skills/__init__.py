"""CodeSense skills — SKILL.md files bundled with the package, exposed as MCP Prompts."""

from __future__ import annotations

import importlib.resources
import re
from dataclasses import dataclass

# Directory names under src/codesense_v1/skills/ — order determines list_prompts() order.
_SKILL_DIR_NAMES: tuple[str, ...] = ("codesense-flow", "codesense-init")


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    body: str


def _parse_skill(text: str) -> tuple[str, str, str]:
    """Parse a SKILL.md file; return (name, description, body).

    Handles YAML folded scalar (``>``) for multi-line description values.
    Frontmatter block is delimited by ``---`` markers.
    """
    if not text.startswith("---"):
        return "", "", text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return "", "", text

    fm_lines = parts[1].splitlines()
    body = parts[2].strip()

    name = ""
    desc_lines: list[str] = []
    in_desc = False

    for line in fm_lines:
        # Detect a top-level YAML key (no leading whitespace, word chars then colon).
        key_match = re.match(r"^(\w[\w-]*):", line)
        if key_match:
            key = key_match.group(1)
            value = line.split(":", 1)[1].strip()
            if key == "name":
                name = value
                in_desc = False
            elif key == "description":
                if value in (">", "|", ""):
                    in_desc = True
                    desc_lines = []
                else:
                    desc_lines = [value]
                    in_desc = False
            else:
                in_desc = False
        elif in_desc:
            stripped = line.strip()
            if stripped:
                desc_lines.append(stripped)

    description = " ".join(desc_lines).strip()
    return name, description, body


def _load_skill(dir_name: str) -> Skill:
    pkg = importlib.resources.files("codesense_v1.skills")
    text = (pkg / dir_name / "SKILL.md").read_text(encoding="utf-8")
    name, description, body = _parse_skill(text)
    return Skill(name=name or dir_name, description=description, body=body)


# Eagerly loaded at import time — fails fast on startup if any bundled file is missing.
_SKILLS: dict[str, Skill] = {
    s.name: s for s in (_load_skill(d) for d in _SKILL_DIR_NAMES)
}


def list_skills() -> list[Skill]:
    """Return all bundled skills in registration order."""
    return list(_SKILLS.values())


def get_skill(name: str) -> Skill | None:
    """Return skill by name, or ``None`` if not found."""
    return _SKILLS.get(name)
