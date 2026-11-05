"""Tests for the seeded trial plan (sketch_capture.trial_plan): class balance,
no repeats, reproducibility for a seed, and shuffled order.
"""

import numpy as np
import pytest

from sketch_capture.trial_plan import build_trial_plan

LABELS = np.tile(np.arange(10), 50)  # 500 samples, 50 per digit


def test_balanced():
    plan = build_trial_plan(LABELS, per_digit=10, seed=1)
    assert len(plan) == 100
    counts = np.bincount(LABELS[plan], minlength=10)
    assert counts.tolist() == [10] * 10


def test_no_repeated_samples():
    plan = build_trial_plan(LABELS, per_digit=10, seed=1)
    assert len(set(plan)) == len(plan)


def test_deterministic():
    assert build_trial_plan(LABELS, 10, 7) == build_trial_plan(LABELS, 10, 7)


def test_seed_changes_sequence():
    assert build_trial_plan(LABELS, 10, 7) != build_trial_plan(LABELS, 10, 8)


def test_shuffled_not_grouped():
    plan = build_trial_plan(LABELS, per_digit=10, seed=3)
    assert LABELS[plan].tolist() != sorted(LABELS[plan].tolist())


def test_too_many_requested():
    with pytest.raises(ValueError):
        build_trial_plan(LABELS, per_digit=51, seed=0)
