from datetime import date

from pitwh.calendar import trading_sessions


def _sessions():
    return trading_sessions(date(2024, 6, 1), date(2024, 12, 31)).set_index("session_date")


def test_holiday_is_not_a_session():
    assert date(2024, 7, 4) not in _sessions().index


def test_open_shifts_with_daylight_saving():
    s = _sessions()
    assert s.loc[date(2024, 7, 1), "market_open_utc"] == "2024-07-01 13:30:00"
    assert s.loc[date(2024, 12, 2), "market_open_utc"] == "2024-12-02 14:30:00"


def test_day_after_thanksgiving_closes_early():
    assert _sessions().loc[date(2024, 11, 29), "market_close_utc"] == "2024-11-29 18:00:00"
