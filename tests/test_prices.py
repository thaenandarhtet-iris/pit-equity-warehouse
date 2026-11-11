import json
from datetime import date

import httpx
import pandas as pd
import pytest

from pitwh.prices import COLUMNS, TiingoClient, land_prices, tiingo_symbol

# Tiingo's response shape around AAPL's 4:1 split on 2020-08-31. The split date
# and factor are real; the prices are illustrative.
AAPL_ROWS = [
    {
        "date": "2020-08-28T00:00:00.000Z",
        "close": 499.23,
        "high": 505.64,
        "low": 495.81,
        "open": 504.05,
        "volume": 46907479,
        "adjClose": 121.0,
        "adjHigh": 122.53,
        "adjLow": 120.15,
        "adjOpen": 122.15,
        "adjVolume": 187629916,
        "divCash": 0.0,
        "splitFactor": 1.0,
    },
    {
        "date": "2020-08-31T00:00:00.000Z",
        "close": 129.04,
        "high": 131.0,
        "low": 126.0,
        "open": 127.58,
        "volume": 225702700,
        "adjClose": 125.0,
        "adjHigh": 126.97,
        "adjLow": 122.12,
        "adjOpen": 123.65,
        "adjVolume": 225702700,
        "divCash": 0.0,
        "splitFactor": 4.0,
    },
]


def test_token_goes_in_header_never_in_url():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["Authorization"]
        return httpx.Response(200, json=[])

    client = TiingoClient(
        "secret-token", transport=httpx.MockTransport(handler), sleep=lambda s: None
    )
    client.get_json("https://api.tiingo.com/tiingo/daily/AAPL/prices", {"startDate": "2020-01-01"})
    assert seen["auth"] == "Token secret-token"
    assert "secret-token" not in seen["url"]


def test_missing_token_is_rejected():
    with pytest.raises(ValueError):
        TiingoClient("")


@pytest.mark.parametrize(("sp", "tiingo"), [("BF.B", "BF-B"), ("BRK.B", "BRK-B"), ("AAPL", "AAPL")])
def test_share_class_dot_becomes_dash(sp, tiingo):
    assert tiingo_symbol(sp) == tiingo


def test_land_prices_keeps_raw_close_split_and_dividend(tmp_path):
    raw = tmp_path / "prices"
    raw.mkdir()
    (raw / "AAPL.json").write_text(json.dumps(AAPL_ROWS))
    (raw / "EMPTY.json").write_text("[]")

    n = land_prices(raw, tmp_path / "prices_daily.parquet")

    df = pd.read_parquet(tmp_path / "prices_daily.parquet")
    assert n == 2
    split_day = df[df.trade_date == date(2020, 8, 31)].iloc[0]
    assert split_day.ticker == "AAPL"
    assert split_day.close == 129.04
    assert split_day.split_factor == 4.0
    assert split_day.adj_close == 125.0
    assert set(df.columns) >= {"open", "high", "low", "volume", "div_cash"}


def test_synthetic_prices_follow_the_corporate_actions():
    from pitwh.prices import synthetic_prices

    sessions = [date(2020, 8, d) for d in (25, 26, 27, 28, 31)] + [date(2020, 9, 1)]
    actions = pd.DataFrame(
        {
            "date": [date(2020, 8, 27), date(2020, 8, 31)],
            "div_cash": [0.5, 0.0],
            "split_factor": [1.0, 4.0],
        }
    )
    rows = synthetic_prices(sessions, actions, seed=3)

    assert rows == synthetic_prices(sessions, actions, seed=3)
    assert [r["date"][:10] for r in rows] == [d.isoformat() for d in sessions]
    by_day = {r["date"][:10]: r for r in rows}
    assert by_day["2020-08-27"]["divCash"] == 0.5
    split, before = by_day["2020-08-31"], by_day["2020-08-28"]
    assert split["splitFactor"] == 4.0
    assert split["close"] / before["close"] < 0.35  # raw price drops with the split
    assert 0.9 < split["adjClose"] / before["adjClose"] < 1.1  # adjusted does not
    assert rows[-1]["adjClose"] == rows[-1]["close"]  # back-adjusted to the last day
    assert set(rows[0]) >= {"date", *COLUMNS}
