#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Research-grade core for safe CBF zero-to-saturation repair.

The core guarantee is strict:
    pixels selected by the target mask are replaced;
    all non-target pixels must remain unchanged.

The module has no GUI dependency. GUI, CLI, and verification utilities all call
these same functions so the behavior is consistent and auditable.
"""

from __future__ import annotations

import csv
import hashlib
import html
import json
import os
import re
import shutil
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Optional, Union

import fabio
import numpy as np


APP_NAME = "CBF Zero2Sat Research Tool"
APP_VERSION = "2.0"
SUPPORTED_EXTENSIONS = (".cbf", ".CBF")
AUTO_OUTPUT_DIR_NAME = "overexposure_corrected"
DUPLICATE_QUARANTINE_DIR_NAME = "duplicate_cbf_quarantine"
DUPLICATE_CBF_SUMMARY_NAME = "duplicate_cbf_summary.csv"
AUTO_PROCESSING_MANIFEST_CSV_NAME = "auto_processing_manifest.csv"
AUTO_PROCESSING_MANIFEST_JSON_NAME = "auto_processing_manifest.json"
PROBLEM_FILES_SUMMARY_NAME = "problem_files_summary.csv"
ORIGINAL_CLEANUP_SUMMARY_NAME = "original_cleanup_summary.csv"
VALIDATION_INDEX_JSON_NAME = "zero2sat_validation_index.json"
VALIDATION_INDEX_CSV_NAME = "zero2sat_validation_index.csv"
VALIDATION_INDEX_SCHEMA_VERSION = 1
AUTO_EXCLUDED_DIR_NAMES = {
    ".git",
    "__pycache__",
    AUTO_OUTPUT_DIR_NAME.lower(),
    DUPLICATE_QUARANTINE_DIR_NAME.lower(),
    "zero2sat_output",
    "cbf_zero2sat_output",
}
COPY_INDEX_RE = re.compile(r"^(?P<base>.+?)\s*[\(\uff08](?P<index>[1-9]\d*)[\)\uff09]$")


@dataclass
class ProjectMetadata:
    project_name: str = ""
    operator: str = ""
    sample: str = ""
    beamline: str = ""
    detector: str = ""
    experiment_date: str = ""
    notes: str = ""


@dataclass
class ProcessConfig:
    input_dir: Path
    output_dir: Path

    # file discovery/output
    recursive: bool = True
    skip_output_dir: bool = True
    preserve_subfolders: bool = True
    suffix: str = "_zero2sat"
    overwrite_output: bool = True
    overwrite_original: bool = False
    backup_before_overwrite: bool = True
    copy_unmodified: bool = False

    # repair definition
    mode: str = "all_zero"  # all_zero | near_bright
    zero_value: int = 0
    replacement_value: int = 32766
    bright_threshold: int = 20000
    radius: int = 3
    minor_zero_pixel_threshold: int = 0

    # safety/reproducibility
    verify_after_write: bool = True
    compute_sha256: bool = False
    use_validation_index: bool = True
    generate_html_report: bool = True
    workers: int = 1
    dry_run: bool = False

    # metadata
    metadata: ProjectMetadata = field(default_factory=ProjectMetadata)

    def normalized(self) -> "ProcessConfig":
        self.input_dir = Path(self.input_dir).expanduser().resolve()
        self.output_dir = Path(self.output_dir).expanduser().resolve()
        self.radius = max(1, int(self.radius))
        self.workers = max(1, int(self.workers))
        self.minor_zero_pixel_threshold = max(0, int(self.minor_zero_pixel_threshold))
        return self


@dataclass
class FileResult:
    input_file: str
    relative_path: str = ""
    output_file: str = ""
    status: str = ""  # scan, repaired_verified, repaired_unverified, dry_run, no_repair_needed, copied_unmodified, output_exists, error

    total_pixels: int = 0
    zero_pixels: int = 0
    target_pixels: int = 0
    ignored_zero_pixels: int = 0
    replaced_pixels: int = 0
    target_fraction_percent: float = 0.0

    nontarget_changed_before_write: int = 0
    target_not_replaced_before_write: int = 0
    readback_different_pixels: int = 0
    readback_nontarget_different_pixels: int = 0
    output_content_verified: bool = False

    min_before: Optional[float] = None
    max_before: Optional[float] = None
    mean_before: Optional[float] = None
    min_after: Optional[float] = None
    max_after: Optional[float] = None
    mean_after: Optional[float] = None

    dtype_before: str = ""
    dtype_after: str = ""
    shape_before: str = ""
    shape_after: str = ""

    original_sha256: str = ""
    output_sha256: str = ""
    elapsed_s: float = 0.0
    warning: str = ""
    error: str = ""


@dataclass
class BatchSummary:
    total_files: int = 0
    repaired: int = 0
    verified: int = 0
    dry_run_files: int = 0
    no_repair_needed: int = 0
    copied_unmodified: int = 0
    output_exists: int = 0
    errors: int = 0
    total_zero_pixels: int = 0
    total_target_pixels: int = 0
    ignored_zero_pixels: int = 0
    total_replaced_pixels: int = 0
    nontarget_changed_before_write: int = 0
    readback_different_pixels: int = 0
    readback_nontarget_different_pixels: int = 0
    csv_path: str = ""
    html_path: str = ""
    config_path: str = ""


@dataclass
class AutoDirectoryResult:
    data_dir: str
    output_dir: str = ""
    status: str = ""  # repaired | skipped_no_overexposure | error
    total_files: int = 0
    overexposed_files: int = 0
    total_target_pixels: int = 0
    ignored_zero_pixels: int = 0
    repaired_files: int = 0
    copied_unmodified: int = 0
    errors: int = 0
    csv_path: str = ""
    html_path: str = ""
    config_path: str = ""
    error: str = ""


@dataclass
class DuplicateCbfResult:
    data_dir: str
    original_file: str = ""
    duplicate_file: str = ""
    action: str = ""  # ready_to_quarantine | moved_to_quarantine | report_only | quarantine_failed
    status: str = ""  # duplicate_confirmed | quarantined | name_pattern_hash_mismatch | orphan_duplicate_name | error
    size_bytes: int = 0
    original_sha256: str = ""
    duplicate_sha256: str = ""
    quarantine_path: str = ""
    error: str = ""


@dataclass
class AutoProcessingDirectoryResult:
    data_dir: str
    status: str = ""  # clean_original_usable | duplicates_quarantined_original_usable | overexposure_corrected_usable | already_corrected_usable | corrected_usable_original_cleaned | corrected_only_original_absent | needs_review | failed
    recommended_data_dir: str = ""
    total_files: int = 0
    duplicate_candidates: int = 0
    duplicates_quarantined: int = 0
    duplicate_problem_files: int = 0
    overexposed_files: int = 0
    total_target_pixels: int = 0
    ignored_zero_pixels: int = 0
    repaired_files: int = 0
    copied_unmodified: int = 0
    problem_files: int = 0
    overexposure_output_dir: str = ""
    duplicate_quarantine_dir: str = ""
    corrected_validation_status: str = ""
    cleanup_status: str = ""
    validation_mode: str = ""
    index_status: str = ""
    index_path: str = ""
    cleanup_eligible_reason: str = ""
    strict_validation_elapsed_s: float = 0.0
    fast_path_elapsed_s: float = 0.0
    original_files_deleted: int = 0
    original_bytes_deleted: int = 0
    error: str = ""
    notes: str = ""


@dataclass
class ProblemFileResult:
    data_dir: str
    file_path: str = ""
    stage: str = ""
    status: str = ""
    action: str = ""
    size_bytes: int = 0
    original_file: str = ""
    quarantine_path: str = ""
    error: str = ""


@dataclass
class CorrectedOutputEvaluation:
    data_dir: str
    output_dir: str
    status: str = ""  # valid_corrected_output | corrected_only_original_absent | missing_output | no_output_files | name_mismatch | pixel_validation_failed | read_error
    original_files: int = 0
    output_files: int = 0
    files_checked: int = 0
    missing_in_output: int = 0
    extra_in_output: int = 0
    total_target_pixels: int = 0
    ignored_zero_pixels: int = 0
    bytes_eligible_for_cleanup: int = 0
    validation_mode: str = ""
    index_status: str = ""
    index_path: str = ""
    cleanup_eligible_reason: str = ""
    strict_validation_elapsed_s: float = 0.0
    fast_path_elapsed_s: float = 0.0
    error: str = ""


@dataclass
class OriginalCleanupResult:
    data_dir: str
    output_dir: str = ""
    action: str = ""  # detect_only | delete_original_cbf
    status: str = ""  # ready_to_delete | deleted | already_cleaned | skipped_no_output | skipped_needs_review | delete_failed | error
    corrected_validation_status: str = ""
    original_files: int = 0
    output_files: int = 0
    files_checked: int = 0
    files_deleted: int = 0
    bytes_eligible_for_cleanup: int = 0
    bytes_deleted: int = 0
    recommended_data_dir: str = ""
    validation_mode: str = ""
    index_status: str = ""
    index_path: str = ""
    cleanup_eligible_reason: str = ""
    strict_validation_elapsed_s: float = 0.0
    fast_path_elapsed_s: float = 0.0
    error: str = ""


def config_to_dict(cfg: ProcessConfig) -> dict:
    d = asdict(cfg)
    d["input_dir"] = str(cfg.input_dir)
    d["output_dir"] = str(cfg.output_dir)
    return d


def config_from_dict(d: dict) -> ProcessConfig:
    meta_d = d.get("metadata") or {}
    meta = ProjectMetadata(**{k: meta_d.get(k, "") for k in ProjectMetadata.__dataclass_fields__.keys()})
    kwargs = dict(d)
    kwargs["input_dir"] = Path(kwargs.get("input_dir", ""))
    kwargs["output_dir"] = Path(kwargs.get("output_dir", ""))
    kwargs["metadata"] = meta
    allowed = set(ProcessConfig.__dataclass_fields__.keys())
    kwargs = {k: v for k, v in kwargs.items() if k in allowed}
    return ProcessConfig(**kwargs).normalized()


def repair_rules_dict(cfg: ProcessConfig) -> dict:
    """Rules that define pixel-selection and replacement semantics."""
    return {
        "mode": cfg.mode,
        "zero_value": int(cfg.zero_value),
        "replacement_value": int(cfg.replacement_value),
        "bright_threshold": int(cfg.bright_threshold),
        "radius": int(cfg.radius),
        "minor_zero_pixel_threshold": int(cfg.minor_zero_pixel_threshold),
    }


def repair_config_hash(cfg: ProcessConfig) -> str:
    payload = json.dumps(repair_rules_dict(cfg), sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def file_stat_signature(path: Path) -> dict[str, int]:
    st = Path(path).stat()
    return {
        "size_bytes": int(st.st_size),
        "mtime_ns": int(st.st_mtime_ns),
    }


def validation_index_paths(output_dir: Path) -> tuple[Path, Path]:
    output_dir = Path(output_dir)
    return output_dir / VALIDATION_INDEX_JSON_NAME, output_dir / VALIDATION_INDEX_CSV_NAME


def load_validation_index(output_dir: Path) -> tuple[Optional[dict], str, str]:
    json_path, _csv_path = validation_index_paths(output_dir)
    if not json_path.exists():
        return None, "missing", f"Missing validation index: {json_path}"
    try:
        with json_path.open("r", encoding="utf-8") as f:
            index = json.load(f)
    except Exception as exc:
        return None, "read_error", str(exc)
    return index, "loaded", ""


def write_validation_index(data_dir: Path, output_dir: Path, cfg: ProcessConfig,
                           records: list[dict], validation_mode: str,
                           trusted_for_cleanup: bool) -> tuple[Path, Path]:
    output_dir = Path(output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path, csv_path = validation_index_paths(output_dir)
    index = {
        "schema_version": VALIDATION_INDEX_SCHEMA_VERSION,
        "app_name": APP_NAME,
        "app_version": APP_VERSION,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "data_dir": str(Path(data_dir).expanduser().resolve()),
        "output_dir": str(output_dir),
        "config_hash": repair_config_hash(cfg),
        "repair_rules": repair_rules_dict(cfg),
        "validation_mode": validation_mode,
        "trusted_for_cleanup": bool(trusted_for_cleanup),
        "records": records,
    }
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(index, f, indent=2, ensure_ascii=False)

    fieldnames = [
        "original_name", "output_name",
        "original_size_bytes", "original_mtime_ns",
        "output_size_bytes", "output_mtime_ns",
        "shape", "dtype", "zero_pixels", "target_pixels",
        "ignored_zero_pixels", "replacement_value",
        "status", "readback_validation_passed",
        "non_target_diff", "target_bad",
        "validation_mode", "config_hash",
    ]
    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            row = {name: record.get(name, "") for name in fieldnames}
            row["validation_mode"] = validation_mode
            row["config_hash"] = index["config_hash"]
            writer.writerow(row)
    return json_path, csv_path


def validation_record_from_file_result(data_dir: Path, output_dir: Path, cfg: ProcessConfig,
                                       result: FileResult) -> Optional[dict]:
    if not result.output_file or result.status not in {"repaired_verified", "repaired_unverified", "copied_unmodified"}:
        return None
    original_path = Path(result.input_file).expanduser().resolve()
    output_path = Path(result.output_file).expanduser().resolve()
    if not original_path.exists() or not output_path.exists():
        return None
    original_stat = file_stat_signature(original_path)
    output_stat = file_stat_signature(output_path)
    return {
        "original_name": original_path.name,
        "output_name": output_path.name,
        "original_size_bytes": original_stat["size_bytes"],
        "original_mtime_ns": original_stat["mtime_ns"],
        "output_size_bytes": output_stat["size_bytes"],
        "output_mtime_ns": output_stat["mtime_ns"],
        "shape": result.shape_before or result.shape_after,
        "dtype": result.dtype_before or result.dtype_after,
        "zero_pixels": int(result.zero_pixels),
        "target_pixels": int(result.target_pixels),
        "ignored_zero_pixels": int(result.ignored_zero_pixels),
        "replacement_value": int(cfg.replacement_value),
        "status": result.status,
        "readback_validation_passed": (
            result.status == "repaired_verified"
            and result.output_content_verified
            and result.nontarget_changed_before_write == 0
            and result.target_not_replaced_before_write == 0
            and result.readback_different_pixels == 0
            and result.readback_nontarget_different_pixels == 0
        ) or (
            result.status == "copied_unmodified"
            and result.output_content_verified
            and result.readback_different_pixels == 0
            and result.readback_nontarget_different_pixels == 0
        ),
        "non_target_diff": int(result.readback_nontarget_different_pixels),
        "target_bad": int(result.target_not_replaced_before_write),
    }


def validation_index_trusted_from_records(data_dir: Path, cfg: ProcessConfig,
                                          records: list[dict]) -> bool:
    if not cfg.verify_after_write:
        return False
    original_names = {p.name for p in direct_cbf_files(data_dir)}
    record_names = {str(r.get("original_name", "")) for r in records}
    if not original_names or record_names != original_names:
        return False
    return all(bool(r.get("readback_validation_passed")) for r in records)


def write_validation_index_from_results(data_dir: Path, output_dir: Path, cfg: ProcessConfig,
                                        results: Iterable[FileResult],
                                        trusted_for_cleanup: Optional[bool] = None,
                                        validation_mode: str = "process_write") -> Optional[Path]:
    records = []
    for result in results:
        record = validation_record_from_file_result(data_dir, output_dir, cfg, result)
        if record is not None:
            records.append(record)
    if not records:
        return None
    if trusted_for_cleanup is None:
        trusted_for_cleanup = validation_index_trusted_from_records(data_dir, cfg, records)
    json_path, _csv_path = write_validation_index(
        data_dir, output_dir, cfg, records,
        validation_mode=validation_mode,
        trusted_for_cleanup=trusted_for_cleanup,
    )
    return json_path


def save_config_json(cfg: ProcessConfig, output_dir: Path, prefix: str = "cbf_zero2sat_config") -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    path = output_dir / f"{prefix}_{timestamp}.json"
    with path.open("w", encoding="utf-8") as f:
        json.dump(config_to_dict(cfg), f, indent=2, ensure_ascii=False)
    return path


def load_config_json(path: Path) -> ProcessConfig:
    with Path(path).open("r", encoding="utf-8") as f:
        return config_from_dict(json.load(f))


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def iter_cbf_files(input_dir: Path, output_dir: Path, recursive: bool = True, skip_output_dir: bool = True) -> list[Path]:
    input_dir = Path(input_dir).expanduser().resolve()
    output_dir = Path(output_dir).expanduser().resolve()
    patterns = ["**/*.cbf", "**/*.CBF"] if recursive else ["*.cbf", "*.CBF"]
    files: list[Path] = []
    for pattern in patterns:
        files.extend(input_dir.glob(pattern))
    unique = sorted(set(p.resolve() for p in files if p.is_file()))
    if skip_output_dir and output_dir.exists():
        unique = [p for p in unique if not is_relative_to(p, output_dir)]
    # Avoid processing backup and temporary files created by this tool.
    unique = [p for p in unique if ".tmp_zero2sat_" not in p.name and not p.name.endswith(".bak_zero2sat_original")]
    return unique


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def read_image_data(path: Path):
    image = fabio.open(str(path))
    data = np.asarray(image.data)
    if data.size == 0:
        raise ValueError("Detector matrix is empty.")
    if not np.issubdtype(data.dtype, np.number):
        raise ValueError(f"Detector matrix is not numeric: dtype={data.dtype}.")
    return image, data


def dtype_can_hold_value(dtype, value: Union[int, float]) -> bool:
    if np.issubdtype(dtype, np.integer):
        info = np.iinfo(dtype)
        return info.min <= int(value) <= info.max
    if np.issubdtype(dtype, np.floating):
        return np.isfinite(float(value))
    return False


def replacement_for_dtype(dtype, value: Union[int, float]):
    if not dtype_can_hold_value(dtype, value):
        raise ValueError(f"Replacement value {value} is outside dtype range for {dtype}.")
    if np.issubdtype(dtype, np.integer):
        return int(value)
    return float(value)


def array_stats(data) -> tuple[float, float, float, str, str]:
    return (
        float(np.min(data)),
        float(np.max(data)),
        float(np.mean(data)),
        str(data.dtype),
        str(tuple(data.shape)),
    )


def near_bright_mask(data, zero_mask, bright_threshold: int, radius: int):
    if data.ndim != 2:
        raise ValueError("near_bright mode requires a 2D detector image.")
    bright = data >= bright_threshold
    near = np.zeros(data.shape, dtype=bool)
    h, w = data.shape
    r = max(1, int(radius))

    for dy in range(-r, r + 1):
        if dy < 0:
            src_y, dst_y = slice(-dy, h), slice(0, h + dy)
        elif dy > 0:
            src_y, dst_y = slice(0, h - dy), slice(dy, h)
        else:
            src_y = dst_y = slice(0, h)
        for dx in range(-r, r + 1):
            if dx < 0:
                src_x, dst_x = slice(-dx, w), slice(0, w + dx)
            elif dx > 0:
                src_x, dst_x = slice(0, w - dx), slice(dx, w)
            else:
                src_x = dst_x = slice(0, w)
            near[dst_y, dst_x] |= bright[src_y, src_x]
    return zero_mask & near


def make_target_mask(data, cfg: ProcessConfig):
    zero_mask = data == cfg.zero_value
    if cfg.mode == "all_zero":
        return zero_mask, zero_mask
    if cfg.mode == "near_bright":
        return zero_mask, near_bright_mask(data, zero_mask, cfg.bright_threshold, cfg.radius)
    raise ValueError(f"Unknown mode: {cfg.mode}")


def apply_minor_zero_threshold(target_mask, cfg: ProcessConfig) -> tuple[np.ndarray, int]:
    """Return actionable target mask and ignored target-pixel count."""
    target_count = int(np.count_nonzero(target_mask))
    if target_count and target_count <= cfg.minor_zero_pixel_threshold:
        return np.zeros_like(target_mask, dtype=bool), target_count
    return target_mask, 0


def count_differences(a, b) -> int:
    if a.shape != b.shape:
        return int(max(a.size, b.size))
    return int(np.count_nonzero(a != b))


def count_masked_differences(a, b, mask) -> int:
    if a.shape != b.shape:
        return int(max(a.size, b.size))
    return int(np.count_nonzero(a[mask] != b[mask]))


def output_path_for(src: Path, cfg: ProcessConfig) -> Path:
    if cfg.overwrite_original:
        return src
    if cfg.preserve_subfolders:
        rel = src.resolve().relative_to(cfg.input_dir.resolve())
        out = cfg.output_dir / rel
    else:
        out = cfg.output_dir / src.name
    suffix = cfg.suffix.strip()
    if suffix:
        out = out.with_name(out.stem + suffix + out.suffix)
    if out.resolve() == src.resolve():
        raise ValueError("Output path equals input path. Choose another output folder/suffix or enable overwrite_original explicitly.")
    out.parent.mkdir(parents=True, exist_ok=True)
    return out


def temporary_path_for(final_path: Path) -> Path:
    timestamp = time.strftime("%Y%m%d%H%M%S")
    return final_path.with_name(f".{final_path.name}.tmp_zero2sat_{os.getpid()}_{timestamp}.cbf")


def validate_repaired_matrix(original, repaired, target_mask, effective_replacement) -> tuple[int, int]:
    if original.shape != repaired.shape:
        raise ValueError("Shape changed during repair.")
    if original.dtype != repaired.dtype:
        raise ValueError("Dtype changed during repair.")
    non_target = ~target_mask
    nontarget_changed = count_masked_differences(original, repaired, non_target)
    target_not_replaced = int(np.count_nonzero(repaired[target_mask] != effective_replacement))
    return nontarget_changed, target_not_replaced


def validate_readback(path: Path, expected, original, target_mask) -> tuple[int, int]:
    _, readback = read_image_data(path)
    total_diff = count_differences(expected, readback)
    if original.shape == readback.shape:
        non_target = ~target_mask
        nontarget_diff = count_masked_differences(original, readback, non_target)
    else:
        nontarget_diff = total_diff
    return total_diff, nontarget_diff


def write_repaired(image, repaired, final_path: Path, cfg: ProcessConfig, original_path: Path, original, target_mask) -> tuple[str, int, int]:
    final_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = temporary_path_for(final_path)

    if final_path.exists() and not cfg.overwrite_output and not cfg.overwrite_original:
        raise FileExistsError(f"Output exists: {final_path}")

    image.data = repaired
    image.write(str(tmp_path))

    if cfg.verify_after_write:
        tmp_diff, tmp_non_target_diff = validate_readback(tmp_path, repaired, original, target_mask)
        if tmp_diff != 0 or tmp_non_target_diff != 0:
            try:
                tmp_path.unlink()
            except OSError:
                pass
            raise RuntimeError(f"Temporary readback failed: total_diff={tmp_diff}, non_target_diff={tmp_non_target_diff}.")

    backup_path = None
    if cfg.overwrite_original and cfg.backup_before_overwrite:
        backup_path = original_path.with_name(original_path.name + ".bak_zero2sat_original")
        shutil.copy2(original_path, backup_path)

    os.replace(tmp_path, final_path)

    if cfg.verify_after_write:
        final_diff, final_non_target_diff = validate_readback(final_path, repaired, original, target_mask)
        if final_diff != 0 or final_non_target_diff != 0:
            if cfg.overwrite_original and backup_path and backup_path.exists():
                shutil.copy2(backup_path, original_path)
            else:
                try:
                    final_path.unlink()
                except OSError:
                    pass
            raise RuntimeError(f"Final readback failed: total_diff={final_diff}, non_target_diff={final_non_target_diff}.")
        return str(final_path), final_diff, final_non_target_diff
    return str(final_path), 0, 0


def init_result(src: Path, cfg: ProcessConfig) -> FileResult:
    try:
        rel = str(src.resolve().relative_to(cfg.input_dir.resolve()))
    except Exception:
        rel = src.name
    return FileResult(input_file=str(src), relative_path=rel)


def scan_file(src: Path, cfg: ProcessConfig) -> FileResult:
    start = time.time()
    result = init_result(src, cfg)
    result.status = "scan"
    try:
        _, data = read_image_data(src)
        result.total_pixels = int(data.size)
        result.min_before, result.max_before, result.mean_before, result.dtype_before, result.shape_before = array_stats(data)
        result.min_after = result.min_before
        result.max_after = result.max_before
        result.mean_after = result.mean_before
        result.dtype_after = result.dtype_before
        result.shape_after = result.shape_before
        zero_mask, target_mask = make_target_mask(data, cfg)
        result.zero_pixels = int(np.count_nonzero(zero_mask))
        target_mask, result.ignored_zero_pixels = apply_minor_zero_threshold(target_mask, cfg)
        result.target_pixels = int(np.count_nonzero(target_mask))
        result.replaced_pixels = result.target_pixels
        result.target_fraction_percent = round(100.0 * result.target_pixels / result.total_pixels, 6)
        if result.ignored_zero_pixels:
            result.status = "minor_zero_ignored"
        if cfg.compute_sha256:
            result.original_sha256 = sha256_file(src)
    except Exception as exc:
        result.status = "error"
        result.error = f"{exc}\n{traceback.format_exc(limit=8)}"
    result.elapsed_s = round(time.time() - start, 4)
    return result


def process_file(src: Path, cfg: ProcessConfig) -> FileResult:
    start = time.time()
    result = init_result(src, cfg)
    try:
        if cfg.compute_sha256:
            result.original_sha256 = sha256_file(src)

        image, original = read_image_data(src)
        result.total_pixels = int(original.size)
        result.min_before, result.max_before, result.mean_before, result.dtype_before, result.shape_before = array_stats(original)

        effective_replacement = replacement_for_dtype(original.dtype, cfg.replacement_value)
        zero_mask, target_mask = make_target_mask(original, cfg)
        result.zero_pixels = int(np.count_nonzero(zero_mask))
        target_mask, result.ignored_zero_pixels = apply_minor_zero_threshold(target_mask, cfg)
        result.target_pixels = int(np.count_nonzero(target_mask))
        result.replaced_pixels = result.target_pixels
        result.target_fraction_percent = round(100.0 * result.target_pixels / result.total_pixels, 6)

        final_path = output_path_for(src, cfg)
        result.output_file = str(final_path)

        if result.target_pixels == 0:
            result.status = "minor_zero_ignored" if result.ignored_zero_pixels else "no_repair_needed"
            result.min_after = result.min_before
            result.max_after = result.max_before
            result.mean_after = result.mean_before
            result.dtype_after = result.dtype_before
            result.shape_after = result.shape_before
            if cfg.copy_unmodified and not cfg.overwrite_original:
                if final_path.exists() and not cfg.overwrite_output:
                    result.status = "output_exists"
                    return result
                final_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, final_path)
                if cfg.compute_sha256:
                    if not result.original_sha256:
                        result.original_sha256 = sha256_file(src)
                    result.output_sha256 = sha256_file(final_path)
                    result.output_content_verified = result.original_sha256 == result.output_sha256
                result.status = "copied_unmodified"
            return result

        repaired = original.copy()
        repaired[target_mask] = effective_replacement
        result.min_after, result.max_after, result.mean_after, result.dtype_after, result.shape_after = array_stats(repaired)

        nontarget_changed, target_not_replaced = validate_repaired_matrix(original, repaired, target_mask, effective_replacement)
        result.nontarget_changed_before_write = nontarget_changed
        result.target_not_replaced_before_write = target_not_replaced
        if nontarget_changed != 0:
            raise RuntimeError(f"Pre-write validation failed: {nontarget_changed} non-target pixels changed.")
        if target_not_replaced != 0:
            raise RuntimeError(f"Pre-write validation failed: {target_not_replaced} target pixels were not replaced.")

        if cfg.dry_run:
            result.status = "dry_run"
            return result

        result.output_file, result.readback_different_pixels, result.readback_nontarget_different_pixels = write_repaired(
            image=image,
            repaired=repaired,
            final_path=final_path,
            cfg=cfg,
            original_path=src,
            original=original,
            target_mask=target_mask,
        )
        if cfg.compute_sha256 and result.output_file:
            result.output_sha256 = sha256_file(Path(result.output_file))

        result.status = "repaired_verified" if cfg.verify_after_write else "repaired_unverified"
        result.output_content_verified = (
            result.status == "repaired_verified"
            and result.readback_different_pixels == 0
            and result.readback_nontarget_different_pixels == 0
        )
    except FileExistsError as exc:
        result.status = "output_exists"
        result.error = str(exc)
    except Exception as exc:
        result.status = "error"
        result.error = f"{exc}\n{traceback.format_exc(limit=8)}"
    result.elapsed_s = round(time.time() - start, 4)
    return result


def result_fieldnames() -> list[str]:
    return list(asdict(FileResult(input_file="")).keys())


def write_summary_csv(results: Iterable[FileResult], output_dir: Path, prefix: str = "cbf_zero2sat") -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    path = output_dir / f"{prefix}_summary_{timestamp}.csv"
    rows = [asdict(r) for r in results]
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=result_fieldnames())
        writer.writeheader()
        writer.writerows(rows)
    return path


def summarize_results(results: Iterable[FileResult]) -> BatchSummary:
    results = list(results)
    return BatchSummary(
        total_files=len(results),
        repaired=sum(1 for r in results if r.status in ("repaired_verified", "repaired_unverified")),
        verified=sum(1 for r in results if r.status == "repaired_verified"),
        dry_run_files=sum(1 for r in results if r.status == "dry_run"),
        no_repair_needed=sum(1 for r in results if r.status in ("no_repair_needed", "minor_zero_ignored")),
        copied_unmodified=sum(1 for r in results if r.status == "copied_unmodified"),
        output_exists=sum(1 for r in results if r.status == "output_exists"),
        errors=sum(1 for r in results if r.status == "error"),
        total_zero_pixels=sum(r.zero_pixels for r in results),
        total_target_pixels=sum(r.target_pixels for r in results),
        ignored_zero_pixels=sum(r.ignored_zero_pixels for r in results),
        total_replaced_pixels=sum(r.replaced_pixels for r in results if r.status in ("repaired_verified", "repaired_unverified", "dry_run")),
        nontarget_changed_before_write=sum(r.nontarget_changed_before_write for r in results),
        readback_different_pixels=sum(r.readback_different_pixels for r in results),
        readback_nontarget_different_pixels=sum(r.readback_nontarget_different_pixels for r in results),
    )


def write_html_report(results: Iterable[FileResult], cfg: ProcessConfig, output_dir: Path, prefix: str = "cbf_zero2sat") -> Path:
    results = list(results)
    summary = summarize_results(results)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    path = output_dir / f"{prefix}_report_{timestamp}.html"

    rows = sorted(results, key=lambda r: (-r.target_pixels, r.relative_path))
    top_rows = rows[:200]
    status_counts = {}
    for r in results:
        status_counts[r.status] = status_counts.get(r.status, 0) + 1

    def esc(x):
        return html.escape(str(x))

    metadata = asdict(cfg.metadata)
    status_html = "".join(f"<li><b>{esc(k)}</b>: {v}</li>" for k, v in sorted(status_counts.items()))
    meta_html = "".join(f"<tr><th>{esc(k)}</th><td>{esc(v)}</td></tr>" for k, v in metadata.items() if v)
    if not meta_html:
        meta_html = "<tr><td colspan='2'>No project metadata entered.</td></tr>"

    table_rows = []
    for r in top_rows:
        safe = (
            r.status in ("repaired_verified", "scan", "dry_run", "no_repair_needed", "minor_zero_ignored", "copied_unmodified")
            and r.nontarget_changed_before_write == 0
            and r.target_not_replaced_before_write == 0
            and r.readback_nontarget_different_pixels == 0
        )
        table_rows.append(
            "<tr>"
            f"<td>{esc(r.relative_path)}</td>"
            f"<td>{esc(r.status)}</td>"
            f"<td>{r.zero_pixels}</td>"
            f"<td>{r.target_pixels}</td>"
            f"<td>{r.ignored_zero_pixels}</td>"
            f"<td>{r.target_fraction_percent}</td>"
            f"<td>{esc(r.dtype_before)}</td>"
            f"<td>{esc(r.shape_before)}</td>"
            f"<td>{r.max_before}</td>"
            f"<td>{'PASS' if safe else 'CHECK'}</td>"
            f"<td>{esc((r.error or r.warning)[:180])}</td>"
            "</tr>"
        )

    html_doc = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>CBF Zero2Sat QC Report</title>
<style>
body {{ font-family: Arial, sans-serif; margin: 28px; color: #222; }}
h1, h2 {{ color: #123; }}
.grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 16px 0; }}
.card {{ border: 1px solid #ddd; border-radius: 10px; padding: 12px; background: #fafafa; }}
.card .num {{ font-size: 1.5em; font-weight: 700; }}
table {{ border-collapse: collapse; width: 100%; margin: 12px 0; font-size: 13px; }}
th, td {{ border: 1px solid #ddd; padding: 6px 8px; vertical-align: top; }}
th {{ background: #f0f3f7; text-align: left; }}
code {{ background: #f5f5f5; padding: 1px 4px; border-radius: 4px; }}
.warn {{ color: #9a4b00; }}
.ok {{ color: #116611; }}
</style>
</head>
<body>
<h1>CBF Zero2Sat QC Report</h1>
<p>Generated by <b>{APP_NAME} v{APP_VERSION}</b> at {esc(time.strftime('%Y-%m-%d %H:%M:%S'))}.</p>

<h2>Project metadata</h2>
<table>{meta_html}</table>

<h2>Batch summary</h2>
<div class="grid">
<div class="card"><div>Total files</div><div class="num">{summary.total_files}</div></div>
<div class="card"><div>Repaired</div><div class="num">{summary.repaired}</div></div>
<div class="card"><div>Verified</div><div class="num">{summary.verified}</div></div>
<div class="card"><div>Errors</div><div class="num">{summary.errors}</div></div>
<div class="card"><div>Zero pixels</div><div class="num">{summary.total_zero_pixels}</div></div>
<div class="card"><div>Target pixels</div><div class="num">{summary.total_target_pixels}</div></div>
<div class="card"><div>Ignored minor zeros</div><div class="num">{summary.ignored_zero_pixels}</div></div>
<div class="card"><div>Replaced pixels</div><div class="num">{summary.total_replaced_pixels}</div></div>
<div class="card"><div>Readback non-target diffs</div><div class="num">{summary.readback_nontarget_different_pixels}</div></div>
</div>

<h2>Safety criteria</h2>
<p class="ok">A repaired file is considered safe when <code>status=repaired_verified</code>, <code>nontarget_changed_before_write=0</code>, <code>target_not_replaced_before_write=0</code>, <code>readback_different_pixels=0</code>, and <code>readback_nontarget_different_pixels=0</code>.</p>
<p class="warn">This tool does not recover true saturated intensity. It replaces erroneous zero pixels with the configured saturation value.</p>

<h2>Configuration</h2>
<table>
<tr><th>Input</th><td>{esc(cfg.input_dir)}</td></tr>
<tr><th>Output</th><td>{esc(cfg.output_dir)}</td></tr>
<tr><th>Mode</th><td>{esc(cfg.mode)}</td></tr>
<tr><th>Zero value</th><td>{cfg.zero_value}</td></tr>
<tr><th>Replacement value</th><td>{cfg.replacement_value}</td></tr>
<tr><th>Minor zero threshold</th><td>{cfg.minor_zero_pixel_threshold}</td></tr>
<tr><th>Verify after write</th><td>{cfg.verify_after_write}</td></tr>
<tr><th>SHA256</th><td>{cfg.compute_sha256}</td></tr>
<tr><th>Workers</th><td>{cfg.workers}</td></tr>
</table>

<h2>Status counts</h2>
<ul>{status_html}</ul>

<h2>Top files by target-pixel count</h2>
<table>
<tr><th>Relative path</th><th>Status</th><th>Zero pixels</th><th>Target pixels</th><th>Ignored minor zeros</th><th>Target %</th><th>Dtype</th><th>Shape</th><th>Max before</th><th>Safety</th><th>Message</th></tr>
{''.join(table_rows)}
</table>
</body>
</html>
"""
    path.write_text(html_doc, encoding="utf-8")
    return path


