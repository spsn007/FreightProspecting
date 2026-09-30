import sys
sys.path.insert(0, ".")
import time
import sqlite3
from pathlib import Path
from starlette.testclient import TestClient
from src.backend.main import app
from src.backend.db.connection import get_db_path
from src.backend.db.queries import (
    get_prospects_list,
    get_company_grouped_prospects,
    get_prospect_detail,
    get_summary_counts
)

DB_PATH = get_db_path()

class QueryCounter:
    def __init__(self, conn):
        self.count = 0
        self.queries = []
        conn.set_trace_callback(self.trace)

    def trace(self, stmt):
        self.count += 1
        self.queries.append(stmt)

def profile():
    client = TestClient(app)
    
    print("=" * 80)
    print("PROFILING CURRENT STAGE 3G / REMEDIATION A DIRECTORY PERFORMANCE")
    print("=" * 80)
    
    # 1. Summary Counts
    conn = sqlite3.connect(DB_PATH)
    qc = QueryCounter(conn)
    t0 = time.perf_counter()
    counts = get_summary_counts(db_path=DB_PATH)
    t_counts = time.perf_counter() - t0
    print(f"1. get_summary_counts(): {qc.count} queries in {t_counts*1000:.2f} ms")
    conn.close()

    # 2. get_prospects_list(ALL) (Facility View)
    # We trace by counting inside get_prospects_list
    t0 = time.perf_counter()
    fac_list = get_prospects_list(lifecycle_stage="ALL", db_path=DB_PATH)
    t_fac = time.perf_counter() - t0
    print(f"2. get_prospects_list(ALL): {len(fac_list)} facilities in {t_fac*1000:.2f} ms")

    # 3. get_company_grouped_prospects(ALL) (Company View)
    t0 = time.perf_counter()
    comp_groups = get_company_grouped_prospects(lifecycle_stage="ALL", db_path=DB_PATH)
    t_comp = time.perf_counter() - t0
    print(f"3. get_company_grouped_prospects(ALL): {len(comp_groups)} companies in {t_comp*1000:.2f} ms")

    # 4. Tracing exact SQL queries for get_company_grouped_prospects
    # To trace all queries made during get_company_grouped_prospects, let's wrap sqlite3.connect
    orig_connect = sqlite3.connect
    total_sql_calls = 0
    sql_statements = []

    def counting_connect(*args, **kwargs):
        c = orig_connect(*args, **kwargs)
        def trace_fn(stmt):
            nonlocal total_sql_calls
            total_sql_calls += 1
            sql_statements.append(stmt)
        c.set_trace_callback(trace_fn)
        return c

    sqlite3.connect = counting_connect
    try:
        total_sql_calls = 0
        sql_statements.clear()
        t0 = time.perf_counter()
        groups = get_company_grouped_prospects(lifecycle_stage="ALL", db_path=DB_PATH)
        t_groups = time.perf_counter() - t0
        print(f"   -> Exact SQL calls in get_company_grouped_prospects(ALL): {total_sql_calls} statements ({t_groups*1000:.2f} ms)")

        total_sql_calls = 0
        sql_statements.clear()
        t0 = time.perf_counter()
        facs = get_prospects_list(lifecycle_stage="ALL", db_path=DB_PATH)
        t_facs = time.perf_counter() - t0
        print(f"   -> Exact SQL calls in get_prospects_list(ALL): {total_sql_calls} statements ({t_facs*1000:.2f} ms)")

        # 5. Full HTTP endpoint /prospects
        total_sql_calls = 0
        t0 = time.perf_counter()
        resp = client.get("/prospects")
        t_http = time.perf_counter() - t0
        print(f"4. HTTP GET /prospects: Status {resp.status_code}, {len(resp.content):,} bytes, {total_sql_calls} SQL statements, {t_http*1000:.2f} ms")

        # 6. Full HTTP endpoint /api/companies
        total_sql_calls = 0
        t0 = time.perf_counter()
        resp_api = client.get("/api/companies")
        t_api = time.perf_counter() - t0
        print(f"5. HTTP GET /api/companies: Status {resp_api.status_code}, {len(resp_api.content):,} bytes, {total_sql_calls} SQL statements, {t_api*1000:.2f} ms")

        # 7. Facility detail /prospects/18
        total_sql_calls = 0
        t0 = time.perf_counter()
        resp_det = client.get("/prospects/18")
        t_det = time.perf_counter() - t0
        print(f"6. HTTP GET /prospects/18: Status {resp_det.status_code}, {len(resp_det.content):,} bytes, {total_sql_calls} SQL statements, {t_det*1000:.2f} ms")

    finally:
        sqlite3.connect = orig_connect

if __name__ == "__main__":
    profile()
