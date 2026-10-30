"""Payload for /ground_truth: the true label of the sketch just published."""

import json


def ground_truth_json(trial, mnist_index, digit, stamp_sec, stamp_nanosec):
    """Return the JSON string published on /ground_truth.

    `stamp` must be the `/sketch_image` `header.stamp` of the same trial: it is
    the key listeners use to join this message to the sketch and to `/strokes`.
    """
    return json.dumps({
        'trial': int(trial),
        'mnist_index': int(mnist_index),
        'digit': int(digit),
        'stamp': {'sec': int(stamp_sec), 'nanosec': int(stamp_nanosec)},
    })
