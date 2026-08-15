"""Checks for repository-local links used by the Markdown documentation."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MARKDOWN_LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
HTML_SOURCE_RE = re.compile(r"(?:src|href)=[\"']([^\"']+)[\"']", re.IGNORECASE)
EXCLUDED_PARTS = {".git", ".pytest_cache", ".ruff_cache", "__pycache__"}


def _targets_outside_fenced_code(text: str):
    in_fence = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        yield from MARKDOWN_LINK_RE.findall(line)
        yield from HTML_SOURCE_RE.findall(line)


def _local_target(markdown_path: Path, raw_target: str) -> Path | None:
    target = raw_target.strip().strip("<>")
    if not target or target.startswith(("#", "http://", "https://", "mailto:")):
        return None
    # Markdown permits an optional title after a whitespace-delimited target.
    target = target.split(maxsplit=1)[0]
    target = unquote(target.split("#", 1)[0].split("?", 1)[0])
    if not target:
        return None
    return (markdown_path.parent / target).resolve()


def test_repository_markdown_local_links_exist():
    missing = []
    markdown_paths = sorted(REPOSITORY_ROOT.rglob("*.md"))
    for markdown_path in markdown_paths:
        if any(part in EXCLUDED_PARTS for part in markdown_path.parts):
            continue
        text = markdown_path.read_text(encoding="utf-8")
        for raw_target in _targets_outside_fenced_code(text):
            target = _local_target(markdown_path, raw_target)
            if target is not None and not target.exists():
                missing.append(
                    f"{markdown_path.relative_to(REPOSITORY_ROOT)} -> {raw_target}"
                )

    assert not missing, "Missing repository-local documentation targets:\n" + "\n".join(
        missing
    )
