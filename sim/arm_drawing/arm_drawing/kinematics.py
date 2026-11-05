"""Forward and inverse kinematics of the Kinova Gen3 7-DOF (no gripper).

The joint origins are copied from ros2_kortex `jazzy`,
kortex_description/arms/gen3/7dof/urdf/gen3_macro.xacro, so poses here match
what RViz shows. Every joint rotates about its own z axis.
"""

import numpy as np

JOINT_NAMES = [f'joint_{i}' for i in range(1, 8)]

# (xyz, rpy) of each joint origin relative to its parent link.
_JOINT_ORIGINS = [
    ((0.0, 0.0, 0.15643), (3.1416, 2.7629e-18, -4.9305e-36)),
    ((0.0, 0.005375, -0.12838), (1.5708, 2.1343e-17, -1.1102e-16)),
    ((0.0, -0.21038, -0.006375), (-1.5708, 1.2326e-32, -2.9122e-16)),
    ((0.0, 0.006375, -0.21038), (1.5708, -6.6954e-17, -1.6653e-16)),
    ((0.0, -0.20843, -0.006375), (-1.5708, 2.2204e-16, -6.373e-17)),
    ((0.0, 0.00017505, -0.10593), (1.5708, 9.2076e-28, -8.2157e-15)),
    ((0.0, -0.10593, -0.00017505), (-1.5708, -5.5511e-17, 9.6396e-17)),
]
# bracelet_link -> end_effector_link (fixed).
_EE_ORIGIN = ((0.0, 0.0, -0.061525), (np.pi, 1.09937075168372e-32, 0.0))

# Revolute limits (rad); None = continuous joint.
JOINT_LIMITS = [None, (-2.24, 2.24), None, (-2.57, 2.57),
                None, (-2.09, 2.09), None]

# Kinova "Home" position, used as the IK starting guess.
HOME = np.radians([0.0, 15.0, 180.0, -130.0, 0.0, 55.0, 90.0])


def _origin(xyz, rpy):
    """4x4 transform of a URDF <origin> (fixed-axis roll, pitch, yaw)."""
    r, p, y = rpy
    cr, sr, cp, sp, cy, sy = (np.cos(r), np.sin(r), np.cos(p),
                              np.sin(p), np.cos(y), np.sin(y))
    t = np.eye(4)
    t[:3, :3] = [
        [cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr],
        [sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr],
        [-sp, cp * sr, cp * cr],
    ]
    t[:3, 3] = xyz
    return t


def _rot_z(q):
    """4x4 rotation by `q` rad about z (a revolute joint's motion)."""
    c, s = np.cos(q), np.sin(q)
    t = np.eye(4)
    t[:2, :2] = [[c, -s], [s, c]]
    return t


_ORIGINS = [_origin(*o) for o in _JOINT_ORIGINS]
_EE = _origin(*_EE_ORIGIN)


def _tool(tool_length):
    """4x4 offset of `tool_length` m along z (end effector to pen tip)."""
    t = np.eye(4)
    t[2, 3] = tool_length
    return t


def forward(q, tool_length=0.0):
    """4x4 pose of the tool tip in base_link.

    The tool tip sits `tool_length` metres along the z axis of
    end_effector_link (straight out of the flange).
    """
    t = np.eye(4)
    for origin, angle in zip(_ORIGINS, q):
        t = t @ origin @ _rot_z(angle)
    return t @ _EE @ _tool(tool_length)


def _jacobian(q, tool_length):
    """6x7 geometric Jacobian of the tool tip (linear rows first)."""
    t = np.eye(4)
    axes, points = [], []
    for origin, angle in zip(_ORIGINS, q):
        t = t @ origin
        axes.append(t[:3, 2].copy())
        points.append(t[:3, 3].copy())
        t = t @ _rot_z(angle)
    tip = (t @ _EE @ _tool(tool_length))[:3, 3]
    jac = np.zeros((6, 7))
    for i, (z, p) in enumerate(zip(axes, points)):
        jac[:3, i] = np.cross(z, tip - p)
        jac[3:, i] = z
    return jac


def within_limits(q):
    """True if every joint angle in `q` is inside JOINT_LIMITS."""
    return all(lim is None or lim[0] <= a <= lim[1]
               for a, lim in zip(q, JOINT_LIMITS))


def solve_ik(position, z_axis, seed, tool_length=0.0,
             tol=1e-5, max_iter=300, damping=0.05):
    """Damped least squares IK for a tool position and pointing direction.

    Only the tool's z axis is constrained (rotation about it is free), which
    leaves the redundant joints to stay close to `seed`. Returns the joint
    angles, or None if it does not converge inside the joint limits.
    """
    q = np.array(seed, dtype=float)
    target_p = np.asarray(position, dtype=float)
    target_z = np.asarray(z_axis, dtype=float)
    target_z = target_z / np.linalg.norm(target_z)
    for _ in range(max_iter):
        pose = forward(q, tool_length)
        err_p = target_p - pose[:3, 3]
        # Small-angle orientation error between the current and target z
        # axes; zero when they align, whatever the roll about z.
        err_r = np.cross(pose[:3, 2], target_z)
        err = np.concatenate([err_p, err_r])
        if np.linalg.norm(err) < tol:
            if within_limits(q):
                return q
            return None
        # Damped least squares step: stays bounded near singularities,
        # where a plain pseudo-inverse would blow up.
        jac = _jacobian(q, tool_length)
        step = jac.T @ np.linalg.solve(
            jac @ jac.T + damping ** 2 * np.eye(6), err)
        q = q + step
        for i, lim in enumerate(JOINT_LIMITS):
            if lim is not None:
                q[i] = np.clip(q[i], lim[0], lim[1])
    return None
