"""Tests for reading MNIST IDX files (sketch_capture.mnist_loader), using
small synthetic files: plain and gzipped round trips, missing files, bad
magic numbers and truncated data.
"""

import gzip
import struct

import numpy as np
import pytest

from sketch_capture.mnist_loader import (
    IMAGES_STEM, LABELS_STEM, load_mnist_test, read_idx_images, read_idx_labels)


def _write_idx(tmp_path, images, labels, gz=False):
    """Write images and labels as MNIST test IDX files into tmp_path."""
    n = len(images)
    img = struct.pack('>IIII', 2051, n, 28, 28) + images.tobytes()
    lab = struct.pack('>II', 2049, n) + labels.tobytes()
    for stem, raw in ((IMAGES_STEM, img), (LABELS_STEM, lab)):
        if gz:
            (tmp_path / (stem + '.gz')).write_bytes(gzip.compress(raw))
        else:
            (tmp_path / stem).write_bytes(raw)


def _synthetic(n=5):
    rng = np.random.default_rng(0)
    images = rng.integers(0, 256, size=(n, 28, 28), dtype=np.uint8)
    labels = np.arange(n, dtype=np.uint8)
    return images, labels


@pytest.mark.parametrize('gz', [False, True])
def test_roundtrip(tmp_path, gz):
    images, labels = _synthetic()
    _write_idx(tmp_path, images, labels, gz=gz)
    got_images, got_labels = load_mnist_test(str(tmp_path))
    assert got_images.shape == (5, 28, 28)
    assert got_images.dtype == np.uint8
    np.testing.assert_array_equal(got_images, images)
    np.testing.assert_array_equal(got_labels, labels)


def test_missing_files(tmp_path):
    with pytest.raises(FileNotFoundError, match='fetch_mnist'):
        load_mnist_test(str(tmp_path))


def test_bad_magic(tmp_path):
    bad = tmp_path / 'bad'
    bad.write_bytes(struct.pack('>IIII', 1234, 0, 28, 28))
    with pytest.raises(ValueError):
        read_idx_images(str(bad))
    bad.write_bytes(struct.pack('>II', 1234, 0))
    with pytest.raises(ValueError):
        read_idx_labels(str(bad))


def test_truncated_file(tmp_path):
    images, _ = _synthetic()
    path = tmp_path / 'short'
    path.write_bytes(struct.pack('>IIII', 2051, 5, 28, 28) + images.tobytes()[:-1])
    with pytest.raises(ValueError):
        read_idx_images(str(path))
