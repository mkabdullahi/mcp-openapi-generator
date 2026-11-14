"""Utilities for the MCP OpenAPI Generator."""

from __future__ import annotations

from .config_inference import infer_project_config, suggest_target, get_git_root
from .post_process import post_process_generation, apply_formatting, generate_test_stubs
from .spec_resolver import resolve_spec, merge_specs, resolve_refs, fetch_remote_spec, load_local_spec

__all__ = [
    "infer_project_config",
    "suggest_target",
    "get_git_root",
    "post_process_generation",
    "apply_formatting",
    "generate_test_stubs",
    "resolve_spec",
    "merge_specs",
    "resolve_refs",
    "fetch_remote_spec",
    "load_local_spec",
]