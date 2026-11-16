"""Fixed time frame of the synthetic dataset.

Everything is derived from ``as_of`` (the last day of the dataset, IST), never
from the wall clock, so the same seed always produces the same data. Times are
UTC epoch seconds internally; IST only matters for time-of-day curves.
Used by every factory and scenario in ``datagen``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

IST_OFFSET_S = 19_800
DAY_S = 86_400
HOUR_S = 3_600
MINUTE_S = 60


def ist_midnight_utc(day: date) -> int:
    """Return the UTC epoch second of ``day`` 00:00 IST."""
    return int(datetime(day.year, day.month, day.day, tzinfo=UTC).timestamp()) - IST_OFFSET_S


def to_datetime(ts: int | float) -> datetime:
    """Convert a UTC epoch second to an aware UTC ``datetime``."""
    return datetime.fromtimestamp(int(ts), tz=UTC)


@dataclass(frozen=True)
class Timebase:
    """Dataset time frame.

    Attributes:
        as_of: Last calendar day of the dataset (IST).
        end_ts: Exclusive end (``as_of`` + 1 day, 00:00 IST).
        window_start_ts: Start of the 14-day alert window.
        history_start_ts: Start of the 90-day backstory before the window.
        dataset_start_ts: Start of the whole dataset.
    """

    as_of: date
    end_ts: int
    window_start_ts: int
    history_start_ts: int
    dataset_start_ts: int

    @classmethod
    def build(cls, as_of: date, dataset_days: int, window_days: int, history_days: int) -> Timebase:
        """Derive the frame from ``as_of`` and the configured spans."""
        end = ist_midnight_utc(as_of + timedelta(days=1))
        window_start = end - window_days * DAY_S
        return cls(
            as_of=as_of,
            end_ts=end,
            window_start_ts=window_start,
            history_start_ts=window_start - history_days * DAY_S,
            dataset_start_ts=end - dataset_days * DAY_S,
        )

    def month_starts(self) -> list[int]:
        """IST month starts (UTC epoch) from the dataset start month to ``as_of``."""
        start = to_datetime(self.dataset_start_ts + IST_OFFSET_S).date().replace(day=1)
        out: list[int] = []
        current = start
        while current <= self.as_of:
            out.append(ist_midnight_utc(current))
            year, month = (current.year + 1, 1) if current.month == 12 else (current.year, current.month + 1)
            current = date(year, month, 1)
        return out
