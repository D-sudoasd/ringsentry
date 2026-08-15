"""EDF (European Data Format) read/write operations.

EDF is a binary image format widely used in synchrotron diffraction
experiments.  An EDF file consists of:

- A **header** section: ASCII text enclosed in curly braces ``{ ... }``,
  containing key-value pairs separated by semicolons (e.g.,
  ``Dim_1 = 2048 ;``).  The header is padded to a multiple of 1024 bytes.

- A **data** section: raw binary pixel values in row-major (C) order,
  with byte order specified by the ``ByteOrder`` header key.
  ``Dim_1`` = number of columns, ``Dim_2`` = number of rows.

Supports common detector data types: uint8, int16, uint16, int32, uint32,
int64, uint64, float32, float64.
"""

import math
import re
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

import numpy as np


def _parse_edf_header_bytes(header_bytes: bytes) -> Dict[str, str]:
    """Parse EDF header bytes into a key-value dictionary."""
    text_header = header_bytes.decode('latin-1', errors='replace')
    pairs = re.findall(r'([^=;{}\n\r]+?)\s*=\s*([^;{}]+?)\s*;', text_header)
    return {k.strip(): v.strip() for k, v in pairs}


def _edf_dtype_from_header(header: Dict[str, str]) -> np.dtype:
    """Return a numpy dtype from EDF header fields."""
    dtype_map = {
        'UnsignedByte': np.uint8,
        'SignedByte': np.int8,
        'UnsignedShort': np.uint16,
        'SignedShort': np.int16,
        'UnsignedInteger': np.uint32,
        'SignedInteger': np.int32,
        'UnsignedLong': np.uint64,
        'SignedLong': np.int64,
        'FloatValue': np.float32,
        'DoubleValue': np.float64,
        'Float': np.float32,
        'Double': np.float64,
    }
    data_type = header.get('DataType')
    if data_type not in dtype_map:
        raise ValueError(f"Unsupported EDF DataType: {data_type}")
    dtype = np.dtype(dtype_map[data_type])

    byte_order = header.get('ByteOrder', 'LowByteFirst')
    if byte_order not in {'LowByteFirst', 'HighByteFirst'}:
        raise ValueError(f"Unsupported EDF ByteOrder: {byte_order}")
    if dtype.itemsize > 1:
        dtype = dtype.newbyteorder(
            '<' if byte_order == 'LowByteFirst' else '>'
        )
    return dtype


def _parse_positive_int(value: Optional[str]) -> Optional[int]:
    """Parse an EDF integer field, returning None when absent/invalid."""
    if value is None:
        return None
    try:
        parsed = int(str(value).strip())
    except Exception:
        return None
    return parsed if parsed > 0 else None


def _choose_edf_data_offset(
    *,
    file_size: int,
    payload_size: int,
    header_end_pos: int,
    declared_header_size: Optional[int],
) -> int:
    """Choose the most plausible EDF binary data offset.

    Older versions of this application wrote 1024-byte headers without the
    EDF_HeaderSize field and placed the closing brace before the padding.
    Some readers assume a 512-byte header in that case, which turns header
    padding spaces into bogus pixel values.  Prefer exact single-image file
    size matches so both old files and FabIO-generated EDF files are read
    correctly.
    """
    if declared_header_size is not None:
        if declared_header_size < header_end_pos:
            raise ValueError(
                "EDF_HeaderSize/HeaderSize ends before the header closing "
                "brace"
            )
        if declared_header_size + payload_size != file_size:
            raise ValueError(
                "EDF_HeaderSize/HeaderSize is inconsistent with the file "
                "size and declared image payload"
            )
        return declared_header_size

    candidates = []
    for block in (512, 1024):
        rounded = int(math.ceil(header_end_pos / block) * block)
        candidates.append(rounded)

    candidates.append(header_end_pos)

    seen = set()
    unique_candidates = []
    for value in candidates:
        if value not in seen and value >= header_end_pos:
            seen.add(value)
            unique_candidates.append(value)

    for value in unique_candidates:
        if value + payload_size == file_size:
            return value

    raise ValueError(
        "EDF payload position is inconsistent with the declared image size; "
        "trailing bytes or unsupported multiple images may be present"
    )


