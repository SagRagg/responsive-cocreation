"""Tests for the /ground_truth JSON payload (sketch_capture.ground_truth)."""

import json

import numpy as np

from sketch_capture.ground_truth import ground_truth_json


def test_payload_fields_and_stamp():
    data = json.loads(ground_truth_json(3, 6788, 7, 1760000000, 123456789))
    assert data == {
        'trial': 3,
        'mnist_index': 6788,
        'digit': 7,
        'stamp': {'sec': 1760000000, 'nanosec': 123456789},
    }


def test_numpy_integers_are_serialised():
    """The node passes numpy integers from the MNIST arrays, which
    json.dumps cannot encode unless converted."""
    text = ground_truth_json(np.int64(1), np.int64(12), np.uint8(4),
                             np.int32(5), np.uint32(6))
    data = json.loads(text)
    assert data['digit'] == 4
    assert data['stamp'] == {'sec': 5, 'nanosec': 6}
