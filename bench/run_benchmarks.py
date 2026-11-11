"""Benchmarks for the README (SPEC section 9). Every number in the README's
benchmark block comes from this script's output.

    uv run python bench/run_benchmarks.py            # cold build, then measure
    uv run python bench/run_benchmarks.py --skip-build   # measure the existing build

Writes bench/results/latest.json, a timestamped copy, and the README block.
"""

import argparse
import json
import os
import platform
import statistics
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from pitwh import config
from pitwh.bench import STRATEGIES, nested_subsets, replace_block, run_strategy

RESULTS_DIR = config.REPO_ROOT / "bench" / "results"
README = config.REPO_ROOT / "README.md"
SIZES = [50, 100, 200]
WARMUPS, RUNS = 1, 5
MARTS = [
    "dim_security",
    "fct_universe_daily",
    "fct_prices_daily",
    "fct_features_daily",
    "fct_features_daily_naive",
    "rpt_leakage_summary",
]
DBT = [str(Path(sys.executable).parent / "dbt"), "--no-use-colors"]
DBT_ARGS = ["--project-dir", str(config.DBT_DIR), "--profiles-dir", str(config.DBT_DIR)]


def db_path() -> Path:
    return Path(os.environ.get("DUCKDB_PATH", config.DATA_DIR / "pitwh.duckdb"))


def machine() -> dict:
    if sys.platform == "darwin":
        cpu = subprocess.run(
            ["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True
        ).stdout.strip()
    else:
        lines = Path("/proc/cpuinfo").read_text().splitlines()
        cpu = next((ln.split(":", 1)[1].strip() for ln in lines if "model name" in ln), "")
    ram = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    return {
        "cpu": cpu or platform.processor(),
        "cores": os.cpu_count(),
        "ram_gb": round(ram / 2**30, 1),
        "os": f"{platform.system()} {platform.release()} ({platform.machine()})",
        "python": platform.python_version(),
        "duckdb": duckdb.__version__,
    }


def cold_build() -> dict:
    """Delete the database, then time `dbt seed` + `dbt build` from scratch."""
    path = db_path()
    for p in (path, path.with_name(path.name + ".wal")):
        p.unlink(missing_ok=True)
    timings = {}
    for step in (["seed", "--full-refresh"], ["build"]):
        start = time.perf_counter()
        # A failing test makes `dbt build` exit 1; the counts below record it.
        subprocess.run([*DBT, *step, *DBT_ARGS], check=False, capture_output=True)
        timings[step[0]] = round(time.perf_counter() - start, 1)
    results = json.loads((config.DBT_DIR / "target" / "run_results.json").read_text())
    statuses: dict[str, int] = {}
    for r in results["results"]:
        statuses[r["status"]] = statuses.get(r["status"], 0) + 1
    return {
        "seed_seconds": timings["seed"],
        "build_seconds": timings["build"],
        "total_seconds": round(timings["seed"] + timings["build"], 1),
        "node_statuses": statuses,
    }


def load_inputs(con: duckdb.DuckDBPyConnection, securities: list[int]) -> int:
    """Grid and events for these securities, built exactly as fct_features_daily builds them."""
    con.execute(
        "create or replace temp table subset as select unnest(?) as security_id", [securities]
    )
    metrics = [r[0] for r in con.execute("select metric from wh.rpt_leakage_summary").fetchall()]
    con.execute(
        """
        create or replace temp table grid as
        select u.trade_date, u.security_id, m.metric
        from wh.fct_universe_daily as u
        semi join subset using (security_id)
        cross join (select unnest(?) as metric) as m
        """,
        [metrics],
    )
    con.execute(
        """
        create or replace temp table events as
        select security_id, metric, event_date, value, source_available_date
        from (
            select security_id, metric, event_date, value, available_date as source_available_date
            from wh.int_fundamentals__snapshot_events
            union all
            select security_id, metric, event_date, value, source_available_date
            from wh.int_fundamentals__ttm_events
        )
        semi join subset using (security_id)
        where metric in (select unnest(?))
        """,
        [metrics],
    )
    return con.execute("select count(*) from grid").fetchone()[0]


def same_rows(con: duckdb.DuckDBPyConnection, a: str, b: str) -> bool:
    diff = con.execute(
        f"""
        select
            (select count(*) from (select * from {a} except all select * from {b}))
            + (select count(*) from (select * from {b} except all select * from {a}))
        """
    ).fetchone()[0]
    return diff == 0


def asof_benchmarks(con: duckdb.DuckDBPyConnection) -> list[dict]:
    rows = con.execute("select security_id from wh.stg_universe__securities").fetchall()
    ids = [r[0] for r in rows]
    subsets = nested_subsets(ids, SIZES, config.UNIVERSE_SEED)
    out = []
    for size, securities in zip(SIZES, subsets, strict=True):
        grid_rows = load_inputs(con, securities)
        row = {"securities": size, "grid_rows": grid_rows, "seconds": {}}
        for name in STRATEGIES:
            times = []
            for i in range(WARMUPS + RUNS):
                start = time.perf_counter()
                run_strategy(con, name, f"out_{name}")
                if i >= WARMUPS:
                    times.append(time.perf_counter() - start)
            row["seconds"][name] = round(statistics.median(times), 4)
            print(f"{size} securities, {name}: {row['seconds'][name]}s", flush=True)
        for name in STRATEGIES:
            if not same_rows(con, "out_asof_join", f"out_{name}"):
                raise AssertionError(f"{name} differs from asof_join at {size} securities")
        row["output_rows"] = con.execute("select count(*) from out_asof_join").fetchone()[0]
        row["matched_rows"] = con.execute(
            "select count(*) from out_asof_join where value is not null"
        ).fetchone()[0]
        out.append(row)
    return out


def leakage(con: duckdb.DuckDBPyConnection) -> dict:
    metrics = [r[0] for r in con.execute("select metric from wh.rpt_leakage_summary").fetchall()]
    pairs = " union all ".join(
        f"""
        select n.{m} as naive_value, p.{m} as pit_value,
            n.{m}_source_available_date - n.trade_date as lead_days
        from wh.fct_features_daily_naive as n
        inner join wh.fct_features_daily as p using (trade_date, security_id)
        """
        for m in metrics
    )
    overall = con.execute(
        f"""
        select
            count(*) filter (where naive_value is not null) as naive_rows,
            count(*) filter (where naive_value is not null
                and (naive_value is distinct from pit_value or lead_days > 0)) as leaky_rows,
            count(*) filter (where naive_value is not null and lead_days > 0) as lookahead_rows,
            median(lead_days) filter (where naive_value is not null and lead_days > 0),
            quantile_cont(lead_days, 0.9) filter (where naive_value is not null and lead_days > 0),
            count(*) filter (where naive_value is distinct from pit_value
                and naive_value is not null) as differs_rows
        from ({pairs})
        """
    ).fetchone()
    versions = con.execute(
        """
        select count(*) filter (where is_restatement), count(*) filter (where is_derived),
            count(*)
        from wh.int_fundamentals__versions
        """
    ).fetchone()
    per_metric = con.execute("select * from wh.rpt_leakage_summary order by metric").df()
    return {
        "naive_rows": overall[0],
        "leaky_rows": overall[1],
        "pct_leaky": round(100 * overall[1] / overall[0], 2),
        "lookahead_rows": overall[2],
        "median_lookahead_days": overall[3],
        "p90_lookahead_days": overall[4],
        "differs_rows": overall[5],
        "pct_differs": round(100 * overall[5] / overall[0], 2),
        "restated_versions": versions[0],
        "derived_quarter_versions": versions[1],
        "fundamental_versions": versions[2],
        "per_metric": json.loads(per_metric.to_json(orient="records")),
    }


def dir_bytes(path: Path) -> int:
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())


