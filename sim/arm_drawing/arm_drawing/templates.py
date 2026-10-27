"""Stroke templates per digit, on the normalised canvas.

Copy of STROKE_TEMPLATES in perception/mnist_perception_node.py
(`perception` branch, 21 Oct). The joint poses are precomputed from these, so
if the perception side changes a template, copy it here and rerun
make_joint_poses. The drawing node warns when a received /strokes does not
match.
"""

STROKE_TEMPLATES = {
    0: [[[0.5,0.1],[0.3,0.15],[0.2,0.35],[0.2,0.65],[0.3,0.85],[0.5,0.9],[0.7,0.85],[0.8,0.65],[0.8,0.35],[0.7,0.15],[0.5,0.1]]],
    1: [[[0.4,0.25],[0.5,0.1],[0.5,0.9]]],
    2: [[[0.2,0.25],[0.35,0.1],[0.6,0.1],[0.8,0.3],[0.65,0.5],[0.2,0.9],[0.8,0.9]]],
    3: [[[0.2,0.15],[0.5,0.1],[0.75,0.25],[0.5,0.5],[0.75,0.75],[0.5,0.9],[0.2,0.85]]],
    4: [[[0.7,0.9],[0.7,0.1]], [[0.7,0.1],[0.2,0.6],[0.85,0.6]]],
    5: [[[0.8,0.1],[0.3,0.1],[0.25,0.45],[0.55,0.45],[0.8,0.6],[0.7,0.85],[0.45,0.9],[0.2,0.8]]],
    6: [[[0.7,0.15],[0.45,0.1],[0.25,0.35],[0.2,0.65],[0.35,0.9],[0.65,0.85],[0.8,0.65],[0.65,0.45],[0.35,0.45],[0.2,0.6]]],
    7: [[[0.2,0.1],[0.8,0.1],[0.55,0.45],[0.4,0.9]]],
    8: [[[0.5,0.5],[0.3,0.4],[0.25,0.2],[0.5,0.1],[0.75,0.2],[0.7,0.4],[0.5,0.5],[0.3,0.6],[0.25,0.8],[0.5,0.9],[0.75,0.8],[0.7,0.6],[0.5,0.5]]],
    9: [[[0.8,0.45],[0.65,0.55],[0.4,0.55],[0.25,0.4],[0.25,0.2],[0.45,0.1],[0.7,0.2],[0.8,0.45],[0.7,0.7],[0.5,0.9]]],
}


def matches_template(digit, strokes, tol=1e-6):
    """True if `strokes` (as decoded from /strokes JSON) equals the template."""
    template = STROKE_TEMPLATES.get(digit)
    if template is None or len(template) != len(strokes):
        return False
    for a, b in zip(template, strokes):
        if len(a) != len(b):
            return False
        for (ax, ay), point in zip(a, b):
            if len(point) != 2:
                return False
            if abs(ax - point[0]) > tol or abs(ay - point[1]) > tol:
                return False
    return True
