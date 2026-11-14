# MCP OpenAPI Generator

[![PyPI version](https://img.shields.io/pypi/v/mcp-openapi-generator.svg?cacheSeconds=300)](https://pypi.org/project/mcp-openapi-generator/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

An **MCP (Model Context Protocol) server** that provides OpenAPI code generation and validation capabilities to AI assistants. Wraps industry-standard tools:

- **Code Generation**: `openapi-generator` and `swagger-codegen` for 50+ target languages/frameworks
- **Validation**: `Spectral` and `Vacuum` for OpenAPI specification linting
- **Project Intelligence**: Auto-detects project type and suggests appropriate targets

## Features

| Capability | Tools | Description |
|------------|-------|-------------|
| **Generate Client** | openapi-generator, swagger-codegen | Generate SDKs for TypeScript, Python, Java, Go, Rust, Swift, C#, Kotlin, and more |
| **Validate Spec** | Spectral, Vacuum | Lint OpenAPI specs with customizable rulesets |
| **List Generators** | — | Discover available generators and targets |
| **Infer Project** | — | Auto-detect project type (Node, Python, Rust, Go, Java, etc.) and suggest targets |

## Quick Start

### Installation

```bash
# Via pip (recommended)
pip install mcp-openapi-generator

# Or via Smithery (for MCP clients)
smithery install @mkabdullahi/mcp-openapi-generator
```

### Usage as MCP Server

Configure in your MCP client (Claude Desktop, Cursor, etc.):

```json
{
  "mcpServers": {
    "openapi-generator": {
      "command": "python",
      "args": ["-m", "mcp_openapi_generator.server"]
    }
  }
}
```

For a local VS Code setup, create `.vscode/mcp.json` with the following
configuration after creating and installing into the project virtual
environment:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
```

```json
{
  "servers": {
    "openapi-generator": {
      "type": "stdio",
      "command": "${workspaceFolder}/.venv/bin/python",
      "args": ["-m", "mcp_openapi_generator.server"],
      "cwd": "${workspaceFolder}"
    }
  }
}
```

In VS Code, open the MCP server controls and start `openapi-generator`. This
workspace configuration is ignored by Git because it points to a local virtual
environment.

### Usage as CLI Tool

```bash
# Generate TypeScript client from Petstore
mcp-openapi-generator generate https://petstore.swagger.io/v2/swagger.json \
  --target typescript-axios \
  --output ./petstore-client

# Validate a spec
mcp-openapi-generator validate https://petstore.swagger.io/v2/swagger.json

# List available generators
mcp-openapi-generator generators

# Infer project config
mcp-openapi-generator infer
```

## Available Tools (MCP)

| Tool | Description | Parameters |
|------|-------------|------------|
| `generate-client` | Generate client code from OpenAPI spec | `spec`, `target`, `output_dir`, `package_name`, `package_version`, `additional_properties`, `generate_tests`, `post_process` |
| `validate-spec` | Validate OpenAPI specification | `spec`, `tool` (spectral/vacuum), `ruleset`, `fail_on_warnings` |
| `list-generators` | List available generators and targets | — |
| `infer-project` | Detect project type and suggest target | — |

### Tool: generate-client

```json
{
  "spec": {
    "source": "url",
    "location": "https://api.example.com/openapi.yaml",
    "format": "yaml"
  },
  "target": "typescript-axios",
  "output_dir": "./generated",
  "package_name": "my-api-client",
  "package_version": "1.0.0",
  "additional_properties": {
    "supportsES6": "true",
    "npmName": "@myorg/api-client"
  },
  "generate_tests": true,
  "post_process": true
}
```

### Tool: validate-spec

```json
{
  "spec": {
    "source": "file",
    "location": "./openapi.yaml"
  },
  "tool": "spectral",
  "ruleset": "spectral:oas",
  "fail_on_warnings": false
}
```

## Supported Targets

| Category | Targets |
|----------|---------|
| **TypeScript** | `typescript-axios`, `typescript-fetch`, `typescript-node` |
| **Python** | `python`, `python-aiohttp` |
| **Java** | `spring`, `spring-boot` |
| **Kotlin** | `kotlin-spring` |
| **Go** | `go`, `go-gin` |
| **Rust** | `rust` |
| **Swift** | `swift5` |
| **C#** | `csharp-netcore` |

Run `mcp-openapi-generator generators` for the full list (depends on installed generators).

## Prerequisites

The server wraps external CLI tools. Install them for full functionality:

```bash
# Code generators (choose one or both)
npm install -g @openapitools/openapi-generator-cli
npm install -g swagger-codegen

# Validators
npm install -g @stoplight/spectral-cli
npm install -g vacuum
```

Or use the Docker image which includes everything:

```bash
docker run --rm -v $(pwd):/workspace ghcr.io/mkabdullahi/mcp-openapi-generator generate ...
```

## Configuration

### Project Auto-Detection

The server automatically detects your project type:

| File | Detected As |
|------|-------------|
| `package.json` | TypeScript/JavaScript |
| `pyproject.toml` / `requirements.txt` | Python |
| `Cargo.toml` | Rust |
| `go.mod` | Go |
| `pom.xml` / `build.gradle` | Java/Kotlin |

### Default Targets by Language

| Language | Default Target |
|----------|----------------|
| TypeScript | `typescript-axios` |
| Python | `python` |
| Java | `spring-boot` |
| Kotlin | `kotlin-spring` |
| Go | `go-gin` |
| Rust | `rust` |
| Swift | `swift5` |
| C# | `csharp-netcore` |

## Development

### Setup

```bash
git clone https://github.com/mkabdullahi/mcp-openapi-generator
cd mcp-openapi-generator

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install in development mode
pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=mcp_openapi_generator --cov-report=html

# Run only unit tests (skip integration)
pytest -m "not integration"
```

### Code Quality

```bash
# Format
ruff format .

# Lint
ruff check .

# Type check
mypy src/
```

## Publishing

### To PyPI

```bash
# Build
python -m build

# Publish
twine upload dist/*
```

### To Smithery

```bash
# Build Docker image
docker build -t ghcr.io/mkabdullahi/mcp-openapi-generator:latest .

# Push
docker push ghcr.io/mkabdullahi/mcp-openapi-generator:latest

# Publish to Smithery
smithery publish
```

## Architecture

```
mcp_openapi_generator/
├── server.py          # MCP server implementation
├── cli.py             # CLI entry points
├── tools/
│   ├── generate.py    # Code generation wrapper
│   └── validate.py    # Validation wrapper
├── utils/
│   ├── config_inference.py  # Project type detection
│   ├── spec_resolver.py     # Spec fetching & resolution
│   └── post_process.py      # Formatting & test stubs
└── types/
    └── __init__.py    # Type definitions (dataclasses, enums)
```

## License

MIT License - see [LICENSE](LICENSE) for details.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests and linting
5. Submit a PR

## Related

- [Model Context Protocol](https://modelcontextprotocol.io/)
- [OpenAPI Generator](https://openapi-generator.tech/)
- [Spectral](https://meta.stoplight.io/spectral/)
- [Vacuum](https://github.com/daveshanley/vacuum)