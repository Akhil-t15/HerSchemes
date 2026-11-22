from datetime import datetime, timedelta

from app.schemes_repo import is_stale

NOW = datetime(2025, 1, 31, 12, 0, 0)


def test_none_is_stale():
    assert is_stale(None, NOW) is True


def test_just_verified_is_not_stale():
    assert is_stale(NOW, NOW) is False


def test_exactly_30_days_is_not_stale():
    assert is_stale(NOW - timedelta(days=30), NOW) is False


def test_30_days_plus_one_second_is_stale():
    assert is_stale(NOW - timedelta(days=30, seconds=1), NOW) is True


def test_31_days_is_stale():
    assert is_stale(NOW - timedelta(days=31), NOW) is True
