import numpy as np
import pytest

from sketch_capture.canvas import render_canvas, render_image


def _digit():
    d = np.zeros((28, 28), dtype=np.uint8)
    d[5:10, 3:6] = 255  # a white stroke on black, as in MNIST
    return d


def test_shape_and_dtype():
    out = render_canvas(_digit())
    assert out.shape == (280, 280)
    assert out.dtype == np.uint8


def test_polarity_black_ink_on_white():
    out = render_canvas(_digit())
    assert out[0, 0] == 255      # background is white
    assert out[60, 40] == 0      # stroke is black


def test_upscale_blocks():
    out = render_canvas(_digit())
    assert (out[50:100, 30:60] == 0).all()
    assert (out[100:110, 30:60] == 255).all()


def test_wrong_shape():
    with pytest.raises(ValueError):
        render_canvas(np.zeros((10, 10), dtype=np.uint8))


def test_mnist_format_is_raw_digit():
    digit = _digit()
    out = render_image(digit, 'mnist')
    assert out.shape == (28, 28) and out.dtype == np.uint8
    np.testing.assert_array_equal(out, digit)   # white digit on black
    assert out.nbytes == 784


def test_canvas_format_matches_render_canvas():
    np.testing.assert_array_equal(render_image(_digit(), 'canvas'),
                                  render_canvas(_digit()))


def test_default_format_is_mnist():
    assert render_image(_digit()).shape == (28, 28)


def test_unknown_format():
    with pytest.raises(ValueError):
        render_image(_digit(), 'jpeg')


def test_mnist_format_checks_shape():
    with pytest.raises(ValueError):
        render_image(np.zeros((10, 10), dtype=np.uint8), 'mnist')
