"""Write the XNYS trading calendar as a dbt seed."""

from datetime import date
from pathlib import Path

import exchange_calendars as xcals
import pandas as pd

from pitwh import config


def trading_sessions(start: date, end: date) -> pd.DataFrame:
    cal = xcals.get_calendar("XNYS", start=start.isoformat(), end=end.isoformat())
    sched = cal.schedule
    return pd.DataFrame(
        {
            "session_date": sched.index.date,
            "market_open_utc": sched["open"].dt.strftime("%Y-%m-%d %H:%M:%S"),
            "market_close_utc": sched["close"].dt.strftime("%Y-%m-%d %H:%M:%S"),
        }
    )


def write_calendar_seed(
    path: Path = config.SEEDS_DIR / "trading_calendar.csv",
    start: date = config.CALENDAR_START,
    end: date = config.CALENDAR_END,
) -> int:
    sessions = trading_sessions(start, end)
    sessions.to_csv(path, index=False)
    return len(sessions)
