"""Turn a 28x28 MNIST digit into the image published on /sketch_image."""

import numpy as np

# 10x nearest-neighbour upscale: 28 px -> 280 px, a paper-sized canvas.
SCALE = 10
MNIST_SIZE = 28
CANVAS_SIZE = MNIST_SIZE * SCALE

# mnist: the raw digit, white on black, 28x28 (what the perception model takes).
# canvas: a 280x280 render, black ink on white, like a photo of paper.
IMAGE_FORMATS = ('mnist', 'canvas')


def _check_digit(digit):
    """Return `digit` as uint8, raising ValueError unless it is 28x28."""
    digit = np.asarray(digit, dtype=np.uint8)
    if digit.shape != (MNIST_SIZE, MNIST_SIZE):
        raise ValueError(f'expected a 28x28 image, got {digit.shape}')
    return digit


def render_canvas(digit):
    """28x28 uint8 (white digit on black) -> 280x280 uint8 (black ink on white)."""
    digit = _check_digit(digit)
    big = np.repeat(np.repeat(digit, SCALE, axis=0), SCALE, axis=1)
    return 255 - big


def render_image(digit, image_format='mnist'):
    """The image to publish for `digit` in the given format."""
    if image_format == 'mnist':
        return _check_digit(digit).copy()
    if image_format == 'canvas':
        return render_canvas(digit)
    raise ValueError(
        f'unknown image_format {image_format!r}, expected one of {IMAGE_FORMATS}')
