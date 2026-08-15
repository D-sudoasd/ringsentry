"""Image loading utilities for various detector formats."""

import os
from pathlib import Path
from typing import Any, Dict, Tuple

import numpy as np

from .constants import (
    TIFF_SUFFIXES,
    FABIO_OPTIONAL_SUFFIXES,
    HDF5_SUFFIXES,
    EDF_SUFFIXES,
    SUPPORTED_FORMATS,
    DEFAULT_H5_PATH,
)
from .utils import is_numeric_frame_suffix


# --- Lazy imports for heavy libraries ---
def _lazy_import_imageio():
    import imageio.v3 as iio
    return iio


def _lazy_import_fabio():
    import fabio
    return fabio


def _lazy_import_tifffile():
    import tifffile
    return tifffile


def _lazy_import_h5py():
    import h5py
    return h5py


def _lazy_import_matplotlib():
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.figure import Figure
    return Figure, FigureCanvasTkAgg


# --- File detection ---

def sniff_file_kind(file: Path) -> str:
    """Detect file kind from content header first, then extension."""
    ext = file.suffix.lower()
    try:
        with open(file, 'rb') as f:
            header = f.read(4096)
    except Exception:
        header = b''

    if header.startswith((b'II*\x00', b'MM\x00*', b'II+\x00', b'MM\x00+')):
        return 'tiff'
    if header.startswith(b'\x89HDF\r\n\x1a\n'):
        return 'hdf5'
    if (
        header.startswith(b'{')
        and (b'Dim_1' in header or b'HeaderID' in header or b'DataType' in header)
    ):
        return 'edf'
    if b'###CBF:' in header or b'--CIF-BINARY-FORMAT-SECTION--' in header:
        return 'cbf'
    # ADSC SMV format (used at APS, SSRL, etc.) — header starts with "{"
    # and contains "HEADER_BYTES" or "SIZE1" keywords (but NOT EDF keywords)
    if (
        header.startswith(b'{')
        and b'Dim_1' not in header
        and (b'HEADER_BYTES' in header or b'SIZE1' in header)
    ):
        return 'fabio'
    # Bruker CCD format — header starts with "FORMAT" or contains "##NPIXELS"
    if header.startswith(b'FORMAT') or b'##NPIXELS' in header or b'##NROWS' in header:
        return 'fabio'
    # MarCCD — is actually TIFF-based so already caught above

    if ext in TIFF_SUFFIXES or is_numeric_frame_suffix(file):
        return 'tiff'
    if ext in HDF5_SUFFIXES:
        return 'hdf5'
    if ext in EDF_SUFFIXES:
        return 'edf'
    if ext in FABIO_OPTIONAL_SUFFIXES:
        return 'fabio'
    raise ValueError(f"\u4E0D\u652F\u6301\u6216\u65E0\u6CD5\u8BC6\u522B\u7684\u6587\u4EF6\u7C7B\u578B: {file.name}")


def is_supported_input_file(path: Path) -> bool:
    """Check if a file is a supported input format."""
    if not path.is_file():
        return False
    ext = path.suffix.lower()
    if ext in SUPPORTED_FORMATS:
        return True
    if is_numeric_frame_suffix(path):
        try:
            sniff_file_kind(path)
            return True
        except Exception:
            return False
    return False


# --- Internal helpers ---

def _normalize_loaded_array(arr: np.ndarray, file: Path) -> np.ndarray:
    """Ensure the loaded array is 2D.

    Handles unambiguous singleton-axis patterns from synchrotron detectors:
    - (1, H, W): squeeze leading singleton frame axis
    - (H, W, 1): squeeze trailing singleton channel axis

    Non-singleton 3D layouts and arrays with more than 3 dimensions are
    rejected instead of silently selecting a frame or channel.
    """
    arr = np.asarray(arr)
    if arr.ndim == 2:
        return arr
    if arr.ndim == 3:
        import logging

        logger = logging.getLogger(__name__)
        s0, s1, s2 = arr.shape

        if s0 == 1:
            logger.info(
                f"{file.name}: loaded 3D array shape={arr.shape}, "
                "squeezing leading singleton frame axis"
            )
            arr = arr[0]
        elif s2 == 1:
            logger.info(
                f"{file.name}: loaded 3D array shape={arr.shape}, "
                "squeezing trailing singleton channel axis"
            )
            arr = arr[..., 0]
        else:
            raise ValueError(
                f"{file.name}: 3D \u6570\u7EC4 shape={arr.shape} \u5305\u542B\u591A\u4E2A\u5E27\u6216\u901A\u9053\uFF0C"
                "\u8BF7\u5148\u663E\u5F0F\u9009\u62E9\u5355\u4E2A 2D \u6570\u636E\u96C6/\u5E27"
            )
    elif arr.ndim > 3:
        raise ValueError(
            f"{file.name}: \u671F\u671B 2D \u56FE\u50CF\uff0c\u4E0D\u652F\u6301 shape={arr.shape} "
            "\u7684\u9AD8\u7EF4\u6570\u7EC4"
        )
    if arr.ndim != 2:
        raise ValueError(
            f"{file.name}: \u671F\u671B 2D \u56FE\u50CF\uFF0C\u5B9E\u9645 shape={arr.shape}"
        )
    return arr


