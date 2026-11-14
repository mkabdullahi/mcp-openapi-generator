"""Post-processing hooks for generated code."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Any

from ..types import GenerationOptions, GenerationResult, ProjectConfig

logger = logging.getLogger(__name__)

__all__ = ["post_process_generation", "apply_formatting", "generate_test_stubs"]


async def post_process_generation(
    result: GenerationResult,
    options: GenerationOptions,
    project_config: ProjectConfig | None = None,
) -> GenerationResult:
    """
    Apply post-processing to generated code.

    Includes:
    - Code formatting (prettier, black, gofmt, rustfmt, etc.)
    - Test stub generation
    - Project-specific naming conventions
    - Linting fixes
    """
    if not options.post_process:
        return result

    logger.info("Post-processing generated code in %s", result.output_dir)

    warnings = list(result.warnings)
    new_files = list(result.files_created)

    # Apply formatting based on target language
    fmt_warnings = await apply_formatting(result.output_dir, options.target, project_config)
    warnings.extend(fmt_warnings)

    # Generate test stubs if requested
    if options.generate_tests:
        test_files = await generate_test_stubs(result.output_dir, options.target, options.spec)
        new_files.extend(test_files)

    return GenerationResult(
        success=result.success,
        output_dir=result.output_dir,
        files_created=new_files,
        target=result.target,
        spec_source=result.spec_source,
        warnings=warnings,
        error=result.error,
    )


async def apply_formatting(
    output_dir: Path,
    target: Any,  # GeneratorTarget
    project_config: ProjectConfig | None = None,
) -> list[str]:
    """Apply appropriate code formatter for the target language."""
    warnings = []
    target_str = str(target.value) if hasattr(target, "value") else str(target)

    formatters = {
        "typescript": ["prettier", "--write"],
        "typescript-axios": ["prettier", "--write"],
        "typescript-fetch": ["prettier", "--write"],
        "typescript-node": ["prettier", "--write"],
        "python": ["black"],
        "python-aiohttp": ["black"],
        "go": ["gofmt", "-w"],
        "go-gin": ["gofmt", "-w"],
        "rust": ["rustfmt"],
        "java": ["google-java-format"],
        "kotlin": ["ktfmt"],
        "csharp": ["dotnet", "format"],
        "swift": ["swiftformat"],
    }

    formatter_cmd = formatters.get(target_str)
    if not formatter_cmd:
        return warnings

    try:
        # Check if formatter is available
        check_result = subprocess.run(
            [formatter_cmd[0], "--version"],
            capture_output=True,
            timeout=5,
        )
        if check_result.returncode != 0:
            warnings.append(f"Formatter {formatter_cmd[0]} not available, skipping formatting")
            return warnings

        # Run formatter
        result = subprocess.run(
            formatter_cmd + [str(output_dir)],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=output_dir,
        )
        if result.returncode != 0:
            warnings.append(f"Formatting failed: {result.stderr[:200]}")
        else:
            logger.debug("Formatted %s code in %s", target_str, output_dir)
    except FileNotFoundError:
        warnings.append(f"Formatter {formatter_cmd[0]} not installed")
    except subprocess.TimeoutExpired:
        warnings.append("Formatting timed out")
    except Exception as e:
        warnings.append(f"Formatting error: {e}")

    return warnings


async def generate_test_stubs(
    output_dir: Path,
    target: Any,
    spec: Any,  # SpecInput
) -> list[Path]:
    """Generate basic test stubs for the generated client."""
    new_files = []
    target_str = str(target.value) if hasattr(target, "value") else str(target)

    # For now, create a simple test file template
    # This would be expanded based on the actual generated code structure
    test_templates = {
        "typescript": """
import { describe, it, expect, vi } from 'vitest';

describe('Generated API Client', () => {
  it('should be importable', () => {
    // TODO: Add actual tests
    expect(true).toBe(true);
  });
});
""",
        "typescript-axios": """
import { describe, it, expect, vi } from 'vitest';

describe('Generated API Client (axios)', () => {
  it('should be importable', () => {
    // TODO: Add actual tests
    expect(true).toBe(true);
  });
});
""",
        "python": """
import pytest

def test_generated_client_imports():
    \"\"\"Test that the generated client can be imported.\"\"\"
    # TODO: Add actual tests
    assert True
""",
        "python-aiohttp": """
import pytest

def test_generated_client_imports():
    \"\"\"Test that the generated client can be imported.\"\"\"
    # TODO: Add actual tests
    assert True
""",
        "go": """
package generated_test

import "testing"

func TestGeneratedClient(t *testing.T) {
    // TODO: Add actual tests
    if true != true {
        t.Errorf("unexpected")
    }
}
""",
        "rust": """
#[cfg(test)]
mod tests {
    #[test]
    fn test_generated_client() {
        // TODO: Add actual tests
        assert!(true);
    }
}
""",
    }

    template = test_templates.get(target_str)
    if not template:
        return new_files

    # Determine test file location
    test_dirs = {
        "typescript": output_dir / "tests",
        "typescript-axios": output_dir / "tests",
        "typescript-fetch": output_dir / "tests",
        "python": output_dir / "tests",
        "python-aiohttp": output_dir / "tests",
        "go": output_dir,
        "rust": output_dir / "tests",
    }

    test_dir = test_dirs.get(target_str, output_dir / "tests")
    test_dir.mkdir(parents=True, exist_ok=True)

    test_file = test_dir / f"test_generated.{_test_extension(target_str)}"
    test_file.write_text(template.strip() + "\n", encoding="utf-8")
    new_files.append(test_file)

    logger.debug("Created test stub: %s", test_file)
    return new_files


def _test_extension(target: str) -> str:
    extensions = {
        "typescript": "test.ts",
        "typescript-axios": "test.ts",
        "typescript-fetch": "test.ts",
        "python": "py",
        "python-aiohttp": "py",
        "go": "_test.go",
        "rust": "rs",
    }
    return extensions.get(target, "txt")