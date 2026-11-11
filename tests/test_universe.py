from datetime import date

import pandas as pd
import pytest

from pitwh.universe import (
    UnresolvedTickers,
    apply_filer_history,
    filed_during,
    filenames_cite,
    in_window,
    late_filers,
    membership_intervals,
    names_match,
    price_coverage,
    securities_table,
    select_universe,
)

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


def _filings(rows):
    return pd.DataFrame(rows, columns=["filing_date", "form", "primary_document"]).assign(
        filing_date=lambda d: pd.to_datetime(d.filing_date).dt.date
    )


# Dow Inc (CIK 1751788) took the DOW ticker in 2019; Dow Chemical held it until 2017.
DOW_INC = _filings(
    [("2019-05-02", "10-Q", "dow-20190331.htm"), ("2020-02-07", "10-K", "dow-10k.htm")]
)
# Meta's 10-Ks were filed as fb-*.htm while the ticker was FB.
META = _filings(
    [("2021-02-04", "10-K", "fb-20201231.htm"), ("2022-02-03", "10-K", "fb-20211231.htm")]
)
# Arch Capital replaced Twitter in the index the day Twitter left; different company.
ARCH = _filings(
    [("2022-02-25", "10-K", "acgl-20211231.htm"), ("2015-02-27", "10-K", "a201410-k.htm")]
)


def test_reused_ticker_fails_the_filing_window():
    assert not filed_during(DOW_INC, date(1996, 1, 2), date(2017, 8, 31))
    assert filed_during(DOW_INC, date(2019, 4, 2), None)


def test_filenames_link_old_ticker_to_renamed_company():
    assert filenames_cite(META, "FB", date(2013, 12, 23), date(2022, 6, 9))
    assert not filenames_cite(ARCH, "TWTR", date(2013, 12, 23), date(2022, 11, 1))


def test_single_letter_ticker_needs_a_separator():
    # "a201410-k.htm" is Arch Capital's file, not Agilent's (ticker A).
    assert not filenames_cite(ARCH, "A", date(2014, 1, 1), date(2016, 1, 1))


@pytest.mark.parametrize(
    ("a", "b", "same"),
    [
        ("Celgene Corp", "CELGENE CORP /DE/", True),
        ("Twitter Inc", "Twitter, Inc.", True),
        ("Twitter Inc", "ARCH CAPITAL GROUP LTD.", False),
        ("The Kraft Heinz Company", "Kraft Heinz Co", True),
    ],
)
def test_company_names_match_after_dropping_legal_suffixes(a, b, same):
    assert names_match(a, b) is same


POOL = pd.DataFrame(
    [
        # Departed names; OLDB is the former ticker of current member NEWB.
        ("GONE1", date(2010, 1, 4), date(2018, 3, 1)),
        ("GONE2", date(2016, 5, 2), date(2021, 9, 1)),
        ("OLDB", date(2012, 1, 3), date(2020, 6, 1)),
        ("NEWB", date(2020, 6, 1), None),
        ("CUR1", date(2001, 1, 2), None),
        ("CUR2", date(2005, 1, 3), None),
        ("CUR3", date(2017, 1, 3), None),
    ],
    columns=["ticker", "start_date", "end_date"],
)
CIKS = {"GONE1": 1, "GONE2": 2, "OLDB": 3, "NEWB": 3, "CUR1": 4, "CUR2": 5, "CUR3": 6}


def _resolve(ticker, start, end):
    return CIKS[ticker]


def _same(ticker, start, end, cik):
    return CIKS[ticker] == cik


def test_selection_is_reproducible_and_meets_departed_floor():
    a = select_universe(POOL, _resolve, _same, seed=7, size=4, min_departed=2)
    b = select_universe(POOL, _resolve, _same, seed=7, size=4, min_departed=2)
    pd.testing.assert_frame_equal(a, b)
    assert a.cik.nunique() == 4
    open_ciks = set(a[a.end_date.isna()].cik)
    assert len(set(a.cik) - open_ciks) >= 2


def test_renamed_company_carries_both_tickers():
    sel = select_universe(POOL, _resolve, _same, seed=7, size=6, min_departed=2)
    assert set(sel[sel.cik == 3].ticker) == {"OLDB", "NEWB"}


def test_unresolved_ticker_fails_loudly():
    def resolve(ticker, start, end):
        return None if ticker == "GONE2" else CIKS[ticker]

    with pytest.raises(UnresolvedTickers, match="GONE2"):
        select_universe(POOL, resolve, _same, seed=7, size=6, min_departed=2)


SUPPORTED = pd.DataFrame(
    [
        ("DOW", "1972-06-01", "2017-08-31"),
        ("DOW", "2019-03-20", "2026-11-09"),
        ("TWTR", "2013-11-07", "2022-10-28"),
        # COR: Cencora (renamed from ABC, history back to 1995) is still trading;
        # the other row is CoreSite, which used COR until 2021.
        ("COR", "2010-09-23", "2021-12-28"),
        ("COR", "1995-04-04", "2026-11-09"),
        # Kenvue's prices stop after the universe window ends (2026-08-18).
        ("KVUE", "2023-05-04", "2026-10-30"),
    ],
    columns=["ticker", "startDate", "endDate"],
)