def read_edf(file: Path) -> np.ndarray:
    """Read an EDF file and return a 2D numpy array."""
    with open(file, 'rb') as f:
        buf = b''
        end_pos = -1
        while True:
            chunk = f.read(1024)
            if not chunk:
                break
            buf += chunk
            if b'}\n' in buf:
                end_pos = buf.index(b'}\n') + 2
                break
            if b'}' in buf:
                end_pos = buf.index(b'}') + 1
                break
            if len(buf) > 1024 * 1024:
                raise ValueError("EDF header too large or malformed.")

        if end_pos < 0:
            raise ValueError("Could not locate EDF header end.")

        if not buf.lstrip().startswith(b'{'):
            raise ValueError("EDF header must start with an opening brace.")

        header = _parse_edf_header_bytes(buf[:end_pos])
        compression = header.get('Compression')
        if compression is not None:
            normalized_compression = re.sub(
                r'[\s_-]+', ' ', compression.strip().lower()
            )
            uncompressed_values = {
                '', 'none', 'no', 'no compression', 'not compressed',
                'nocompression', 'notcompressed', 'raw', 'uncompressed',
            }
            if normalized_compression not in uncompressed_values:
                raise ValueError(
                    f"Unsupported EDF Compression: {compression}"
                )
        dtype = _edf_dtype_from_header(header)

        try:
            dim1 = int(header.get('Dim_1'))
            dim2 = int(header.get('Dim_2'))
        except (TypeError, ValueError) as exc:
            raise ValueError("EDF dimensions Dim_1 and Dim_2 must be integers") from exc
        if dim1 <= 0 or dim2 <= 0:
            raise ValueError("EDF dimensions Dim_1 and Dim_2 must be positive")
        expected_payload_size = dim1 * dim2 * dtype.itemsize
        declared_binary_fields = [
            (name, header[name])
            for name in ('EDF_BinarySize', 'Size')
            if name in header
        ]
        parsed_binary_sizes = []
        for name, value in declared_binary_fields:
            parsed = _parse_positive_int(value)
            if parsed is None:
                raise ValueError(
                    f"{name} must be a positive integer"
                )
            parsed_binary_sizes.append(parsed)
        if len(set(parsed_binary_sizes)) > 1:
            raise ValueError(
                "EDF_BinarySize and Size declare conflicting payload sizes"
            )
        declared_binary_size = (
            parsed_binary_sizes[0] if parsed_binary_sizes else None
        )
        if declared_binary_size is not None and declared_binary_size != expected_payload_size:
            raise ValueError(
                "EDF declared binary size does not match dimensions/dtype: "
                f"expected {expected_payload_size} bytes, got {declared_binary_size}"
            )
        size = expected_payload_size

        declared_header_fields = [
            (name, header[name])
            for name in ('EDF_HeaderSize', 'HeaderSize')
            if name in header
        ]
        parsed_header_sizes = []
        for name, value in declared_header_fields:
            parsed = _parse_positive_int(value)
            if parsed is None:
                raise ValueError(f"{name} must be a positive integer")
            parsed_header_sizes.append(parsed)
        if len(set(parsed_header_sizes)) > 1:
            raise ValueError(
                "EDF_HeaderSize and HeaderSize declare conflicting offsets"
            )
        declared_header_size = (
            parsed_header_sizes[0] if parsed_header_sizes else None
        )
        file_size = Path(file).stat().st_size
        header_size = _choose_edf_data_offset(
            file_size=file_size,
            payload_size=size,
            header_end_pos=end_pos,
            declared_header_size=declared_header_size,
        )

        f.seek(header_size)
        raw = f.read(size)
        if len(raw) != size:
            raise ValueError(
                f"EDF payload truncated: expected {size} bytes, got {len(raw)}"
            )
        arr = np.frombuffer(raw, dtype=dtype, count=dim1 * dim2)
        arr = arr.reshape((dim2, dim1))
        return arr.copy()


