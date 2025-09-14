"""
SQLite -> SQL Server migration utility (schema + data).

Usage (PowerShell):
  # Ensure MSSQL_CONN env var is set to your pyodbc URL
  # Example: mssql+pyodbc://user:pass@host,1433/DB?driver=ODBC+Driver+17+for+SQL+Server
  $env:MSSQL_CONN = "..."
  .\.venv\Scripts\python.exe .\scripts\migrate_sqlite_to_mssql.py --sqlite .\database\portal_demo3.db

Options:
  --sqlite PATH            Path to source SQLite DB (default: database/portal_demo3.db)
  --tables t1,t2           Only migrate these tables (comma-separated)
  --exclude t1,t2          Exclude these tables
  --drop-existing          Drop existing tables in SQL Server before creating
  --batch-size N           Insert batch size (default: 1000)

Notes:
  - Requires Microsoft ODBC Driver and pyodbc installed.
  - Preserves primary key values by enabling IDENTITY_INSERT per table when possible.
"""
import argparse
import os
from typing import List, Set

from sqlalchemy import create_engine, MetaData, inspect, text
from sqlalchemy import BigInteger
from sqlalchemy.schema import DefaultClause


def parse_args():
    p = argparse.ArgumentParser(description="Migrate SQLite schema and data to SQL Server")
    p.add_argument("--sqlite", dest="sqlite_path", default=os.path.join(os.path.dirname(__file__), "..", "database", "portal_demo3.db"))
    p.add_argument("--tables", dest="tables", default="")
    p.add_argument("--exclude", dest="exclude", default="")
    p.add_argument("--drop-existing", dest="drop_existing", action="store_true")
    p.add_argument("--batch-size", dest="batch_size", type=int, default=1000)
    return p.parse_args()


def normalize_names(csv: str) -> List[str]:
    if not csv:
        return []
    return [x.strip() for x in csv.split(',') if x.strip()]


def bracket(name: str) -> str:
    # Basic T-SQL quoting for identifiers
    return f"[{name}]"


def drop_table_if_exists(conn, table_name: str):
    try:
        conn.execute(text(f"IF OBJECT_ID(N'{table_name}', N'U') IS NOT NULL DROP TABLE {bracket(table_name)}"))
        print(f"[drop] {table_name} dropped (if existed)")
    except Exception as e:
        print(f"[drop] {table_name} skip: {e}")


def enable_identity_insert(conn, table_name: str, on: bool):
    try:
        state = 'ON' if on else 'OFF'
        conn.execute(text(f"SET IDENTITY_INSERT {bracket(table_name)} {state}"))
        return True
    except Exception:
        return False


