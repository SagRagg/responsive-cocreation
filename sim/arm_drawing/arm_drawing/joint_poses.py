"""Precompute the fixed joint trajectory the arm plays for each digit.

Run once offline (`ros2 run arm_drawing make_joint_poses`, or
`python3 -m arm_drawing.joint_poses` from sim/arm_drawing). The result is
config/digit_poses.json, which the drawing node loads at start-up, so no
planning happens during a trial.

Each digit's trajectory starts and ends at the ready pose above the paper
centre. Between strokes the pen lifts by `lift` and travels above the paper.
"""

import argparse
import json
import os

import numpy as np

from arm_drawing.kinematics import (HOME, JOINT_LIMITS, JOINT_NAMES,
                                    forward, solve_ik)
from arm_drawing.templates import STROKE_TEMPLATES

# Paper placement in base_link (metres) and motion settings.
DEFAULTS = {
    'paper_center_x': 0.45,   # in front of the base
    'paper_center_y': 0.0,
    'paper_z': 0.0,           # table height = base mounting surface
    'paper_size': 0.20,       # side of the square the 0-1 canvas maps onto
    'lift': 0.03,             # pen-up height above the paper
    'ready_height': 0.10,     # ready pose height above the paper centre
    'tool_length': 0.10,      # pen tip distance from end_effector_link
    'spacing': 0.02,          # resample step, canvas units (4 mm on 0.20 m)
    'draw_speed': 0.05,       # m/s, pen down
    'travel_speed': 0.10,     # m/s, pen up
    'ready_move_time': 2.0,   # s, ready pose <-> first/last point
    'max_joint_speed_ratio': 0.5,  # of each joint's velocity limit
}

# Joint velocity limits from the URDF (rad/s).
JOINT_SPEED_LIMITS = [1.3963] * 4 + [1.2218] * 3

PEN_DOWN = np.array([0.0, 0.0, -1.0])


def resample(points, spacing):
    """Points along a polyline, roughly `spacing` apart, keeping its corners."""
    points = np.asarray(points, dtype=float)
    out = [points[0]]
    for a, b in zip(points[:-1], points[1:]):
        n = max(1, int(np.ceil(np.linalg.norm(b - a) / spacing)))
        for k in range(1, n + 1):
            out.append(a + (b - a) * k / n)
    return np.array(out)


def canvas_to_base(u, v, cfg, height=0.0):
    """Canvas (u right, v down, 0-1) to a base_link point.

    The top of the canvas is the far edge of the paper and canvas right is
    the robot's -y, so the digit reads upright to someone standing behind the
    arm looking along +x.
    """
    size = cfg['paper_size']
    return np.array([
        cfg['paper_center_x'] + (0.5 - v) * size,
        cfg['paper_center_y'] + (0.5 - u) * size,
        cfg['paper_z'] + height,
    ])


def cartesian_path(strokes, cfg):
    """Tool-tip waypoints for one digit as (xyz, pen_down) pairs.

    Does not include the ready pose at either end.
    """
    path = []
    for stroke in strokes:
        pts = resample(stroke, cfg['spacing'])
        path.append((canvas_to_base(*pts[0], cfg, cfg['lift']), False))
        for u, v in pts:
            path.append((canvas_to_base(u, v, cfg), True))
        path.append((canvas_to_base(*pts[-1], cfg, cfg['lift']), False))
    # A stroke that starts where the last one ended gives two identical
    # pen-up points; the controller needs strictly increasing times.
    return [w for i, w in enumerate(path)
            if i == 0 or not np.allclose(w[0], path[i - 1][0])]


def ready_position(cfg):
    """Tool-tip position of the ready pose: `ready_height` above the paper
    centre, in base_link (m)."""
    return canvas_to_base(0.5, 0.5, cfg, cfg['ready_height'])


def solve_ready(cfg):
    """Joint angles of the ready pose, pen pointing straight down.

    Raises:
        RuntimeError: If IK finds no solution from HOME.
    """
    q = solve_ik(ready_position(cfg), PEN_DOWN, HOME, cfg['tool_length'])
    if q is None:
        raise RuntimeError('no IK solution for the ready pose')
    return q


def _segment_time(q0, q1, p0, p1, speed, cfg):
    """Duration (s) of one segment: the Cartesian time at `speed`, or longer
    if any joint would exceed `max_joint_speed_ratio` of its limit."""
    t = np.linalg.norm(p1 - p0) / speed
    for a, b, limit in zip(q0, q1, JOINT_SPEED_LIMITS):
        t = max(t, abs(b - a) / (limit * cfg['max_joint_speed_ratio']))
    return t


