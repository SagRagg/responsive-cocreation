"""Ways to look at the image that was sent: terminal text and PNG files."""

import struct
import zlib

import numpy as np

from sketch_capture.canvas import CANVAS_SIZE, MNIST_SIZE, SCALE

_RAMP = ' .:+#'  # light ink -> dark ink


def to_ascii(image):
    """Return a text picture of the sent image, one 2-char cell per MNIST pixel.

    Takes either format: 28x28 white on black or 280x280 black on white.
    """
    image = np.asarray(image).astype(int)
    if image.shape == (CANVAS_SIZE, CANVAS_SIZE):
        ink = 255 - image[::SCALE, ::SCALE]
    elif image.shape == (MNIST_SIZE, MNIST_SIZE):
        ink = image
    else:
        raise ValueError(f'unexpected image shape {image.shape}')
    levels = ink * (len(_RAMP) - 1) // 255
    return '\n'.join(''.join(_RAMP[v] * 2 for v in row) for row in levels)


def _chunk(kind, data):
    body = kind + data
    return struct.pack('>I', len(data)) + body + struct.pack('>I', zlib.crc32(body))


def write_png(path, image):
    """Write a 2-D uint8 array as an 8-bit grayscale PNG."""
    image = np.asarray(image, dtype=np.uint8)
    height, width = image.shape
    rows = b''.join(b'\x00' + image[y].tobytes() for y in range(height))
    with open(path, 'wb') as f:
        f.write(b'\x89PNG\r\n\x1a\n')
        f.write(_chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 0, 0, 0, 0)))
        f.write(_chunk(b'IDAT', zlib.compress(rows)))
        f.write(_chunk(b'IEND', b''))
