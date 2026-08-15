import json
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised on Python 3.8-3.10
    import tomli as tomllib

from core.constants import APP_VERSION
from core.overexposure_repair import SOFTWARE_VERSION


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _normalized_keywords(values):
    return {str(value).casefold() for value in values}


def _match_version(path: Path, pattern: str) -> str:
    text = path.read_text(encoding="utf-8")
    match = re.search(pattern, text, flags=re.MULTILINE)
    assert match is not None, f"Version not found in {path.name}"
    return match.group(1)


def test_software_version_metadata_is_consistent():
    pyproject_version = _match_version(
        REPOSITORY_ROOT / "pyproject.toml",
        r'^version\s*=\s*"([^"]+)"\s*$',
    )
    citation_version = _match_version(
        REPOSITORY_ROOT / "CITATION.cff",
        r'^version:\s*"?([^"\s]+)"?\s*$',
    )
    zenodo_version = json.loads(
        (REPOSITORY_ROOT / ".zenodo.json").read_text(encoding="utf-8")
    )["version"]
    runtime_version = APP_VERSION[1:] if APP_VERSION.startswith("v") else APP_VERSION

    assert {
        pyproject_version,
        citation_version,
        str(zenodo_version),
        runtime_version,
        SOFTWARE_VERSION,
    } == {pyproject_version}