def digit_trajectory(digit, cfg, ready_q):
    """Timed joint trajectory for one digit, ready pose to ready pose."""
    ready_p = ready_position(cfg)
    times, joints, xyz, pen = [], [], [], []
    q_prev, p_prev, t = ready_q, ready_p, 0.0
    for i, (p, down) in enumerate(cartesian_path(STROKE_TEMPLATES[digit], cfg)):
        # Seeding IK with the previous solution keeps consecutive poses on
        # the same branch, so the redundant joints do not jump.
        q = solve_ik(p, PEN_DOWN, q_prev, cfg['tool_length'])
        if q is None:
            raise RuntimeError(f'digit {digit}: no IK solution at {p}')
        if i == 0:
            # First move leaves the ready pose: at least ready_move_time so it
            # stays gentle even though the distance is short.
            t += max(cfg['ready_move_time'],
                     _segment_time(q_prev, q, p_prev, p, cfg['travel_speed'], cfg))
        else:
            # Draw speed only between two pen-down points; lifts, lowers and
            # pen-up travel use the faster travel speed.
            speed = cfg['draw_speed'] if down and pen[-1] else cfg['travel_speed']
            t += _segment_time(q_prev, q, p_prev, p, speed, cfg)
        times.append(t)
        joints.append(q)
        xyz.append(p)
        pen.append(down)
        q_prev, p_prev = q, p
    t += max(cfg['ready_move_time'],
             _segment_time(q_prev, ready_q, p_prev, ready_p, cfg['travel_speed'], cfg))
    times.append(t)
    joints.append(ready_q)
    xyz.append(ready_p)
    pen.append(False)
    # Rounded so the committed JSON is compact and stable between runs.
    return {
        'time': [round(x, 4) for x in times],
        'joints': [[round(float(a), 6) for a in q] for q in joints],
        'xyz': [[round(float(a), 5) for a in p] for p in xyz],
        'pen_down': pen,
    }


def build_pose_table(cfg=None):
    """Build the full table the drawing node loads.

    Args:
        cfg: Overrides for DEFAULTS, or None.

    Returns:
        Dict with 'settings', 'joint_names', 'ready' (joint angles) and
        'digits' ('0'-'9' -> digit_trajectory() output). Digit keys are
        strings because the table is stored as JSON.
    """
    cfg = dict(DEFAULTS, **(cfg or {}))
    ready_q = solve_ready(cfg)
    return {
        'settings': cfg,
        'joint_names': JOINT_NAMES,
        'ready': [round(float(a), 6) for a in ready_q],
        'digits': {str(d): digit_trajectory(d, cfg, ready_q)
                   for d in sorted(STROKE_TEMPLATES)},
    }


def check_pose_table(table, tol=1e-3):
    """Largest tool-tip error (m) of the stored joints; raises if over `tol`
    or if any joint is outside its limits.

    Recomputes forward kinematics from the rounded joint angles, so it also
    checks that rounding did not move the pen.
    """
    tool = table['settings']['tool_length']
    worst = 0.0
    for digit, traj in table['digits'].items():
        for q, p in zip(traj['joints'], traj['xyz']):
            for a, lim in zip(q, JOINT_LIMITS):
                if lim is not None and not lim[0] <= a <= lim[1]:
                    raise ValueError(f'digit {digit}: joint outside limits')
            err = np.linalg.norm(forward(q, tool)[:3, 3] - p)
            worst = max(worst, err)
    if worst > tol:
        raise ValueError(f'tool tip error {worst:.4f} m over {tol} m')
    return worst


def default_path():
    """config/digit_poses.json in the package source tree."""
    return os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), 'config', 'digit_poses.json')


def main(args=None):
    """Command-line entry point: build, check and write the pose table."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('-o', '--output', default=default_path(),
                        help='where to write the JSON (default: %(default)s)')
    opts = parser.parse_args(args)
    table = build_pose_table()
    worst = check_pose_table(table)
    os.makedirs(os.path.dirname(os.path.abspath(opts.output)), exist_ok=True)
    with open(opts.output, 'w') as f:
        json.dump(table, f)
    for digit, traj in table['digits'].items():
        print(f'digit {digit}: {len(traj["time"])} points, '
              f'{traj["time"][-1]:.1f} s')
    print(f'max tool tip error {worst * 1000:.3f} mm, wrote {opts.output}')


if __name__ == '__main__':
    main()
