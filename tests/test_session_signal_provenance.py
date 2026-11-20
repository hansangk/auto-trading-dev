import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from session_signal_provenance import mask_session_signals


class SessionSignalProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.times = pd.DatetimeIndex([
            "2025-01-02 14:30Z", "2025-01-02 19:30Z", "2025-01-02 20:30Z",
            "2025-01-03 14:30Z", "2025-01-03 15:30Z", "2025-01-03 16:30Z",
        ])
        self.scores = np.arange(1, 13).reshape(6, 2)

    def test_engine_delay_maps_actual_score_row_to_entry(self):
        base = mask_session_signals(self.scores, self.times, delay=0)
        np.testing.assert_array_equal(np.any(base, axis=1), [True, True, False, True, True, False])
        delayed = mask_session_signals(self.scores, self.times, delay=1)
        # Penultimate and final session scores would both cross the overnight.
        np.testing.assert_array_equal(np.any(delayed, axis=1), [True, False, False, True, False, False])

    def test_shifted_event_provenance_and_engine_delay_are_distinct(self):
        shifted = np.zeros_like(self.scores)
        shifted[2] = [1, 0]  # Event row 1 shifted to score row 2, then next open.
        shifted[3] = [0, 1]  # Event row 2 shifted into next session's score row.
        score_only = mask_session_signals(shifted, self.times, 0, origin_lag=1)
        event = mask_session_signals(shifted, self.times, 0, origin_lag=1, policy="event")
        np.testing.assert_array_equal(np.any(score_only, axis=1), [False, False, False, True, False, False])
        self.assertFalse(np.any(event))
        shifted[:] = 0
        shifted[2] = [1, 0]
        # A rolled penultimate-bar event plus engine delay=1 enters next session.
        self.assertFalse(np.any(mask_session_signals(shifted, self.times, 1, 1, "event")))

    def test_event_lag_zero_matches_score_policy_and_drops_missing_origin(self):
        np.testing.assert_array_equal(
            mask_session_signals(self.scores, self.times, 1),
            mask_session_signals(self.scores, self.times, 1, policy="event"),
        )
        actual = mask_session_signals(self.scores, self.times, 0, origin_lag=1, policy="event")
        np.testing.assert_array_equal(np.any(actual, axis=1), [False, True, False, False, True, False])

    def test_uses_new_york_date_including_dst(self):
        times = pd.DatetimeIndex(["2025-03-09 03:55Z", "2025-03-09 04:00Z", "2025-03-09 07:05Z"])
        result = mask_session_signals(np.ones((3, 1)), times, 0)
        # First pair shares March 8 in NY; the third is March 9 despite the same UTC date.
        np.testing.assert_array_equal(result[:, 0], [1, 0, 0])

    def test_copy_and_known_execution_prefix_invariance(self):
        original = self.scores.copy()
        for policy in ("score", "event"):
            for delay in (0, 1):
                whole = mask_session_signals(self.scores, self.times, delay, 1, policy)
                for n in range(1, len(self.times) + 1):
                    prefix = mask_session_signals(self.scores[:n], self.times[:n], delay, 1, policy)
                    known = max(0, n - 1 - delay)
                    np.testing.assert_array_equal(prefix[:known], whole[:known])
                    self.assertFalse(np.any(prefix[known:]))
        result = mask_session_signals(self.scores, self.times, 0)
        result[0] = 0
        np.testing.assert_array_equal(self.scores, original)

    def test_empty_and_delay_past_calendar(self):
        self.assertEqual(mask_session_signals(np.zeros((0, 4)), [], 0).shape, (0, 4))
        self.assertFalse(np.any(mask_session_signals(self.scores, self.times, 100)))
        self.assertTrue(np.any(mask_session_signals(self.scores, self.times, np.int64(0))))

    def test_invalid_parameters_and_shapes(self):
        for key in ("delay", "origin_lag"):
            for value in (-1, 1.0, True, np.bool_(False), "1"):
                kwargs = dict(delay=0, origin_lag=0)
                kwargs[key] = value
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    mask_session_signals(self.scores, self.times, **kwargs)
        for scores, times in ((np.ones(6), self.times), (self.scores, self.times[:2]),
                              (self.scores, np.ones((6, 1))), (self.scores, [None] * 6)):
            with self.assertRaises(ValueError):
                mask_session_signals(scores, times, 0)
        with self.assertRaises(ValueError):
            mask_session_signals(self.scores, self.times, 0, policy="other")
