"""MCP server for OpenAPI code generation and validation."""

from __future__ import annotations

import asyncio
import logging
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.types import (
    CallToolRequestParams,
    CallToolResult,
    ListToolsResult,
    PaginatedRequestParams,
    TextContent,
    Tool,
)

from .tools.generate import generate_client, list_generators
from .tools.validate import validate_spec
from .types import (
    GeneratorTarget,
    MCPToolError,
    SpecInput,
    SpecSource,
    ValidationTool,
)
from .utils.config_inference import infer_project_config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)

__all__ = ["main", "create_server"]


_SPEC_SCHEMA = {
    "type": "object",
    "description": "OpenAPI specification input",
    "properties": {
        "source": {
            "type": "string",
            "enum": ["url", "file", "stdin"],
            "description": "Source type for the specification",
        },
        "location": {
            "type": "string",
            "description": "URL, file path, or '-' for stdin",
        },
        "format": {
            "type": "string",
            "enum": ["json", "yaml", "yml"],
            "default": "yaml",
            "description": "Format of the specification",
        },
    },
    "required": ["source", "location"],
}

TOOLS = [
    Tool(
        name="generate-client",
        description=(
            "Generate client code from an OpenAPI specification using openapi-generator "
            "or swagger-codegen"
        ),
        input_schema={
            "type": "object",
            "properties": {
                "spec": _SPEC_SCHEMA,
                "target": {
                    "type": "string",
                    "enum": [target.value for target in GeneratorTarget],
                    "default": "typescript-axios",
                    "description": "Target language/framework for generation",
                },
                "output_dir": {
                    "type": "string",
                    "default": "./generated",
                    "description": "Output directory for generated code",
                },
                "package_name": {"type": "string"},
                "package_version": {"type": "string"},
                "additional_properties": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                },
                "generate_tests": {"type": "boolean", "default": True},
                "post_process": {"type": "boolean", "default": True},
            },
            "required": ["spec"],
        },
    ),
    Tool(
        name="validate-spec",
        description="Validate an OpenAPI specification using Spectral or Vacuum",
        input_schema={
            "type": "object",
            "properties": {
                "spec": _SPEC_SCHEMA,
                "tool": {
                    "type": "string",
                    "enum": ["spectral", "vacuum"],
                    "default": "spectral",
                },
                "ruleset": {"type": "string"},
                "fail_on_warnings": {"type": "boolean", "default": False},
            },
            "required": ["spec"],
        },
    ),
    Tool(
        name="list-generators",
        description="List available code generators and their targets",
        input_schema={"type": "object", "properties": {}},
    ),
    Tool(
        name="infer-project",
        description="Infer project configuration and suggest generation target",
        input_schema={"type": "object", "properties": {}},
    ),
]


async def _handle_generate_client(arguments: dict[str, Any]) -> CallToolResult:
    spec_data = arguments["spec"]
    spec = SpecInput(
        source=SpecSource(spec_data["source"]),
        location=spec_data["location"],
        format=spec_data.get("format", "yaml"),
    )
    target = GeneratorTarget(arguments.get("target", "typescript-axios"))
    result = await generate_client(
        spec=spec,
        target=target,
        output_dir=Path(arguments.get("output_dir", "./generated")),
        package_name=arguments.get("package_name"),
        package_version=arguments.get("package_version"),
        additional_properties=arguments.get("additional_properties", {}),
        generate_tests=arguments.get("generate_tests", True),
        post_process=arguments.get("post_process", True),
    )

    if not result.success:
        return CallToolResult(
            content=[TextContent(type="text", text=f"Generation failed: {result.error}")],
            is_error=True,
        )

    text = f"{result.summary}\nFiles created: {len(result.files_created)}"
    if result.warnings:
        text += "\nWarnings:\n" + "\n".join(f"- {warning}" for warning in result.warnings)
    return CallToolResult(content=[TextContent(type="text", text=text)])