def volume(con: duckdb.DuckDBPyConnection) -> dict:
    rows = {m: con.execute(f"select count(*) from wh.{m}").fetchone()[0] for m in MARTS}
    securities = con.execute(
        "select count(*), count(*) filter (where is_departed), count(price_symbol)"
        " from wh.stg_universe__securities"
    ).fetchone()
    reconciliation = con.execute(
        """
        select
            (select count(*) from wh.fct_prices_daily where vendor_return is not null),
            (select count(*) from wh.reconciliation_exceptions)
        """
    ).fetchone()
    fallbacks = con.execute(
        """
        select metric, count(*) as facts,
            count(*) filter (where priority > 1) as fallback_facts,
            round(100.0 * count(*) filter (where priority > 1) / count(*), 1) as pct_fallback,
            string_agg(distinct tag, ', ' order by tag) filter (where priority > 1)
                as fallback_tags
        from wh.int_facts__mapped
        group by metric
        order by metric
        """
    ).df()
    return {
        "mart_rows": rows,
        "tag_fallbacks": json.loads(fallbacks.to_json(orient="records")),
        "securities": securities[0],
        "departed_securities": securities[1],
        "priced_securities": securities[2],
        "reconciled_returns": reconciliation[0],
        "reviewed_vendor_exceptions": reconciliation[1],
        "raw_cache_mb": round(dir_bytes(config.RAW_DIR) / 2**20, 1),
        "duckdb_file_mb": round(db_path().stat().st_size / 2**20, 1),
    }


def test_inventory() -> dict:
    def count(cmd: list[str]) -> int:
        out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
        return len([ln for ln in out.splitlines() if ln.strip()])

    ls = [*DBT, "--quiet", "ls", *DBT_ARGS, "--output", "name", "--resource-type"]
    collected = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q"],
        capture_output=True,
        text=True,
        cwd=config.REPO_ROOT,
        check=True,
    ).stdout
    return {
        "dbt_data_tests": count([*ls, "test"]),
        "dbt_unit_tests": count([*ls, "unit_test"]),
        "pytest_tests": sum(1 for ln in collected.splitlines() if "::" in ln),
    }