def run_batch(
    cfg: ProcessConfig,
    action: str = "repair",
    progress_callback: Optional[Callable[[int, int, FileResult], None]] = None,
    cancel_event=None,
) -> tuple[list[FileResult], BatchSummary]:
    cfg = cfg.normalized()
    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    files = iter_cbf_files(cfg.input_dir, cfg.output_dir, cfg.recursive, cfg.skip_output_dir)
    total = len(files)

    func = scan_file if action == "scan" else process_file
    results: list[FileResult] = []

    if cfg.workers <= 1 or total <= 1:
        for i, src in enumerate(files, 1):
            if cancel_event is not None and cancel_event.is_set():
                break
            r = func(src, cfg)
            results.append(r)
            if progress_callback:
                progress_callback(i, total, r)
            if cancel_event is not None and cancel_event.is_set():
                break
    else:
        done = 0
        with ThreadPoolExecutor(max_workers=cfg.workers) as ex:
            future_to_src = {}
            for src in files:
                if cancel_event is not None and cancel_event.is_set():
                    break
                future_to_src[ex.submit(func, src, cfg)] = src
            for fut in as_completed(future_to_src):
                r = fut.result()
                results.append(r)
                done += 1
                if progress_callback:
                    progress_callback(done, total, r)
                if cancel_event is not None and cancel_event.is_set():
                    for pending in future_to_src:
                        if not pending.done():
                            pending.cancel()
                    break
        results.sort(key=lambda r: r.relative_path)

    prefix = "cbf_zero2sat_scan" if action == "scan" else ("cbf_zero2sat_dryrun" if cfg.dry_run else "cbf_zero2sat_repair")
    csv_path = write_summary_csv(results, cfg.output_dir, prefix=prefix)
    config_path = save_config_json(cfg, cfg.output_dir, prefix=prefix + "_config")
    html_path = ""
    if cfg.generate_html_report:
        html_path = str(write_html_report(results, cfg, cfg.output_dir, prefix=prefix))

    summary = summarize_results(results)
    summary.csv_path = str(csv_path)
    summary.config_path = str(config_path)
    summary.html_path = html_path
    return results, summary


