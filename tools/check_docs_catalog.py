"""Validate MaverickMCP documentation catalog hygiene.

The checker intentionally stays lightweight:
- every tracked Markdown/text doc must be either cataloged or allowlisted;
- relative Markdown links must resolve;
- root agent entrypoints must stay concise.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = REPO_ROOT / "docs" / "CATALOG.md"

ROOT_DOCS = {
    "AGENTS.md",
    "CLAUDE.md",
    "GEMINI.md",
    "README.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "CODE_OF_CONDUCT.md",
}

NON_DOC_TEXT = {
    "scripts/requirements_tiingo.txt",
}

# Fork-specific: files the catalog marks "deleted" but that still exist on disk
# in this fork.  Listed here so the catalog check does not flag them as
# "outside approved locations" — they ARE referenced in docs/CATALOG.md.
# Authority: keep this set in sync with the "Deleted Or Consolidated" section
# in docs/CATALOG.md; every entry here must appear there and vice versa.
CATALOG_DELETED = {
    "DATABASE_SETUP.md",
    "PLANS.md",
    "maverick_mcp/README.md",
    "maverick_mcp/tests/README_INMEMORY_TESTS.md",
    "scripts/INSTALLATION_GUIDE.md",
    "scripts/README_TIINGO_LOADER.md",
    "tests/README.md",
    "tests/integration/README.md",
}

CONCISE_LIMITS = {
    "AGENTS.md": 220,
    # CLAUDE.md in this fork is the full project guide (not a short pointer),
    # so we do not enforce a line-count limit on it.
    "GEMINI.md": 80,
}

LINK_RE = re.compile(r"!?\[[^\]]+\]\(([^)]+)\)")
CATALOG_TOKEN_RE = re.compile(r"`([^`]+)`")
EXTERNAL_SCHEMES = (
    "http://",
    "https://",
    "mailto:",
    "app://",
    "plugin://",
    "file://",
    "tel:",
)


def git_ls_docs() -> list[Path]:
    """Return tracked Markdown and text documentation paths."""
    result = subprocess.run(
        [
            "git",
            "ls-files",
            "--cached",
            "--",
            "*.md",
            "*.mdx",
            "*.txt",
        ],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [
        path
        for line in result.stdout.splitlines()
        if line.strip()
        for path in [Path(line)]
        if (REPO_ROOT / path).exists()
    ]


def is_allowlisted(path: Path) -> bool:
    """Return whether a tracked doc path is allowed outside the catalog."""
    path_str = path.as_posix()
    return (
        path_str in ROOT_DOCS
        or path_str in NON_DOC_TEXT
        or path_str in CATALOG_DELETED
        or path_str.startswith(".github/")
        or path_str.startswith("conductor/")
        or path_str.startswith("docs/superpowers/")
    )


def validate_catalog(paths: list[Path]) -> list[str]:
    """Validate that tracked docs are allowlisted or cataloged exactly."""
    errors: list[str] = []
    catalog = CATALOG_PATH.read_text(encoding="utf-8")
    catalog_entries = set(CATALOG_TOKEN_RE.findall(catalog))

    for path in paths:
        path_str = path.as_posix()
        if is_allowlisted(path):
            continue
        if path_str.startswith("docs/"):
            catalog_key = path_str.removeprefix("docs/")
            if catalog_key not in catalog_entries:
                errors.append(f"{path_str} is missing from docs/CATALOG.md")
            continue
        errors.append(f"{path_str} is a tracked doc outside approved locations")

    return errors


def normalize_link(target: str) -> str:
    """Normalize a Markdown link target before resolution."""
    target = target.strip()
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1]
    return target


def should_skip_link(target: str) -> bool:
    """Return whether a Markdown link target should not be file-resolved."""
    return (
        not target
        or target.startswith("#")
        or target.startswith(EXTERNAL_SCHEMES)
        or target.startswith("data:")
    )


def without_fenced_code_blocks(text: str) -> str:
    """Remove fenced code blocks while preserving non-code Markdown text."""
    lines = text.splitlines(keepends=True)
    filtered: list[str] = []
    fence_char: str | None = None
    fence_length = 0

    for line in lines:
        stripped = line.lstrip()
        fence_match = re.match(r"(`{3,}|~{3,})(.*)$", stripped)
        if fence_char:
            if (
                fence_match
                and fence_match.group(1)[0] == fence_char
                and len(fence_match.group(1)) >= fence_length
                and not fence_match.group(2).strip()
            ):
                fence_char = None
                fence_length = 0
            continue
        if fence_match:
            fence_char = fence_match.group(1)[0]
            fence_length = len(fence_match.group(1))
            continue
        filtered.append(line)

    return "".join(filtered)


def validate_links(paths: list[Path]) -> list[str]:
    """Validate relative Markdown links in tracked Markdown files."""
    errors: list[str] = []

    for path in paths:
        if path.suffix.lower() not in {".md", ".mdx"}:
            continue

        full_path = REPO_ROOT / path
        text = without_fenced_code_blocks(full_path.read_text(encoding="utf-8"))
        for match in LINK_RE.finditer(text):
            target = normalize_link(match.group(1))
            if should_skip_link(target):
                continue
            if target.startswith("/"):
                errors.append(f"{path}: absolute link is not allowed: {target}")
                continue

            target_path = target.split("#", 1)[0]
            if not target_path:
                continue

            resolved = (full_path.parent / target_path).resolve()
            try:
                resolved.relative_to(REPO_ROOT)
            except ValueError:
                errors.append(f"{path}: link escapes repo: {target}")
                continue

            if not resolved.exists():
                errors.append(f"{path}: broken link: {target}")

    return errors


def validate_concise_entrypoints() -> list[str]:
    """Validate root agent entrypoints stay concise."""
    errors: list[str] = []

    for path_str, limit in CONCISE_LIMITS.items():
        path = REPO_ROOT / path_str
        if not path.exists():
            continue  # fork may omit optional root entrypoints (e.g. AGENTS.md, GEMINI.md)
        line_count = len(path.read_text(encoding="utf-8").splitlines())
        if line_count > limit:
            errors.append(f"{path_str} has {line_count} lines; limit is {limit}")

    return errors


def main() -> int:
    """Run all documentation catalog checks."""
    paths = git_ls_docs()
    errors = [
        *validate_catalog(paths),
        *validate_links(paths),
        *validate_concise_entrypoints(),
    ]

    if errors:
        print("Documentation catalog check failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print(f"Documentation catalog check passed ({len(paths)} tracked docs/text files).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
