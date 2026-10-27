import json

import numpy as np
import pytest

from arm_drawing.joint_poses import (DEFAULTS, build_pose_table,
                                     canvas_to_base, check_pose_table,
                                     default_path, resample)
from arm_drawing.templates import STROKE_TEMPLATES


@pytest.fixture(scope='module')
def table():
    return build_pose_table()


def test_resample_keeps_ends_and_spacing():
    pts = resample([[0, 0], [0.1, 0]], 0.02)
    assert np.allclose(pts[0], [0, 0]) and np.allclose(pts[-1], [0.1, 0])
    assert np.allclose(np.diff(pts[:, 0]), 0.02)


def test_canvas_mapping_reads_upright():
    cfg = DEFAULTS
    top_left = canvas_to_base(0, 0, cfg)
    bottom_right = canvas_to_base(1, 1, cfg)
    # Top of the canvas is the far edge (+x), canvas right is -y.
    assert top_left[0] > bottom_right[0]
    assert top_left[1] > bottom_right[1]
    assert np.isclose(top_left[0] - bottom_right[0], cfg['paper_size'])


def test_every_digit_present_and_within_limits(table):
    assert sorted(table['digits']) == [str(d) for d in range(10)]
    assert check_pose_table(table) < 1e-4


def test_trajectories_start_after_zero_and_end_at_ready(table):
    for traj in table['digits'].values():
        assert traj['time'][0] > 0
        assert all(b > a for a, b in zip(traj['time'], traj['time'][1:]))
        assert np.allclose(traj['joints'][-1], table['ready'])


def test_no_joint_jumps_between_points(table):
    for traj in table['digits'].values():
        steps = np.abs(np.diff(np.array(traj['joints']), axis=0))
        assert steps.max() < 0.5


def test_pen_down_points_lie_on_paper(table):
    z = DEFAULTS['paper_z']
    for traj in table['digits'].values():
        for p, down in zip(traj['xyz'], traj['pen_down']):
            if down:
                assert np.isclose(p[2], z)
            else:
                assert p[2] > z


def test_stroke_count_matches_templates(table):
    for d, traj in table['digits'].items():
        down = traj['pen_down']
        starts = sum(1 for a, b in zip(down, down[1:]) if b and not a)
        assert starts == len(STROKE_TEMPLATES[int(d)])


def test_committed_file_is_up_to_date(table):
    with open(default_path()) as f:
        committed = json.load(f)
    assert committed == json.loads(json.dumps(table)), \
        'config/digit_poses.json is stale: rerun make_joint_poses'
