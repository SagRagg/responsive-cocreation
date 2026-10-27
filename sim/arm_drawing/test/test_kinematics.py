import numpy as np

from arm_drawing.kinematics import HOME, forward, solve_ik, within_limits


def test_zero_pose_is_straight_up():
    # Sum of the URDF link offsets along z.
    assert np.isclose(forward(np.zeros(7))[2, 3], 1.18745, atol=1e-4)


def test_home_matches_kinova_home_pose():
    # Kinova lists Home at x 0.576, z 0.434 with its 0.12 m default tool,
    # the tool pointing straight forward.
    pose = forward(HOME, tool_length=0.12)
    assert np.allclose(pose[:3, 3], [0.576, 0.001, 0.434], atol=2e-3)
    assert np.allclose(pose[:3, 2], [1, 0, 0], atol=1e-3)


def test_ik_reaches_pen_down_target():
    target = np.array([0.45, 0.05, 0.02])
    q = solve_ik(target, [0, 0, -1], HOME, tool_length=0.1)
    assert q is not None and within_limits(q)
    pose = forward(q, tool_length=0.1)
    assert np.allclose(pose[:3, 3], target, atol=1e-4)
    assert np.allclose(pose[:3, 2], [0, 0, -1], atol=1e-3)


def test_ik_out_of_reach_returns_none():
    assert solve_ik([2.0, 0, 0], [0, 0, -1], HOME) is None
