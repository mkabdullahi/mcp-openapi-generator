"""Project configuration inference for target suggestion."""

from __future__ import annotations

import json
import logging
import re
import subprocess
from pathlib import Path
from typing import Any

import yaml

from ..types import ProjectConfig

logger = logging.getLogger(__name__)

__all__ = ["infer_project_config", "suggest_target"]


def _read_json_safe(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _read_yaml_safe(path: Path) -> dict[str, Any] | None:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _detect_package_manager(project_root: Path) -> str | None:
    """Detect the primary package manager from lock files."""
    if (project_root / "pnpm-lock.yaml").exists():
        return "pnpm"
    if (project_root / "yarn.lock").exists():
        return "yarn"
    if (project_root / "package-lock.json").exists():
        return "npm"
    if (project_root / "poetry.lock").exists():
        return "poetry"
    if (project_root / "uv.lock").exists():
        return "uv"
    if (project_root / "Pipfile.lock").exists():
        return "pipenv"
    if (project_root / "requirements.txt").exists():
        return "pip"
    if (project_root / "Cargo.lock").exists():
        return "cargo"
    if (project_root / "go.sum").exists():
        return "go"
    return None


def _detect_typescript_framework(package_json: dict[str, Any]) -> str | None:
    """Detect TypeScript framework from package.json dependencies."""
    deps = {**package_json.get("dependencies", {}), **package_json.get("devDependencies", {})}

    if "next" in deps:
        return "nextjs"
    if "react" in deps and "react-dom" in deps:
        return "react"
    if "vue" in deps:
        return "vue"
    if "@angular/core" in deps:
        return "angular"
    if "svelte" in deps:
        return "svelte"
    if "express" in deps or "fastify" in deps or "koa" in deps:
        return "node-api"
    if "axios" in deps:
        return "axios"
    return "typescript"


def _detect_python_framework(pyproject: dict[str, Any]) -> str | None:
    """Detect Python framework from pyproject.toml."""
    deps = []
    # poetry
    if "tool" in pyproject and "poetry" in pyproject["tool"]:
        deps.extend(pyproject["tool"]["poetry"].get("dependencies", {}).keys())
        deps.extend(pyproject["tool"]["poetry"].get("group", {}).get("dev", {}).get("dependencies", {}).keys())
    # standard
    if "project" in pyproject:
        deps.extend(pyproject["project"].get("dependencies", []))
        for opt in pyproject["project"].get("optional-dependencies", {}).values():
            deps.extend(opt)

    deps_lower = {d.lower().replace("-", "_") for d in deps}

    if "fastapi" in deps_lower:
        return "fastapi"
    if "django" in deps_lower:
        return "django"
    if "flask" in deps_lower:
        return "flask"
    if "starlette" in deps_lower:
        return "starlette"
    if "aiohttp" in deps_lower:
        return "aiohttp"
    if "httpx" in deps_lower:
        return "httpx"
    return "python"


def infer_project_config(project_root: Path | None = None) -> ProjectConfig:
    """
    Infer project configuration from the current working directory.

    Looks for:
    - package.json (Node/TypeScript)
    - pyproject.toml / requirements.txt / Pipfile / poetry.lock (Python)
    - Cargo.toml / Cargo.lock (Rust)
    - go.mod / go.sum (Go)
    - pom.xml / build.gradle / build.gradle.kts (Java/Kotlin)
    - .csproj / .sln (C#)
    """
    if project_root is None:
        project_root = Path.cwd()

    # Collect all detection results first
    has_package_json = False
    has_pyproject_toml = False
    has_cargo_toml = False
    has_go_mod = False
    has_pom_xml = False
    has_build_gradle = False
    language = "typescript"
    framework = None
    package_manager = None

    # Node.js / TypeScript
    package_json_path = project_root / "package.json"
    if package_json_path.exists():
        has_package_json = True
        pkg = _read_json_safe(package_json_path) or {}
        package_manager = _detect_package_manager(project_root)
        framework = _detect_typescript_framework(pkg)
        # Check for TypeScript
        if "typescript" in pkg.get("devDependencies", {}) or "typescript" in pkg.get("dependencies", {}):
            language = "typescript"
        else:
            language = "javascript"

    # Python
    pyproject_path = project_root / "pyproject.toml"
    if pyproject_path.exists():
        has_pyproject_toml = True
        pyproject = _read_yaml_safe(pyproject_path) or {}
        framework = _detect_python_framework(pyproject)
        language = "python"

    if (project_root / "requirements.txt").exists():
        has_pyproject_toml = True  # treat similarly
        language = "python"

    # Rust
    if (project_root / "Cargo.toml").exists():
        has_cargo_toml = True

    # Go
    if (project_root / "go.mod").exists():
        has_go_mod = True

    # Java
    if (project_root / "pom.xml").exists():
        has_pom_xml = True
    if (project_root / "build.gradle").exists() or (project_root / "build.gradle.kts").exists():
        has_build_gradle = True

    # C#
    if list(project_root.glob("*.csproj")):
        language = "csharp"

    config = ProjectConfig(
        language=language,
        framework=framework,
        package_manager=package_manager,
        has_package_json=has_package_json,
        has_pyproject_toml=has_pyproject_toml,
        has_cargo_toml=has_cargo_toml,
        has_go_mod=has_go_mod,
        has_pom_xml=has_pom_xml,
        has_build_gradle=has_build_gradle,
    )

    logger.debug("Inferred project config: %s", config)
    return config


def suggest_target(config: ProjectConfig) -> str:
    """
    Suggest a generator target based on project configuration.

    Returns the target identifier for openapi-generator.
    """
    return config.primary_language


async def get_git_root(path: Path | None = None) -> Path | None:
    """Find the git repository root."""
    if path is None:
        path = Path.cwd()
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=path,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return Path(result.stdout.strip())
    except Exception:
        pass
    return None