def test_requirements_match_runtime_dependencies():
    pyproject_text = (REPOSITORY_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    dependency_block = re.search(
        r"^dependencies\s*=\s*\[(.*?)^\]",
        pyproject_text,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert dependency_block is not None
    pyproject_dependencies = {
        match.group(1).lower(): match.group(2).replace(" ", "")
        for match in re.finditer(
            r'^\s*"([A-Za-z0-9_.-]+)([^";]*)(?:;[^\"]*)?",?\s*$',
            dependency_block.group(1),
            flags=re.MULTILINE,
        )
    }
    requirement_dependencies = {}
    for line in (REPOSITORY_ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines():
        requirement = line.split("#", 1)[0].strip()
        if not requirement:
            continue
        requirement = requirement.split(";", 1)[0].strip()
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)(.*)", requirement)
        assert match is not None, requirement
        requirement_dependencies[match.group(1).lower()] = match.group(2).replace(" ", "")

    assert requirement_dependencies == pyproject_dependencies


def test_public_metadata_keywords_are_consistent():
    pyproject = tomllib.loads(
        (REPOSITORY_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    zenodo = json.loads((REPOSITORY_ROOT / ".zenodo.json").read_text(encoding="utf-8"))
    citation_text = (REPOSITORY_ROOT / "CITATION.cff").read_text(encoding="utf-8")
    citation_keywords_match = re.search(
        r"^keywords:\s*\n((?:\s+-\s+.+\n?)+)",
        citation_text,
        flags=re.MULTILINE,
    )
    assert citation_keywords_match is not None
    citation_keywords = {
        line.split("-", 1)[1].strip()
        for line in citation_keywords_match.group(1).splitlines()
    }

    expected = _normalized_keywords(pyproject["project"]["keywords"])
    assert _normalized_keywords(zenodo["keywords"]) == expected
    assert _normalized_keywords(citation_keywords) == expected


def test_python_classifiers_cover_supported_ci_versions():
    pyproject = tomllib.loads(
        (REPOSITORY_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    classifiers = set(pyproject["project"]["classifiers"])

    for version in ("3.8", "3.12", "3.13"):
        assert f"Programming Language :: Python :: {version}" in classifiers


def test_test_extra_installs_the_no_isolation_build_backend():
    pyproject = tomllib.loads(
        (REPOSITORY_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    test_dependencies = set(pyproject["project"]["optional-dependencies"]["test"])

    assert "setuptools>=61.0" in test_dependencies


def test_package_readme_is_self_contained_for_index_rendering():
    pyproject = tomllib.loads(
        (REPOSITORY_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    assert pyproject["project"]["readme"] == "PACKAGE_README.md"

    package_readme = (REPOSITORY_ROOT / "PACKAGE_README.md").read_text(encoding="utf-8")
    assert "src=\"" not in package_readme
    assert not re.search(r"!?\[[^]]*\]\((?!https?://|#)[^)]+\)", package_readme)


def test_sdist_manifest_declares_review_materials():
    manifest = (REPOSITORY_ROOT / "MANIFEST.in").read_text(encoding="utf-8")
    required_directives = {
        "include CITATION.cff",
        "include CODE_OF_CONDUCT.md",
        "include CONTRIBUTING.md",
        "include LICENSE",
        "include PACKAGE_README.md",
        "include README.md",
        "include SECURITY.md",
        "include paper/paper.bib",
        "include paper/paper.md",
        "include paper/README.md",
        "include paper/figures/make_figures.py",
        "recursive-include examples *.py",
        "recursive-include paper/figures *.svg *.png *.pdf",
        "recursive-include tests *.py",
        "prune paper/_build",
        "prune paper/publishing-artifacts",
        "exclude paper/paper.pdf",
        "exclude paper/paper.tex",
        "exclude paper/paper.html",
        "exclude paper/paper.jats",
        "exclude paper/paper.crossref",
        "exclude paper/paper.cff",
        "exclude paper/paper.preprint*",
    }
    assert required_directives <= set(manifest.splitlines())


def test_built_distributions_separate_review_sources_from_runtime():
    ignored_names = {
        ".git",
        ".pytest_cache",
        ".ruff_cache",
        "*.egg-info",
        "__pycache__",
        "build",
        "dist",
        "paper.pdf",
        "paper.tex",
        "paper.html",
        "paper.jats",
        "paper.crossref",
        "paper.cff",
        "paper.preprint*",
        "_build",
        "publishing-artifacts",
    }
    with tempfile.TemporaryDirectory(prefix="ringsentry-package-test-") as temp_dir:
        workspace = Path(temp_dir)
        snapshot = workspace / "source"
        shutil.copytree(
            REPOSITORY_ROOT,
            snapshot,
            ignore=shutil.ignore_patterns(*ignored_names),
        )

        # These ignored build products model files that can be present in a
        # maintainer checkout. MANIFEST.in must keep them out of the sdist.
        (snapshot / "paper" / "paper.pdf").touch()
        (snapshot / "paper" / "paper.tex").touch()
        (snapshot / "paper" / "_build").mkdir()
        (snapshot / "paper" / "_build" / "stale.pdf").touch()
        (snapshot / "paper" / "publishing-artifacts").mkdir()
        (snapshot / "paper" / "publishing-artifacts" / "stale.txt").touch()

        dist = workspace / "dist"
        subprocess.run(
            [
                sys.executable,
                "-m",
                "build",
                "--no-isolation",
                "--outdir",
                str(dist),
                str(snapshot),
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        sdist = next(dist.glob("ringsentry-*.tar.gz"))
        wheel = next(dist.glob("ringsentry-*.whl"))
        prefix = "ringsentry-7.0.0/"

        with tarfile.open(sdist, "r:gz") as archive:
            sdist_members = {member.name.replace("\\", "/") for member in archive}

        with zipfile.ZipFile(wheel) as archive:
            wheel_members = {name.replace("\\", "/") for name in archive.namelist()}
            metadata_name = next(
                name for name in wheel_members if name.endswith(".dist-info/METADATA")
            )
            metadata = archive.read(metadata_name).decode("utf-8")

    required_sdist_members = {
        "CITATION.cff",
        "CODE_OF_CONDUCT.md",
        "CONTRIBUTING.md",
        "LICENSE",
        "PACKAGE_README.md",
        "README.md",
        "SECURITY.md",
        ".zenodo.json",
        "examples/minimal_preprocessing.py",
        "paper/README.md",
        "paper/paper.bib",
        "paper/paper.md",
        "paper/figures/architecture_workflow.pdf",
        "paper/figures/architecture_workflow.png",
        "paper/figures/architecture_workflow.svg",
        "paper/figures/make_figures.py",
        "tests/test_metadata_consistency.py",
        "tests/test_minimal_example.py",
    }
    assert {prefix + member for member in required_sdist_members} <= sdist_members
    assert prefix + "paper/paper.pdf" not in sdist_members
    assert prefix + "paper/paper.tex" not in sdist_members
    assert not any("/paper/_build/" in member for member in sdist_members)
    assert not any("/paper/publishing-artifacts/" in member for member in sdist_members)
    assert not any("/__pycache__/" in member for member in sdist_members)

    assert {"main.py", "core/__init__.py", "gui/__init__.py"} <= wheel_members
    assert any(
        name.endswith((".dist-info/licenses/LICENSE", ".dist-info/LICENSE"))
        for name in wheel_members
    )
    assert not any(
        name.startswith(("assets/", "docs/", "examples/", "paper/", "tests/"))
        for name in wheel_members
    )
    assert "Requires-Python: >=3.8" in metadata
    assert "Description-Content-Type: text/markdown" in metadata
    assert "Classifier: Programming Language :: Python :: 3.13" in metadata
    assert "License: MIT" in metadata
    assert "License-Expression:" not in metadata
    assert "https://github.com/D-sudoasd/ringsentry#readme" in metadata
