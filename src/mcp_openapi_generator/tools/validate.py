"""Specification validation tool using Spectral and Vacuum."""

from __future__ import annotations

import asyncio
import logging
import shutil
import tempfile
from pathlib import Path

from ..types import SpecInput, ValidationOptions, ValidationResult, ValidationTool
from ..utils.spec_resolver import resolve_spec

logger = logging.getLogger(__name__)

__all__ = ["validate_spec", "ValidationWrapper"]

# Validator executable names
SPECTRAL_CLI = "spectral"
VACUUM_CLI = "vacuum"


class ValidationWrapper:
    """Wrapper for OpenAPI validation tools."""

    def __init__(self) -> None:
        self._spectral_path = shutil.which(SPECTRAL_CLI)
        self._vacuum_path = shutil.which(VACUUM_CLI)

    @property
    def available_tools(self) -> list[ValidationTool]:
        tools = []
        if self._spectral_path:
            tools.append(ValidationTool.SPECTRAL)
        if self._vacuum_path:
            tools.append(ValidationTool.VACUUM)
        return tools

    @property
    def preferred_tool(self) -> ValidationTool:
        if ValidationTool.SPECTRAL in self.available_tools:
            return ValidationTool.SPECTRAL
        if ValidationTool.VACUUM in self.available_tools:
            return ValidationTool.VACUUM
        return ValidationTool.SPECTRAL  # default

    def get_executable(self, tool: ValidationTool) -> str | None:
        if tool == ValidationTool.SPECTRAL:
            return self._spectral_path
        if tool == ValidationTool.VACUUM:
            return self._vacuum_path
        return None

    async def validate(
        self,
        options: ValidationOptions,
    ) -> ValidationResult:
        """Validate an OpenAPI specification."""
        tool = options.tool or self.preferred_tool
        executable = self.get_executable(tool)

        if not executable:
            return ValidationResult(
                success=False,
                valid=False,
                tool=tool,
                spec_source=options.spec.location,
                error=f"Validator {tool.value} not found. Install spectral or vacuum.",
            )

        # Resolve spec
        try:
            spec = await resolve_spec(options.spec)
        except Exception as e:
            return ValidationResult(
                success=False,
                valid=False,
                tool=tool,
                spec_source=options.spec.location,
                error=f"Failed to resolve spec: {e}",
            )

        # Write spec to temp file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            import yaml

            yaml.dump(spec, f)
            spec_file = Path(f.name)

        try:
            return await self._run_validation(executable, tool, spec_file, options)
        finally:
            spec_file.unlink(missing_ok=True)

    async def _run_validation(
        self,
        executable: str,
        tool: ValidationTool,
        spec_file: Path,
        options: ValidationOptions,
    ) -> ValidationResult:
        """Run the validation CLI."""
        if tool == ValidationTool.SPECTRAL:
            cmd = [executable, "lint", str(spec_file), "--format", "json"]
            if options.ruleset:
                cmd.extend(["--ruleset", options.ruleset])
        elif tool == ValidationTool.VACUUM:
            cmd = [executable, "lint", str(spec_file), "-format", "json"]
            if options.ruleset:
                cmd.extend(["-ruleset", options.ruleset])
        else:
            return ValidationResult(
                success=False,
                valid=False,
                tool=tool,
                spec_source=options.spec.location,
                error=f"Unknown validation tool: {tool}",
            )

        logger.info("Running validation: %s", " ".join(cmd))

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()

            # Parse results
            if tool == ValidationTool.SPECTRAL:
                return self._parse_spectral_output(
                    stdout.decode() if stdout else "[]",
                    options.spec.location,
                    options.fail_on_warnings,
                )
            if tool == ValidationTool.VACUUM:
                return self._parse_vacuum_output(
                    stdout.decode() if stdout else "[]",
                    options.spec.location,
                    options.fail_on_warnings,
                )

        except Exception as e:
            logger.exception("Validation error")
            return ValidationResult(
                success=False,
                valid=False,
                tool=tool,
                spec_source=options.spec.location,
                error=str(e),
            )

    def _parse_spectral_output(
        self,
        stdout: str,
        spec_source: str,
        fail_on_warnings: bool = False,
    ) -> ValidationResult:
        """Parse Spectral JSON output."""
        import json

        try:
            results = json.loads(stdout) if stdout.strip() else []
        except json.JSONDecodeError:
            return ValidationResult(
                success=False,
                valid=False,
                tool=ValidationTool.SPECTRAL,
                spec_source=spec_source,
                error=f"Failed to parse Spectral output: {stdout[:200]}",
            )

        errors = []
        warnings = []

        for result in results:
            severity_value = result.get("severity", "error")
            if isinstance(severity_value, int):
                severity = {0: "error", 1: "warning", 2: "info", 3: "hint"}.get(
                    severity_value, "error"
                )
            else:
                severity = str(severity_value).lower()
            message = {
                "code": result.get("code", ""),
                "message": result.get("message", ""),
                "path": result.get("path", ""),
                "range": result.get("range", {}),
                "severity": severity,
            }
            if severity == "error":
                errors.append(message)
            else:
                warnings.append(message)

        valid = len(errors) == 0
        if fail_on_warnings:
            valid = valid and len(warnings) == 0

        return ValidationResult(
            success=True,
            valid=valid,
            tool=ValidationTool.SPECTRAL,
            spec_source=spec_source,
            errors=errors,
            warnings=warnings,
        )

    def _parse_vacuum_output(
        self,
        stdout: str,
        spec_source: str,
        fail_on_warnings: bool = False,
    ) -> ValidationResult:
        """Parse Vacuum JSON output."""
        import json

        try:
            results = json.loads(stdout) if stdout.strip() else []
        except json.JSONDecodeError:
            return ValidationResult(
                success=False,
                valid=False,
                tool=ValidationTool.VACUUM,
                spec_source=spec_source,
                error=f"Failed to parse Vacuum output: {stdout[:200]}",
            )

        errors = []
        warnings = []

        for result in results:
            # Vacuum output format differs slightly
            severity = result.get("severity", "error").lower()
            message = {
                "code": result.get("code", ""),
                "message": result.get("message", ""),
                "path": result.get("path", ""),
                "line": result.get("line", 0),
                "severity": severity,
            }
            if severity == "error":
                errors.append(message)
            else:
                warnings.append(message)

        valid = len(errors) == 0
        if fail_on_warnings:
            valid = valid and len(warnings) == 0

        return ValidationResult(
            success=True,
            valid=valid,
            tool=ValidationTool.VACUUM,
            spec_source=spec_source,
            errors=errors,
            warnings=warnings,
        )


async def validate_spec(
    spec: SpecInput,
    tool: ValidationTool = ValidationTool.SPECTRAL,
    ruleset: str | None = None,
    fail_on_warnings: bool = False,
) -> ValidationResult:
    """High-level function to validate an OpenAPI specification."""
    options = ValidationOptions(
        spec=spec,
        tool=tool,
        ruleset=ruleset,
        fail_on_warnings=fail_on_warnings,
    )

    wrapper = ValidationWrapper()
    return await wrapper.validate(options)
