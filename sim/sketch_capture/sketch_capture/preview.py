"""Ways to look at the canvas that was sent: terminal text and PNG files."""

import struct
import zlib

import numpy as np

from sketch_capture.canvas import SCALE

_RAMP = ' .:+#'  # light ink -> dark ink


def to_ascii(canvas):
    """Return a text picture of the canvas, one 2-char cell per MNIST pixel."""
    small = 255 - np.asarray(canvas)[::SCALE, ::SCALE].astype(int)  # ink level
    levels = small * (len(_RAMP) - 1) // 255
    return '\n'.join(''.join(_RAMP[v] * 2 for v in row) for row in levels)


def _chunk(kind, data):
    body = kind + data
    return struct.pack('>I', len(data)) + body + struct.pack('>I', zlib.crc32(body))


def write_png(path, canvas):
    """Write a 2-D uint8 array as an 8-bit grayscale PNG."""
    canvas = np.asarray(canvas, dtype=np.uint8)
    height, width = canvas.shape
    rows = b''.join(b'\x00' + canvas[y].tobytes() for y in range(height))
    with open(path, 'wb') as f:
        f.write(b'\x89PNG\r\n\x1a\n')
        f.write(_chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 0, 0, 0, 0)))
        f.write(_chunk(b'IDAT', zlib.compress(rows)))
        f.write(_chunk(b'IEND', b''))