def test_price_coverage_uses_the_row_tiingo_actually_serves():
    # Tiingo serves the newest company behind a reused ticker.
    assert not price_coverage(SUPPORTED, "DOW", date(2015, 1, 2), date(2017, 8, 31))
    assert price_coverage(SUPPORTED, "DOW", date(2019, 4, 2), None, today=date(2026, 11, 9))
    assert price_coverage(SUPPORTED, "TWTR", date(2015, 1, 2), date(2022, 10, 28))


def test_price_coverage_follows_the_row_still_trading():
    # The served row is the active one, even when an older holder started later.
    assert price_coverage(SUPPORTED, "COR", date(2015, 1, 2), None, today=date(2026, 11, 9))


def test_open_membership_needs_prices_only_to_the_window_end():
    members = pd.DataFrame(
        {
            "security_id": [1944048],
            "ticker": ["KVUE"],
            "start_date": [date(2023, 8, 25)],
            "end_date": [None],
        }
    )

    class _Resolver:
        sec_map = {"KVUE": 1944048}

        def name(self, cik):
            return "Kenvue Inc."

    securities = securities_table(members, _Resolver(), SUPPORTED, window_end=date(2026, 8, 18))
    assert securities.price_symbol.tolist() == ["KVUE"]


class _NamesOnly:
    """Resolver stand-in: names come from overrides or SEC filings by CIK."""

    sec_map: dict[str, int] = {}

    def name(self, cik):
        return {-1: "Signature Bank", 320193: "Apple Inc."}[cik]


def test_non_sec_filer_keeps_its_override_name():
    # Signature Bank filed with the FDIC, so it has a made-up negative ID and
    # no SEC filings to read a name from.
    members = pd.DataFrame(
        {
            "security_id": [-1, 320193],
            "ticker": ["SBNY", "AAPL"],
            "start_date": [date(2021, 12, 20), date(1996, 1, 2)],
            "end_date": [date(2023, 3, 15), None],
        }
    )
    securities = securities_table(members, _NamesOnly(), SUPPORTED)
    assert securities.set_index("security_id").name.to_dict() == {
        -1: "Signature Bank",
        320193: "Apple Inc.",
    }


MEMBERS = pd.DataFrame(
    {
        "cik": [1730168, 1754301, 320193],
        "ticker": ["AVGO", "FOXA", "AAPL"],
        "start_date": [date(2014, 5, 8), date(2004, 12, 20), date(1996, 1, 2)],
        "end_date": [None, None, None],
        "resolution": ["sec_map"] * 3,
    }
)

# AVGO is one business that re-domiciled twice; FOXA was 21st Century Fox
# until Disney bought it, then the spun-off Fox Corp.
HISTORY = pd.DataFrame(
    [
        ("AVGO", "2014-05-08", 1441634, "2014-05-08", True),
        ("AVGO", "2014-05-08", 1649338, "2016-02-02", True),
        ("AVGO", "2014-05-08", 1730168, "2018-04-04", True),
        ("FOXA", "2004-12-20", 1308161, "2004-12-20", False),
        ("FOXA", "2004-12-20", 1754301, "2019-03-20", False),
    ],
    columns=["ticker", "start_date", "cik", "valid_from", "same_security"],
)


def test_reorganized_company_keeps_one_security_with_each_filer_in_turn():
    members, filers = apply_filer_history(MEMBERS, HISTORY)
    avgo = members[members.ticker == "AVGO"]
    assert avgo[["security_id", "start_date", "end_date"]].values.tolist() == [
        [1730168, date(2014, 5, 8), None]
    ]
    assert filers[filers.security_id == 1730168].values.tolist() == [
        [1730168, 1441634, None, date(2016, 2, 2)],
        [1730168, 1649338, date(2016, 2, 2), date(2018, 4, 4)],
        [1730168, 1730168, date(2018, 4, 4), None],
    ]


def test_merged_away_company_becomes_its_own_departed_security():
    members, filers = apply_filer_history(MEMBERS, HISTORY)
    foxa = members[members.ticker == "FOXA"]
    assert foxa[["security_id", "start_date", "end_date"]].values.tolist() == [
        [1308161, date(2004, 12, 20), date(2019, 3, 20)],
        [1754301, date(2019, 3, 20), None],
    ]
    assert filers[filers.security_id.isin([1308161, 1754301])].values.tolist() == [
        [1308161, 1308161, None, date(2019, 3, 20)],
        [1754301, 1754301, date(2019, 3, 20), None],
    ]


def test_company_without_history_is_its_own_only_filer():
    members, filers = apply_filer_history(MEMBERS, HISTORY)
    assert members[members.ticker == "AAPL"].security_id.tolist() == [320193]
    assert filers[filers.security_id == 320193].values.tolist() == [[320193, 320193, None, None]]


def test_filer_that_starts_reporting_late_is_flagged():
    # XOM resolved to ExxonMobil Holdings, whose first 10-Q is 2026-07-01.
    members = pd.DataFrame(
        {
            "security_id": [2115436],
            "ticker": ["XOM"],
            "start_date": [date(1996, 1, 2)],
            "end_date": [None],
        }
    )
    filers = pd.DataFrame(
        [(2115436, 2115436, None, None)], columns=["security_id", "cik", "valid_from", "valid_to"]
    )
    first = {2115436: date(2026, 7, 1)}
    assert late_filers(members, filers, first.get) == [
        "XOM from 1996-01-02: CIK 2115436 first files 2026-07-01"
    ]
    first[2115436] = date(2015, 2, 1)
    assert late_filers(members, filers, first.get) == []
