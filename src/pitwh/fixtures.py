"""Land the committed offline fixtures into Parquet, shaped like the real landing tables."""

from pathlib import Path

import pandas as pd

from pitwh import config, prices, sec

UNIVERSE_TABLES = ("universe_membership", "universe_securities", "universe_filers")


def land_fixtures(out_dir: Path, fixtures_dir: Path = config.FIXTURES_DIR) -> dict[str, int]:
    counts = sec.land_all(raw_dir=fixtures_dir / "sec", out_dir=out_dir)
    for name in UNIVERSE_TABLES:
        df = pd.read_csv(fixtures_dir / "universe" / f"{name}.csv")
        for col in ("start_date", "end_date", "valid_from", "valid_to"):
            if col in df:
                df[col] = pd.to_datetime(df[col]).dt.date
        df.to_parquet(out_dir / f"{name}.parquet", index=False)
        counts[name] = len(df)
    # An absent price fixture lands an empty table, so dbt still builds offline.
    counts["prices_daily"] = prices.land_prices(
        fixtures_dir / "tiingo" / "prices", out_dir / "prices_daily.parquet"
    )
    return counts
