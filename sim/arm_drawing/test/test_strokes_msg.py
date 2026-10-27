import json

import pytest

from arm_drawing.strokes_msg import parse_strokes
from arm_drawing.templates import STROKE_TEMPLATES, matches_template


def payload(**overrides):
    data = {'trial': 3, 'digit': 7, 'confidence': 0.99,
            'source_stamp': {'sec': 1761540000, 'nanosec': 5},
            'frame_id': 'canvas', 'strokes': STROKE_TEMPLATES[7]}
    data.update(overrides)
    return json.dumps(data)


def test_parse_valid_payload():
    trial, digit, conf, source_ns, strokes = parse_strokes(payload())
    assert (trial, digit, conf) == (3, 7, 0.99)
    assert source_ns == 1761540000 * 1_000_000_000 + 5
    assert matches_template(digit, strokes)


@pytest.mark.parametrize('text', [
    'not json', payload(digit=12), json.dumps({'trial': 1}),
])
def test_parse_rejects_bad_payloads(text):
    with pytest.raises(ValueError):
        parse_strokes(text)


def test_template_mismatch_detected():
    assert not matches_template(7, STROKE_TEMPLATES[1])
    assert not matches_template(4, STROKE_TEMPLATES[4][:1])