def direct_cbf_files(directory: Path) -> list[Path]:
    directory = Path(directory)
    files: list[Path] = []
    for suffix in SUPPORTED_EXTENSIONS:
        files.extend(directory.glob(f"*{suffix}"))
    return sorted(set(p.resolve() for p in files if p.is_file()))


def parse_duplicate_copy_name(path: Path) -> Optional[tuple[str, int]]:
    match = COPY_INDEX_RE.match(Path(path).stem)
    if not match:
        return None
    base = match.group("base").rstrip()
    if not base:
        return None
    return base, int(match.group("index"))


def discover_cbf_data_dirs(root: Path, excluded_names: Optional[Iterable[str]] = None) -> list[Path]:
    root = Path(root).expanduser().resolve()
    excluded = {name.lower() for name in AUTO_EXCLUDED_DIR_NAMES}
    if excluded_names:
        excluded.update(str(name).lower() for name in excluded_names)

    data_dirs: list[Path] = []
    for cur, dirs, _files in os.walk(root):
        dirs[:] = [
            d for d in dirs
            if not d.startswith(".")
            and d.lower() not in excluded
            and ".tmp_zero2sat_" not in d
        ]
        cur_path = Path(cur)
        if direct_cbf_files(cur_path):
            data_dirs.append(cur_path.resolve())
    return sorted(set(data_dirs))


def discover_cbf_data_dirs_with_corrected_parents(root: Path, excluded_names: Optional[Iterable[str]] = None) -> list[Path]:
    """Find raw CBF data dirs plus parents that only contain an auto-corrected output dir."""
    root = Path(root).expanduser().resolve()
    excluded = {name.lower() for name in AUTO_EXCLUDED_DIR_NAMES}
    if excluded_names:
        excluded.update(str(name).lower() for name in excluded_names)

    data_dirs: set[Path] = set(discover_cbf_data_dirs(root, excluded_names=excluded_names))
    for cur, dirs, _files in os.walk(root):
        dirs[:] = [
            d for d in dirs
            if not d.startswith(".")
            and d.lower() not in {DUPLICATE_QUARANTINE_DIR_NAME.lower(), "zero2sat_output", "cbf_zero2sat_output"}
            and ".tmp_zero2sat_" not in d.lower()
        ]
        cur_path = Path(cur)
        for d in dirs:
            if d.lower() != AUTO_OUTPUT_DIR_NAME.lower():
                continue
            output_dir = cur_path / d
            if direct_cbf_files(output_dir):
                data_dirs.add(cur_path.resolve())
    return sorted(data_dirs)


def find_original_for_duplicate(candidate: Path, files_by_lower_name: dict[str, Path]) -> Optional[Path]:
    parsed = parse_duplicate_copy_name(candidate)
    if parsed is None:
        return None
    original_stem, _copy_index = parsed
    suffixes = [candidate.suffix] + [s for s in SUPPORTED_EXTENSIONS if s.lower() != candidate.suffix.lower()]
    for suffix in suffixes:
        original = files_by_lower_name.get(f"{original_stem}{suffix}".lower())
        if (
            original
            and original.resolve() != candidate.resolve()
            and parse_duplicate_copy_name(original) is None
        ):
            return original
    return None


def scan_cbf_dir_for_duplicate_downloads(
    data_dir: Path,
    progress_callback: Optional[Callable[[int, int, DuplicateCbfResult], None]] = None,
) -> list[DuplicateCbfResult]:
    data_dir = Path(data_dir).expanduser().resolve()
    files = direct_cbf_files(data_dir)
    files_by_lower_name = {p.name.lower(): p for p in files}
    candidates = [p for p in files if parse_duplicate_copy_name(p) is not None]
    results: list[DuplicateCbfResult] = []
    total = len(candidates)

    for i, duplicate in enumerate(candidates, 1):
        result = DuplicateCbfResult(
            data_dir=str(data_dir),
            duplicate_file=str(duplicate),
            action="report_only",
        )
        try:
            result.size_bytes = int(duplicate.stat().st_size)
            original = find_original_for_duplicate(duplicate, files_by_lower_name)
            if original is None:
                result.status = "orphan_duplicate_name"
                result.error = "No original CBF found after removing copy index from file name."
            else:
                result.original_file = str(original)
                original_size = int(original.stat().st_size)
                if original_size != result.size_bytes:
                    result.status = "name_pattern_size_mismatch"
                    result.error = f"File sizes differ: original={original_size}, duplicate={result.size_bytes}."
                else:
                    result.original_sha256 = sha256_file(original)
                    result.duplicate_sha256 = sha256_file(duplicate)
                    if result.original_sha256 == result.duplicate_sha256:
                        result.status = "duplicate_confirmed"
                        result.action = "ready_to_quarantine"
                    else:
                        result.status = "name_pattern_hash_mismatch"
                        result.error = "File names look duplicated, but SHA256 hashes differ."
        except Exception as exc:
            result.status = "error"
            result.action = "report_only"
            result.error = f"{exc}\n{traceback.format_exc(limit=8)}"
        results.append(result)
        if progress_callback:
            progress_callback(i, total, result)
    return results


