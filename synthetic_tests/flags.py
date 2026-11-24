"""Flags the synthetic tests read from the environment, in one place: the tests import KEEP_GOING from here, so a check of the flag is about the flag they use.

HRP_KEEP_GOING: a test lists every check that fails instead of stopping at the first (to see what a change fixes). It is on for any value but empty or 0.
"""
import os


def keep_going(value):
    return value not in (None, "", "0")


KEEP_GOING = keep_going(os.environ.get("HRP_KEEP_GOING"))
