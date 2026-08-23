"""Shared planning and filesystem-safety helpers for batch outputs.

The conversion worker is intentionally able to run concurrently.  This module
keeps the output naming and directory checks at one seam so that writers do
not need to know how a batch was assembled.
"""

import os
import re
import stat
import threading
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Tuple

from .utils import get_output_base_name


_OUTPUT_EXTENSIONS = {
    "xycsv": "csv",
    "xydat": "dat",
}


class OutputSafetyError(ValueError):
    """Base error for an output path that cannot be used safely."""


class UnsafeOutputPathError(OutputSafetyError):
    """Raised when an output directory resolves outside its output root."""


class OutputCollisionError(OutputSafetyError):
    """Raised when a batch cannot be assigned unambiguous output names."""


class OutputPlan:
    """Immutable-ish lookup object for paths assigned to a batch.

    Keys are ``(source_path, format_name)`` pairs.  The small public object is
    deliberately independent of the GUI, allowing callers to prepare a plan
    before submitting workers to a thread pool.
    """

    def __init__(self, targets: Mapping[Tuple[Path, str], Path]):
        self._targets = dict(targets)

    def path_for(self, source_path: Path, fmt: str) -> Path:
        """Return the planned output path for one source and format."""
        key = (Path(source_path), str(fmt))
        try:
            return self._targets[key]
        except KeyError as exc:
            raise KeyError(
                f"No output path was planned for {source_path!s} [{fmt}]"
            ) from exc

    def __getitem__(self, key: Tuple[Path, str]) -> Path:
        return self.path_for(key[0], key[1])

    def get(
        self,
        source_path: Path,
        fmt: str,
        default: Optional[Path] = None,
    ) -> Optional[Path]:
        return self._targets.get((Path(source_path), str(fmt)), default)

    def items(self):
        """Expose a read-only-style iterator for diagnostics and adapters."""
        return self._targets.items()

    def paths_for_format(self, fmt: str) -> Tuple[Path, ...]:
        """Return all paths planned for one format.

        This small read-only view lets preflight checks inspect the exact same
        paths that workers will use, including collision disambiguation.
        """
        fmt = str(fmt)
        return tuple(
            path
            for (_source_path, planned_fmt), path in self._targets.items()
            if planned_fmt == fmt
        )

    def existing_paths(self, fmt: Optional[str] = None) -> Tuple[Path, ...]:
        """Return currently existing planned paths, optionally by format."""
        paths = (
            self.paths_for_format(fmt)
            if fmt is not None
            else tuple(self._targets.values())
        )
        return tuple(path for path in paths if path.exists())


def output_extension(fmt: str) -> str:
    """Return the on-disk extension for an output format."""
    return _OUTPUT_EXTENSIONS.get(str(fmt), str(fmt))


def canonical_output_path(
    file_path: Path,
    rel_path: Path,
    outroot: Path,
    fmt: str,
) -> Path:
    """Build the legacy single-input output path without creating it."""
    file_path = Path(file_path)
    rel_path = Path(rel_path)
    outroot = Path(outroot)
    ext = output_extension(fmt)
    return (
        outroot
        / rel_path.parent
        / str(fmt)
        / f"{get_output_base_name(file_path)}.{ext}"
    )


def _normalise_entries(file_entries: Iterable) -> List[Tuple[Path, Path]]:
    entries = []
    for entry in file_entries:
        if isinstance(entry, (tuple, list)) and len(entry) == 2:
            source_path, rel_path = entry
        else:
            source_path = entry
            rel_path = Path(entry).name
        entries.append((Path(source_path), Path(rel_path)))
    return entries


def _path_key(path: Path) -> str:
    try:
        path = path.resolve(strict=False)
    except OSError:
        path = Path(os.path.abspath(str(path)))
    return os.path.normcase(str(path))


def _safe_source_tag(source_path: Path) -> str:
    suffix = Path(source_path).suffix.lstrip(".") or "source"
    tag = re.sub(r"[^A-Za-z0-9_-]+", "_", suffix)
    return tag or "source"


def plan_output_paths(
    file_entries: Iterable,
    outroot: Path,
    formats: Iterable[str],
) -> OutputPlan:
    """Plan all output paths for a batch.

    A single source keeps the historical ``sample.npy`` name.  If two or
    more sources would otherwise target the same output, every member of that
    collision group receives a source-tagged name (for example
    ``sample__edf.npy`` and ``sample__tif.npy``).  Thus neither concurrent
    workers can silently overwrite or skip the other source's result.
    """
    entries = _normalise_entries(file_entries)
    formats = [str(fmt) for fmt in formats]
    targets = {}

    for fmt in formats:
        candidates = []
        for source_path, rel_path in entries:
            path = canonical_output_path(source_path, rel_path, outroot, fmt)
            candidates.append((source_path, rel_path, path))

        groups = {}
        for source_path, rel_path, path in candidates:
            groups.setdefault(_path_key(path), []).append(
                (source_path, rel_path, path)
            )

        # Keep canonical names for non-colliding sources.  Collision-group
        # suffixes are allocated afterwards against this complete set because
        # a generated name can itself be another source's valid base name
        # (for example ``sample__edf.edf``).
        used_paths = set()
        for group in groups.values():
            if len(group) == 1:
                source_path, _rel_path, path = group[0]
                targets[(source_path, fmt)] = path
                used_paths.add(_path_key(path))

        for group in groups.values():
            if len(group) == 1:
                continue

            for source_path, _rel_path, path in group:
                tag = _safe_source_tag(source_path)
                candidate = path.with_name(
                    f"{path.stem}__{tag}{path.suffix}"
                )
                counter = 2
                while _path_key(candidate) in used_paths:
                    candidate = path.with_name(
                        f"{path.stem}__{tag}__{counter}{path.suffix}"
                    )
                    counter += 1
                used_paths.add(_path_key(candidate))
                targets[(source_path, fmt)] = candidate

    return OutputPlan(targets)


