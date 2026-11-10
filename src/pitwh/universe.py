"""Historical S&P 500 membership and the reproducible security sample."""

from datetime import date
from pathlib import Path

import pandas as pd

from pitwh import config

# fja05680/sp500 (MIT). Pinned so the sample is reproducible.
SP500_COMMIT = "a2430f2af0c79ddf0748e91de11bdeb1616ab5a7"
SP500_URL = (
    f"https://raw.githubusercontent.com/fja05680/sp500/{SP500_COMMIT}/"
    "S%26P%20500%20Historical%20Components%20%26%20Changes%20(Updated).csv"
)


def membership_intervals(snapshots: pd.DataFrame) -> pd.DataFrame:
    """Turn dated constituent snapshots into (ticker, start_date, end_date) intervals.

    end_date is the first snapshot date on which the ticker is absent (exclusive),
    or null if it is still a member in the last snapshot.
    """
    snaps = snapshots.assign(date=pd.to_datetime(snapshots["date"]).dt.date).sort_values("date")
    dates = list(snaps["date"])
    open_since: dict[str, date] = {}
    rows = []
    for d, tickers in zip(dates, snaps["tickers"], strict=True):
        current = set(tickers.split(","))
        for t in current - open_since.keys():
            open_since[t] = d
        for t in open_since.keys() - current:
            rows.append((t, open_since.pop(t), d))
    rows.extend((t, start, None) for t, start in open_since.items())
    out = pd.DataFrame(rows, columns=["ticker", "start_date", "end_date"])
    return out.sort_values(["ticker", "start_date"]).reset_index(drop=True)


def in_window(intervals: pd.DataFrame, start: date = config.START_DATE) -> pd.DataFrame:
    keep = intervals["end_date"].isna() | (intervals["end_date"] > start)
    return intervals[keep].reset_index(drop=True)


def load_snapshots(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype={"tickers": str})