def write_duplicate_cbf_summary_csv(
    results: Iterable[DuplicateCbfResult],
    root: Path,
    output_name: str = DUPLICATE_CBF_SUMMARY_NAME,
) -> Path:
    root = Path(root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    path = root / output_name
    fieldnames = list(asdict(DuplicateCbfResult(data_dir="")).keys())
    rows = [asdict(r) for r in results]
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


def duplicate_cbf_counts(results: Iterable[DuplicateCbfResult]) -> dict[str, int]:
    result_list = list(results)
    return {
        "candidate_files": len(result_list),
        "confirmed_duplicates": sum(1 for r in result_list if r.status in {"duplicate_confirmed", "quarantined"}),
        "ready_to_quarantine": sum(1 for r in result_list if r.status == "duplicate_confirmed"),
        "quarantined": sum(1 for r in result_list if r.status == "quarantined"),
        "hash_mismatch": sum(1 for r in result_list if r.status == "name_pattern_hash_mismatch"),
        "size_mismatch": sum(1 for r in result_list if r.status == "name_pattern_size_mismatch"),
        "orphan_candidates": sum(1 for r in result_list if r.status == "orphan_duplicate_name"),
        "errors": sum(1 for r in result_list if r.status == "error" or r.action == "quarantine_failed"),
        "total_duplicate_bytes": sum(int(r.size_bytes) for r in result_list if r.status in {"duplicate_confirmed", "quarantined"}),
    }


def scan_duplicate_cbf_downloads(
    root: Path,
    progress_callback: Optional[Callable[[dict], None]] = None,
) -> tuple[list[DuplicateCbfResult], Path]:
    root = Path(root).expanduser().resolve()
    data_dirs = discover_cbf_data_dirs(root, excluded_names={DUPLICATE_QUARANTINE_DIR_NAME})
    total_dirs = len(data_dirs)
    all_results: list[DuplicateCbfResult] = []

    for dir_index, data_dir in enumerate(data_dirs, 1):
        if progress_callback:
            progress_callback({
                "phase": "duplicate_directory_start",
                "dir_index": dir_index,
                "total_dirs": total_dirs,
                "data_dir": str(data_dir),
            })

        def file_progress(file_index: int, total_files: int, result: DuplicateCbfResult) -> None:
            if not progress_callback:
                return
            progress_callback({
                "phase": "duplicate_file",
                "dir_index": dir_index,
                "total_dirs": total_dirs,
                "file_index": file_index,
                "total_files": total_files,
                "data_dir": str(data_dir),
                "duplicate_file": result.duplicate_file,
                "status": result.status,
                "action": result.action,
                "size_bytes": result.size_bytes,
            })

        dir_results = scan_cbf_dir_for_duplicate_downloads(data_dir, file_progress)
        all_results.extend(dir_results)
        if progress_callback:
            counts = duplicate_cbf_counts(all_results)
            progress_callback({
                "phase": "duplicate_directory_done",
                "dir_index": dir_index,
                "total_dirs": total_dirs,
                "data_dir": str(data_dir),
                **counts,
            })

    summary_path = write_duplicate_cbf_summary_csv(all_results, root)
    if progress_callback:
        progress_callback({
            "phase": "duplicate_scan_done",
            "total_dirs": total_dirs,
            "summary_path": str(summary_path),
            **duplicate_cbf_counts(all_results),
        })
    return all_results, summary_path


def unique_quarantine_path(quarantine_dir: Path, file_name: str) -> Path:
    quarantine_dir = Path(quarantine_dir)
    candidate = quarantine_dir / file_name
    if not candidate.exists():
        return candidate
    stem = Path(file_name).stem
    suffix = Path(file_name).suffix
    for i in range(1, 10000):
        candidate = quarantine_dir / f"{stem}__quarantine_{i:03d}{suffix}"
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Cannot find a free quarantine file name for {file_name!r}.")


def quarantine_duplicate_cbf_downloads(
    root: Path,
    scan_results: Optional[Iterable[DuplicateCbfResult]] = None,
    progress_callback: Optional[Callable[[dict], None]] = None,
) -> tuple[list[DuplicateCbfResult], Path]:
    root = Path(root).expanduser().resolve()
    if scan_results is None:
        scan_results, _summary_path = scan_duplicate_cbf_downloads(root)

    updated: list[DuplicateCbfResult] = []
    targets = [
        r for r in scan_results
        if r.status == "duplicate_confirmed" and r.action == "ready_to_quarantine"
    ]
    total_targets = len(targets)
    moved = 0
    target_index = 0

    for result in scan_results:
        current = DuplicateCbfResult(**asdict(result))
        if not (current.status == "duplicate_confirmed" and current.action == "ready_to_quarantine"):
            updated.append(current)
            continue

        target_index += 1
        try:
            data_dir = Path(current.data_dir).expanduser().resolve()
            original = Path(current.original_file).expanduser().resolve()
            duplicate = Path(current.duplicate_file).expanduser().resolve()
            if duplicate.parent != data_dir:
                raise ValueError("Duplicate CBF is not directly inside its recorded data directory.")
            if not original.exists():
                raise FileNotFoundError(f"Original CBF no longer exists: {original}")
            if not duplicate.exists():
                raise FileNotFoundError(f"Duplicate CBF no longer exists: {duplicate}")
            if int(original.stat().st_size) != int(duplicate.stat().st_size):
                current.status = "name_pattern_size_mismatch"
                current.action = "report_only"
                current.error = "Recheck before quarantine failed: file sizes differ."
                updated.append(current)
                continue
            original_sha = sha256_file(original)
            duplicate_sha = sha256_file(duplicate)
            current.original_sha256 = original_sha
            current.duplicate_sha256 = duplicate_sha
            if original_sha != duplicate_sha:
                current.status = "name_pattern_hash_mismatch"
                current.action = "report_only"
                current.error = "Recheck before quarantine failed: SHA256 hashes differ."
                updated.append(current)
                continue

            quarantine_dir = data_dir / DUPLICATE_QUARANTINE_DIR_NAME
            quarantine_dir.mkdir(parents=True, exist_ok=True)
            destination = unique_quarantine_path(quarantine_dir, duplicate.name)
            shutil.move(str(duplicate), str(destination))
            current.status = "quarantined"
            current.action = "moved_to_quarantine"
            current.quarantine_path = str(destination)
            current.error = ""
            moved += 1
        except Exception as exc:
            current.status = "error"
            current.action = "quarantine_failed"
            current.error = f"{exc}\n{traceback.format_exc(limit=8)}"
        updated.append(current)
        if progress_callback:
            progress_callback({
                "phase": "duplicate_quarantine_file",
                "file_index": target_index,
                "total_files": total_targets,
                "duplicate_file": current.duplicate_file,
                "quarantine_path": current.quarantine_path,
                "status": current.status,
                "moved": moved,
                **duplicate_cbf_counts(updated),
            })

    summary_path = write_duplicate_cbf_summary_csv(updated, root)
    if progress_callback:
        progress_callback({
            "phase": "duplicate_quarantine_done",
            "summary_path": str(summary_path),
            "moved": moved,
            **duplicate_cbf_counts(updated),
        })
    return updated, summary_path


def write_problem_files_summary_csv(
    results: Iterable[ProblemFileResult],
    root: Path,
    output_name: str = PROBLEM_FILES_SUMMARY_NAME,
) -> Path:
    root = Path(root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    path = root / output_name
    fieldnames = list(asdict(ProblemFileResult(data_dir="")).keys())
    rows = [asdict(r) for r in results]
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


def write_auto_processing_manifest(
    results: Iterable[AutoProcessingDirectoryResult],
    root: Path,
    csv_name: str = AUTO_PROCESSING_MANIFEST_CSV_NAME,
    json_name: str = AUTO_PROCESSING_MANIFEST_JSON_NAME,
) -> tuple[Path, Path]:
    root = Path(root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    rows = [asdict(r) for r in results]
    csv_path = root / csv_name
    json_path = root / json_name
    fieldnames = list(asdict(AutoProcessingDirectoryResult(data_dir="")).keys())
    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2, ensure_ascii=False)
    return csv_path, json_path


def auto_processing_counts(results: Iterable[AutoProcessingDirectoryResult]) -> dict[str, int]:
    result_list = list(results)
    return {
        "total_dirs": len(result_list),
        "clean_original_usable": sum(1 for r in result_list if r.status == "clean_original_usable"),
        "duplicates_quarantined_original_usable": sum(1 for r in result_list if r.status == "duplicates_quarantined_original_usable"),
        "overexposure_corrected_usable": sum(1 for r in result_list if r.status == "overexposure_corrected_usable"),
        "already_corrected_usable": sum(1 for r in result_list if r.status == "already_corrected_usable"),
        "corrected_usable_original_cleaned": sum(1 for r in result_list if r.status == "corrected_usable_original_cleaned"),
        "corrected_only_original_absent": sum(1 for r in result_list if r.status == "corrected_only_original_absent"),
        "needs_review": sum(1 for r in result_list if r.status == "needs_review"),
        "failed": sum(1 for r in result_list if r.status == "failed"),
        "duplicates_quarantined": sum(int(r.duplicates_quarantined) for r in result_list),
        "repaired_files": sum(int(r.repaired_files) for r in result_list),
        "total_target_pixels": sum(int(r.total_target_pixels) for r in result_list),
        "ignored_zero_pixels": sum(int(r.ignored_zero_pixels) for r in result_list),
        "problem_files": sum(int(r.problem_files) for r in result_list),
        "trusted_index_fast_path": sum(1 for r in result_list if r.validation_mode == "trusted_index_fast_path"),
        "strict_pixel_validation_once": sum(1 for r in result_list if r.validation_mode == "strict_pixel_validation_once"),
        "original_files_deleted": sum(int(r.original_files_deleted) for r in result_list),
        "original_bytes_deleted": sum(int(r.original_bytes_deleted) for r in result_list),
    }


def group_duplicate_results_by_dir(results: Iterable[DuplicateCbfResult]) -> dict[str, list[DuplicateCbfResult]]:
    grouped: dict[str, list[DuplicateCbfResult]] = {}
    for result in results:
        grouped.setdefault(str(Path(result.data_dir).expanduser().resolve()), []).append(result)
    return grouped


def duplicate_results_needing_review(results: Iterable[DuplicateCbfResult]) -> list[DuplicateCbfResult]:
    review_statuses = {
        "name_pattern_hash_mismatch",
        "name_pattern_size_mismatch",
        "orphan_duplicate_name",
        "error",
    }
    return [
        r for r in results
        if r.status in review_statuses or r.action == "quarantine_failed"
    ]


def problem_from_duplicate(result: DuplicateCbfResult) -> ProblemFileResult:
    return ProblemFileResult(
        data_dir=result.data_dir,
        file_path=result.duplicate_file,
        stage="duplicate_check",
        status=result.status,
        action=result.action,
        size_bytes=result.size_bytes,
        original_file=result.original_file,
        quarantine_path=result.quarantine_path,
        error=result.error,
    )


def problem_from_file_result(data_dir: Path, stage: str, result: FileResult) -> ProblemFileResult:
    return ProblemFileResult(
        data_dir=str(data_dir),
        file_path=result.input_file,
        stage=stage,
        status=result.status,
        action="report_only",
        error=result.error,
    )


def verify_original_repaired_pair_with_config(original_path: Path, repaired_path: Path, cfg: ProcessConfig) -> dict:
    _, original = read_image_data(original_path)
    _, repaired = read_image_data(repaired_path)
    if original.shape != repaired.shape:
        return {
            "pass": False,
            "reason": "shape_mismatch",
            "original_shape": str(tuple(original.shape)),
            "repaired_shape": str(tuple(repaired.shape)),
        }
    zero_mask, target_mask = make_target_mask(original, cfg)
    target_mask, ignored = apply_minor_zero_threshold(target_mask, cfg)
    non_target = ~target_mask
    effective_replacement = replacement_for_dtype(original.dtype, cfg.replacement_value)
    non_target_diff = int(np.count_nonzero(original[non_target] != repaired[non_target]))
    target_bad = int(np.count_nonzero(repaired[target_mask] != effective_replacement))
    target_pixels = int(np.count_nonzero(target_mask))
    return {
        "pass": non_target_diff == 0 and target_bad == 0,
        "reason": "ok" if non_target_diff == 0 and target_bad == 0 else "pixel_validation_failed",
        "target_pixels": target_pixels,
        "ignored_zero_pixels": ignored,
        "zero_pixels": int(np.count_nonzero(zero_mask)),
        "non_target_diff": non_target_diff,
        "target_bad": target_bad,
        "original_dtype": str(original.dtype),
        "repaired_dtype": str(repaired.dtype),
        "original_shape": str(tuple(original.shape)),
        "repaired_shape": str(tuple(repaired.shape)),
    }


def validation_record_from_strict_check(original_path: Path, repaired_path: Path,
                                        cfg: ProcessConfig, check: dict) -> dict:
    original_stat = file_stat_signature(original_path)
    output_stat = file_stat_signature(repaired_path)
    return {
        "original_name": original_path.name,
        "output_name": repaired_path.name,
        "original_size_bytes": original_stat["size_bytes"],
        "original_mtime_ns": original_stat["mtime_ns"],
        "output_size_bytes": output_stat["size_bytes"],
        "output_mtime_ns": output_stat["mtime_ns"],
        "shape": check.get("original_shape", ""),
        "dtype": check.get("original_dtype", ""),
        "zero_pixels": int(check.get("zero_pixels", 0) or 0),
        "target_pixels": int(check.get("target_pixels", 0) or 0),
        "ignored_zero_pixels": int(check.get("ignored_zero_pixels", 0) or 0),
        "replacement_value": int(cfg.replacement_value),
        "status": "strict_pixel_validated",
        "readback_validation_passed": bool(check.get("pass")),
        "non_target_diff": int(check.get("non_target_diff", 0) or 0),
        "target_bad": int(check.get("target_bad", 0) or 0),
    }


def evaluate_validation_index_fast_path(
    data_dir: Path,
    output_dir: Path,
    cfg: ProcessConfig,
    original_by_name: dict[str, Path],
    output_by_name: dict[str, Path],
) -> tuple[bool, str, str, dict]:
    start = time.time()
    index, load_status, load_error = load_validation_index(output_dir)
    json_path, _csv_path = validation_index_paths(output_dir)
    meta = {
        "index_status": load_status,
        "index_path": str(json_path),
        "fast_path_elapsed_s": 0.0,
        "total_target_pixels": 0,
        "ignored_zero_pixels": 0,
        "bytes_eligible_for_cleanup": 0,
        "original_files": len(original_by_name),
        "output_files": len(output_by_name),
    }
    if index is None:
        meta["fast_path_elapsed_s"] = round(time.time() - start, 4)
        return False, load_status, load_error, meta
    if index.get("schema_version") != VALIDATION_INDEX_SCHEMA_VERSION:
        meta["index_status"] = "schema_mismatch"
        meta["fast_path_elapsed_s"] = round(time.time() - start, 4)
        return False, "schema_mismatch", "Validation index schema version does not match.", meta
    if index.get("config_hash") != repair_config_hash(cfg):
        meta["index_status"] = "config_mismatch"
        meta["fast_path_elapsed_s"] = round(time.time() - start, 4)
        return False, "config_mismatch", "Validation index repair-rule hash does not match current settings.", meta
    if not index.get("trusted_for_cleanup"):
        meta["index_status"] = "not_trusted_for_cleanup"
        meta["fast_path_elapsed_s"] = round(time.time() - start, 4)
        return False, "not_trusted_for_cleanup", "Validation index is not marked trusted for cleanup.", meta

    records = index.get("records") or []
    if not records:
        meta["index_status"] = "empty_index"
        meta["fast_path_elapsed_s"] = round(time.time() - start, 4)
        return False, "empty_index", "Validation index has no file records.", meta

    original_names = {r.get("original_name", "") for r in records}
    output_names = {r.get("output_name", "") for r in records}
    if set(output_by_name) != output_names:
        meta["index_status"] = "output_name_mismatch"
        meta["fast_path_elapsed_s"] = round(time.time() - start, 4)
        return False, "output_name_mismatch", "Output CBF file set differs from validation index.", meta
    if original_by_name and set(original_by_name) != original_names:
        meta["index_status"] = "original_name_mismatch"
        meta["fast_path_elapsed_s"] = round(time.time() - start, 4)
        return False, "original_name_mismatch", "Original CBF file set differs from validation index.", meta

    bytes_eligible = 0
    total_target = 0
    ignored_zero = 0
    for record in records:
        output_path = output_by_name.get(record.get("output_name", ""))
        if output_path is None:
            meta["index_status"] = "missing_output_file"
            meta["fast_path_elapsed_s"] = round(time.time() - start, 4)
            return False, "missing_output_file", "Output CBF listed in index is missing.", meta
        try:
            output_stat = file_stat_signature(output_path)
        except OSError as exc:
            meta["index_status"] = "output_stat_error"
            meta["fast_path_elapsed_s"] = round(time.time() - start, 4)
            return False, "output_stat_error", str(exc), meta
        if (
            output_stat["size_bytes"] != int(record.get("output_size_bytes", -1))
            or output_stat["mtime_ns"] != int(record.get("output_mtime_ns", -1))
        ):
            meta["index_status"] = "output_stat_mismatch"
            meta["fast_path_elapsed_s"] = round(time.time() - start, 4)
            return False, "output_stat_mismatch", f"Output CBF changed since validation index: {output_path.name}", meta

        if original_by_name:
            original_path = original_by_name.get(record.get("original_name", ""))
            if original_path is None:
                meta["index_status"] = "missing_original_file"
                meta["fast_path_elapsed_s"] = round(time.time() - start, 4)
                return False, "missing_original_file", "Original CBF listed in index is missing.", meta
            try:
                original_stat = file_stat_signature(original_path)
            except OSError as exc:
                meta["index_status"] = "original_stat_error"
                meta["fast_path_elapsed_s"] = round(time.time() - start, 4)
                return False, "original_stat_error", str(exc), meta
            if (
                original_stat["size_bytes"] != int(record.get("original_size_bytes", -1))
                or original_stat["mtime_ns"] != int(record.get("original_mtime_ns", -1))
            ):
                meta["index_status"] = "original_stat_mismatch"
                meta["fast_path_elapsed_s"] = round(time.time() - start, 4)
                return False, "original_stat_mismatch", f"Original CBF changed since validation index: {original_path.name}", meta
            bytes_eligible += original_stat["size_bytes"]
        total_target += int(record.get("target_pixels", 0) or 0)
        ignored_zero += int(record.get("ignored_zero_pixels", 0) or 0)

    meta.update({
        "index_status": "trusted",
        "fast_path_elapsed_s": round(time.time() - start, 4),
        "total_target_pixels": total_target,
        "ignored_zero_pixels": ignored_zero,
        "bytes_eligible_for_cleanup": bytes_eligible,
    })
    return True, "trusted", "Validation index fast path passed.", meta


def evaluate_corrected_output(
    data_dir: Path,
    output_dir: Path,
    cfg: ProcessConfig,
    progress_callback: Optional[Callable[[int, int, Path, str], None]] = None,
    use_validation_index: Optional[bool] = None,
    write_index: Optional[bool] = None,
) -> CorrectedOutputEvaluation:
    strict_start = time.time()
    if use_validation_index is None:
        use_validation_index = bool(getattr(cfg, "use_validation_index", True))
    if write_index is None:
        write_index = bool(use_validation_index)
    data_dir = Path(data_dir).expanduser().resolve()
    output_dir = Path(output_dir).expanduser().resolve()
    original_files = direct_cbf_files(data_dir)
    output_files = direct_cbf_files(output_dir) if output_dir.exists() else []
    original_by_name = {p.name: p for p in original_files}
    output_by_name = {p.name: p for p in output_files}
    bytes_eligible = 0
    for p in original_by_name.values():
        try:
            bytes_eligible += int(p.stat().st_size)
        except OSError:
            pass

    result = CorrectedOutputEvaluation(
        data_dir=str(data_dir),
        output_dir=str(output_dir),
        original_files=len(original_by_name),
        output_files=len(output_by_name),
        bytes_eligible_for_cleanup=bytes_eligible,
    )
    result.index_path = str(validation_index_paths(output_dir)[0])

    if not output_dir.exists():
        result.status = "missing_output"
        result.error = f"Missing {AUTO_OUTPUT_DIR_NAME} output directory."
        return result
    if not output_by_name:
        result.status = "no_output_files"
        result.error = f"{AUTO_OUTPUT_DIR_NAME} contains no direct CBF files."
        return result

    if use_validation_index:
        ok, index_status, index_message, index_meta = evaluate_validation_index_fast_path(
            data_dir, output_dir, cfg, original_by_name, output_by_name)
        result.index_status = index_meta.get("index_status", index_status)
        result.fast_path_elapsed_s = float(index_meta.get("fast_path_elapsed_s", 0.0) or 0.0)
        result.index_path = str(index_meta.get("index_path") or result.index_path)
        if ok:
            result.validation_mode = "trusted_index_fast_path"
            result.files_checked = 0
            result.total_target_pixels = int(index_meta.get("total_target_pixels", 0) or 0)
            result.ignored_zero_pixels = int(index_meta.get("ignored_zero_pixels", 0) or 0)
            result.bytes_eligible_for_cleanup = int(index_meta.get("bytes_eligible_for_cleanup", bytes_eligible) or 0)
            result.cleanup_eligible_reason = "trusted_validation_index_matched_current_files"
            result.status = "valid_corrected_output" if original_by_name else "corrected_only_original_absent"
            return result
        result.error = "" if index_status in {"missing", "not_trusted_for_cleanup"} else index_message

    if not original_by_name:
        total = len(output_by_name)
        for i, output_path in enumerate(output_by_name.values(), 1):
            try:
                read_image_data(output_path)
                result.files_checked += 1
                if progress_callback:
                    progress_callback(i, total, output_path, "readable")
            except Exception as exc:
                result.status = "read_error"
                result.error = f"{output_path}: {exc}\n{traceback.format_exc(limit=8)}"
                if progress_callback:
                    progress_callback(i, total, output_path, "read_error")
                return result
        result.status = "corrected_only_original_absent"
        result.validation_mode = "readable_output_scan"
        result.cleanup_eligible_reason = "original_direct_cbf_absent"
        result.strict_validation_elapsed_s = round(time.time() - strict_start, 4)
        result.error = ""
        return result

    original_names = set(original_by_name)
    output_names = set(output_by_name)
    missing = sorted(original_names - output_names)
    extra = sorted(output_names - original_names)
    result.missing_in_output = len(missing)
    result.extra_in_output = len(extra)
    if missing or extra:
        result.status = "name_mismatch"
        result.error = (
            f"CBF file names differ: missing_in_output={len(missing)}, extra_in_output={len(extra)}."
        )
        result.validation_mode = "metadata_name_check"
        result.strict_validation_elapsed_s = round(time.time() - strict_start, 4)
        return result

    total = len(original_by_name)
    strict_records: list[dict] = []
    for i, name in enumerate(sorted(original_by_name), 1):
        original_path = original_by_name[name]
        repaired_path = output_by_name[name]
        try:
            check = verify_original_repaired_pair_with_config(original_path, repaired_path, cfg)
            result.files_checked += 1
            result.total_target_pixels += int(check.get("target_pixels", 0))
            result.ignored_zero_pixels += int(check.get("ignored_zero_pixels", 0))
            strict_records.append(validation_record_from_strict_check(original_path, repaired_path, cfg, check))
            status = "valid" if check.get("pass") else "pixel_validation_failed"
            if progress_callback:
                progress_callback(i, total, original_path, status)
            if not check.get("pass"):
                result.status = "pixel_validation_failed"
                result.error = (
                    f"{original_path.name}: {check.get('reason')}; "
                    f"non_target_diff={check.get('non_target_diff')}, "
                    f"target_bad={check.get('target_bad')}, "
                    f"ignored_zero_pixels={check.get('ignored_zero_pixels')}."
                )
                result.validation_mode = "strict_pixel_validation_once"
                result.strict_validation_elapsed_s = round(time.time() - strict_start, 4)
                return result
        except Exception as exc:
            result.status = "read_error"
            result.error = f"{original_path}: {exc}\n{traceback.format_exc(limit=8)}"
            if progress_callback:
                progress_callback(i, total, original_path, "read_error")
            result.validation_mode = "strict_pixel_validation_once"
            result.strict_validation_elapsed_s = round(time.time() - strict_start, 4)
            return result

    result.status = "valid_corrected_output"
    result.validation_mode = "strict_pixel_validation_once"
    result.cleanup_eligible_reason = "strict_pixel_validation_passed"
    result.strict_validation_elapsed_s = round(time.time() - strict_start, 4)
    result.error = ""
    if write_index and strict_records:
        json_path, _csv_path = write_validation_index(
            data_dir, output_dir, cfg, strict_records,
            validation_mode=result.validation_mode,
            trusted_for_cleanup=True,
        )
        result.index_status = "written_trusted"
        result.index_path = str(json_path)
    return result


def write_original_cleanup_summary_csv(
    results: Iterable[OriginalCleanupResult],
    root: Path,
    output_name: str = ORIGINAL_CLEANUP_SUMMARY_NAME,
) -> Path:
    root = Path(root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    path = root / output_name
    rows = [asdict(r) for r in results]
    fieldnames = list(asdict(OriginalCleanupResult(data_dir="")).keys())
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


def original_cleanup_counts(results: Iterable[OriginalCleanupResult]) -> dict[str, int]:
    result_list = list(results)
    return {
        "total_dirs": len(result_list),
        "ready_to_delete": sum(1 for r in result_list if r.status == "ready_to_delete"),
        "deleted_dirs": sum(1 for r in result_list if r.status == "deleted"),
        "already_cleaned": sum(1 for r in result_list if r.status == "already_cleaned"),
        "skipped_needs_review": sum(1 for r in result_list if r.status == "skipped_needs_review"),
        "delete_failed": sum(1 for r in result_list if r.status == "delete_failed"),
        "trusted_index_fast_path": sum(1 for r in result_list if r.validation_mode == "trusted_index_fast_path"),
        "strict_pixel_validation_once": sum(1 for r in result_list if r.validation_mode == "strict_pixel_validation_once"),
        "readable_output_scan": sum(1 for r in result_list if r.validation_mode == "readable_output_scan"),
        "files_eligible_for_cleanup": sum(int(r.original_files) for r in result_list if r.status in {"ready_to_delete", "deleted"}),
        "files_deleted": sum(int(r.files_deleted) for r in result_list),
        "bytes_eligible_for_cleanup": sum(int(r.bytes_eligible_for_cleanup) for r in result_list if r.status in {"ready_to_delete", "deleted"}),
        "bytes_deleted": sum(int(r.bytes_deleted) for r in result_list),
    }


def delete_direct_original_cbfs(data_dir: Path) -> tuple[int, int, str]:
    deleted_files = 0
    deleted_bytes = 0
    errors: list[str] = []
    for path in direct_cbf_files(Path(data_dir)):
        try:
            size = int(path.stat().st_size)
            path.unlink()
            deleted_files += 1
            deleted_bytes += size
        except Exception as exc:
            errors.append(f"{path}: {exc}")
    return deleted_files, deleted_bytes, "; ".join(errors)


def cleanup_corrected_original_cbfs(
    root: Path,
    base_cfg: ProcessConfig,
    delete_original: bool = False,
    progress_callback: Optional[Callable[[dict], None]] = None,
) -> tuple[list[OriginalCleanupResult], Path]:
    root = Path(root).expanduser().resolve()
    data_dirs = discover_cbf_data_dirs_with_corrected_parents(root)
    total_dirs = len(data_dirs)
    results: list[OriginalCleanupResult] = []

    for dir_index, data_dir in enumerate(data_dirs, 1):
        data_dir = Path(data_dir).expanduser().resolve()
        output_dir = data_dir / AUTO_OUTPUT_DIR_NAME
        if progress_callback:
            progress_callback({
                "phase": "cleanup_directory_start",
                "dir_index": dir_index,
                "total_dirs": total_dirs,
                "data_dir": str(data_dir),
                "output_dir": str(output_dir),
                "delete_original": delete_original,
            })

        if not output_dir.exists():
            current = OriginalCleanupResult(
                data_dir=str(data_dir),
                output_dir=str(output_dir),
                action="delete_original_cbf" if delete_original else "detect_only",
                status="skipped_no_output",
                corrected_validation_status="missing_output",
                original_files=len(direct_cbf_files(data_dir)),
                error=f"No {AUTO_OUTPUT_DIR_NAME} output directory exists.",
            )
            results.append(current)
            if progress_callback:
                progress_callback({"phase": "cleanup_directory_done", **asdict(current), **original_cleanup_counts(results)})
            continue

        def eval_progress(file_index: int, total_files: int, file_path: Path, status: str) -> None:
            if not progress_callback:
                return
            progress_callback({
                "phase": "cleanup_validate_file",
                "dir_index": dir_index,
                "total_dirs": total_dirs,
                "file_index": file_index,
                "total_files": total_files,
                "data_dir": str(data_dir),
                "file": str(file_path),
                "status": status,
            })

        evaluation = evaluate_corrected_output(data_dir, output_dir, base_cfg, eval_progress)
        current = OriginalCleanupResult(
            data_dir=str(data_dir),
            output_dir=str(output_dir),
            action="delete_original_cbf" if delete_original else "detect_only",
            corrected_validation_status=evaluation.status,
            original_files=evaluation.original_files,
            output_files=evaluation.output_files,
            files_checked=evaluation.files_checked,
            bytes_eligible_for_cleanup=evaluation.bytes_eligible_for_cleanup,
            recommended_data_dir=str(output_dir) if evaluation.status in {"valid_corrected_output", "corrected_only_original_absent"} else "",
            validation_mode=evaluation.validation_mode,
            index_status=evaluation.index_status,
            index_path=evaluation.index_path,
            cleanup_eligible_reason=evaluation.cleanup_eligible_reason,
            strict_validation_elapsed_s=evaluation.strict_validation_elapsed_s,
            fast_path_elapsed_s=evaluation.fast_path_elapsed_s,
            error=evaluation.error,
        )

        if evaluation.status == "corrected_only_original_absent":
            current.status = "already_cleaned"
        elif evaluation.status == "valid_corrected_output":
            if delete_original:
                deleted_files, deleted_bytes, delete_error = delete_direct_original_cbfs(data_dir)
                current.files_deleted = deleted_files
                current.bytes_deleted = deleted_bytes
                if delete_error:
                    current.status = "delete_failed"
                    current.error = delete_error
                else:
                    current.status = "deleted"
            else:
                current.status = "ready_to_delete"
        elif evaluation.status in {"missing_output", "no_output_files"}:
            current.status = "skipped_no_output"
        else:
            current.status = "skipped_needs_review"

        results.append(current)
        if progress_callback:
            progress_callback({"phase": "cleanup_directory_done", **asdict(current), **original_cleanup_counts(results)})

    summary_path = write_original_cleanup_summary_csv(results, root)
    if progress_callback:
        progress_callback({
            "phase": "cleanup_done",
            "summary_path": str(summary_path),
            **original_cleanup_counts(results),
        })
    return results, summary_path


def auto_process_cbf_tree(
    root: Path,
    base_cfg: ProcessConfig,
    progress_callback: Optional[Callable[[dict], None]] = None,
    cleanup_original: bool = False,
) -> tuple[list[AutoProcessingDirectoryResult], dict[str, str]]:
    root = Path(root).expanduser().resolve()
    data_dirs = discover_cbf_data_dirs_with_corrected_parents(root)
    total_dirs = len(data_dirs)
    manifest_results: list[AutoProcessingDirectoryResult] = []
    overexposure_results: list[AutoDirectoryResult] = []
    problem_results: list[ProblemFileResult] = []
    cleanup_results: list[OriginalCleanupResult] = []

    if progress_callback:
        progress_callback({
            "phase": "pipeline_start",
            "root": str(root),
            "total_dirs": total_dirs,
        })

    if total_dirs == 0:
        manifest_csv, manifest_json = write_auto_processing_manifest([], root)
        problem_csv = write_problem_files_summary_csv([], root)
        duplicate_summary_path = write_duplicate_cbf_summary_csv([], root)
        overexposure_summary_path = write_auto_summary_csv([], root)
        cleanup_summary_path = write_original_cleanup_summary_csv([], root)
        report_paths = {
            "manifest_csv": str(manifest_csv),
            "manifest_json": str(manifest_json),
            "problem_csv": str(problem_csv),
            "duplicate_summary_csv": str(duplicate_summary_path),
            "overexposure_summary_csv": str(overexposure_summary_path),
            "original_cleanup_summary_csv": str(cleanup_summary_path),
        }
        if progress_callback:
            progress_callback({
                "phase": "pipeline_done",
                "root": str(root),
                "warning": "No direct CBF data directories were found.",
                **auto_processing_counts([]),
                **report_paths,
            })
        return [], report_paths

    duplicate_scan_results, _duplicate_scan_summary = scan_duplicate_cbf_downloads(
        root, progress_callback=progress_callback)
    duplicate_results, duplicate_summary_path = quarantine_duplicate_cbf_downloads(
        root, scan_results=duplicate_scan_results, progress_callback=progress_callback)
    duplicate_by_dir = group_duplicate_results_by_dir(duplicate_results)

    for dir_index, data_dir in enumerate(data_dirs, 1):
        data_dir = Path(data_dir).expanduser().resolve()
        data_dir_key = str(data_dir)
        if progress_callback:
            progress_callback({
                "phase": "pipeline_directory_start",
                "dir_index": dir_index,
                "total_dirs": total_dirs,
                "data_dir": data_dir_key,
            })

        dir_duplicates = duplicate_by_dir.get(data_dir_key, [])
        duplicate_counts = duplicate_cbf_counts(dir_duplicates)
        duplicate_problem_results = duplicate_results_needing_review(dir_duplicates)
        for duplicate_problem in duplicate_problem_results:
            problem_results.append(problem_from_duplicate(duplicate_problem))

        result = AutoProcessingDirectoryResult(
            data_dir=data_dir_key,
            total_files=len(direct_cbf_files(data_dir)),
            duplicate_candidates=duplicate_counts["candidate_files"],
            duplicates_quarantined=duplicate_counts["quarantined"],
            duplicate_problem_files=len(duplicate_problem_results),
            duplicate_quarantine_dir=str(data_dir / DUPLICATE_QUARANTINE_DIR_NAME)
            if duplicate_counts["quarantined"] else "",
        )
        invalid_existing_output_error = ""

        if duplicate_problem_results:
            result.status = "needs_review"
            result.problem_files = len(duplicate_problem_results)
            result.error = "Duplicate-name CBF candidates require manual review; automatic overexposure repair was skipped for this directory."
            result.notes = "Resolve duplicate hash/size/orphan problems before using this directory for downstream analysis."
            overexposure_results.append(AutoDirectoryResult(
                data_dir=data_dir_key,
                status="skipped_needs_review",
                total_files=result.total_files,
                errors=len(duplicate_problem_results),
                error=result.error,
            ))
            manifest_results.append(result)
            if progress_callback:
                progress_callback({
                    "phase": "pipeline_directory_done",
                    "dir_index": dir_index,
                    "total_dirs": total_dirs,
                    "data_dir": data_dir_key,
                    **auto_processing_counts(manifest_results),
                })
            continue

        existing_output_dir = data_dir / AUTO_OUTPUT_DIR_NAME
        if existing_output_dir.exists():
            def corrected_eval_progress(file_index: int, total_files: int, file_path: Path, status: str) -> None:
                if not progress_callback:
                    return
                progress_callback({
                    "phase": "pipeline_corrected_output_validate_file",
                    "dir_index": dir_index,
                    "total_dirs": total_dirs,
                    "file_index": file_index,
                    "total_files": total_files,
                    "data_dir": data_dir_key,
                    "output_dir": str(existing_output_dir),
                    "file": str(file_path),
                    "status": status,
                })

            evaluation = evaluate_corrected_output(
                data_dir, existing_output_dir, base_cfg, corrected_eval_progress)
            result.corrected_validation_status = evaluation.status
            result.overexposure_output_dir = str(existing_output_dir)
            result.ignored_zero_pixels = evaluation.ignored_zero_pixels
            result.total_target_pixels = evaluation.total_target_pixels
            result.validation_mode = evaluation.validation_mode
            result.index_status = evaluation.index_status
            result.index_path = evaluation.index_path
            result.cleanup_eligible_reason = evaluation.cleanup_eligible_reason
            result.strict_validation_elapsed_s = evaluation.strict_validation_elapsed_s
            result.fast_path_elapsed_s = evaluation.fast_path_elapsed_s

            if evaluation.status in {"valid_corrected_output", "corrected_only_original_absent"}:
                result.total_files = evaluation.original_files or evaluation.output_files
                result.recommended_data_dir = str(existing_output_dir)
                result.status = (
                    "corrected_only_original_absent"
                    if evaluation.status == "corrected_only_original_absent"
                    else "already_corrected_usable"
                )
                result.notes = (
                    "Original direct CBF files are absent; use existing overexposure_corrected for downstream processing."
                    if evaluation.status == "corrected_only_original_absent"
                    else "Existing overexposure_corrected passed strict validation; repair was skipped."
                )

                cleanup_record = OriginalCleanupResult(
                    data_dir=data_dir_key,
                    output_dir=str(existing_output_dir),
                    action="delete_original_cbf" if cleanup_original else "detect_only",
                    corrected_validation_status=evaluation.status,
                    original_files=evaluation.original_files,
                    output_files=evaluation.output_files,
                    files_checked=evaluation.files_checked,
                    bytes_eligible_for_cleanup=evaluation.bytes_eligible_for_cleanup,
                    recommended_data_dir=str(existing_output_dir),
                    validation_mode=evaluation.validation_mode,
                    index_status=evaluation.index_status,
                    index_path=evaluation.index_path,
                    cleanup_eligible_reason=evaluation.cleanup_eligible_reason,
                    strict_validation_elapsed_s=evaluation.strict_validation_elapsed_s,
                    fast_path_elapsed_s=evaluation.fast_path_elapsed_s,
                )

                if evaluation.status == "corrected_only_original_absent":
                    cleanup_record.status = "already_cleaned"
                    result.cleanup_status = "already_cleaned"
                elif cleanup_original:
                    deleted_files, deleted_bytes, delete_error = delete_direct_original_cbfs(data_dir)
                    cleanup_record.files_deleted = deleted_files
                    cleanup_record.bytes_deleted = deleted_bytes
                    result.original_files_deleted = deleted_files
                    result.original_bytes_deleted = deleted_bytes
                    if delete_error:
                        cleanup_record.status = "delete_failed"
                        cleanup_record.error = delete_error
                        result.cleanup_status = "delete_failed"
                        problem_results.append(ProblemFileResult(
                            data_dir=data_dir_key,
                            stage="original_cleanup",
                            status="delete_failed",
                            action="delete_original_cbf",
                            error=delete_error,
                        ))
                    else:
                        cleanup_record.status = "deleted"
                        result.status = "corrected_usable_original_cleaned"
                        result.cleanup_status = "deleted"
                        result.notes = "Existing overexposure_corrected passed strict validation; original direct CBF files were deleted."
                else:
                    cleanup_record.status = "ready_to_delete"
                    result.cleanup_status = "ready_to_delete"

                cleanup_results.append(cleanup_record)
                overexposure_results.append(AutoDirectoryResult(
                    data_dir=data_dir_key,
                    output_dir=str(existing_output_dir),
                    status=result.status,
                    total_files=evaluation.original_files or evaluation.output_files,
                    total_target_pixels=evaluation.total_target_pixels,
                    ignored_zero_pixels=evaluation.ignored_zero_pixels,
                ))
                manifest_results.append(result)
                if progress_callback:
                    progress_callback({
                        "phase": "pipeline_directory_done",
                        "dir_index": dir_index,
                        "total_dirs": total_dirs,
                        "data_dir": data_dir_key,
                        "status": result.status,
                        **auto_processing_counts(manifest_results),
                    })
                continue

            problem_results.append(ProblemFileResult(
                data_dir=data_dir_key,
                file_path=str(existing_output_dir),
                stage="corrected_output_validation",
                status=evaluation.status,
                action="report_only",
                error=evaluation.error,
            ))
            invalid_existing_output_error = evaluation.error or evaluation.status
            if not direct_cbf_files(data_dir):
                result.status = "needs_review"
                result.problem_files = 1
                result.error = evaluation.error
                result.notes = "Existing overexposure_corrected could not be validated, and no original CBF files remain for repair."
                manifest_results.append(result)
                overexposure_results.append(AutoDirectoryResult(
                    data_dir=data_dir_key,
                    output_dir=str(existing_output_dir),
                    status="error",
                    total_files=evaluation.output_files,
                    errors=1,
                    error=evaluation.error,
                ))
                if progress_callback:
                    progress_callback({
                        "phase": "pipeline_directory_done",
                        "dir_index": dir_index,
                        "total_dirs": total_dirs,
                        "data_dir": data_dir_key,
                        "status": result.status,
                        **auto_processing_counts(manifest_results),
                    })
                continue

        try:
            def scan_progress(file_index: int, total_files: int, file_result: FileResult) -> None:
                if progress_callback:
                    progress_callback({
                        "phase": "pipeline_overexposure_scan_file",
                        "dir_index": dir_index,
                        "total_dirs": total_dirs,
                        "file_index": file_index,
                        "total_files": total_files,
                        "data_dir": data_dir_key,
                        "file": file_result.relative_path or Path(file_result.input_file).name,
                        "target_pixels": file_result.target_pixels,
                        "status": file_result.status,
                    })

            scan_results = scan_cbf_dir_for_overexposure(data_dir, base_cfg, scan_progress)
            scan_errors = [r for r in scan_results if r.status == "error"]
            total_target = sum(r.target_pixels for r in scan_results if r.status != "error")
            ignored_zero = sum(r.ignored_zero_pixels for r in scan_results if r.status != "error")
            overexposed_files = sum(1 for r in scan_results if r.target_pixels > 0)
            result.total_files = len(scan_results)
            result.overexposed_files = overexposed_files
            result.total_target_pixels = total_target
            result.ignored_zero_pixels = ignored_zero

            if scan_errors:
                for scan_error in scan_errors:
                    problem_results.append(problem_from_file_result(data_dir, "overexposure_scan", scan_error))
                result.status = "needs_review"
                result.problem_files = len(scan_errors)
                result.error = scan_errors[0].error.splitlines()[0] if scan_errors[0].error else "CBF scan error."
                result.notes = "One or more CBF files could not be read; no recommended_data_dir is assigned."
                overexposure_results.append(AutoDirectoryResult(
                    data_dir=data_dir_key,
                    status="error",
                    total_files=len(scan_results),
                    overexposed_files=overexposed_files,
                    total_target_pixels=total_target,
                    ignored_zero_pixels=ignored_zero,
                    errors=len(scan_errors),
                    error=result.error,
                ))
            elif total_target == 0:
                if invalid_existing_output_error:
                    result.status = "needs_review"
                    result.problem_files = 1
                    result.error = invalid_existing_output_error
                    result.notes = "Existing overexposure_corrected is invalid, while the original directory does not require repair."
                else:
                    result.recommended_data_dir = data_dir_key
                    result.status = (
                        "duplicates_quarantined_original_usable"
                        if duplicate_counts["quarantined"] else "clean_original_usable"
                    )
                    result.notes = (
                        "Use the original directory for downstream processing."
                        if ignored_zero == 0
                        else f"Use the original directory; {ignored_zero} minor zero pixels were ignored by threshold."
                    )
                overexposure_results.append(AutoDirectoryResult(
                    data_dir=data_dir_key,
                    status="skipped_no_overexposure" if not invalid_existing_output_error else "error",
                    total_files=len(scan_results),
                    ignored_zero_pixels=ignored_zero,
                    errors=1 if invalid_existing_output_error else 0,
                    error=invalid_existing_output_error,
                ))
            else:
                output_dir = data_dir / AUTO_OUTPUT_DIR_NAME

                def repair_progress(file_index: int, total_files: int, file_result: FileResult) -> None:
                    if progress_callback:
                        progress_callback({
                            "phase": "pipeline_overexposure_repair_file",
                            "dir_index": dir_index,
                            "total_dirs": total_dirs,
                            "file_index": file_index,
                            "total_files": total_files,
                            "data_dir": data_dir_key,
                            "output_dir": str(output_dir),
                            "file": file_result.relative_path or Path(file_result.input_file).name,
                            "target_pixels": file_result.target_pixels,
                            "status": file_result.status,
                        })

                repair_results, summary = repair_cbf_dir_to_local_output(
                    data_dir, output_dir, base_cfg,
                    clean_existing=True,
                    scan_results=scan_results,
                    progress_callback=repair_progress,
                )
                result.overexposure_output_dir = str(output_dir)
                result.repaired_files = summary.repaired
                result.copied_unmodified = summary.copied_unmodified
                result.total_target_pixels = summary.total_target_pixels
                result.ignored_zero_pixels = summary.ignored_zero_pixels
                result.overexposed_files = overexposed_files
                if summary.errors == 0:
                    result.status = "overexposure_corrected_usable"
                    result.recommended_data_dir = str(output_dir)
                    result.notes = "Use overexposure_corrected for downstream processing."
                    if cleanup_original:
                        evaluation = evaluate_corrected_output(data_dir, output_dir, base_cfg)
                        result.corrected_validation_status = evaluation.status
                        result.validation_mode = evaluation.validation_mode
                        result.index_status = evaluation.index_status
                        result.index_path = evaluation.index_path
                        result.cleanup_eligible_reason = evaluation.cleanup_eligible_reason
                        result.strict_validation_elapsed_s = evaluation.strict_validation_elapsed_s
                        result.fast_path_elapsed_s = evaluation.fast_path_elapsed_s
                        cleanup_record = OriginalCleanupResult(
                            data_dir=data_dir_key,
                            output_dir=str(output_dir),
                            action="delete_original_cbf",
                            corrected_validation_status=evaluation.status,
                            original_files=evaluation.original_files,
                            output_files=evaluation.output_files,
                            files_checked=evaluation.files_checked,
                            bytes_eligible_for_cleanup=evaluation.bytes_eligible_for_cleanup,
                            recommended_data_dir=str(output_dir) if evaluation.status == "valid_corrected_output" else "",
                            validation_mode=evaluation.validation_mode,
                            index_status=evaluation.index_status,
                            index_path=evaluation.index_path,
                            cleanup_eligible_reason=evaluation.cleanup_eligible_reason,
                            strict_validation_elapsed_s=evaluation.strict_validation_elapsed_s,
                            fast_path_elapsed_s=evaluation.fast_path_elapsed_s,
                            error=evaluation.error,
                        )
                        if evaluation.status == "valid_corrected_output":
                            deleted_files, deleted_bytes, delete_error = delete_direct_original_cbfs(data_dir)
                            cleanup_record.files_deleted = deleted_files
                            cleanup_record.bytes_deleted = deleted_bytes
                            result.original_files_deleted = deleted_files
                            result.original_bytes_deleted = deleted_bytes
                            if delete_error:
                                cleanup_record.status = "delete_failed"
                                cleanup_record.error = delete_error
                                result.cleanup_status = "delete_failed"
                                problem_results.append(ProblemFileResult(
                                    data_dir=data_dir_key,
                                    stage="original_cleanup",
                                    status="delete_failed",
                                    action="delete_original_cbf",
                                    error=delete_error,
                                ))
                            else:
                                cleanup_record.status = "deleted"
                                result.status = "corrected_usable_original_cleaned"
                                result.cleanup_status = "deleted"
                                result.notes = "Use overexposure_corrected for downstream processing; original direct CBF files were deleted."
                        else:
                            cleanup_record.status = "skipped_needs_review"
                            result.cleanup_status = "skipped_needs_review"
                            problem_results.append(ProblemFileResult(
                                data_dir=data_dir_key,
                                file_path=str(output_dir),
                                stage="post_repair_cleanup_validation",
                                status=evaluation.status,
                                action="report_only",
                                error=evaluation.error,
                            ))
                        cleanup_results.append(cleanup_record)
                else:
                    repair_errors = [r for r in repair_results if r.status == "error"]
                    for repair_error in repair_errors:
                        problem_results.append(problem_from_file_result(data_dir, "overexposure_repair", repair_error))
                    result.status = "needs_review"
                    result.problem_files = max(summary.errors, len(repair_errors))
                    result.error = "One or more files failed during overexposure repair."
                    result.notes = "Repair output is not recommended until the error report is reviewed."
                overexposure_results.append(AutoDirectoryResult(
                    data_dir=data_dir_key,
                    output_dir=str(output_dir),
                    status="repaired" if summary.errors == 0 else "error",
                    total_files=len(repair_results),
                    overexposed_files=overexposed_files,
                    total_target_pixels=summary.total_target_pixels,
                    ignored_zero_pixels=summary.ignored_zero_pixels,
                    repaired_files=summary.repaired,
                    copied_unmodified=summary.copied_unmodified,
                    errors=summary.errors,
                    csv_path=summary.csv_path,
                    html_path=summary.html_path,
                    config_path=summary.config_path,
                    error="" if summary.errors == 0 else result.error,
                ))
        except Exception as exc:
            result.status = "failed"
            result.problem_files = 1
            result.error = f"{exc}\n{traceback.format_exc(limit=8)}"
            result.notes = "Directory-level exception; inspect problem_files_summary.csv before using this directory."
            problem_results.append(ProblemFileResult(
                data_dir=data_dir_key,
                stage="pipeline",
                status="failed",
                action="report_only",
                error=result.error,
            ))
            overexposure_results.append(AutoDirectoryResult(
                data_dir=data_dir_key,
                status="error",
                total_files=result.total_files,
                errors=1,
                error=result.error,
            ))

        manifest_results.append(result)
        if progress_callback:
            progress_callback({
                "phase": "pipeline_directory_done",
                "dir_index": dir_index,
                "total_dirs": total_dirs,
                "data_dir": data_dir_key,
                "status": result.status,
                **auto_processing_counts(manifest_results),
            })

    manifest_csv, manifest_json = write_auto_processing_manifest(manifest_results, root)
    problem_csv = write_problem_files_summary_csv(problem_results, root)
    duplicate_summary_path = write_duplicate_cbf_summary_csv(duplicate_results, root)
    overexposure_summary_path = write_auto_summary_csv(overexposure_results, root)
    cleanup_summary_path = write_original_cleanup_summary_csv(cleanup_results, root)
    report_paths = {
        "manifest_csv": str(manifest_csv),
        "manifest_json": str(manifest_json),
        "problem_csv": str(problem_csv),
        "duplicate_summary_csv": str(duplicate_summary_path),
        "overexposure_summary_csv": str(overexposure_summary_path),
        "original_cleanup_summary_csv": str(cleanup_summary_path),
    }

    if progress_callback:
        progress_callback({
            "phase": "pipeline_done",
            "root": str(root),
            **auto_processing_counts(manifest_results),
            **report_paths,
        })
    return manifest_results, report_paths


def clone_config_for_dir(base_cfg: ProcessConfig, input_dir: Path, output_dir: Path,
                         dry_run: bool = False) -> ProcessConfig:
    return ProcessConfig(
        input_dir=Path(input_dir),
        output_dir=Path(output_dir),
        recursive=False,
        skip_output_dir=True,
        preserve_subfolders=False,
        suffix="",
        overwrite_output=True,
        overwrite_original=False,
        backup_before_overwrite=True,
        copy_unmodified=True,
        mode=base_cfg.mode,
        zero_value=base_cfg.zero_value,
        replacement_value=base_cfg.replacement_value,
        bright_threshold=base_cfg.bright_threshold,
        radius=base_cfg.radius,
        minor_zero_pixel_threshold=base_cfg.minor_zero_pixel_threshold,
        verify_after_write=base_cfg.verify_after_write,
        compute_sha256=base_cfg.compute_sha256,
        use_validation_index=base_cfg.use_validation_index,
        generate_html_report=base_cfg.generate_html_report,
        workers=base_cfg.workers,
        dry_run=dry_run,
        metadata=base_cfg.metadata,
    ).normalized()


def scan_cbf_dir_for_overexposure(data_dir: Path, cfg: ProcessConfig,
                                  progress_callback: Optional[Callable[[int, int, FileResult], None]] = None) -> list[FileResult]:
    data_dir = Path(data_dir).expanduser().resolve()
    scan_cfg = clone_config_for_dir(cfg, data_dir, data_dir / AUTO_OUTPUT_DIR_NAME, dry_run=False)
    files = direct_cbf_files(data_dir)
    results = []
    total = len(files)
    for i, src in enumerate(files, 1):
        result = scan_file(src, scan_cfg)
        results.append(result)
        if progress_callback:
            progress_callback(i, total, result)
    return results


def copy_unmodified_from_scan_result(src: Path, cfg: ProcessConfig, scan_result: FileResult) -> FileResult:
    start = time.time()
    result = FileResult(**asdict(scan_result))
    try:
        final_path = output_path_for(src, cfg)
        result.output_file = str(final_path)
        if final_path.exists() and not cfg.overwrite_output and not cfg.overwrite_original:
            result.status = "output_exists"
            return result
        final_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, final_path)
        if cfg.compute_sha256:
            if not result.original_sha256:
                result.original_sha256 = sha256_file(src)
            result.output_sha256 = sha256_file(final_path)
            result.output_content_verified = result.original_sha256 == result.output_sha256
        result.status = "copied_unmodified"
    except FileExistsError as exc:
        result.status = "output_exists"
        result.error = str(exc)
    except Exception as exc:
        result.status = "error"
        result.error = f"{exc}\n{traceback.format_exc(limit=8)}"
    result.elapsed_s = round(time.time() - start, 4)
    return result


def run_repair_from_scan_results(
    cfg: ProcessConfig,
    scan_results: Iterable[FileResult],
    progress_callback: Optional[Callable[[int, int, FileResult], None]] = None,
) -> tuple[list[FileResult], BatchSummary]:
    cfg = cfg.normalized()
    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    scan_results = list(scan_results)
    total = len(scan_results)
    results: list[FileResult] = []

    def handle_scan_result(scan_result: FileResult) -> FileResult:
        src = Path(scan_result.input_file).expanduser().resolve()
        if scan_result.status == "error":
            return FileResult(**asdict(scan_result))
        if scan_result.target_pixels == 0 and cfg.copy_unmodified and not cfg.overwrite_original:
            return copy_unmodified_from_scan_result(src, cfg, scan_result)
        return process_file(src, cfg)

    if cfg.workers <= 1 or total <= 1:
        for i, scan_result in enumerate(scan_results, 1):
            result = handle_scan_result(scan_result)
            results.append(result)
            if progress_callback:
                progress_callback(i, total, result)
    else:
        done = 0
        with ThreadPoolExecutor(max_workers=cfg.workers) as ex:
            futures = [ex.submit(handle_scan_result, scan_result) for scan_result in scan_results]
            for fut in as_completed(futures):
                result = fut.result()
                results.append(result)
                done += 1
                if progress_callback:
                    progress_callback(done, total, result)
        results.sort(key=lambda r: r.relative_path)

    prefix = "cbf_zero2sat_repair"
    csv_path = write_summary_csv(results, cfg.output_dir, prefix=prefix)
    config_path = save_config_json(cfg, cfg.output_dir, prefix=prefix + "_config")
    html_path = ""
    if cfg.generate_html_report:
        html_path = str(write_html_report(results, cfg, cfg.output_dir, prefix=prefix))

    summary = summarize_results(results)
    summary.csv_path = str(csv_path)
    summary.config_path = str(config_path)
    summary.html_path = html_path
    return results, summary


def clean_auto_output_dir(output_dir: Path) -> None:
    output_dir = Path(output_dir)
    if not output_dir.exists():
        return
    for item in output_dir.iterdir():
        if not item.is_file():
            continue
        name = item.name
        lower = name.lower()
        generated_report = (
            lower.startswith("cbf_zero2sat_")
            and lower.endswith((".csv", ".html", ".json"))
        )
        generated_summary = lower == "auto_overexposure_summary.csv"
        generated_index = lower in {VALIDATION_INDEX_JSON_NAME.lower(), VALIDATION_INDEX_CSV_NAME.lower()}
        if lower.endswith(".cbf") or generated_report or generated_summary or generated_index:
            item.unlink()


def repair_cbf_dir_to_local_output(data_dir: Path, output_dir: Path, cfg: ProcessConfig,
                                   clean_existing: bool = True,
                                   scan_results: Optional[Iterable[FileResult]] = None,
                                   progress_callback: Optional[Callable[[int, int, FileResult], None]] = None) -> tuple[list[FileResult], BatchSummary]:
    data_dir = Path(data_dir).expanduser().resolve()
    output_dir = Path(output_dir).expanduser().resolve()
    if output_dir == data_dir:
        raise ValueError("Auto output directory must differ from the source CBF directory.")
    if output_dir.parent != data_dir:
        raise ValueError("Auto output directory must be directly inside the source CBF directory.")
    if output_dir.name.lower() != AUTO_OUTPUT_DIR_NAME.lower():
        raise ValueError(f"Auto output directory must be named {AUTO_OUTPUT_DIR_NAME!r}.")
    if clean_existing:
        clean_auto_output_dir(output_dir)
    repair_cfg = clone_config_for_dir(cfg, data_dir, output_dir, dry_run=False)
    if scan_results is None:
        results, summary = run_batch(repair_cfg, action="repair", progress_callback=progress_callback)
    else:
        results, summary = run_repair_from_scan_results(
            repair_cfg, scan_results, progress_callback=progress_callback)
    if summary.errors == 0 and getattr(repair_cfg, "use_validation_index", True):
        write_validation_index_from_results(
            data_dir, output_dir, repair_cfg, results,
            trusted_for_cleanup=None,
            validation_mode="process_write",
        )
    return results, summary


def write_auto_summary_csv(results: Iterable[AutoDirectoryResult], root: Path,
                           output_name: str = "auto_overexposure_summary.csv") -> Path:
    root = Path(root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    path = root / output_name
    rows = [asdict(r) for r in results]
    fieldnames = list(asdict(AutoDirectoryResult(data_dir="")).keys())
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


def auto_overexposure_repair(root: Path, base_cfg: ProcessConfig,
                             output_folder_name: str = AUTO_OUTPUT_DIR_NAME,
                             overwrite_existing_output: bool = True,
                             progress_callback: Optional[Callable[[dict], None]] = None,
                             cleanup_original: bool = False,
                             cancel_event=None) -> tuple[list[AutoDirectoryResult], Path]:
    if output_folder_name != AUTO_OUTPUT_DIR_NAME:
        raise ValueError(f"Only {AUTO_OUTPUT_DIR_NAME!r} is supported for auto output folders.")

    root = Path(root).expanduser().resolve()
    dirs = discover_cbf_data_dirs_with_corrected_parents(root)
    total_dirs = len(dirs)
    auto_results: list[AutoDirectoryResult] = []
    cleanup_results: list[OriginalCleanupResult] = []

    for dir_index, data_dir in enumerate(dirs, 1):
        if cancel_event is not None and cancel_event.is_set():
            break
        if progress_callback:
            progress_callback({
                "phase": "directory_start",
                "dir_index": dir_index,
                "total_dirs": total_dirs,
                "data_dir": str(data_dir),
            })

        def emit_directory_done(result: AutoDirectoryResult) -> None:
            if not progress_callback:
                return
            progress_callback({
                "phase": "directory_done",
                "dir_index": dir_index,
                "total_dirs": total_dirs,
                "data_dir": str(data_dir),
                "status": result.status,
                "scanned_dirs": len(auto_results),
                "repaired_dirs": sum(1 for r in auto_results if r.status == "repaired"),
                "skipped_dirs": sum(1 for r in auto_results if r.status == "skipped_no_overexposure"),
                "error_dirs": sum(1 for r in auto_results if r.status == "error"),
                "total_files": result.total_files,
                "overexposed_files": result.overexposed_files,
                "target_pixels": result.total_target_pixels,
                "output_dir": result.output_dir,
                "error": result.error,
            })

        try:
            existing_output_dir = data_dir / AUTO_OUTPUT_DIR_NAME
            if existing_output_dir.exists():
                evaluation = evaluate_corrected_output(data_dir, existing_output_dir, base_cfg)
                if evaluation.status in {"valid_corrected_output", "corrected_only_original_absent"}:
                    cleanup_record = OriginalCleanupResult(
                        data_dir=str(data_dir),
                        output_dir=str(existing_output_dir),
                        action="delete_original_cbf" if cleanup_original else "detect_only",
                        corrected_validation_status=evaluation.status,
                        original_files=evaluation.original_files,
                        output_files=evaluation.output_files,
                        files_checked=evaluation.files_checked,
                        bytes_eligible_for_cleanup=evaluation.bytes_eligible_for_cleanup,
                        recommended_data_dir=str(existing_output_dir),
                        validation_mode=evaluation.validation_mode,
                        index_status=evaluation.index_status,
                        index_path=evaluation.index_path,
                        cleanup_eligible_reason=evaluation.cleanup_eligible_reason,
                        strict_validation_elapsed_s=evaluation.strict_validation_elapsed_s,
                        fast_path_elapsed_s=evaluation.fast_path_elapsed_s,
                    )
                    status = "corrected_only_original_absent" if evaluation.status == "corrected_only_original_absent" else "already_corrected"
                    deleted_files = 0
                    deleted_bytes = 0
                    if evaluation.status == "corrected_only_original_absent":
                        cleanup_record.status = "already_cleaned"
                    elif cleanup_original:
                        deleted_files, deleted_bytes, delete_error = delete_direct_original_cbfs(data_dir)
                        cleanup_record.files_deleted = deleted_files
                        cleanup_record.bytes_deleted = deleted_bytes
                        if delete_error:
                            cleanup_record.status = "delete_failed"
                            cleanup_record.error = delete_error
                        else:
                            cleanup_record.status = "deleted"
                            status = "corrected_usable_original_cleaned"
                    else:
                        cleanup_record.status = "ready_to_delete"
                    cleanup_results.append(cleanup_record)
                    result = AutoDirectoryResult(
                        data_dir=str(data_dir),
                        output_dir=str(existing_output_dir),
                        status=status,
                        total_files=evaluation.original_files or evaluation.output_files,
                        total_target_pixels=evaluation.total_target_pixels,
                        ignored_zero_pixels=evaluation.ignored_zero_pixels,
                        repaired_files=0,
                        copied_unmodified=0,
                        errors=1 if cleanup_record.status == "delete_failed" else 0,
                        error=cleanup_record.error,
                    )
                    auto_results.append(result)
                    emit_directory_done(result)
                    continue
                if not direct_cbf_files(data_dir):
                    result = AutoDirectoryResult(
                        data_dir=str(data_dir),
                        output_dir=str(existing_output_dir),
                        status="error",
                        total_files=evaluation.output_files,
                        errors=1,
                        error=evaluation.error,
                    )
                    auto_results.append(result)
                    emit_directory_done(result)
                    continue

            def scan_progress(i, total, file_result):
                if progress_callback:
                    progress_callback({
                        "phase": "scan_file",
                        "dir_index": dir_index,
                        "total_dirs": total_dirs,
                        "file_index": i,
                        "total_files": total,
                        "data_dir": str(data_dir),
                        "file": file_result.relative_path or Path(file_result.input_file).name,
                        "target_pixels": file_result.target_pixels,
                        "status": file_result.status,
                    })

            scan_results = scan_cbf_dir_for_overexposure(data_dir, base_cfg, scan_progress)
            scan_errors = [r for r in scan_results if r.status == "error"]
            total_target = sum(r.target_pixels for r in scan_results if r.status != "error")
            ignored_zero = sum(r.ignored_zero_pixels for r in scan_results if r.status != "error")
            overexposed_files = sum(1 for r in scan_results if r.target_pixels > 0)

            if scan_errors:
                first_error = scan_errors[0].error.splitlines()[0] if scan_errors[0].error else "scan error"
                result = AutoDirectoryResult(
                    data_dir=str(data_dir),
                    status="error",
                    total_files=len(scan_results),
                    overexposed_files=overexposed_files,
                    total_target_pixels=total_target,
                    ignored_zero_pixels=ignored_zero,
                    errors=len(scan_errors),
                    error=first_error,
                )
                auto_results.append(result)
                emit_directory_done(result)
                continue

            if total_target == 0:
                result = AutoDirectoryResult(
                    data_dir=str(data_dir),
                    status="skipped_no_overexposure",
                    total_files=len(scan_results),
                    ignored_zero_pixels=ignored_zero,
                )
                auto_results.append(result)
                emit_directory_done(result)
                continue

            output_dir = data_dir / AUTO_OUTPUT_DIR_NAME

            def repair_progress(i, total, file_result):
                if progress_callback:
                    progress_callback({
                        "phase": "repair_file",
                        "dir_index": dir_index,
                        "total_dirs": total_dirs,
                        "file_index": i,
                        "total_files": total,
                        "data_dir": str(data_dir),
                        "output_dir": str(output_dir),
                        "file": file_result.relative_path or Path(file_result.input_file).name,
                        "target_pixels": file_result.target_pixels,
                        "status": file_result.status,
                    })

            repair_results, summary = repair_cbf_dir_to_local_output(
                data_dir, output_dir, base_cfg,
                clean_existing=overwrite_existing_output,
                scan_results=scan_results,
                progress_callback=repair_progress,
            )
            result = AutoDirectoryResult(
                data_dir=str(data_dir),
                output_dir=str(output_dir),
                status="repaired" if summary.errors == 0 else "error",
                total_files=len(repair_results),
                overexposed_files=overexposed_files,
                total_target_pixels=summary.total_target_pixels,
                ignored_zero_pixels=summary.ignored_zero_pixels,
                repaired_files=summary.repaired,
                copied_unmodified=summary.copied_unmodified,
                errors=summary.errors,
                csv_path=summary.csv_path,
                html_path=summary.html_path,
                config_path=summary.config_path,
                error="" if summary.errors == 0 else "One or more files failed during repair.",
            )
            if summary.errors == 0 and cleanup_original:
                evaluation = evaluate_corrected_output(data_dir, output_dir, base_cfg)
                cleanup_record = OriginalCleanupResult(
                    data_dir=str(data_dir),
                    output_dir=str(output_dir),
                    action="delete_original_cbf",
                    corrected_validation_status=evaluation.status,
                    original_files=evaluation.original_files,
                    output_files=evaluation.output_files,
                    files_checked=evaluation.files_checked,
                    bytes_eligible_for_cleanup=evaluation.bytes_eligible_for_cleanup,
                    recommended_data_dir=str(output_dir) if evaluation.status == "valid_corrected_output" else "",
                    validation_mode=evaluation.validation_mode,
                    index_status=evaluation.index_status,
                    index_path=evaluation.index_path,
                    cleanup_eligible_reason=evaluation.cleanup_eligible_reason,
                    strict_validation_elapsed_s=evaluation.strict_validation_elapsed_s,
                    fast_path_elapsed_s=evaluation.fast_path_elapsed_s,
                    error=evaluation.error,
                )
                if evaluation.status == "valid_corrected_output":
                    deleted_files, deleted_bytes, delete_error = delete_direct_original_cbfs(data_dir)
                    cleanup_record.files_deleted = deleted_files
                    cleanup_record.bytes_deleted = deleted_bytes
                    if delete_error:
                        cleanup_record.status = "delete_failed"
                        cleanup_record.error = delete_error
                        result.errors = max(result.errors, 1)
                        result.error = delete_error
                    else:
                        cleanup_record.status = "deleted"
                        result.status = "corrected_usable_original_cleaned"
                else:
                    cleanup_record.status = "skipped_needs_review"
                    result.errors = max(result.errors, 1)
                    result.error = evaluation.error
                cleanup_results.append(cleanup_record)
            auto_results.append(result)
            emit_directory_done(result)
        except Exception as exc:
            result = AutoDirectoryResult(
                data_dir=str(data_dir),
                status="error",
                error=f"{exc}\n{traceback.format_exc(limit=8)}",
            )
            auto_results.append(result)
            emit_directory_done(result)

    summary_path = write_auto_summary_csv(auto_results, root)
    cleanup_summary_path = write_original_cleanup_summary_csv(cleanup_results, root)
    if progress_callback:
        progress_callback({
            "phase": "done",
            "total_dirs": total_dirs,
            "summary_path": str(summary_path),
            "original_cleanup_summary_path": str(cleanup_summary_path),
        })
    return auto_results, summary_path


def verify_original_repaired_pair(original_path: Path, repaired_path: Path, zero_value: int = 0, replacement_value: int = 32766) -> dict:
    _, original = read_image_data(original_path)
    _, repaired = read_image_data(repaired_path)
    if original.shape != repaired.shape:
        return {"pass": False, "reason": "shape_mismatch", "original_shape": str(tuple(original.shape)), "repaired_shape": str(tuple(repaired.shape))}
    target = original == zero_value
    non_target = ~target
    non_target_diff = int(np.count_nonzero(original[non_target] != repaired[non_target]))
    target_bad = int(np.count_nonzero(repaired[target] != replacement_value))
    return {
        "pass": non_target_diff == 0 and target_bad == 0,
        "reason": "ok" if non_target_diff == 0 and target_bad == 0 else "pixel_validation_failed",
        "target_pixels": int(np.count_nonzero(target)),
        "non_target_diff": non_target_diff,
        "target_bad": target_bad,
        "original_dtype": str(original.dtype),
        "repaired_dtype": str(repaired.dtype),
        "original_shape": str(tuple(original.shape)),
        "repaired_shape": str(tuple(repaired.shape)),
        "original_sha256": sha256_file(original_path),
        "repaired_sha256": sha256_file(repaired_path),
    }