async def _handle_validate_spec(arguments: dict[str, Any]) -> CallToolResult:
    spec_data = arguments["spec"]
    spec = SpecInput(
        source=SpecSource(spec_data["source"]),
        location=spec_data["location"],
        format=spec_data.get("format", "yaml"),
    )
    result = await validate_spec(
        spec=spec,
        tool=ValidationTool(arguments.get("tool", "spectral")),
        ruleset=arguments.get("ruleset"),
        fail_on_warnings=arguments.get("fail_on_warnings", False),
    )

    if not result.success:
        return CallToolResult(
            content=[TextContent(type="text", text=f"Validation failed: {result.error}")],
            is_error=True,
        )

    text = "Specification is valid" if result.valid else "Specification invalid"
    text += f"\nErrors: {len(result.errors)}, Warnings: {len(result.warnings)}"
    for label, entries in (("Errors", result.errors), ("Warnings", result.warnings)):
        if entries:
            text += f"\n\n{label}:\n"
            text += "\n".join(
                f"- {item.get('path', '')}: {item.get('message', '')}" for item in entries[:10]
            )
    return CallToolResult(
        content=[TextContent(type="text", text=text)],
        is_error=not result.valid,
    )


async def _handle_list_generators(_arguments: dict[str, Any]) -> CallToolResult:
    result = await list_generators()
    text = f"Generator: {result['generator']}\nAvailable: {'Yes' if result['available'] else 'No'}"
    if result["targets"]:
        text += "\n\nAvailable targets:\n" + "\n".join(
            f"- {target}" for target in sorted(result["targets"])
        )
    else:
        text += "\n\nNo targets found (generator not installed)"
    return CallToolResult(content=[TextContent(type="text", text=text)])


async def _handle_infer_project(_arguments: dict[str, Any]) -> CallToolResult:
    config = infer_project_config()
    text = (
        "Project Configuration:\n"
        f"  Language: {config.language}\n"
        f"  Framework: {config.framework or 'auto'}\n"
        f"  Package Manager: {config.package_manager or 'unknown'}\n"
        f"  Has package.json: {config.has_package_json}\n"
        f"  Has pyproject.toml: {config.has_pyproject_toml}\n"
        f"  Has Cargo.toml: {config.has_cargo_toml}\n"
        f"  Has go.mod: {config.has_go_mod}\n"
        f"  Has pom.xml: {config.has_pom_xml}\n"
        f"  Has build.gradle: {config.has_build_gradle}\n"
        f"\nSuggested Target: {config.primary_language}"
    )
    return CallToolResult(content=[TextContent(type="text", text=text)])


ToolHandler = Callable[[dict[str, Any]], Awaitable[CallToolResult]]
TOOL_HANDLERS: dict[str, ToolHandler] = {
    "generate-client": _handle_generate_client,
    "validate-spec": _handle_validate_spec,
    "list-generators": _handle_list_generators,
    "infer-project": _handle_infer_project,
}


async def handle_list_tools(_context: Any, _request: PaginatedRequestParams) -> ListToolsResult:
    return ListToolsResult(tools=TOOLS)


async def handle_call_tool(_context: Any, request: CallToolRequestParams) -> CallToolResult:
    name = request.name
    arguments = request.arguments or {}
    logger.info("Tool called: %s", name)

    handler = TOOL_HANDLERS.get(name)
    if handler is None:
        return CallToolResult(
            content=[TextContent(type="text", text=f"Unknown tool: {name}")],
            is_error=True,
        )

    try:
        return await handler(arguments)
    except MCPToolError as error:
        logger.error("MCP tool error: %s", error)
        return CallToolResult(
            content=[TextContent(type="text", text=f"Tool error: {error}")],
            is_error=True,
        )
    except Exception as error:
        logger.exception("Tool execution failed")
        return CallToolResult(
            content=[TextContent(type="text", text=f"Internal error: {error}")],
            is_error=True,
        )


def create_server() -> Server:
    """Create and configure the MCP server."""
    mcp_server = Server("mcp-openapi-generator")
    mcp_server.add_request_handler("tools/list", PaginatedRequestParams, handle_list_tools)
    mcp_server.add_request_handler("tools/call", CallToolRequestParams, handle_call_tool)
    return mcp_server


async def run_server() -> None:
    """Run the MCP server with stdio transport."""
    from mcp.server.stdio import stdio_server

    mcp_server = create_server()
    async with stdio_server() as (read_stream, write_stream):
        await mcp_server.run(
            read_stream,
            write_stream,
            mcp_server.create_initialization_options(),
        )


def main() -> None:
    """Main entry point for the MCP server."""
    try:
        asyncio.run(run_server())
    except KeyboardInterrupt:
        logger.info("Server stopped")
    except Exception:
        logger.exception("Server error")
        sys.exit(1)


if __name__ == "__main__":
    main()
