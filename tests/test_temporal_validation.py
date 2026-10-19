import pytest

from src.temporal_validation import in_scope, inside


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [
        ("2025-12-31T00:00:00Z", "2026-01-01T00:00:00Z", False),
        ("2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z", True),
        ("2026-09-30T00:00:00Z", "2026-10-01T00:00:00Z", True),
        ("2026-10-01T00:00:00Z", "2026-10-02T00:00:00Z", False),
        ("2026-09-30T00:00:00Z", "2026-09-30T12:00:00Z", False),
        ("invalid", "2026-01-02T00:00:00Z", False),
    ],
)
def test_temporal_period_excludes_current_october_and_partial_days(start, end, expected):
    assert in_scope({"window_start_utc": start, "window_end_utc": end}) is expected


def test_external_source_cannot_escape_its_own_directory(tmp_path):
    with pytest.raises(ValueError, match="超出"):
        inside(tmp_path, "../unexpected.csv")
