"""Type definitions for the MCP OpenAPI Generator server."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Literal

__all__ = [
    "GeneratorTarget",
    "ValidationTool",
    "SpecSource",
    "GenerationResult",
    "ValidationResult",
    "ProjectConfig",
    "MCPToolError",
]


class GeneratorTarget(str, Enum):
    """Supported code generation targets for openapi-generator."""

    TYPESCRIPT_AXIOS = "typescript-axios"
    TYPESCRIPT_FETCH = "typescript-fetch"
    TYPESCRIPT_NODE = "typescript-node"
    PYTHON = "python"
    PYTHON_AIOHTTP = "python-aiohttp"
    JAVA_SPRING = "spring"
    JAVA_SPRING_BOOT = "spring-boot"
    KOTLIN_SPRING = "kotlin-spring"
    GO = "go"
    GO_GIN = "go-gin"
    CSHARP_NETCORE = "csharp-netcore"
    RUST = "rust"
    SWIFT = "swift5"

    @classmethod
    def from_project_config(cls, config: ProjectConfig) -> GeneratorTarget:
        """Infer target from project configuration."""
        if config.language == "typescript":
            return cls.TYPESCRIPT_AXIOS
        if config.language == "python":
            return cls.PYTHON
        if config.language == "java":
            return cls.JAVA_SPRING_BOOT
        if config.language == "kotlin":
            return cls.KOTLIN_SPRING
        if config.language == "go":
            return cls.GO_GIN
        if config.language == "csharp":
            return cls.CSHARP_NETCORE
        if config.language == "rust":
            return cls.RUST
        if config.language == "swift":
            return cls.SWIFT
        return cls.TYPESCRIPT_AXIOS  # default


class ValidationTool(str, Enum):
    """Supported validation tools."""

    SPECTRAL = "spectral"
    VACUUM = "vacuum"


class SpecSource(str, Enum):
    """Source type for OpenAPI specification."""

    URL = "url"
    FILE = "file"
    STDIN = "stdin"


@dataclass(frozen=True, slots=True)
class SpecInput:
    """Input specification for generation or validation."""

    source: SpecSource
    location: str  # URL, file path, or "-" for stdin
    format: Literal["json", "yaml", "yml"] = "yaml"

    @property
    def is_remote(self) -> bool:
        return self.source == SpecSource.URL


@dataclass(frozen=True, slots=True)
class GenerationOptions:
    """Options for code generation."""

    target: GeneratorTarget
    spec: SpecInput
    output_dir: Path
    package_name: str | None = None
    package_version: str | None = None
    additional_properties: dict[str, str] = field(default_factory=dict)
    generate_tests: bool = True
    generate_docs: bool = False
    post_process: bool = True


@dataclass(frozen=True, slots=True)
class ValidationOptions:
    """Options for specification validation."""

    spec: SpecInput
    tool: ValidationTool = ValidationTool.SPECTRAL
    ruleset: str | None = None  # custom ruleset path/url
    fail_on_warnings: bool = False


@dataclass(frozen=True, slots=True)
class ProjectConfig:
    """Inferred project configuration for target suggestion."""

    language: str = "typescript"
    framework: str | None = None
    package_manager: str | None = None
    has_package_json: bool = False
    has_pyproject_toml: bool = False
    has_cargo_toml: bool = False
    has_go_mod: bool = False
    has_pom_xml: bool = False
    has_build_gradle: bool = False

    @property
    def primary_language(self) -> str:
        if self.has_package_json:
            return "typescript"
        if self.has_pyproject_toml:
            return "python"
        if self.has_cargo_toml:
            return "rust"
        if self.has_go_mod:
            return "go"
        if self.has_pom_xml or self.has_build_gradle:
            return "java"
        return "typescript"


@dataclass(frozen=True, slots=True)
class GenerationResult:
    """Result of a code generation operation."""

    success: bool
    output_dir: Path
    files_created: list[Path]
    target: GeneratorTarget
    spec_source: str
    warnings: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def summary(self) -> str:
        if self.success:
            return f"Generated {len(self.files_created)} files to {self.output_dir}"
        return f"Generation failed: {self.error}"


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """Result of a specification validation operation."""

    success: bool
    valid: bool
    tool: ValidationTool
    spec_source: str
    errors: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None

    @property
    def summary(self) -> str:
        if not self.success:
            return f"Validation failed: {self.error}"
        if self.valid:
            return "Specification is valid"
        return f"Specification invalid: {len(self.errors)} errors, {len(self.warnings)} warnings"


class MCPToolError(Exception):
    """Base exception for MCP tool errors."""

    def __init__(self, message: str, tool: str, details: dict | None = None):
        super().__init__(message)
        self.tool = tool
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": str(self),
            "tool": self.tool,
            "details": self.details,
        }