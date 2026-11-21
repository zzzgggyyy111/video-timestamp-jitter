"""Red tests for the RTP video jitter buffer.

All 15 tests exercise the public stubs in ``jitter.buffer``.  They use only
pytest and explicit time values -- no sleeps, no randomness, no network.
"""

import pytest

from jitter import (
    JitterError,
    adapt_delay,
    detect_wrap,
    estimate_jitter,
    insert,
    jitter_batch,
    playout,
    reorder,
    validate,
)


def pkt(seq, ts, arrival):
    """Build a packet with the documented wire fields."""
    return {"seq": seq, "ts": ts, "arrival": arrival}


def make_buffer(clock=90000):
    """Fresh jitter buffer as described by jitter.buffer.insert."""
    return {
        "clock": clock,
        "now": 0,
        "base_ts": None,
        "base_play": None,
        "slots": {},
        "next_seq": None,
    }


def seqs_or_none(entries):
    """Map a playout/reorder list to sequence numbers, keeping placeholders."""
    return [None if entry is None else entry["seq"] for entry in entries]


# ---------------------------------------------------------------------------
# One test per documented defect.
# ---------------------------------------------------------------------------


def test_estimate_jitter_normalizes_by_rtp_timestamp():
    """Defect 1: jitter must subtract timestamp progress, not just arrivals."""
    arrivals = [0, 20, 45]
    ts = [0, 1800, 4050]  # 45 ms at 90 kHz == 4050 ticks
    # Arrival gaps differ (20 ms, 25 ms) but each matches its RTP gap exactly,
    # so the correct transit difference is zero on both steps.
    assert estimate_jitter(arrivals, ts, 90000) == pytest.approx(0.0, abs=1e-9)


def test_reorder_is_stable_for_duplicate_sequence():
    """Defect 2: equal sequence numbers keep their first-seen order."""
    first = pkt(2, 0, 0)
    second = pkt(2, 0, 1)
    later = pkt(4, 0, 2)
    result = reorder([second, first, later])
    # Anchor seq=2, gap at 3 -- and the duplicate group keeps input order.
    assert [None if p is None else p["arrival"] for p in result] == [1, 0, None, 2]


def test_insert_applies_target_delay():
    """Defect 3: a packet must not play before arrival + target_delay."""
    buffer = make_buffer()
    inserted = insert(pkt(10, 0, 1000), buffer, 200)
    assert inserted["status"] == "queued"
    assert inserted["play_at"] == 1200

    assert playout(buffer, 1000) == []  # 200 ms early: nothing is due
    due = playout(buffer, 1200)
    assert seqs_or_none(due) == [10]


def test_playout_keeps_missing_slot_as_none():
    """Defect 4: a lost packet leaves a None slot instead of shrinking time."""
    buffer = make_buffer()
    insert(pkt(0, 0, 0), buffer, 50)  # play_at = 50
    insert(pkt(2, 1800, 20), buffer, 50)  # play_at = 50 + 20 = 70

    released = playout(buffer, 70)
    assert seqs_or_none(released) == [0, None, 2]
    assert released[1] is None


def test_adapt_delay_clamps_to_minimum():
    """Defect 5: tiny jitter must not collapse the delay to zero."""
    assert adapt_delay(0.0, 30.0, 200.0) == 30.0
    assert adapt_delay(10.0, 0.0, 100.0) == 20.0
    assert adapt_delay(500.0, 0.0, 100.0) == 100.0


def test_detect_wrap_across_16_bit_boundary():
    """Defect 6: after 65535 the stream continues at 0, it is not 'old'."""
    assert detect_wrap(65535, 0) is True
    assert detect_wrap(65535, 65534) is False
    assert detect_wrap(100, 101) is False

    wrapped = [
        pkt(65534, 0, 0),
        pkt(65535, 1800, 20),
        pkt(0, 3600, 40),
        pkt(1, 5400, 60),
    ]
    assert seqs_or_none(reorder(wrapped)) == [65534, 65535, 0, 1]


def test_validate_reports_timestamp_regression():
    """Defect 7: a backwards RTP timestamp must be reported, not played back."""
    problems = validate([pkt(0, 1000, 0), pkt(1, 900, 10)], 90000)
    assert problems == ["timestamp regression at seq 1"]


def test_insert_deduplicates_repeated_sequence():
    """Defect 8: the same sequence number must not be queued twice."""
    buffer = make_buffer()
    first = insert(pkt(5, 0, 0), buffer, 50)
    duplicate = insert(pkt(5, 0, 10), buffer, 50)

    assert first["status"] == "queued"
    assert duplicate["status"] == "duplicate"

    released = playout(buffer, 50)
    assert seqs_or_none(released) == [5]
    assert released[0]["arrival"] == 0  # the first copy wins


def test_batch_keeps_stream_state_isolated():
    """Defect 9: streams in one batch must not share buffers or slots."""
    streams = {
        "a": [pkt(0, 0, 0), pkt(1, 1800, 20)],
        "b": [pkt(0, 9000, 0), pkt(1, 10800, 20)],
    }
    result = jitter_batch(
        streams, {"clock": 90000, "min_delay": 10, "max_delay": 100}
    )

    assert set(result) == {"a", "b"}
    assert seqs_or_none(result["a"]["packets"]) == [0, 1]
    assert seqs_or_none(result["b"]["packets"]) == [0, 1]
    assert result["a"]["packets"][0]["ts"] == 0
    assert result["b"]["packets"][0]["ts"] == 9000


def test_validate_reports_zero_clock():
    """Defect 10: clock=0 is a validation problem, not a division by zero."""
    assert validate([pkt(0, 0, 0)], 0) == ["clock must be positive"]


# ---------------------------------------------------------------------------
# Five edge/combination cases.
# ---------------------------------------------------------------------------


def test_constant_arrival_has_zero_jitter():
    """Evenly paced arrivals on the same 90 kHz grid have zero jitter."""
    assert estimate_jitter([0, 20, 40, 60], [0, 1800, 3600, 5400], 90000) == (
        pytest.approx(0.0)
    )


def test_adapt_delay_fixed_when_min_equals_max():
    """A pinned delay window overrides the 2x-jitter target."""
    assert adapt_delay(5.0, 40.0, 40.0) == 40.0
    assert adapt_delay(500.0, 40.0, 40.0) == 40.0


def test_empty_stream_returns_empty():
    """Empty input is valid and produces empty output, not an error."""
    assert playout(make_buffer(), 1000) == []

    result = jitter_batch(
        {"empty": []}, {"clock": 90000, "min_delay": 10, "max_delay": 100}
    )
    assert result["empty"] == {"jitter": 0.0, "delay": 10.0, "packets": []}


def test_estimate_jitter_rejects_zero_clock():
    """Normalising by a zero clock must raise JitterError, not ZeroDivisionError."""
    with pytest.raises(JitterError):
        estimate_jitter([0, 10], [0, 900], 0)


def test_batch_preserves_stream_order():
    """All-valid batches keep the caller's stream order and content."""
    streams = {
        "z": [pkt(0, 0, 0)],
        "a": [pkt(0, 1000, 0)],
        "m": [pkt(0, 2000, 0)],
    }
    result = jitter_batch(
        streams, {"clock": 90000, "min_delay": 5, "max_delay": 50}
    )
    assert list(result) == ["z", "a", "m"]
    assert all(entry["delay"] == 5.0 for entry in result.values())
