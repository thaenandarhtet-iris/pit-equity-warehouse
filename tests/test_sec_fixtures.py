import json

import duckdb

from pitwh import config
from pitwh.sec import land_all, trim_fixtures

SUB_COLS = ["accessionNumber", "filingDate", "reportDate", "acceptanceDateTime", "form"]


def _block(rows: list[tuple]) -> dict:
    return {col: [r[i] for r in rows] for i, col in enumerate(SUB_COLS)}


def _fact(val, end, accn, start=None):
    f = {
        "val": val,
        "end": end,
        "accn": accn,
        "fy": 2020,
        "fp": "Q1",
        "form": "10-Q",
        "filed": "2020-05-01",
    }
    if start:
        f["start"] = start
    return f


def _write(path, doc):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc))


def test_trim_keeps_mapped_facts_and_only_their_filings(tmp_path):
    raw, out = tmp_path / "raw", tmp_path / "out"
    _write(
        raw / "companyfacts" / "CIK0000000042.json",
        {
            "cik": 42,
            "facts": {
                "us-gaap": {
                    "NetIncomeLoss": {
                        "units": {
                            "USD": [
                                _fact(5.0, "2020-03-31", "A-1", start="2020-01-01"),
                                _fact(9.0, "2019-03-31", "OLD-1", start="2019-01-01"),
                            ]
                        }
                    },
                    "SomeUnmappedTag": {"units": {"USD": [_fact(1.0, "2020-03-31", "X-1")]}},
                }
            },
        },
    )
    _write(
        raw / "submissions" / "CIK0000000042.json",
        {
            "cik": "42",
            "name": "Example Co",
            "tickers": ["EX"],
            "fiscalYearEnd": "1231",
            "sicDescription": "Widgets",
            "filings": {
                "recent": _block(
                    [
                        ("A-1", "2020-05-01", "2020-03-31", "2020-05-01T20:00:00.000Z", "10-Q"),
                        ("X-1", "2020-05-02", "", "2020-05-02T20:00:00.000Z", "8-K"),
                    ]
                ),
                "files": [
                    {"name": "CIK0000000042-submissions-001.json", "filingCount": 2},
                    {"name": "CIK0000000042-submissions-002.json", "filingCount": 1},
                ],
            },
        },
    )
    _write(
        raw / "submissions" / "CIK0000000042-submissions-001.json",
        _block(
            [
                ("OLD-1", "2019-05-01", "2019-03-31", "2019-05-01T20:00:00.000Z", "10-Q"),
                ("OLD-2", "2019-06-01", "", "2019-06-01T20:00:00.000Z", "8-K"),
            ]
        ),
    )
    _write(
        raw / "submissions" / "CIK0000000042-submissions-002.json",
        _block(
            [
                ("ANCIENT", "2009-05-01", "", "2009-05-01T20:00:00.000Z", "8-K"),
            ]
        ),
    )

    # A company in the cache but not in the fixture set is left out.
    _write(raw / "companyfacts" / "CIK0000000099.json", {"cik": 99, "facts": {}})

    trim_fixtures(raw, out, config.SEEDS_DIR / "concept_map.csv", ciks=[42])

    assert not (out / "companyfacts" / "CIK0000000099.json").exists()

    facts = json.loads((out / "companyfacts" / "CIK0000000042.json").read_text())
    assert list(facts["facts"]["us-gaap"]) == ["NetIncomeLoss"]
    assert len(facts["facts"]["us-gaap"]["NetIncomeLoss"]["units"]["USD"]) == 2

    subs = json.loads((out / "submissions" / "CIK0000000042.json").read_text())
    assert subs["filings"]["recent"]["accessionNumber"] == ["A-1"]
    assert subs["name"] == "Example Co"
    # An overflow file with nothing referenced is dropped, and so is its index entry.
    assert [f["name"] for f in subs["filings"]["files"]] == ["CIK0000000042-submissions-001.json"]
    overflow = json.loads((out / "submissions" / "CIK0000000042-submissions-001.json").read_text())
    assert overflow["accessionNumber"] == ["OLD-1"]
    assert not (out / "submissions" / "CIK0000000042-submissions-002.json").exists()


def test_committed_fixtures_land_to_a_consistent_dataset(tmp_path):
    counts = land_all(raw_dir=config.FIXTURES_DIR / "sec", out_dir=tmp_path)
    assert counts["sec_companies"] == 5

    con = duckdb.connect()
    unmatched = con.execute(f"""
        select count(*) from '{tmp_path}/sec_facts.parquet' f
        left join '{tmp_path}/sec_filings.parquet' s on f.accn = s.accession_number
        where s.accession_number is null
    """).fetchone()[0]
    assert unmatched == 0

    # TWTR's 10-Qs before late 2015 live only in its overflow submissions file.
    twtr_2014 = con.execute(f"""
        select count(*) from '{tmp_path}/sec_filings.parquet'
        where cik = 1418091 and form = '10-Q' and filing_date < '2015-01-01'
    """).fetchone()[0]
    assert twtr_2014 > 0
