"""Decode the /strokes JSON payload (see docs/interfaces.md)."""

import json


def parse_strokes(text):
    """Return (trial, digit, confidence, source_stamp_ns, strokes).

    Raises ValueError if the payload is not valid.
    """
    try:
        payload = json.loads(text)
        trial = int(payload['trial'])
        digit = int(payload['digit'])
        stamp = payload['source_stamp']
        source_ns = int(stamp['sec']) * 1_000_000_000 + int(stamp['nanosec'])
        strokes = payload['strokes']
    except (ValueError, TypeError, KeyError) as exc:
        raise ValueError(f'bad /strokes payload: {exc}') from exc
    if not 0 <= digit <= 9:
        raise ValueError(f'digit {digit} out of range')
    confidence = payload.get('confidence')
    return trial, digit, confidence, source_ns, strokes
