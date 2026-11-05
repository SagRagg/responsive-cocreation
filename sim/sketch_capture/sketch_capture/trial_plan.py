"""Seeded, class-balanced selection of MNIST test samples."""

import numpy as np

NUM_CLASSES = 10


def build_trial_plan(labels, per_digit=10, seed=42):
    """Return the MNIST indices to replay, in trial order.

    Picks `per_digit` distinct samples of every digit 0-9, then shuffles the
    whole selection. The same labels, per_digit and seed always give the same
    sequence, so edge and cloud runs see identical inputs.
    """
    labels = np.asarray(labels)
    # One generator for both steps, so the selection and the order both
    # depend on the seed alone.
    rng = np.random.default_rng(seed)
    chosen = []
    for digit in range(NUM_CLASSES):
        candidates = np.flatnonzero(labels == digit)
        if len(candidates) < per_digit:
            raise ValueError(
                f'digit {digit} has {len(candidates)} samples, '
                f'need {per_digit}')
        chosen.append(rng.choice(candidates, size=per_digit, replace=False))
    return rng.permutation(np.concatenate(chosen)).tolist()