def fmt_s(seconds: float) -> str:
    return f"{seconds * 1000:.0f} ms" if seconds < 1 else f"{seconds:.2f} s"


def render(r: dict) -> str:
    lk, vol, tests, m = r["leakage"], r["volume"], r["tests"], r["machine"]
    lines = [
        f"_Generated by `bench/run_benchmarks.py` on {r['generated_at'][:10]}. "
        f"{vol['securities']} securities ({vol['departed_securities']} left the index), "
        f"universe {r['universe']['start']} to {r['universe']['end']}._",
        "",
        "**Look-ahead leakage in the naive model** (feature rows with a value)",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Naive rows that differ from PIT or cite a not-yet-public filing | "
        f"**{lk['pct_leaky']}%** ({lk['leaky_rows']:,} of {lk['naive_rows']:,}) |",
        f"| Naive rows whose value differs from PIT (stricter) | "
        f"{lk['pct_differs']}% ({lk['differs_rows']:,}) |",
        f"| Median look-ahead, leaky rows | **{lk['median_lookahead_days']:.0f} days** |",
        f"| p90 look-ahead | {lk['p90_lookahead_days']:.0f} days |",
        f"| Restated versions handled point-in-time | {lk['restated_versions']:,} |",
        f"| Quarters derived from YTD or annual filings | {lk['derived_quarter_versions']:,} |",
        "",
        "**As-of join, median of 5 runs after 1 warm-up** (identical output asserted)",
        "",
        "| Securities | Grid rows | DuckDB `ASOF JOIN` | Correlated subquery "
        "| Window `LAST_VALUE` | ASOF speed-up vs slowest |",
        "|---:|---:|---:|---:|---:|---:|",
    ]
    for row in r["asof"]:
        s = row["seconds"]
        lines.append(
            f"| {row['securities']} | {row['grid_rows']:,} | {fmt_s(s['asof_join'])} "
            f"| {fmt_s(s['correlated_subquery'])} | {fmt_s(s['window_last_value'])} "
            f"| {max(s.values()) / s['asof_join']:.1f}x |"
        )
    b = r["build"]
    build = (
        f"{b['total_seconds']:.0f} s "
        f"(seed {b['seed_seconds']:.0f} s, build {b['build_seconds']:.0f} s)"
        if b
        else "not run"
    )
    mart_rows = ", ".join(f"`{k}` {v:,}" for k, v in vol["mart_rows"].items())
    lines += [
        "",
        "| Build and data | |",
        "|---|---|",
        f"| Cold `dbt seed` + `dbt build`, all securities | {build} |",
        f"| Mart rows | {mart_rows} |",
        f"| Securities with Tiingo prices | {vol['priced_securities']} of "
        f"{vol['securities']} (the rest are departed names Tiingo does not serve) |",
        f"| Daily returns reconciled to vendor | {vol['reconciled_returns']:,} "
        f"({vol['reviewed_vendor_exceptions']} reviewed vendor-side exception) |",
        f"| Raw cache / DuckDB file | {vol['raw_cache_mb']:,.0f} MB / "
        f"{vol['duckdb_file_mb']:,.0f} MB |",
        f"| Tests | {tests['dbt_data_tests']} dbt data tests, {tests['dbt_unit_tests']} dbt "
        f"unit tests, {tests['pytest_tests']} pytest tests |",
        "",
        "<details><summary>XBRL tag fallbacks: how often a metric came from a "
        "lower-priority tag</summary>",
        "",
        "| Metric | Mapped facts | From a fallback tag | Fallback tags used |",
        "|---|---:|---:|---|",
        *(
            f"| {t['metric']} | {t['facts']:,} | {t['pct_fallback']}% "
            f"| {t['fallback_tags'] or ''} |"
            for t in vol["tag_fallbacks"]
        ),
        "",
        "</details>",
        "",
        f"_Machine: {m['cpu']}, {m['cores']} cores, {m['ram_gb']:.0f} GB RAM, {m['os']}, "
        f"DuckDB {m['duckdb']}._",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-build", action="store_true", help="measure the existing build")
    args = parser.parse_args()

    build = None if args.skip_build else cold_build()
    con = duckdb.connect()
    con.execute(f"attach '{db_path()}' as wh (read_only)")
    project = (config.DBT_DIR / "dbt_project.yml").read_text()
    result = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "machine": machine(),
        "universe": {
            "start": project.split('universe_start: "')[1][:10],
            "end": project.split('universe_end: "')[1][:10],
        },
        "build": build,
        "asof": asof_benchmarks(con),
        "leakage": leakage(con),
        "volume": volume(con),
        "tests": test_inventory(),
    }
    con.close()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    body = json.dumps(result, indent=2, default=str) + "\n"
    (RESULTS_DIR / "latest.json").write_text(body)
    stamp = result["generated_at"].replace(":", "").replace("-", "")
    (RESULTS_DIR / f"{stamp}.json").write_text(body)
    README.write_text(replace_block(README.read_text(), render(result)))
    print(render(result))


if __name__ == "__main__":
    main()
