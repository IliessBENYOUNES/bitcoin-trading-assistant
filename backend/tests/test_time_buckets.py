"""Tests pour le module time_buckets."""

import pytest
from datetime import datetime, timezone, timedelta

from app.utils.time_buckets import (
    VALID_TIMEFRAMES,
    get_timeframe_hours,
    is_valid_timeframe,
    normalize_to_utc,
    align_to_bucket,
    get_rolling_window,
    calculate_expected_count,
    calculate_freshness_status,
    calculate_global_status,
)


class TestValidTimeframes:
    def test_valid_list(self):
        assert "30m" in VALID_TIMEFRAMES
        assert "1h" in VALID_TIMEFRAMES
        assert "4h" in VALID_TIMEFRAMES
        assert "1d" in VALID_TIMEFRAMES
        assert "4d" not in VALID_TIMEFRAMES

    def test_is_valid(self):
        assert is_valid_timeframe("4h") is True
        assert is_valid_timeframe("4d") is False

    def test_hours(self):
        assert get_timeframe_hours("30m") == 0.5
        assert get_timeframe_hours("1h") == 1.0
        assert get_timeframe_hours("4h") == 4.0
        assert get_timeframe_hours("1d") == 24.0

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            get_timeframe_hours("4d")


class TestNormalizeToUtc:
    def test_naive_becomes_utc(self):
        dt = datetime(2026, 1, 7, 12, 0, 0)
        result = normalize_to_utc(dt)
        assert result.tzinfo == timezone.utc

    def test_other_tz_converted(self):
        paris = timezone(timedelta(hours=1))
        dt = datetime(2026, 1, 7, 13, 0, 0, tzinfo=paris)
        result = normalize_to_utc(dt)
        assert result.hour == 12


class TestAlignToBucket:
    def test_4h_bucket_0(self):
        dt = datetime(2026, 1, 7, 3, 30, 0, tzinfo=timezone.utc)
        assert align_to_bucket(dt, "4h").hour == 0

    def test_4h_bucket_4(self):
        dt = datetime(2026, 1, 7, 7, 59, 0, tzinfo=timezone.utc)
        assert align_to_bucket(dt, "4h").hour == 4

    def test_4h_bucket_8(self):
        dt = datetime(2026, 1, 7, 11, 0, 0, tzinfo=timezone.utc)
        assert align_to_bucket(dt, "4h").hour == 8

    def test_4h_bucket_12(self):
        dt = datetime(2026, 1, 7, 14, 35, 0, tzinfo=timezone.utc)
        assert align_to_bucket(dt, "4h").hour == 12

    def test_4h_bucket_16(self):
        dt = datetime(2026, 1, 7, 19, 0, 0, tzinfo=timezone.utc)
        assert align_to_bucket(dt, "4h").hour == 16

    def test_4h_bucket_20(self):
        dt = datetime(2026, 1, 7, 23, 59, 0, tzinfo=timezone.utc)
        assert align_to_bucket(dt, "4h").hour == 20

    def test_30m_first_half(self):
        dt = datetime(2026, 1, 7, 14, 15, 0, tzinfo=timezone.utc)
        result = align_to_bucket(dt, "30m")
        assert result.minute == 0

    def test_30m_second_half(self):
        dt = datetime(2026, 1, 7, 14, 45, 0, tzinfo=timezone.utc)
        result = align_to_bucket(dt, "30m")
        assert result.minute == 30

    def test_1d(self):
        dt = datetime(2026, 1, 7, 15, 45, 0, tzinfo=timezone.utc)
        result = align_to_bucket(dt, "1d")
        assert result.hour == 0
        assert result.minute == 0

    def test_invalid_raises(self):
        dt = datetime(2026, 1, 7, 12, 0, 0, tzinfo=timezone.utc)
        with pytest.raises(ValueError):
            align_to_bucket(dt, "4d")


class TestRollingWindow:
    def test_7_days_4h(self):
        anchor = datetime(2026, 1, 7, 14, 35, 0, tzinfo=timezone.utc)
        start, end = get_rolling_window(anchor, 7, "4h")
        assert end.hour == 12  # Aligné au bucket 12
        assert (end - start).days == 7


class TestExpectedCount:
    def test_7_days_4h(self):
        start = datetime(2025, 12, 31, 12, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 1, 7, 12, 0, 0, tzinfo=timezone.utc)
        count = calculate_expected_count(start, end, "4h")
        assert count == 43


class TestFreshnessStatus:
    def test_fresh(self):
        assert calculate_freshness_status(3.5, "4h") == "FRESH"

    def test_stale(self):
        assert calculate_freshness_status(5.0, "4h") == "STALE"

    def test_very_stale(self):
        assert calculate_freshness_status(10.0, "4h") == "VERY_STALE"


class TestGlobalStatus:
    def test_ok(self):
        assert calculate_global_status("OK", "FRESH") == "OK"

    def test_stale(self):
        assert calculate_global_status("OK", "STALE") == "STALE"

    def test_gaps_priority(self):
        assert calculate_global_status("GAPS_DETECTED", "FRESH") == "GAPS"
        assert calculate_global_status("GAPS_DETECTED", "STALE") == "GAPS"