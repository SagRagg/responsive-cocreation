"""Tests for the image previews (sketch_capture.preview): the ASCII picture
and the hand-written PNG encoder, for both image formats.
"""

import struct
import zlib

import numpy as np
import pytest

from sketch_capture.canvas import render_canvas
from sketch_capture.preview import to_ascii, write_png


def _canvas():
    d = np.zeros((28, 28), dtype=np.uint8)
    d[5:10, 3:6] = 255
    return render_canvas(d)


def test_ascii_shape_and_ink():
    lines = to_ascii(_canvas()).split('\n')
    assert len(lines) == 28
    assert all(len(line) == 56 for line in lines)
    assert lines[0].strip() == ''          # blank background
    assert '#' in lines[6]                 # stroke rows show ink


def test_png_roundtrip(tmp_path):
    """Decode the PNG by hand (fixed chunk offsets for a single IDAT) and
    compare every pixel with the source image."""
    canvas = _canvas()
    path = tmp_path / 'a.png'
    write_png(str(path), canvas)
    raw = path.read_bytes()
    assert raw[:8] == b'\x89PNG\r\n\x1a\n'
    width, height = struct.unpack('>II', raw[16:24])
    assert (width, height) == (280, 280)
    # decode the single IDAT chunk and compare pixels
    idat_len = struct.unpack('>I', raw[33:37])[0]
    data = zlib.decompress(raw[41:41 + idat_len])
    rows = np.frombuffer(data, dtype=np.uint8).reshape(280, 281)
    assert (rows[:, 0] == 0).all()
    np.testing.assert_array_equal(rows[:, 1:], canvas)


def _mnist():
    d = np.zeros((28, 28), dtype=np.uint8)
    d[5:10, 3:6] = 255
    return d


def test_ascii_same_picture_for_both_formats():
    assert to_ascii(_mnist()) == to_ascii(_canvas())


def test_ascii_rejects_other_sizes():
    with pytest.raises(ValueError):
        to_ascii(np.zeros((10, 10), dtype=np.uint8))


def test_png_of_mnist_image(tmp_path):
    path = tmp_path / 'm.png'
    write_png(str(path), _mnist())
    width, height = struct.unpack('>II', path.read_bytes()[16:24])
    assert (width, height) == (28, 28)
