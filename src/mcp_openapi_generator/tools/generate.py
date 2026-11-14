"""Code generation tool using openapi-generator and swagger-codegen."""

from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import TypedDict

from ..types import GenerationOptions, GenerationResult, GeneratorTarget, SpecInput
from ..utils.config_inference import infer_project_config
from ..utils.post_process import post_process_generation
from ..utils.spec_resolver import resolve_spec

logger = logging.getLogger(__name__)

__all__ = ["generate_client", "list_generators", "GeneratorWrapper"]


class GeneratorListResult(TypedDict):
    generator: str
    available: bool
    targets: list[str]


# Generator executable names
OPENAPI_GENERATOR_CLI = "openapi-generator-cli"
SWAGGER_CODEGEN_CLI = "swagger-codegen"


class GeneratorWrapper:
    """Wrapper for OpenAPI code generators."""

    def __init__(self, prefer: str = "openapi-generator"):
        self.prefer = prefer
        self._openapi_generator_path = shutil.which(OPENAPI_GENERATOR_CLI)
        self._swagger_codegen_path = shutil.which(SWAGGER_CODEGEN_CLI)

    @property
    def available(self) -> bool:
        return bool(self._openapi_generator_path or self._swagger_codegen_path)

    @property
    def generator_name(self) -> str:
        if self._openapi_generator_path and self.prefer == "openapi-generator":
            return "openapi-generator"
        if self._swagger_codegen_path:
            return "swagger-codegen"
        if self._openapi_generator_path:
            return "openapi-generator"
        return "none"

    @property
    def executable(self) -> str | None:
        if self.generator_name == "openapi-generator":
            return self._openapi_generator_path
        if self.generator_name == "swagger-codegen":
            return self._swagger_codegen_path
        return None

    def get_supported_targets(self) -> list[str]:
        """Get list of supported generation targets."""
        if not self.executable:
            return []

        try:
            command = [self.executable, "list"]
            if self.generator_name == "openapi-generator":
                command.append("-s")
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                if self.generator_name == "openapi-generator":
                    return sorted({
                        target.strip()
                        for target in result.stdout.replace("\n", ",").split(",")
                        if target.strip()
                    })

                return [
                    line.split()[0]
                    for line in result.stdout.splitlines()
                    if line.strip() and not line.strip().startswith("Available")
                ]
        except Exception as e:
            logger.warning("Failed to list generators: %s", e)
        return []

    async def generate(
        self,
        options: GenerationOptions,
        project_root: Path | None = None,
    ) -> GenerationResult:
        """Generate client code using the configured generator."""
        if not self.executable:
            return GenerationResult(
                success=False,
                output_dir=options.output_dir,
                files_created=[],
                target=options.target,
                spec_source=options.spec.location,
                error=(
                    "No OpenAPI generator found. Install openapi-generator-cli or swagger-codegen."
                ),
            )

        # Resolve spec
        try:
            spec = await resolve_spec(options.spec)
            logger.debug("Resolved spec with %d top-level keys", len(spec))
        except Exception as e:
            return GenerationResult(
                success=False,
                output_dir=options.output_dir,
                files_created=[],
                target=options.target,
                spec_source=options.spec.location,
                error=f"Failed to resolve spec: {e}",
            )

        # Write spec to temp file for generator
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            import yaml

            yaml.dump(spec, f)
            spec_file = Path(f.name)

        try:
            return await self._run_generation(options, spec_file, project_root)
        finally:
            spec_file.unlink(missing_ok=True)

    async def _run_generation(
        self,
        options: GenerationOptions,
        spec_file: Path,
        project_root: Path | None,
    ) -> GenerationResult:
        """Run the generator CLI."""
        executable = self.executable
        if executable is None:
            return GenerationResult(
                success=False,
                output_dir=options.output_dir,
                files_created=[],
                target=options.target,
                spec_source=options.spec.location,
                error="No OpenAPI generator is available.",
            )

        output_dir = options.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)

        cmd = [
            executable,
            "generate",
            "-i",
            str(spec_file),
            "-g",
            options.target.value,
            "-o",
            str(output_dir),
        ]

        # Add optional parameters
        if options.package_name:
            cmd.extend(["--package-name", options.package_name])
        if options.package_version:
            cmd.extend(["--package-version", options.package_version])

        # Add additional properties
        for key, value in options.additional_properties.items():
            cmd.extend(["--additional-properties", f"{key}={value}"])

        # Generator-specific options
        if self.generator_name == "openapi-generator":
            if not options.generate_tests:
                cmd.extend(["--global-property", "apiTests=false,modelTests=false"])
        elif self.generator_name == "swagger-codegen":
            # swagger-codegen uses different flags
            pass

        logger.info("Running generation: %s", " ".join(cmd))

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=project_root,
            )
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                error_msg = stderr.decode() if stderr else "Unknown error"
                logger.error("Generation failed: %s", error_msg)
                return GenerationResult(
                    success=False,
                    output_dir=output_dir,
                    files_created=[],
                    target=options.target,
                    spec_source=options.spec.location,
                    error=error_msg[:500],
                )

            # Collect generated files
            files_created = list(output_dir.rglob("*"))
            files_created = [f for f in files_created if f.is_file()]

            return GenerationResult(
                success=True,
                output_dir=output_dir,
                files_created=files_created,
                target=options.target,
                spec_source=options.spec.location,
            )

        except Exception as e:
            logger.exception("Generation error")
            return GenerationResult(
                success=False,
                output_dir=output_dir,
                files_created=[],
                target=options.target,
                spec_source=options.spec.location,
                error=str(e),
            )


async def generate_client(
    spec: SpecInput,
    target: GeneratorTarget,
    output_dir: Path,
    package_name: str | None = None,
    package_version: str | None = None,
    additional_properties: dict[str, str] | None = None,
    generate_tests: bool = True,
    generate_docs: bool = False,
    post_process: bool = True,
    project_root: Path | None = None,
) -> GenerationResult:
    """
    High-level function to generate a client from an OpenAPI spec.

    This is the main entry point for the MCP tool.
    """
    # Infer project config for defaults
    if project_root is None:
        project_root = Path.cwd()
    config = infer_project_config(project_root)

    # Use inferred target if not specified
    if target is None:
        target = GeneratorTarget.from_project_config(config)

    options = GenerationOptions(
        target=target,
        spec=spec,
        output_dir=output_dir,
        package_name=package_name,
        package_version=package_version,
        additional_properties=additional_properties or {},
        generate_tests=generate_tests,
        generate_docs=generate_docs,
        post_process=post_process,
    )

    wrapper = GeneratorWrapper()
    result = await wrapper.generate(options, project_root)

    if result.success and post_process:
        result = await post_process_generation(result, options, config)

    return result


async def list_generators() -> GeneratorListResult:
    """List available generators and their targets."""
    wrapper = GeneratorWrapper()
    return {
        "generator": wrapper.generator_name,
        "available": wrapper.available,
        "targets": wrapper.get_supported_targets(),
    }
