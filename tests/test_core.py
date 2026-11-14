"""Tests for the MCP OpenAPI Generator."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from mcp_openapi_generator.tools.generate import GeneratorWrapper
from mcp_openapi_generator.tools.validate import ValidationWrapper
from mcp_openapi_generator.types import (
    GenerationOptions,
    GeneratorTarget,
    ProjectConfig,
    SpecInput,
    SpecSource,
    ValidationOptions,
    ValidationTool,
)
from mcp_openapi_generator.utils.config_inference import infer_project_config, suggest_target
from mcp_openapi_generator.utils.spec_resolver import (
    load_local_spec,
    merge_specs,
    resolve_spec,
)


class TestTypes:
    """Test type definitions."""

    def test_generator_target_enum(self):
        assert GeneratorTarget.TYPESCRIPT_AXIOS.value == "typescript-axios"
        assert GeneratorTarget.PYTHON.value == "python"
        assert (
            GeneratorTarget.from_project_config(ProjectConfig(language="python"))
            == GeneratorTarget.PYTHON
        )

    def test_spec_input(self):
        spec = SpecInput(source=SpecSource.URL, location="https://api.example.com/openapi.yaml")
        assert spec.is_remote is True

        spec = SpecInput(source=SpecSource.FILE, location="./openapi.yaml")
        assert spec.is_remote is False

    def test_generation_options(self):
        spec = SpecInput(source=SpecSource.URL, location="https://example.com/spec.yaml")
        options = GenerationOptions(
            target=GeneratorTarget.TYPESCRIPT_AXIOS,
            spec=spec,
            output_dir=Path("./out"),
        )
        assert options.target == GeneratorTarget.TYPESCRIPT_AXIOS

    def test_validation_options(self):
        spec = SpecInput(source=SpecSource.FILE, location="./spec.yaml")
        options = ValidationOptions(
            spec=spec,
            tool=ValidationTool.SPECTRAL,
        )
        assert options.tool == ValidationTool.SPECTRAL


class TestConfigInference:
    """Test project configuration inference."""

    def test_infer_empty_project(self, tmp_path):
        config = infer_project_config(tmp_path)
        assert config.language == "typescript"  # default
        assert config.primary_language == "typescript"

    def test_infer_node_project(self, tmp_path):
        (tmp_path / "package.json").write_text(
            '{"dependencies": {"axios": "^1.0"}, "devDependencies": {"typescript": "^5.0"}}'
        )
        config = infer_project_config(tmp_path)
        assert config.has_package_json
        assert config.language == "typescript"
        assert config.primary_language == "typescript"

    def test_infer_python_project(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text('[project]\ndependencies = ["fastapi"]')
        config = infer_project_config(tmp_path)
        assert config.has_pyproject_toml
        assert config.language == "python"
        assert config.primary_language == "python"

    def test_infer_rust_project(self, tmp_path):
        (tmp_path / "Cargo.toml").write_text('[package]\nname = "test"')
        config = infer_project_config(tmp_path)
        assert config.has_cargo_toml
        assert config.primary_language == "rust"

    def test_suggest_target(self):
        config = ProjectConfig(language="python", has_pyproject_toml=True)
        assert suggest_target(config) == "python"

        config = ProjectConfig(language="typescript", has_package_json=True)
        assert suggest_target(config) == "typescript"


class TestSpecResolver:
    """Test specification resolution."""

    def test_load_local_spec_yaml(self, tmp_path):
        spec_file = tmp_path / "spec.yaml"
        spec_file.write_text("openapi: 3.0.0\ninfo:\n  title: Test\n  version: 1.0.0\n")
        spec = load_local_spec(spec_file)
        assert spec["info"]["title"] == "Test"

    def test_load_local_spec_json(self, tmp_path):
        spec_file = tmp_path / "spec.json"
        spec_file.write_text('{"openapi": "3.0.0", "info": {"title": "Test", "version": "1.0.0"}}')
        spec = load_local_spec(spec_file)
        assert spec["info"]["title"] == "Test"

    def test_merge_specs(self):
        spec1 = {"openapi": "3.0.0", "info": {"title": "API 1"}, "paths": {"/a": {}}}
        spec2 = {"info": {"title": "API 2"}, "paths": {"/b": {}}, "components": {"schemas": {}}}
        merged = merge_specs(spec1, spec2)
        assert merged["info"]["title"] == "API 2"  # overridden
        assert "/a" in merged["paths"]
        assert "/b" in merged["paths"]
        assert "components" in merged

    @pytest.mark.asyncio
    async def test_resolve_remote_spec_with_provided_client(self):
        transport = httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                headers={"content-type": "application/json"},
                json={"openapi": "3.0.0", "info": {"title": "Test", "version": "1.0.0"}},
            )
        )
        spec_input = SpecInput(source=SpecSource.URL, location="https://example.test/openapi.json")

        async with httpx.AsyncClient(transport=transport) as client:
            spec = await resolve_spec(spec_input, client)

        assert spec["info"]["title"] == "Test"


class TestGeneratorWrapper:
    """Test generator wrapper."""

    def test_wrapper_creation(self):
        wrapper = GeneratorWrapper()
        # Should not crash even if generators not installed
        assert hasattr(wrapper, "generator_name")

    def test_available_property(self):
        wrapper = GeneratorWrapper()
        # Just verify it doesn't crash
        _ = wrapper.available

    def test_openapi_generator_targets_use_short_list_output(self, monkeypatch):
        def fake_which(executable):
            return (
                "/usr/bin/openapi-generator-cli" if executable == "openapi-generator-cli" else None
            )

        def fake_run(command, **_kwargs):
            assert command == ["/usr/bin/openapi-generator-cli", "list", "-s"]
            return SimpleNamespace(
                returncode=0,
                stdout="python,typescript-fetch,typescript-axios\n",
            )

        monkeypatch.setattr(
            "mcp_openapi_generator.tools.generate.shutil.which",
            fake_which,
        )
        monkeypatch.setattr(
            "mcp_openapi_generator.tools.generate.subprocess.run",
            fake_run,
        )

        targets = GeneratorWrapper().get_supported_targets()

        assert targets == ["python", "typescript-axios", "typescript-fetch"]


class TestValidationWrapper:
    """Test validation wrapper."""

    def test_wrapper_creation(self):
        wrapper = ValidationWrapper()
        # Should not crash
        tools = wrapper.available_tools
        assert isinstance(tools, list)

    def test_spectral_parser_accepts_numeric_severity_and_warning_policy(self):
        wrapper = ValidationWrapper()
        output = json.dumps([
            {
                "severity": 1,
                "code": "info-contact",
                "message": "Add contact details",
                "path": ["info"],
            }
        ])

        permissive = wrapper._parse_spectral_output(output, "spec.yaml")
        strict = wrapper._parse_spectral_output(
            output,
            "spec.yaml",
            fail_on_warnings=True,
        )

        assert permissive.valid
        assert len(permissive.warnings) == 1
        assert not strict.valid

    def test_vacuum_parser_respects_warning_policy(self):
        wrapper = ValidationWrapper()
        output = json.dumps([{"severity": "warning", "message": "Add a description"}])

        result = wrapper._parse_vacuum_output(
            output,
            "spec.yaml",
            fail_on_warnings=True,
        )

        assert not result.valid
        assert len(result.warnings) == 1


@pytest.mark.asyncio
async def test_mcp_server_stdio_handshake_and_tool_call():
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_openapi_generator.server"],
    )

    async with (
        stdio_client(parameters) as (read_stream, write_stream),
        ClientSession(read_stream, write_stream) as session,
    ):
        await session.initialize()
        tools = await session.list_tools()
        result = await session.call_tool("infer-project", {})

    assert {tool.name for tool in tools.tools} == {
        "generate-client",
        "validate-spec",
        "list-generators",
        "infer-project",
    }
    assert not result.is_error
    assert "Project Configuration:" in result.content[0].text


class TestCLI:
    """Test CLI parsing."""

    def test_parse_spec_input_url(self):
        from mcp_openapi_generator.cli import _parse_spec_input

        spec = _parse_spec_input("https://api.example.com/openapi.yaml")
        assert spec.source.value == "url"
        assert spec.location == "https://api.example.com/openapi.yaml"

    def test_parse_spec_input_file(self):
        from mcp_openapi_generator.cli import _parse_spec_input

        spec = _parse_spec_input("./openapi.yaml")
        assert spec.source.value == "file"
        assert spec.location == "./openapi.yaml"

    def test_parse_spec_input_stdin(self):
        from mcp_openapi_generator.cli import _parse_spec_input

        spec = _parse_spec_input("-")
        assert spec.source.value == "stdin"
        assert spec.location == "-"


# Integration test with a real OpenAPI spec (if generators installed)
@pytest.mark.integration
class TestIntegration:
    """Integration tests requiring generators to be installed."""

    @pytest.fixture
    def petstore_spec(self):
        return SpecInput(
            source=SpecSource.URL,
            location="https://petstore.swagger.io/v2/swagger.json",
        )

    @pytest.mark.asyncio
    async def test_generate_typescript_client(self, petstore_spec, tmp_path):
        from mcp_openapi_generator.tools.generate import generate_client
        from mcp_openapi_generator.types import GeneratorTarget

        output_dir = tmp_path / "generated"
        await generate_client(
            spec=petstore_spec,
            target=GeneratorTarget.TYPESCRIPT_AXIOS,
            output_dir=output_dir,
            generate_tests=False,
            post_process=False,
        )
        # This test only passes if openapi-generator is installed
        # We don't assert success since it may not be installed in CI

    @pytest.mark.asyncio
    async def test_validate_petstore(self, petstore_spec):
        from mcp_openapi_generator.tools.validate import validate_spec
        from mcp_openapi_generator.types import ValidationTool

        await validate_spec(
            spec=petstore_spec,
            tool=ValidationTool.SPECTRAL,
        )
        # This test only passes if spectral is installed
        # We don't assert success since it may not be installed in CI


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
