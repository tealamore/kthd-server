"""Arm-selection policy.

This is the only file you should need to touch to change how arms are picked.
The API calls `choose_arm` at every intervention opportunity and `update`
whenever a reward arrives. Whatever you do in here, return the probability
of the arm you picked: an unbiased analysis needs it (micro-randomized
trial / off-policy evaluation both need it).
"""
import random

POLICY_VERSION = "uniform-v1"

# The arm that is delivered when a participant is not available for
# randomization. It should mean "do nothing".
CONTROL_ARM = "no_intervention"

# Arm name -> randomization probability. Must sum to 1.
ARMS = {
    "no_intervention": 0.5,
    "intervention": 0.5,
}

_rng = random.SystemRandom()

assert abs(sum(ARMS.values()) - 1.0) < 1e-9, "ARMS probabilities must sum to 1"
assert CONTROL_ARM in ARMS


def choose_arm(participant_id: str, context: dict, available: bool) -> tuple[str, float]:
    """Return (arm, probability_of_that_arm)."""
    if not available:
        # Not randomized: control arm with certainty.
        return CONTROL_ARM, 1.0

    names = list(ARMS)
    weights = [ARMS[n] for n in names]
    arm = _rng.choices(names, weights=weights, k=1)[0]
    return arm, ARMS[arm]


def update(participant_id: str, context: dict, arm: str, probability: float, reward: float) -> None:
    """Called after every reward is saved. Uniform randomization learns nothing.

    To switch to a bandit (e.g. Thompson sampling), keep per-arm parameters
    (in memory, or better, in a table), update them here, and sample from
    them in `choose_arm`. Bump POLICY_VERSION when you change the policy.
    """
    return None
