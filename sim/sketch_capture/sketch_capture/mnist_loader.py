"""Read the MNIST test split from raw IDX files (optionally gzipped)."""

import gzip
import os
import struct

import numpy as np

IMAGES_STEM = 't10k-images-idx3-ubyte'
LABELS_STEM = 't10k-labels-idx1-ubyte'

# IDX header magic numbers: 0x0803 (uint8, 3 dims) and 0x0801 (uint8, 1 dim).
_IMAGES_MAGIC = 2051
_LABELS_MAGIC = 2049


def _find_file(dataset_dir, stem):
    """Return the path of `stem` or `stem.gz` inside dataset_dir."""
    for name in (stem, stem + '.gz'):
        path = os.path.join(dataset_dir, name)
        if os.path.isfile(path):
            return path
    raise FileNotFoundError(
        f'{stem}[.gz] not found in {dataset_dir}. '
        'Run scripts/fetch_mnist.sh or set the dataset_dir parameter.')


def _read_bytes(path):
    """Whole file contents, gunzipped if the name ends in .gz."""
    opener = gzip.open if path.endswith('.gz') else open
    with opener(path, 'rb') as f:
        return f.read()


def read_idx_images(path):
    """Return an (N, rows, cols) uint8 array from an IDX3 image file."""
    raw = _read_bytes(path)
    magic, count, rows, cols = struct.unpack('>IIII', raw[:16])
    if magic != _IMAGES_MAGIC:
        raise ValueError(f'{path}: bad image magic number {magic}')
    if len(raw) - 16 != count * rows * cols:
        raise ValueError(f'{path}: size does not match header')
    return np.frombuffer(raw, dtype=np.uint8, offset=16).reshape(count, rows, cols)


def read_idx_labels(path):
    """Return an (N,) uint8 array from an IDX1 label file."""
    raw = _read_bytes(path)
    magic, count = struct.unpack('>II', raw[:8])
    if magic != _LABELS_MAGIC:
        raise ValueError(f'{path}: bad label magic number {magic}')
    if len(raw) - 8 != count:
        raise ValueError(f'{path}: size does not match header')
    return np.frombuffer(raw, dtype=np.uint8, offset=8)


def load_mnist_test(dataset_dir='~/datasets/mnist'):
    """Load the MNIST test split. Returns (images, labels)."""
    dataset_dir = os.path.expanduser(dataset_dir)
    images = read_idx_images(_find_file(dataset_dir, IMAGES_STEM))
    labels = read_idx_labels(_find_file(dataset_dir, LABELS_STEM))
    if len(images) != len(labels):
        raise ValueError(
            f'{len(images)} images but {len(labels)} labels in {dataset_dir}')
    return images, labels
