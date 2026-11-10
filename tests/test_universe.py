from datetime import date

import pandas as pd

from pitwh.universe import in_window, membership_intervals

SNAPSHOTS = pd.DataFrame(
    {
        "date": ["2014-06-02", "2014-09-02", "2015-03-02", "2016-01-04", "2017-05-01"],
        "tickers": ["AAA,BBB,OLD", "AAA,BBB", "AAA,BBB,CCC", "AAA,CCC", "AAA,CCC,BBB"],
    }
)


def _intervals():
    return membership_intervals(SNAPSHOTS)


def test_removal_closes_interval_on_first_absent_snapshot():
    bbb = _intervals().query("ticker == 'BBB'")
    assert list(zip(bbb.start_date, bbb.end_date, strict=True)) == [
        (date(2014, 6, 2), date(2016, 1, 4)),
        (date(2017, 5, 1), None),
    ]


def test_current_member_has_open_interval():
    aaa = _intervals().query("ticker == 'AAA'")
    assert len(aaa) == 1
    assert aaa.end_date.iloc[0] is None


def test_window_drops_names_gone_before_start():
    tickers = set(in_window(_intervals(), date(2015, 1, 1)).ticker)
    assert "OLD" not in tickers
    assert {"AAA", "BBB", "CCC"} <= tickers
