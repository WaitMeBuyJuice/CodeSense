"""Project metadata extraction: README, config files, top-level docstrings.

Provides the raw material for 01_identity segment generation.
All functions are read-only and safe to call with arbitrary project roots.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from codesense_v1.data.db import CodeGraphDB
from codesense_v1.data.docstrings import extract_file_docstring

_README_CANDIDATES: tuple[str, ...] = (
    "README.md", "README.rst", "README.txt", "README",
    "readme.md", "readme.rst", "readme.txt",
    "Readme.md", "Readme.rst",
)

_CONFIG_CANDIDATES: tuple[tuple[str, str], ...] = (
    ("pyproject", "pyproject.toml"),
    ("package_json", "package.json"),
    ("cargo_toml", "Cargo.toml"),
    ("go_mod", "go.mod"),
    ("composer_json", "composer.json"),
    ("gemfile", "Gemfile"),
)


@dataclass(frozen=True)
class IdentitySource:
    """A single source of project identity information.

    Attributes:
        kind: Source type identifier.
        path: Relative POSIX path from project root.
        content: Raw text content of the file.
    """

    kind: str    # "readme" | "pyproject" | "package_json" | "cargo_toml" | "go_mod" | "docstring"
    path: str    # relative POSIX path
    content: str # raw text


def read_readme(project_root: Path) -> IdentitySource | None:
    """Find and read the first available README file.

    Searches through _README_CANDIDATES in order. Returns None if none found.
    """
    for name in _README_CANDIDATES:
        p = project_root / name
        if p.is_file():
            try:
                return IdentitySource(
                    kind="readme",
                    path=name,
                    content=p.read_text(encoding="utf-8", errors="replace"),
                )
            except OSError:
                continue
    return None


def read_config_file(project_root: Path, kind: str, filename: str) -> IdentitySource | None:
    """Read a single config file. Returns None if not found."""
    p = project_root / filename
    if not p.is_file():
        return None
    try:
        return IdentitySource(
            kind=kind,
            path=filename,
            content=p.read_text(encoding="utf-8", errors="replace"),
        )
    except OSError:
        return None


def read_package_docstrings(project_root: Path, db: CodeGraphDB) -> list[IdentitySource]:
    """Read top-level package __init__.py / main module docstrings.

    Uses CodeGraph's file index to find candidate entry files.
    Returns a list (may be empty).
    """
    sources: list[IdentitySource] = []
    entry_names = {"__init__.py", "main.py", "__main__.py", "index.ts", "index.js", "main.go"}

    for f in db.iter_files():
        fname = Path(f.path).name
        if fname not in entry_names:
            continue
        # Only pick top-level or one-level-deep files
        depth = f.path.replace("\\", "/").count("/")
        if depth > 2:
            continue
        abs_path = project_root / f.path
        if not abs_path.is_file():
            continue
        docstring = extract_file_docstring(abs_path, f.language)
        if docstring:
            sources.append(IdentitySource(
                kind="docstring",
                path=f.path.replace("\\", "/"),
                content=docstring,
            ))
    return sources


def collect_identity_sources(project_root: Path, db: CodeGraphDB) -> list[IdentitySource]:
    """Collect all available project identity sources, in priority order.

    Priority:
    1. README (highest — human-written project description)
    2. Config files (pyproject.toml, package.json, Cargo.toml, go.mod, etc.)
    3. Top-level package docstrings (fallback for projects without docs)

    Returns an empty list if no sources found (caller handles gracefully).
    """
    sources: list[IdentitySource] = []

    readme = read_readme(project_root)
    if readme:
        sources.append(readme)

    for kind, filename in _CONFIG_CANDIDATES:
        src = read_config_file(project_root, kind, filename)
        if src:
            sources.append(src)

    sources.extend(read_package_docstrings(project_root, db))
    return sources


def extract_tech_stack_hint(sources: list[IdentitySource]) -> dict[str, str]:
    """Extract structured tech stack hints from config sources.

    Returns a dict with keys like 'language', 'python_requires', 'dependencies', 'build_tool'.
    Best-effort; missing keys simply absent.
    """
    hints: dict[str, str] = {}

    for src in sources:
        if src.kind == "pyproject":
            _extract_pyproject_hints(src.content, hints)
        elif src.kind == "package_json":
            _extract_package_json_hints(src.content, hints)
        elif src.kind == "cargo_toml":
            hints.setdefault("language", "Rust")
        elif src.kind == "go_mod":
            hints.setdefault("language", "Go")

    return hints


def _extract_pyproject_hints(content: str, hints: dict[str, str]) -> None:
    hints.setdefault("language", "Python")

    in_dep_groups = False
    in_dev_list = False
    dev_tools: set[str] = set()

    for raw_line in content.splitlines():
        line = raw_line.strip()

        # Section header
        if line.startswith("["):
            in_dep_groups = "dependency-groups" in line or "optional-dependencies" in line
            in_dev_list = False
            continue

        # Key-value
        if line.startswith("requires-python"):
            val = line.split("=", 1)[-1].strip().strip('"').strip("'")
            hints["python_requires"] = val
        if line.startswith("build-backend"):
            backend = line.split("=", 1)[-1].strip().strip('"')
            hints["build_tool"] = backend.split(".")[0]

        # Start of dev list: "dev = ["
        if in_dep_groups and line.startswith("dev") and "=" in line:
            in_dev_list = True

        # End of dev list: "]" at column 0 or 4
        if in_dev_list and line == "]":
            in_dev_list = False
            continue

        # Collect dev dep names
        if in_dev_list:
            pkg = _extract_dep_name(line)
            if pkg:
                dev_tools.add(pkg.lower())

    if "mypy" in dev_tools:
        hints["type_checker"] = "mypy"
    if "ruff" in dev_tools:
        hints["linter"] = "ruff"
    if "pytest" in dev_tools:
        hints["test_framework"] = "pytest" + (" + pytest-asyncio" if "pytest-asyncio" in dev_tools else "")


def _extract_dep_name(line: str) -> str | None:
    """Extract bare package name from a TOML dependency line like '\"mypy>=0.9\",' or 'mypy = ...'."""
    if line.startswith('"') or line.startswith("'"):
        # Strip trailing comma first, then strip quotes from both ends
        raw = line.rstrip(",").strip('"\'').split(">")[0].split("<")[0].split("=")[0].split("[")[0].strip()
        if raw and raw.replace("-", "").replace("_", "").replace(".", "").isalnum():
            return raw
    if "=" in line and not line.startswith("["):
        name = line.split("=")[0].strip()
        if name and name.replace("-", "").replace("_", "").isalnum():
            return name
    return None


def _extract_package_json_hints(content: str, hints: dict[str, str]) -> None:
    hints.setdefault("language", "JavaScript / TypeScript")
    try:
        data = json.loads(content)
        deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
        frameworks = []
        if "react" in deps:
            frameworks.append("React")
        if "vue" in deps:
            frameworks.append("Vue")
        if "typescript" in deps:
            hints["language"] = "TypeScript"
        if frameworks:
            hints["frameworks"] = ", ".join(frameworks)
    except (json.JSONDecodeError, AttributeError):
        pass
