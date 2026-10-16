"""Turn a 28x28 MNIST digit into the 280x280 canvas image."""

import numpy as np

SCALE = 10
CANVAS_SIZE = 28 * SCALE


def render_canvas(digit):
    """28x28 uint8 (white digit on black) -> 280x280 uint8 (black ink on white)."""
    digit = np.asarray(digit, dtype=np.uint8)
    if digit.shape != (28, 28):
        raise ValueError(f'expected a 28x28 image, got {digit.shape}')
    big = np.repeat(np.repeat(digit, SCALE, axis=0), SCALE, axis=1)
    return 255 - big
