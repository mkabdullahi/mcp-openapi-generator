"""CLI entry points for the MCP OpenAPI Generator."""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table

from .tools.generate import generate_client, list_generators
from .tools.validate import validate_spec
from .types import GeneratorTarget, SpecInput, SpecSource, ValidationTool
from .utils.config_inference import infer_project_config

__all__ = ["app", "generate_client", "validate_spec"]

app = typer.Typer(
    name="mcp-openapi-generator",
    help="MCP server for OpenAPI code generation and validation",
    add_completion=False,
    rich_markup_mode="rich",
)

console = Console()
logger = logging.getLogger(__name__)


def _setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, rich_tracebacks=True)],
    )


def _parse_spec_input(spec: str, format: str = "yaml") -> SpecInput:
    """Parse spec argument into SpecInput."""
    if spec.startswith(("http://", "https://")):
        return SpecInput(source=SpecSource.URL, location=spec, format=format)
    if spec == "-":
        return SpecInput(source=SpecSource.STDIN, location="-", format=format)
    return SpecInput(source=SpecSource.FILE, location=spec, format=format)


@app.command()
def generate(
    spec: Annotated[str, typer.Argument(help="OpenAPI spec URL, file path, or '-' for stdin")],
    target: Annotated[
        GeneratorTarget,
        typer.Option("--target", "-t", help="Generation target language/framework"),
    ] = GeneratorTarget.TYPESCRIPT_AXIOS,
    output: Annotated[Path, typer.Option("--output", "-o", help="Output directory")] = Path("./generated"),
    package_name: Annotated[str | None, typer.Option("--package-name", help="Package name for generated code")] = None,
    package_version: Annotated[str | None, typer.Option("--package-version", help="Package version")] = None,
    prop: Annotated[list[str], typer.Option("--prop", "-p", help="Additional properties (key=value)")] = [],
    no_tests: Annotated[bool, typer.Option("--no-tests", help="Skip test generation")] = False,
    no_post_process: Annotated[bool, typer.Option("--no-post-process", help="Skip formatting and test stubs")] = False,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Verbose output")] = False,
) -> None:
    """Generate client code from an OpenAPI specification."""
    _setup_logging(verbose)

    spec_input = _parse_spec_input(spec)
    additional_props = {}
    for p in prop:
        if "=" in p:
            k, v = p.split("=", 1)
            additional_props[k] = v

    console.print(f"[bold]Generating client for {spec_input.location}[/bold]")
    console.print(f"Target: {target.value}")
    console.print(f"Output: {output}")

    result = asyncio.run(
        generate_client(
            spec=spec_input,
            target=target,
            output_dir=output,
            package_name=package_name,
            additional_properties=additional_props,
            generate_tests=not no_tests,
            post_process=not no_post_process,
        )
    )

    if result.success:
        console.print(f"[green]✓[/green] {result.summary}")
        console.print(f"Files created: {len(result.files_created)}")
        if result.warnings:
            for w in result.warnings:
                console.print(f"[yellow]⚠[/yellow] {w}")
        sys.exit(0)
    else:
        console.print(f"[red]✗[/red] Generation failed: {result.error}")
        sys.exit(1)


@app.command()
def validate(
    spec: Annotated[str, typer.Argument(help="OpenAPI spec URL, file path, or '-' for stdin")],
    tool: Annotated[
        ValidationTool,
        typer.Option("--tool", help="Validation tool to use"),
    ] = ValidationTool.SPECTRAL,
    ruleset: Annotated[str | None, typer.Option("--ruleset", "-r", help="Custom ruleset path/URL")] = None,
    fail_on_warnings: Annotated[bool, typer.Option("--fail-on-warnings", help="Fail if warnings found")] = False,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Verbose output")] = False,
) -> None:
    """Validate an OpenAPI specification."""
    _setup_logging(verbose)

    spec_input = _parse_spec_input(spec)

    console.print(f"[bold]Validating {spec_input.location}[/bold]")
    console.print(f"Tool: {tool.value}")

    result = asyncio.run(
        validate_spec(
            spec=spec_input,
            tool=tool,
            ruleset=ruleset,
            fail_on_warnings=fail_on_warnings,
        )
    )

    if result.success:
        if result.valid:
            console.print(f"[green]✓[/green] Specification is valid")
        else:
            console.print(f"[red]✗[/red] Specification invalid")
            console.print(f"Errors: {len(result.errors)}, Warnings: {len(result.warnings)}")
            for err in result.errors[:10]:
                console.print(f"  [red]Error[/red] {err.get('path', '')}: {err.get('message', '')}")
            for warn in result.warnings[:5]:
                console.print(f"  [yellow]Warning[/yellow] {warn.get('path', '')}: {warn.get('message', '')}")
        sys.exit(0 if result.valid else 1)
    else:
        console.print(f"[red]✗[/red] Validation failed: {result.error}")
        sys.exit(1)


@app.command()
def generators() -> None:
    """List available generators and targets."""
    result = asyncio.run(list_generators())

    console.print(f"[bold]Generator:[/bold] {result['generator']}")
    console.print(f"[bold]Available:[/bold] {'Yes' if result['available'] else 'No'}")

    if result["targets"]:
        table = Table(title="Available Targets")
        table.add_column("Target", style="cyan")
        for target in sorted(result["targets"]):
            table.add_row(target)
        console.print(table)
    else:
        console.print("[yellow]No targets found[/yellow]")


@app.command()
def infer() -> None:
    """Infer project configuration and suggest target."""
    config = infer_project_config()
    target = config.primary_language

    table = Table(title="Project Configuration")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Language", config.language)
    table.add_row("Framework", config.framework or "auto")
    table.add_row("Package Manager", config.package_manager or "unknown")
    table.add_row("Has package.json", str(config.has_package_json))
    table.add_row("Has pyproject.toml", str(config.has_pyproject_toml))
    table.add_row("Has Cargo.toml", str(config.has_cargo_toml))
    table.add_row("Has go.mod", str(config.has_go_mod))
    table.add_row("Has pom.xml", str(config.has_pom_xml))
    table.add_row("Has build.gradle", str(config.has_build_gradle))
    table.add_row("Suggested Target", target)

    console.print(table)


def main() -> None:
    """Main entry point."""
    app()


if __name__ == "__main__":
    main()