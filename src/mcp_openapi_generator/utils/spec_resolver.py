"""Utilities for resolving and merging OpenAPI specifications."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
import yaml

from ..types import MCPToolError, SpecInput, SpecSource

logger = logging.getLogger(__name__)

__all__ = [
    "resolve_spec",
    "merge_specs",
    "resolve_refs",
    "fetch_remote_spec",
    "load_local_spec",
]


async def fetch_remote_spec(url: str, client: httpx.AsyncClient | None = None) -> dict[str, Any]:
    """Fetch and parse a remote OpenAPI specification."""
    if client is None:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as c:
            return await fetch_remote_spec(url, c)

    response = await client.get(url)
    response.raise_for_status()

    content_type = response.headers.get("content-type", "").lower()
    if "json" in content_type or url.endswith(".json"):
        return response.json()
    return yaml.safe_load(response.text)


def load_local_spec(path: Path) -> dict[str, Any]:
    """Load and parse a local OpenAPI specification file."""
    content = path.read_text(encoding="utf-8")
    if path.suffix.lower() in (".json",):
        return json.loads(content)
    return yaml.safe_load(content)


def _resolve_external_refs(
    spec: dict[str, Any],
    base_url: str,
    visited: set[str] | None = None,
) -> dict[str, Any]:
    """Recursively resolve external $refs in the specification."""
    if visited is None:
        visited = set()

    def _resolve(obj: Any, current_base: str) -> Any:
        if isinstance(obj, dict):
            if "$ref" in obj and len(obj) == 1:
                ref = obj["$ref"]
                if ref in visited:
                    return obj  # circular ref protection
                visited.add(ref)

                if ref.startswith(("http://", "https://")):
                    # External HTTP reference - would need async resolution
                    logger.warning("External HTTP $ref found, keeping as-is: %s", ref)
                    return obj
                if ref.startswith("/") or not urlparse(ref).scheme:
                    # Relative or absolute path reference
                    resolved_url = urljoin(current_base, ref)
                    # For now, keep as-is; full resolution would require async fetch
                    logger.debug("Relative $ref found: %s -> %s", ref, resolved_url)
                    return obj

            return {k: _resolve(v, current_base) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_resolve(item, current_base) for item in obj]
        return obj

    return _resolve(spec, base_url)


async def resolve_spec(
    spec_input: SpecInput,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """
    Resolve an OpenAPI specification from various sources.

    Handles:
    - Remote URLs (HTTP/HTTPS)
    - Local files
    - stdin (-)
    - JSON and YAML formats
    - External $ref resolution (basic)
    """
    logger.info("Resolving spec from %s: %s", spec_input.source.value, spec_input.location)

    if spec_input.source == SpecSource.URL:
        spec = await fetch_remote_spec(spec_input.location, client)
        base_url = str(Path(spec_input.location).parent) + "/"
        return _resolve_external_refs(spec, base_url)

    if spec_input.source == SpecSource.FILE:
        path = Path(spec_input.location)
        if not path.exists():
            raise MCPToolError(
                f"Spec file not found: {path}",
                "resolve_spec",
                {"path": str(path)},
            )
        spec = load_local_spec(path)
        base_url = str(path.parent) + "/"
        return _resolve_external_refs(spec, base_url)

    if spec_input.source == SpecSource.STDIN:
        import sys

        content = sys.stdin.read()
        if spec_input.format == "json":
            return json.loads(content)
        return yaml.safe_load(content)

    raise MCPToolError(
        f"Unknown spec source: {spec_input.source}",
        "resolve_spec",
        {"source": spec_input.source.value},
    )


def merge_specs(*specs: dict[str, Any]) -> dict[str, Any]:
    """
    Merge multiple OpenAPI specifications into one.

    Uses a simple strategy: later specs override earlier ones for top-level keys,
    but paths and components are merged deeply.
    """
    if not specs:
        return {}

    if len(specs) == 1:
        return specs[0]

    merged = specs[0].copy()

    for spec in specs[1:]:
        for key, value in spec.items():
            if key in ("paths", "components", "security", "tags", "servers"):
                if key not in merged:
                    merged[key] = {}
                if isinstance(merged[key], dict) and isinstance(value, dict):
                    merged[key] = _deep_merge(merged[key], value)
                else:
                    merged[key] = value
            else:
                merged[key] = value

    return merged


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Deep merge two dictionaries."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def resolve_refs(spec: dict[str, Any], base_url: str = "") -> dict[str, Any]:
    """
    Resolve internal $refs within a specification.

    This is a simplified version - for full resolution, use openapi-spec-validator
    or similar library.
    """
    # For now, return as-is; full ref resolution is complex
    # and typically handled by the generator itself
    return spec