def migrate(sqlite_path: str, tables_filter: List[str], exclude: Set[str], drop_existing: bool, batch_size: int):
    conn_str = os.getenv('MSSQL_CONN')
    if not conn_str:
        raise SystemExit("MSSQL_CONN environment variable not set.")

    # Normalize paths
    sqlite_abs = os.path.abspath(sqlite_path)
    if not os.path.exists(sqlite_abs):
        raise SystemExit(f"SQLite file not found: {sqlite_abs}")

    print("[info] SQLite:", sqlite_abs)
    print("[info] MSSQL :", conn_str)

    # Create engines
    sqlite_engine = create_engine(f"sqlite:///{sqlite_abs}")
    # Avoid fast_executemany to reduce memory usage on large inserts (pyodbc can bloat)
    mssql_engine = create_engine(conn_str, pool_pre_ping=True)

    # Reflect source schema
    src_meta = MetaData()
    src_meta.reflect(bind=sqlite_engine)

    # Build table list (respect dependencies)
    candidates = [t for t in src_meta.sorted_tables]
    if tables_filter:
        allow = {t.lower() for t in tables_filter}
        candidates = [t for t in candidates if t.name.lower() in allow]
    if exclude:
        deny = {x.lower() for x in exclude}
        candidates = [t for t in candidates if t.name.lower() not in deny]

    # Always exclude SQLite internal/system tables
    candidates = [t for t in candidates if not t.name.lower().startswith("sqlite_")]

    if not candidates:
        print("[warn] No tables selected for migration.")
        return

    print("[info] Tables to migrate (dependency order):")
    for t in candidates:
        print("  -", t.name)

    # Optional drop existing (reverse order for FK safety)
    if drop_existing:
        with mssql_engine.begin() as mconn:
            for t in reversed(candidates):
                drop_table_if_exists(mconn, t.name)

    # Create tables in SQL Server from reflected metadata
    print("[step] Creating tables in SQL Server...")
    # Pre-scan SQLite integer magnitudes to decide BIGINT upcasts
    def q_sqlite(name: str) -> str:
        return f'"{name}"'
    bigint_cols = {t.name: set() for t in candidates}
    INT_MAX = 2147483647
    try:
        with sqlite_engine.connect() as sconn:
            for t in candidates:
                # Get column names from SQLite inspector directly to avoid type mismatches
                cols = [c['name'] for c in inspect(sqlite_engine).get_columns(t.name)]
                for cname in cols:
                    # Only check likely integer/numeric columns by attempting cast
                    stmt = text(f"SELECT MAX(ABS(CAST({q_sqlite(cname)} AS INTEGER))) FROM {q_sqlite(t.name)} WHERE {q_sqlite(cname)} IS NOT NULL")
                    try:
                        max_abs = sconn.execute(stmt).scalar()
                        if max_abs is not None and isinstance(max_abs, (int, float)) and max_abs > INT_MAX:
                            bigint_cols[t.name].add(cname)
                    except Exception:
                        # Ignore non-castable columns
                        pass
    except Exception:
        pass
    # Create tables one-by-one, cloning metadata so we can adjust defaults/types
    tgt_meta = MetaData()
    for t in candidates:
        try:
            # Clone table into target metadata
            new_t = t.tometadata(tgt_meta)
            # Fix SQLite-specific server defaults like datetime('now') / CURRENT_TIMESTAMP
            for col in new_t.columns:
                sd = col.server_default
                if isinstance(sd, DefaultClause):
                    try:
                        val = str(sd.arg).strip().lower()
                    except Exception:
                        val = ""
                    if (
                        "datetime('now')" in val
                        or "date('now')" in val
                        or "current_timestamp" in val
                    ):
                        # Replace with SQL Server equivalent
                        col.server_default = text("GETDATE()")
                # Map generic/reflected BOOLEAN to MSSQL BIT
                tname = col.type.__class__.__name__.lower()
                if tname == "boolean":
                    try:
                        from sqlalchemy import Boolean
                        col.type = Boolean(create_constraint=False)
                    except Exception:
                        pass
                # Upcast to BIGINT if values in SQLite exceed INT range
                if col.name in bigint_cols.get(t.name, set()):
                    col.type = BigInteger()
            # Create table if not exists
            new_t.create(bind=mssql_engine, checkfirst=True)
            print(f"[create] {t.name} ready")
        except Exception as e:
            print(f"[warn] {t.name} create skipped or partial: {e}")

    # Inspect columns per table once
    s_inspect = inspect(sqlite_engine)
    m_inspect = inspect(mssql_engine)

    # Copy data in chunks
    print("[step] Copying data...")
    copied = {}
    with sqlite_engine.connect() as sconn:
        for t in candidates:
            # Ensure target table exists before copying
            if not m_inspect.has_table(t.name):
                print(f"[skip] {t.name}: target table not present; skipping data copy")
                continue
            cols = [c['name'] for c in s_inspect.get_columns(t.name)]
            if not cols:
                print(f"[skip] {t.name}: no columns detected")
                continue
            col_csv = ", ".join([f"{c}" for c in cols])
            select_sql = text(f"SELECT {col_csv} FROM {t.name}")
            total = 0
            # Stream results
            result = sconn.execution_options(stream_results=True).execute(select_sql)
            with mssql_engine.begin() as mconn:
                # Prepare insert statement for target
                param_csv = ", ".join([f":{c}" for c in cols])
                insert_sql = text(f"INSERT INTO {bracket(t.name)} (" + ", ".join([bracket(c) for c in cols]) + f") VALUES ({param_csv})")
                # Try identity insert ON (ignore if not needed)
                ident_on = enable_identity_insert(mconn, t.name, True)
                try:
                    while True:
                        rows = result.fetchmany(batch_size)
                        if not rows:
                            break
                        batch = [dict(zip(cols, r)) for r in rows]
                        # Execute and immediately drop references to free memory
                        mconn.execute(insert_sql, batch)
                        added = len(batch)
                        total += added
                        print(f"[copy] {t.name}: +{added} (total={total})")
                        del batch
                finally:
                    if ident_on:
                        enable_identity_insert(mconn, t.name, False)

            copied[t.name] = total
    print("[done] Migration complete.")
    for name, cnt in copied.items():
        print(f"  {name}: {cnt} rows")


if __name__ == "__main__":
    args = parse_args()
    migrate(
        sqlite_path=args.sqlite_path,
        tables_filter=normalize_names(args.tables),
        exclude=set(normalize_names(args.exclude)),
        drop_existing=args.drop_existing,
        batch_size=args.batch_size,
    )