def _load_hdf5_dataset(file: Path, h5_path: str):
    """Load a dataset from an HDF5 file."""
    h5py = _lazy_import_h5py()
    with h5py.File(file, 'r') as hf:
        if not h5_path:
            raise ValueError("HDF5 \u8DEF\u5F84\u4E0D\u80FD\u4E3A\u7A7A")
        path_parts = [p for p in h5_path.split('/') if p]
        current = hf
        for part in path_parts:
            if part not in current:
                available = list(current.keys())
                raise ValueError(
                    f"HDF5 \u8DEF\u5F84 '{h5_path}' \u5728 {file} \u4E2D\u672A\u627E\u5230\u3002"
                    f"'{part}' \u4E0D\u5B58\u5728\u3002\u53EF\u7528\u9879: {available}"
                )
            current = current[part]
        if not isinstance(current, h5py.Dataset):
            raise ValueError(
                f"HDF5 \u8DEF\u5F84 '{h5_path}' \u5728 {file} \u4E2D\u4E0D\u662F\u6570\u636E\u96C6"
            )
        return current[()]


def _load_with_fabio(file: Path) -> Tuple[np.ndarray, Dict[str, Any]]:
    """Load an image through FabIO and return data plus selected metadata."""
    fab = _lazy_import_fabio()
    with fab.open(str(file)) as img:
        arr = img.data.copy()
        header = dict(getattr(img, "header", {}) or {})

    meta: Dict[str, Any] = {}
    for key in (
        "conversions",
        "Content-Type",
        "Content-Transfer-Encoding",
        "X-Binary-Element-Type",
        "X-Binary-Element-Byte-Order",
        "X-Binary-Number-of-Elements",
        "X-Binary-Size-Fastest-Dimension",
        "X-Binary-Size-Second-Dimension",
        "X-Binary-Size-Padding",
    ):
        if key in header:
            meta[key] = str(header[key])

    expected_elements = meta.get("X-Binary-Number-of-Elements")
    if expected_elements is not None:
        try:
            expected = int(expected_elements)
        except Exception:
            expected = None
        if expected is not None and expected != int(np.asarray(arr).size):
            raise ValueError(
                f"{file.name}: CBF 元素数量不匹配，header={expected}, "
                f"decoded={int(np.asarray(arr).size)}"
            )

    return arr, meta


# --- Public API ---

def load_image_with_info(
    file: Path, h5_path: str = DEFAULT_H5_PATH
) -> Dict[str, Any]:
    """Load image data and return dict with 'data' and 'metadata'."""
    from .edf_io import read_edf

    kind = sniff_file_kind(file)
    metadata: Dict[str, Any] = {
        "source_kind": kind,
        "source_name": file.name,
    }
    arr = None

    if kind == 'tiff':
        tf = _lazy_import_tifffile()
        try:
            arr = tf.imread(str(file))
        except Exception:
            iio = _lazy_import_imageio()
            arr = iio.imread(file)
    elif kind == 'edf':
        arr = read_edf(file)
    elif kind == 'hdf5':
        arr = _load_hdf5_dataset(file, h5_path)
    elif kind == 'cbf':
        arr, fabio_meta = _load_with_fabio(file)
        metadata.update(fabio_meta)
    elif kind == 'fabio':
        arr, fabio_meta = _load_with_fabio(file)
        metadata.update(fabio_meta)
    else:
        raise ValueError(f"\u4E0D\u652F\u6301\u7684\u683C\u5F0F: {kind}")

    if arr is None:
        raise ValueError("\u65E0\u6CD5\u8BFB\u53D6\u56FE\u50CF\u6570\u636E")

    arr = _normalize_loaded_array(arr, file)
    metadata["dtype"] = str(arr.dtype)
    metadata["shape"] = tuple(arr.shape)
    return {"data": arr, "metadata": metadata}


def load_image(file: Path, h5_path: str = DEFAULT_H5_PATH):
    """Load image data, returning just the numpy array."""
    return load_image_with_info(file, h5_path)["data"]


# --- File discovery ---

def find_files_recursive(root, exts=SUPPORTED_FORMATS, exclude_dirs=()):
    """Recursively find detector image files, including numeric suffix frames."""
    root = Path(root).resolve()
    exclude = {str(Path(d).resolve()) for d in exclude_dirs if d}
    result = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d
            for d in dirnames
            if str(Path(dirpath, d).resolve()) not in exclude
            and d not in ("_converted",)
        ]
        for f in filenames:
            file_path = Path(dirpath) / f
            if is_supported_input_file(file_path):
                rel_path = file_path.relative_to(root)
                result.append((file_path, rel_path))
    return sorted(result, key=lambda x: str(x[0]))


def build_filelist_from_selected_paths(selected_paths):
    """Build filelist tuples from manually selected file paths.

    Returns:
        (filelist, common_root, skipped)
    """
    from .utils import _ensure_unique_relative_path

    cleaned = []
    skipped = []
    for raw in selected_paths:
        try:
            path = Path(raw).expanduser().resolve()
        except Exception:
            path = Path(raw)
        if not path.exists():
            skipped.append((str(raw), "missing"))
            continue
        if not path.is_file():
            skipped.append((str(path), "not a file"))
            continue
        if not is_supported_input_file(path):
            skipped.append((str(path), "unsupported"))
            continue
        cleaned.append(path)

    if not cleaned:
        return [], None, skipped

    common_root = None
    try:
        common_root = Path(os.path.commonpath([str(p.parent) for p in cleaned]))
    except Exception:
        common_root = None

    used = set()
    filelist = []
    for path in sorted(cleaned, key=lambda p: str(p)):
        if common_root is not None:
            try:
                rel_path = path.relative_to(common_root)
            except Exception:
                rel_path = Path(path.name)
        else:
            import re
            parent_tag = re.sub(
                r'[^A-Za-z0-9._-]+', '_', path.parent.name or 'selected'
            )
            rel_path = Path("selected_files") / parent_tag / path.name
        rel_path = _ensure_unique_relative_path(rel_path, used)
        filelist.append((path, rel_path))

    return filelist, common_root, skipped
