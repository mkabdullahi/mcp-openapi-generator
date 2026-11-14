"""Optional end-to-end test for the installed OpenAPI command-line tools."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(
    shutil.which("openapi-generator-cli") is None or shutil.which("spectral") is None,
    reason="OpenAPI Generator and Spectral are required",
)
async def test_mcp_server_generates_and_validates_local_spec(tmp_path):
    spec_path = Path(__file__).parent / "fixtures" / "openapi-smoke.yaml"
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_openapi_generator.server"],
    )

    async with (
        stdio_client(parameters) as (read_stream, write_stream),
        ClientSession(read_stream, write_stream) as session,
    ):
        await session.initialize()
        generated = await session.call_tool(
            "generate-client",
            {
                "spec": {"source": "file", "location": str(spec_path)},
                "target": "python",
                "output_dir": str(tmp_path / "generated"),
                "generate_tests": False,
                "post_process": False,
            },
        )
        validated = await session.call_tool(
            "validate-spec",
            {
                "spec": {"source": "file", "location": str(spec_path)},
                "tool": "spectral",
            },
        )

    assert not generated.is_error, generated.content
    assert "Files created:" in generated.content[0].text
    assert not validated.is_error, validated.content
    assert "Specification is valid" in validated.content[0].text