def _edf_data_type_name(arr: np.ndarray) -> Tuple[np.ndarray, str]:
    """Normalize an array dtype and return the corresponding EDF DataType."""
    arr = np.asarray(arr)
    if arr.dtype.kind == 'b':
        arr = arr.astype(np.uint8)

    dtype_map = {
        np.dtype(np.uint8): 'UnsignedByte',
        np.dtype(np.int8): 'SignedByte',
        np.dtype(np.uint16): 'UnsignedShort',
        np.dtype(np.int16): 'SignedShort',
        np.dtype(np.uint32): 'UnsignedInteger',
        np.dtype(np.int32): 'SignedInteger',
        np.dtype(np.uint64): 'UnsignedLong',
        np.dtype(np.int64): 'SignedLong',
        np.dtype(np.float32): 'FloatValue',
        np.dtype(np.float64): 'DoubleValue',
    }

    base_dtype = np.dtype(arr.dtype).newbyteorder('=')
    if base_dtype not in dtype_map:
        if arr.dtype.kind == 'f':
            arr = arr.astype(np.float32)
        elif arr.dtype.kind in ('u', 'i'):
            if arr.dtype.itemsize <= 2:
                arr = arr.astype(
                    np.int16 if arr.dtype.kind == 'i' else np.uint16
                )
            elif arr.dtype.itemsize <= 4:
                arr = arr.astype(
                    np.int32 if arr.dtype.kind == 'i' else np.uint32
                )
            else:
                arr = arr.astype(
                    np.int64 if arr.dtype.kind == 'i' else np.uint64
                )
        else:
            arr = arr.astype(np.float32)
        base_dtype = np.dtype(arr.dtype).newbyteorder('=')

    return arr, dtype_map[base_dtype]


def _build_edf_header(
    arr: np.ndarray,
    data_type: str,
    extras: Dict[str, str],
) -> bytes:
    """Build an EDF header whose closing brace is at the padded header end."""
    header_size = 512
    while True:
        lines = [
            '{',
            'EDF_DataBlockID = 0.Image.Psd ;',
            f'EDF_BinarySize = {arr.nbytes} ;',
            f'EDF_HeaderSize = {header_size} ;',
            'ByteOrder = LowByteFirst ;',
            f'DataType = {data_type} ;',
            f'Dim_1 = {arr.shape[1]} ;',
            f'Dim_2 = {arr.shape[0]} ;',
            'Image = 0 ;',
            'HeaderID = EH:000001:000000:000000 ;',
            f'Size = {arr.nbytes} ;',
        ]
        for k, v in sorted(extras.items()):
            lines.append(f'{k} = {v} ;')

        body = ("\n".join(lines) + "\n").encode('ascii', errors='replace')
        min_size = len(body) + len(b'}\n')
        required = int(math.ceil(min_size / 512) * 512)
        if required == header_size:
            padding = header_size - min_size
            return body + (b' ' * padding) + b'}\n'
        header_size = required


def write_edf(
    arr: np.ndarray,
    out_path: Path,
    header_extra: Optional[Dict[str, Any]] = None,
):
    """Write a 2D numpy array to an EDF file."""
    arr = np.asarray(arr)
    if arr.ndim != 2:
        raise ValueError(f"EDF export expects a 2D array, got shape {arr.shape}")

    arr, data_type = _edf_data_type_name(arr)
    if arr.dtype.itemsize > 1:
        arr = np.ascontiguousarray(
            arr.astype(arr.dtype.newbyteorder('<'), copy=False)
        )
    else:
        arr = np.ascontiguousarray(arr)

    extras = {}
    reserved_keys = {
        'EDF_DataBlockID', 'EDF_BinarySize', 'EDF_HeaderSize',
        'ByteOrder', 'DataType', 'Dim_1', 'Dim_2', 'Image',
        'HeaderID', 'Size', 'Compression', 'HeaderSize',
    }
    if header_extra:
        for k, v in header_extra.items():
            safe_key = re.sub(r'[^A-Za-z0-9_\-]', '_', str(k))
            if safe_key in reserved_keys:
                safe_key = f'User_{safe_key}'
            extras[safe_key] = str(v).replace(';', ',')

    header_bytes = _build_edf_header(arr, data_type, extras)

    with open(out_path, 'wb') as f:
        f.write(header_bytes)
        f.write(arr.tobytes(order='C'))
