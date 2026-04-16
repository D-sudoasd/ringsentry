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

import re
from pathlib import Path
from typing import Dict, Any, Optional

import numpy as np


def _parse_edf_header_bytes(header_bytes: bytes) -> Dict[str, str]:
    """Parse EDF header bytes into a key-value dictionary."""
    text_header = header_bytes.decode('latin-1', errors='replace')
    pairs = re.findall(r'([^=;{}\n\r]+?)\s*=\s*([^;{}]+?)\s*;', text_header)
    return {k.strip(): v.strip() for k, v in pairs}


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

        header_size = ((end_pos + 1023) // 1024) * 1024
        header = _parse_edf_header_bytes(buf[:header_size])

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
        if dtype.itemsize > 1:
            dtype = dtype.newbyteorder(
                '<' if byte_order == 'LowByteFirst' else '>'
            )

        dim1 = int(header.get('Dim_1'))
        dim2 = int(header.get('Dim_2'))
        size = int(header.get('Size', dim1 * dim2 * dtype.itemsize))

        f.seek(header_size)
        raw = f.read(size)
        if len(raw) != size:
            raise ValueError(
                f"EDF payload truncated: expected {size} bytes, got {len(raw)}"
            )
        arr = np.frombuffer(raw, dtype=dtype, count=dim1 * dim2)
        arr = arr.reshape((dim2, dim1))
        return arr.copy()


def write_edf(
    arr: np.ndarray,
    out_path: Path,
    header_extra: Optional[Dict[str, Any]] = None,
):
    """Write a 2D numpy array to an EDF file."""
    arr = np.asarray(arr)
    if arr.ndim != 2:
        raise ValueError(f"EDF export expects a 2D array, got shape {arr.shape}")
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

    base_dtype = np.dtype(arr.dtype)
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
        base_dtype = np.dtype(arr.dtype)

    data_type = dtype_map[base_dtype]
    if arr.dtype.itemsize > 1:
        arr = np.ascontiguousarray(
            arr.astype(arr.dtype.newbyteorder('<'), copy=False)
        )
    else:
        arr = np.ascontiguousarray(arr)

    extras = {}
    if header_extra:
        for k, v in header_extra.items():
            safe_key = re.sub(r'[^A-Za-z0-9_\-]', '_', str(k))
            extras[safe_key] = str(v).replace(';', ',')

    lines = [
        '{',
        'HeaderID = EH:000001:000000:000000 ;',
        'Image = 1 ;',
        'ByteOrder = LowByteFirst ;',
        f'DataType = {data_type} ;',
        f'Dim_1 = {arr.shape[1]} ;',
        f'Dim_2 = {arr.shape[0]} ;',
        f'Size = {arr.nbytes} ;',
    ]
    for k, v in sorted(extras.items()):
        lines.append(f'{k} = {v} ;')
    lines.append('}')
    header_text = "\n".join(lines) + "\n"
    header_bytes = header_text.encode('ascii', errors='replace')
    padding = ((len(header_bytes) + 1023) // 1024) * 1024 - len(header_bytes)
    header_bytes += b' ' * padding

    with open(out_path, 'wb') as f:
        f.write(header_bytes)
        f.write(arr.tobytes(order='C'))