# A descriptive alias for callers that prefer the batch terminology.
plan_batch_outputs = plan_output_paths


def _is_reparse_point(path: Path) -> bool:
    """Return whether a path is a symlink, junction, or Windows reparse point."""
    try:
        if path.is_symlink():
            return True
    except OSError:
        return False

    is_junction = getattr(path, "is_junction", None)
    if is_junction is not None:
        try:
            if is_junction():
                return True
        except OSError:
            return False

    if os.name == "nt":
        try:
            attrs = os.lstat(str(path)).st_file_attributes
        except (AttributeError, FileNotFoundError, OSError):
            return False
        return bool(attrs & stat.FILE_ATTRIBUTE_REPARSE_POINT)
    return False


def _path_is_within(path: Path, root: Path) -> bool:
    """Compare absolute paths using platform case rules."""
    try:
        path_text = os.path.normcase(os.path.abspath(str(path)))
        root_text = os.path.normcase(os.path.abspath(str(root)))
        return os.path.commonpath([path_text, root_text]) == root_text
    except (OSError, ValueError):
        return False


def ensure_output_directory(
    outroot: Path,
    relative_parent: Path,
    fmt: str,
) -> Path:
    """Create and validate one format directory under ``outroot``.

    The check is performed before and after directory creation.  A format
    directory may be a link to another location *inside* the output root, but
    links/junctions that resolve outside the root are rejected before any
    output is written.
    """
    root = Path(outroot)
    relative_parent = Path(relative_parent)
    root.mkdir(parents=True, exist_ok=True)
    resolved_root = root.resolve(strict=True)
    format_dir = root / relative_parent / str(fmt)
    resolved_before = format_dir.resolve(strict=False)
    if not _path_is_within(resolved_before, resolved_root):
        raise UnsafeOutputPathError(
            f"Output format directory escapes output root: {format_dir}"
        )

    # Explicitly retain the reason in the error for a pre-existing link.  The
    # containment check above is the authority for both symlinks and junctions.
    if _is_reparse_point(format_dir) and not _path_is_within(
        resolved_before, resolved_root
    ):
        raise UnsafeOutputPathError(
            f"Output format link points outside output root: {format_dir}"
        )

    format_dir.mkdir(parents=True, exist_ok=True)
    resolved_after = format_dir.resolve(strict=True)
    if not _path_is_within(resolved_after, resolved_root):
        raise UnsafeOutputPathError(
            f"Output format directory escapes output root: {format_dir}"
        )
    return format_dir


_RESERVATION_LOCK = threading.RLock()
_RESERVATIONS: Dict[str, str] = {}


def _disambiguated_path(
    path: Path,
    source_path: Path,
    avoid_existing: bool = False,
) -> Path:
    tag = _safe_source_tag(source_path)
    candidate = path.with_name(f"{path.stem}__{tag}{path.suffix}")
    counter = 2
    while True:
        key = _path_key(candidate)
        owner = _RESERVATIONS.get(key)
        if owner is None and not candidate.exists():
            return candidate
        if owner == _path_key(source_path) and not avoid_existing:
            return candidate
        candidate = path.with_name(
            f"{path.stem}__{tag}__{counter}{path.suffix}"
        )
        counter += 1


def reserve_output_path(
    path: Path,
    source_path: Path,
    avoid_existing: bool = False,
) -> Path:
    """Reserve a path for a worker, suffixing collisions when needed.

    ``avoid_existing`` is the no-plan worker fallback for overwrite-enabled
    jobs: once a prior worker has published a path and released its short-lived
    reservation, a later worker receives a disambiguated path instead of
    overwriting that result.
    """
    path = Path(path)
    source_key = _path_key(Path(source_path))
    with _RESERVATION_LOCK:
        key = _path_key(path)
        owner = _RESERVATIONS.get(key)
        if (
            owner is None
            and (not avoid_existing or not path.exists())
        ) or (owner == source_key and not avoid_existing):
            _RESERVATIONS[key] = source_key
            return path
        path = _disambiguated_path(
            path,
            Path(source_path),
            avoid_existing=avoid_existing,
        )
        _RESERVATIONS[_path_key(path)] = source_key
        return path


def release_output_reservation(path: Path, source_path: Path) -> None:
    """Release a worker reservation without touching the final output."""
    key = _path_key(Path(path))
    source_key = _path_key(Path(source_path))
    with _RESERVATION_LOCK:
        if _RESERVATIONS.get(key) == source_key:
            del _RESERVATIONS[key]


def worker_output_path(
    file_path: Path,
    rel_path: Path,
    outroot: Path,
    fmt: str,
    output_plan=None,
    avoid_existing: bool = False,
) -> Path:
    """Resolve a worker output path from a plan or a concurrent reservation."""
    if output_plan is not None:
        if hasattr(output_plan, "path_for"):
            planned = output_plan.path_for(file_path, fmt)
        elif isinstance(output_plan, Mapping):
            planned = output_plan.get((Path(file_path), str(fmt)))
            if planned is None:
                planned = output_plan.get((str(Path(file_path)), str(fmt)))
            if planned is None:
                raise OutputCollisionError(
                    f"Output plan has no path for {file_path!s} [{fmt}]"
                )
        else:
            raise TypeError("output_plan must provide path_for() or be a mapping")
        return Path(planned)
    canonical = canonical_output_path(file_path, rel_path, outroot, fmt)
    return reserve_output_path(
        canonical,
        file_path,
        avoid_existing=avoid_existing,
    )
