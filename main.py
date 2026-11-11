from decimal import Decimal
import io
import math
import os
import re
import time
from typing import List, Optional, Union

import dotenv
from flask import (
    Flask,
    Response,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
import psycopg2
from psycopg2 import pool

# Constants
DELIMITER = "|"
MAX_SEARCH_COUNT = 1000
MAX_SEARCH_TERMS = 5
MIN_TERM_LENGTH = 3
MIN_CLUSTER_THRESHOLD = 75
MAX_CLUSTER_THRESHOLD = 100
CLUSTER_TOP_RESULTS = 10
DEFAULT_PER_PAGE = 25
PER_PAGE_OPTIONS = (25, 50, 100)
SORTABLE_COLUMNS = (
    "trivial_name",
    "batch_no",
    "conc_um",
    "rel_cell_count",
    "relative_cell_count",
    "induction",
)
SORT_ORDERS = ("asc", "desc")
SORT_COLUMN_DB_MAP = {
    "trivial_name": "c.trivial_name",
    "batch_no": "c.batch_no",
    "conc_um": "c.conc_um",
    "rel_cell_count": "c.relative_cell_count",
    "relative_cell_count": "c.relative_cell_count",
    "induction": "c.induction",
    "cluster_akt_pi3k_mtor": "c.cluster_akt_pi3k_mtor",
    "cluster_aurora": "c.cluster_aurora",
    "cluster_bet": "c.cluster_bet",
    "cluster_dna_synthesis": "c.cluster_dna_synthesis",
    "cluster_hdac": "c.cluster_hdac",
    "cluster_hsp90": "c.cluster_hsp90",
    "cluster_l_ch": "c.cluster_l_ch",
    "cluster_mitostress": "c.cluster_mitostress",
    "cluster_na_k_atpase": "c.cluster_na_k_atpase",
    "cluster_protein_synthesis": "c.cluster_protein_synthesis",
    "cluster_pyrimidine_synthesis": "c.cluster_pyrimidine_synthesis",
    "cluster_tubulin": "c.cluster_tubulin",
    "cluster_uncoupling": "c.cluster_uncoupling",
}
SORT_DEFAULT_ORDERS = {
    "trivial_name": "asc",
    "batch_no": "asc",
    "conc_um": "asc",
    "rel_cell_count": "desc",
    "relative_cell_count": "desc",
    "induction": "desc",
}

app = Flask(__name__)
dotenv.load_dotenv()
app.secret_key = os.getenv("SECRET_KEY")

DATASET_HEADER = [
    "Trivial name",
    "Smiles",
    "Batch No",
    "Conc uM",
    "Structure",
    "Relative cell count",
    "Induction",
    "Cluster AKT/PI3K/MTOR",
    "Cluster Aurora",
    "Cluster BET",
    "Cluster DNA synthesis",
    "Cluster HDAC",
    "Cluster HSP90",
    "Cluster L/CH",
    "Cluster MitoStress",
    "Cluster Na+/K+ ATPase",
    "Cluster Protein synthesis",
    "Cluster Pyrimidine synthesis",
    "Cluster Tubulin",
    "Cluster Uncoupling",
]

# Database Connection Pool
DB_STRING = os.getenv("DB_STRING")
COMPOUNDS_TABLE = os.getenv("COMPOUNDS_TABLE", "compounds_full")
if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", COMPOUNDS_TABLE):
    raise ValueError(f"Invalid COMPOUNDS_TABLE name: {COMPOUNDS_TABLE!r}")
db_pool = None
if DB_STRING:
    try:
        db_pool = pool.ThreadedConnectionPool(minconn=1, maxconn=10, dsn=DB_STRING)
    except Exception as e:
        print(f"Warning: Failed to initialize database connection pool: {e}")


def _sanitize_db_value(v: Union[None, str, Decimal, float, int]) -> Union[str, float, int]:
    """Convert PostgreSQL decimal values to int/float and handle nulls."""
    if v is None:
        return ""
    if isinstance(v, Decimal):
        f = float(v)
        return int(f) if f.is_integer() else f
    return v


def export_to_text(data: List[List[Union[str, float]]]) -> str:
    """Format search result data into a pipe-delimited string in-memory."""
    buf = io.StringIO()
    if data:
        # Header row includes 'Structure' column header
        buf.write(DELIMITER.join(map(str, data[0])) + "\n")
    # Data rows omit the raw structure SVG/image (index 4) for text export
    for row in data[1:]:
        clean_row = row[:4] + row[5:]
        buf.write(DELIMITER.join(map(str, clean_row)) + "\n")
    return buf.getvalue()


CLUSTER_COLUMNS = [
    "cluster_akt_pi3k_mtor",
    "cluster_aurora",
    "cluster_bet",
    "cluster_dna_synthesis",
    "cluster_hdac",
    "cluster_hsp90",
    "cluster_l_ch",
    "cluster_mitostress",
    "cluster_na_k_atpase",
    "cluster_protein_synthesis",
    "cluster_pyrimidine_synthesis",
    "cluster_tubulin",
    "cluster_uncoupling",
]

CLUSTER_DISPLAY_NAMES = {
    "cluster_akt_pi3k_mtor": "AKT/PI3K/MTOR",
    "cluster_aurora": "Aurora Kinases",
    "cluster_bet": "BET",
    "cluster_dna_synthesis": "DNA synthesis",
    "cluster_hdac": "HDAC",
    "cluster_hsp90": "HSP90",
    "cluster_l_ch": "L/CH",
    "cluster_mitostress": "MitoStress",
    "cluster_na_k_atpase": "Na+/K+ ATPase",
    "cluster_protein_synthesis": "Protein synthesis",
    "cluster_pyrimidine_synthesis": "Pyrimidine synthesis",
    "cluster_tubulin": "Tubulin",
    "cluster_uncoupling": "Uncoupling",
}


# Matches ordinary whitespace plus hidden/zero-width and control characters
# (newlines, tabs, non-breaking/zero-width spaces, BOM, etc.).
_WHITESPACE_RE = re.compile(r"[\s\u00a0\u200b-\u200d\u2028\u2029\ufeff\x00-\x1f\x7f]+")


def normalize_text(value: Optional[str]) -> str:
    """Collapse hidden whitespace/newlines and lowercase a raw input value."""
    return _WHITESPACE_RE.sub(" ", value or "").strip().lower()


def format_threshold_value(v: float) -> Union[str, float, int]:
    """Render a numeric cluster threshold without a trailing .0 for integers."""
    f = float(v)
    return int(f) if f.is_integer() else f


def format_conc_value(v: Union[float, int, str]) -> str:
    """Render a concentration value without trailing .0 for integers (e.g. 10 instead of 10.0)."""
    f = float(v)
    return str(int(f)) if f.is_integer() else str(f)


def normalize_concentration_filters(raw: Optional[Union[str, List[str]]]) -> List[float]:
    """Parse comma-separated or multi-value concentration inputs into a sorted list of floats."""
    if not raw:
        return []
    items: List[str] = []
    if isinstance(raw, list):
        for part in raw:
            if part:
                items.extend(str(part).split(","))
    elif isinstance(raw, str):
        items = raw.split(",")
    concs: List[float] = []
    for item in items:
        item = item.strip()
        if not item:
            continue
        try:
            val = float(item)
            if val not in concs:
                concs.append(val)
        except (ValueError, TypeError):
            continue
    concs.sort()
    return concs


def parse_conc_bound(raw: Optional[str]) -> Optional[float]:
    """Parse an optional min_conc/max_conc query value as a float."""
    if raw is None or str(raw).strip() == "":
        return None
    try:
        return float(str(raw).strip())
    except (TypeError, ValueError):
        return None


def describe_conc_range(min_conc: Optional[float], max_conc: Optional[float]) -> str:
    """Human-readable concentration range, e.g. 'Conc: 0.2–50 µM'."""
    if min_conc is not None and max_conc is not None:
        return f"Conc: {format_conc_value(min_conc)}\u2013{format_conc_value(max_conc)} \u00b5M"
    if min_conc is not None:
        return f"Conc: \u2265 {format_conc_value(min_conc)} \u00b5M"
    if max_conc is not None:
        return f"Conc: \u2264 {format_conc_value(max_conc)} \u00b5M"
    return ""


def describe_threshold(col: str, spec: dict) -> str:
    """Human-readable description of a min/max cluster threshold range."""
    cname = CLUSTER_DISPLAY_NAMES.get(col, col)
    lo = spec.get("min")
    hi = spec.get("max")
    if lo is not None and hi is not None:
        return f"{cname} {format_threshold_value(lo)}-{format_threshold_value(hi)}%"
    if lo is not None:
        return f"{cname} \u2265 {format_threshold_value(lo)}%"
    if hi is not None:
        return f"{cname} \u2264 {format_threshold_value(hi)}%"
    return cname


def normalize_search_terms(raw: Optional[str]) -> List[str]:
    """Split keyword input into valid search terms.

    Accepts comma-, whitespace-, and newline-delimited input. Empty tokens and
    terms shorter than MIN_TERM_LENGTH characters are ignored, duplicates are
    removed, and the list is capped at MAX_SEARCH_TERMS.
    """
    if not raw:
        return []

    terms: List[str] = []
    for token in re.split(r"[,\s]+", raw.strip()):
        token = normalize_text(token)
        if len(token) < MIN_TERM_LENGTH:
            continue
        if token not in terms:
            terms.append(token)
        if len(terms) >= MAX_SEARCH_TERMS:
            break
    return terms


def resolve_query_plan(
    substances: Optional[List[str]],
    thresholds: Optional[dict],
) -> Optional[dict]:
    """Determine ordering/limit behaviour for the advanced search cases.

    - Case B (1 cluster, no keywords): order by that cluster DESC, LIMIT 10.
    - Case C (1 cluster + keywords): order by that cluster DESC, no limit.
    - Case A (0 clusters + valid keywords): standard search, no cluster ordering.
    - Case D (0 clusters + no valid keywords): invalid, returns None.
    """
    cluster_col = None
    if thresholds:
        cluster_col = next((c for c in CLUSTER_COLUMNS if c in thresholds), None)

    has_keywords = bool(substances)
    if not has_keywords and not cluster_col:
        return None  # Case D: nothing to search for

    return {
        "order_by_cluster": cluster_col,
        "limit": CLUSTER_TOP_RESULTS if cluster_col else None,
    }


def parse_page_number(raw: Optional[str], default: int = 1) -> int:
    """Parse a 1-based page number, falling back to the default on bad input."""
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return default
    return value if value >= 1 else default


def parse_per_page(raw: Optional[str], default: int = DEFAULT_PER_PAGE) -> int:
    """Parse a page size, accepting only the supported dropdown options."""
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return default
    return value if value in PER_PAGE_OPTIONS else default


def resolve_sort(
    sort_by: Optional[str],
    order: Optional[str],
    thresholds: Optional[dict] = None,
) -> tuple:
    """Validate the requested sort key and direction.

    Compound name, batch, and concentration default to ASC; relative cell count,
    induction, and all 13 bioactivity cluster columns default to DESC.
    Anything unsupported falls back to the default deterministic ordering.
    """
    sort_by = (sort_by or "").strip()
    order = (order or "").strip().lower()
    if order not in SORT_ORDERS:
        order = None

    if sort_by in SORTABLE_COLUMNS:
        default_order = SORT_DEFAULT_ORDERS.get(sort_by, "asc")
        return sort_by, order if order else default_order
    if sort_by in CLUSTER_COLUMNS:
        return sort_by, order if order else "desc"
    return None, "asc"


def _fetch_rows(sql: str, params: tuple) -> Optional[list]:
    """Run a query, retrying once if a pooled connection went stale."""
    conn = None
    try:
        if db_pool:
            conn = db_pool.getconn()
            # A pooled connection may have been dropped since it was returned;
            # discard the stale handle and open a fresh one before querying.
            if getattr(conn, "closed", 0):
                db_pool.putconn(conn, close=True)
                conn = db_pool.getconn()
        else:
            conn = psycopg2.connect(DB_STRING)

        try:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return cur.fetchall()
        except Exception:
            # The connection died mid-query: reconnect and retry exactly once so
            # a dropped pooled connection does not surface as empty results.
            if db_pool:
                db_pool.putconn(conn, close=True)
                conn = db_pool.getconn()
            else:
                conn.close()
                conn = psycopg2.connect(DB_STRING)
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return cur.fetchall()

    except Exception as e:
        print(f"Error querying database: {e}")
        return None
    finally:
        if conn:
            if db_pool:
                db_pool.putconn(conn)
            else:
                conn.close()


def find_compounds(
    query: Optional[str] = None,
    substances: Optional[List[str]] = None,
    thresholds: Optional[dict] = None,
    min_conc: Optional[float] = None,
    max_conc: Optional[float] = None,
    skip_svg: bool = False,
    order_by_cluster: Optional[str] = None,
    limit: Optional[int] = None,
    sort_by: Optional[str] = None,
    sort_order: str = "asc",
    page: Optional[int] = None,
    per_page: Optional[int] = None,
) -> Optional[dict]:
    """Search compounds from PostgreSQL matching query/substances and a cluster threshold.

    Optionally sorts by a chosen column and returns one paginated slice. The
    result carries the total match count so the caller can build page controls.
    ``limit`` remains the hard result cap used by the cluster/concentration
    guardrails (Case B and concentration-only searches).
    """
    if not DB_STRING:
        return None

    paginate = per_page is not None
    if paginate:
        per_page = per_page if per_page in PER_PAGE_OPTIONS else DEFAULT_PER_PAGE
        page = page if isinstance(page, int) and page > 0 else 1
    else:
        page = 1

    conditions = []
    params: List[Union[str, float]] = []

    # 1. Multi-substance filtering (Option A)
    if substances and len(substances) > 0:
        sub_clauses = []
        for s in substances:
            sub_clauses.append("(LOWER(COALESCE(c.trivial_name, 'Unnamed Compound')) LIKE LOWER(%s) OR LOWER(COALESCE(c.smiles, '')) LIKE LOWER(%s))")
            params.extend([f"%{s.strip()}%", f"%{s.strip()}%"])
        if sub_clauses:
            conditions.append("(" + " OR ".join(sub_clauses) + ")")

    # 2. Single text query fallback (standard search)
    elif query and query.strip():
        conditions.append("(LOWER(COALESCE(c.trivial_name, 'Unnamed Compound')) LIKE LOWER(%s) OR LOWER(COALESCE(c.smiles, '')) LIKE LOWER(%s))")
        q = f"%{query.strip()}%"
        params.extend([q, q])

    # 3. Cluster threshold filtering (Option B: min <= c.<cluster> <= max)
    if thresholds:
        for col_name, spec in thresholds.items():
            if col_name not in CLUSTER_COLUMNS:
                continue
            t_min = spec.get("min") if isinstance(spec, dict) else spec
            t_max = spec.get("max") if isinstance(spec, dict) else None
            if t_min is not None:
                conditions.append(f"c.{col_name} >= %s")
                params.append(float(t_min))
            if t_max is not None:
                conditions.append(f"c.{col_name} <= %s")
                params.append(float(t_max))

    # 4. Concentration range filtering (min_conc <= c.conc_um <= max_conc)
    if min_conc is not None:
        conditions.append("c.conc_um >= %s")
        params.append(float(min_conc))
    if max_conc is not None:
        conditions.append("c.conc_um <= %s")
        params.append(float(max_conc))

    # If neither query, substances, thresholds, nor concentration bounds are provided, return early
    if not conditions:
        return None

    # Exclude unnamed compounds from every backend query.
    conditions.append("(c.trivial_name IS NOT NULL AND TRIM(c.trivial_name) <> '')")

    where_clause = " WHERE " + " AND ".join(conditions)

    # Preserve the user's typed keyword order for multi-compound searches: all
    # profiles matching the first term are grouped ahead of every profile
    # matching the second term, and so on. A CASE expression ranks each row by
    # the first keyword it matches (LIKE against trivial name or SMILES). This
    # is equivalent to ORDER BY array_position(ARRAY[...], lower(trivial_name))
    # but also keeps partial-name and SMILES matches grouped correctly.
    order_params: List[Union[str, float]] = []
    group_order_expr = ""
    if substances and len(substances) > 0:
        rank_whens = []
        for idx, s in enumerate(substances):
            rank_whens.append(
                "WHEN (LOWER(COALESCE(c.trivial_name, 'Unnamed Compound')) LIKE LOWER(%s) "
                "OR LOWER(COALESCE(c.smiles, '')) LIKE LOWER(%s)) THEN " + str(idx)
            )
            order_params.extend([f"%{s.strip()}%", f"%{s.strip()}%"])
        group_order_expr = "CASE " + " ".join(rank_whens) + f" ELSE {len(substances)} END, "

    # Ordering: compound groups follow the typed keyword order. Within a group,
    # an explicit sort wins; otherwise cluster searches rank by their cluster
    # (DESC) and plain searches fall back to batch number then concentration.
    # Every branch ends with the same deterministic tie-breakers so pagination
    # never shuffles rows that share the primary value.
    tie_breakers = "c.trivial_name ASC, c.batch_no ASC, c.conc_um ASC"
    if sort_by in SORT_COLUMN_DB_MAP:
        direction = "DESC" if str(sort_order).lower() == "desc" else "ASC"
        sort_col = SORT_COLUMN_DB_MAP[sort_by]
        order_clause = (
            f"ORDER BY {group_order_expr}{sort_col} {direction} NULLS LAST, {tie_breakers}"
        )
    elif order_by_cluster in CLUSTER_COLUMNS:
        order_clause = (
            f"ORDER BY {group_order_expr}c.{order_by_cluster} DESC NULLS LAST, {tie_breakers}"
        )
    else:
        order_clause = (
            f"ORDER BY {group_order_expr}c.batch_no ASC, c.conc_um ASC, c.trivial_name ASC"
        )

    capped = isinstance(limit, int) and limit > 0
    # Capped result sets are small (10 or 50 rows), so fetch the cap once and
    # slice in Python; uncapped sets paginate in SQL with a window count.
    use_window_count = paginate and not capped

    # 4. Structure SVG selection (Option C: skip_svg)
    if skip_svg:
        svg_select = "'' AS svg"
        join_clause = ""
    else:
        svg_select = "cs.svg"
        join_clause = "LEFT JOIN compound_structures cs ON c.smiles = cs.smiles"

    count_select = ", COUNT(*) OVER() AS full_count" if use_window_count else ""

    base_params = params + order_params

    def build_query(offset_value: int) -> tuple:
        if capped:
            tail_sql = " LIMIT %s"
            tail_params: List[Union[str, float]] = [limit]
        elif paginate:
            tail_sql = " LIMIT %s OFFSET %s"
            tail_params = [per_page, offset_value]
        else:
            tail_sql = ""
            tail_params = []

        sql = f"""
            SELECT
                COALESCE(NULLIF(TRIM(c.trivial_name), ''), 'Unnamed Compound') AS trivial_name,
                c.smiles,
                c.batch_no,
                c.conc_um,
                {svg_select},
                c.relative_cell_count,
                c.induction,
                c.cluster_akt_pi3k_mtor,
                c.cluster_aurora,
                c.cluster_bet,
                c.cluster_dna_synthesis,
                c.cluster_hdac,
                c.cluster_hsp90,
                c.cluster_l_ch,
                c.cluster_mitostress,
                c.cluster_na_k_atpase,
                c.cluster_protein_synthesis,
                c.cluster_pyrimidine_synthesis,
                c.cluster_tubulin,
                c.cluster_uncoupling{count_select}
            FROM {COMPOUNDS_TABLE} c
            {join_clause}
            {where_clause}
            {order_clause}{tail_sql};
        """
        return sql, tuple(base_params + tail_params)

    offset = (page - 1) * per_page if paginate else 0

    if capped:
        sql, query_params = build_query(0)
        rows = _fetch_rows(sql, query_params)
        if rows is None:
            return None
        total_results = len(rows)
        total_pages = math.ceil(total_results / per_page) if paginate and total_results else (1 if total_results else 0)
        if paginate:
            if total_pages:
                page = min(page, total_pages)
                offset = (page - 1) * per_page
                rows = rows[offset:offset + per_page]
            else:
                page = 1
                rows = []
    elif paginate:
        sql, query_params = build_query(offset)
        rows = _fetch_rows(sql, query_params)
        if rows is None:
            return None

        if rows:
            total_results = int(rows[0][-1])
            rows = [row[:-1] for row in rows]
        elif offset > 0:
            # Requested page is past the end: count matches, clamp to the last
            # page, then fetch that slice.
            count_sql = f"SELECT COUNT(*) FROM {COMPOUNDS_TABLE} c {where_clause};"
            count_rows = _fetch_rows(count_sql, tuple(params))
            total_results = int(count_rows[0][0]) if count_rows else 0
            total_pages = math.ceil(total_results / per_page) if total_results else 0
            if total_pages:
                page = min(page, total_pages)
                offset = (page - 1) * per_page
                sql, query_params = build_query(offset)
                refreshed = _fetch_rows(sql, query_params) or []
                rows = [row[:-1] for row in refreshed]
            else:
                page = 1
                rows = []
        else:
            total_results = 0

        total_pages = math.ceil(total_results / per_page) if total_results else 0
        page = min(max(page, 1), total_pages) if total_pages else 1
    else:
        sql, query_params = build_query(0)
        rows = _fetch_rows(sql, query_params)
        if rows is None:
            return None
        total_results = len(rows)
        total_pages = 1 if total_results else 0

    matching_rows: List[List[Union[str, float]]] = []
    for row in rows:
        clean_row = [_sanitize_db_value(val) for val in row]
        if not clean_row[0] or str(clean_row[0]).strip() == "":
            clean_row[0] = "Unnamed Compound"
        matching_rows.append(clean_row)

    output: List[List[Union[str, float]]] = [list(DATASET_HEADER)]
    output.extend(matching_rows)

    return {
        "output": output,
        "total_results": total_results,
        "page": page,
        "per_page": per_page or DEFAULT_PER_PAGE,
        "total_pages": total_pages,
    }


@app.route("/")
def landing():
    if "count" in session:
        return render_template("search.html")
    return redirect("/setup")


@app.route("/search", methods=["GET", "POST"])
def search():
    # Post/Redirect/Get: turn any form POST into a canonical GET request so that
    # Back/Forward, refresh, and history navigation never re-POST or hit a 405.
    if request.method == "POST":
        form_dict = request.form.to_dict()
        # Drop empty concentration bounds so they never become "min_conc=".
        for key in ("min_conc", "max_conc"):
            if not form_dict.get(key, "").strip():
                form_dict.pop(key, None)
        return redirect(url_for("search", **form_dict), code=303)

    start = time.time()
    inp = normalize_text(request.args.get("nm") or request.args.get("q") or "")

    # Parse the optional concentration range (min_conc / max_conc).
    min_conc = parse_conc_bound(request.values.get("min_conc"))
    max_conc = parse_conc_bound(request.values.get("max_conc"))
    if min_conc is not None and max_conc is not None and min_conc > max_conc:
        min_conc, max_conc = max_conc, min_conc
    has_conc_filter = min_conc is not None or max_conc is not None

    # Parse Advanced Search keywords. Input may be comma-, space-, or
    # newline-delimited; terms shorter than 3 chars and empty tokens are ignored,
    # and the list is capped at 5 terms. Terms are lowercased and stripped of
    # hidden whitespace before querying.
    substances = normalize_search_terms(request.args.get("substances", ""))

    # Parse cluster threshold filters. A cluster column is selected via the
    # `cluster` field (legacy `threshold` acts as the lower bound); generic
    # min_threshold/max_threshold default to 75/100 and are read from either GET
    # or POST data. Per-cluster inline fields remain supported as a fallback.
    selected_cluster = (
        request.values.get("cluster")
        or request.values.get("cluster_col")
        or request.values.get("order_by_cluster")
    )
    if selected_cluster not in CLUSTER_COLUMNS:
        selected_cluster = next(
            (
                c for c in CLUSTER_COLUMNS
                if any(
                    request.values.get(f"{name}_{c}") not in (None, "")
                    for name in ("min_threshold", "max_threshold", "threshold")
                )
            ),
            None,
        )

    def _to_float(value: object, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return float(default)

    min_threshold = float(MIN_CLUSTER_THRESHOLD)
    max_threshold = float(MAX_CLUSTER_THRESHOLD)
    thresholds = {}
    if selected_cluster in CLUSTER_COLUMNS:
        min_raw = request.values.get(f"min_threshold_{selected_cluster}") or request.values.get("min_threshold")
        max_raw = request.values.get(f"max_threshold_{selected_cluster}") or request.values.get("max_threshold")
        legacy_raw = request.values.get(f"threshold_{selected_cluster}") or request.values.get("threshold")
        if min_raw in (None, "") and legacy_raw not in (None, ""):
            min_raw = legacy_raw
        if min_raw not in (None, ""):
            min_threshold = _to_float(min_raw, MIN_CLUSTER_THRESHOLD)
        if max_raw not in (None, ""):
            max_threshold = _to_float(max_raw, MAX_CLUSTER_THRESHOLD)
        thresholds[selected_cluster] = {"min": min_threshold, "max": max_threshold}

    # Enforce mutual exclusivity between keyword and cluster threshold search:
    # keywords take priority, so any selected cluster/threshold parameters are
    # discarded and never used to filter or constrain keyword results.
    if substances:
        selected_cluster = None
        thresholds = {}

    # Parse skip_svg option
    skip_svg = bool(request.args.get("skip_svg"))

    # Validate that at least one filter criterion is active (Case D is invalid)
    if not inp and not substances and not thresholds and not has_conc_filter:
        return redirect("/error")

    # If advanced search parameters (substances, thresholds, or concentration) are present without
    # an explicit primary keyword input, prioritize them. If a keyword is provided alongside a
    # concentration range, keep inp active so matching compounds are filtered by concentration.
    if substances or thresholds:
        inp = ""

    # Resolve the query plan (Case A/B/C ordering and result cap)
    order_by_cluster = None
    limit = None
    if substances or thresholds:
        plan = resolve_query_plan(substances, thresholds)
        if plan is None:
            return redirect("/error")
        order_by_cluster = plan["order_by_cluster"]
        limit = plan["limit"]
    elif has_conc_filter and not inp:
        # Guardrail: searching purely by concentration without keyword or cluster
        # enforces a strict LIMIT to prevent an unbounded full-table dump.
        limit = 50

    # Sorting is validated against the active cluster filters so a cluster score
    # can only be chosen while that cluster is actually being filtered on.
    sort_by, sort_order = resolve_sort(
        request.args.get("sort_by"),
        request.args.get("order"),
        thresholds,
    )
    per_page = parse_per_page(request.args.get("per_page"))
    page = parse_page_number(request.args.get("page"))

    counter = session.get("count", [time.strftime("%Y-%m-%d"), 0])
    if counter[1] >= MAX_SEARCH_COUNT:
        return render_template(
            "main.html",
            max_reached=True,
            min_threshold=min_threshold,
            max_threshold=max_threshold,
            min_conc=None,
            max_conc=None,
            conc_min_value="0.2",
            conc_max_value="50",
        )

    today = time.strftime("%Y-%m-%d")
    if counter[0] != today:
        session["count"] = [today, 0]
    elif page <= 1:
        # Only a fresh search counts toward the daily quota; paging through an
        # existing result set must not spend searches.
        counter[1] += 1
        session["count"] = counter

    result = find_compounds(
        query=inp if inp else None,
        substances=substances if substances else None,
        thresholds=thresholds if thresholds else None,
        min_conc=min_conc,
        max_conc=max_conc,
        skip_svg=skip_svg,
        order_by_cluster=order_by_cluster,
        limit=limit,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        per_page=per_page,
    )
    if not result or result["total_results"] <= 0 or len(result["output"]) <= 1:
        return redirect("/error")

    output = result["output"]
    total_results = result["total_results"]
    page = result["page"]
    per_page = result["per_page"]
    total_pages = result["total_pages"]

    end = time.time()
    elapsed_ms = int((end - start) * 1000)

    conc_desc = describe_conc_range(min_conc, max_conc)

    # Determine informative display query label
    if substances:
        display_query = ", ".join(substances)
        if thresholds:
            thresh_desc = ", ".join(
                describe_threshold(col, spec) for col, spec in thresholds.items()
            )
            display_query += f" + Cluster filter: {thresh_desc}"
        if conc_desc:
            display_query += f" + {conc_desc}"
    elif thresholds:
        # User searched purely by cluster thresholds
        thresh_desc = ", ".join(
            describe_threshold(col, spec) for col, spec in thresholds.items()
        )
        display_query = f"Cluster filter: {thresh_desc}"
        if conc_desc:
            display_query += f" + {conc_desc}"
    elif inp:
        display_query = inp
        if conc_desc:
            display_query += f" + {conc_desc}"
    else:
        display_query = conc_desc or "All Compounds"

    # Case B (cluster-only) returns the top 10 highest-scoring profiles
    if limit:
        display_query += f" (Top {limit} by score)"

    active_filters = []
    if substances:
        for s in substances:
            active_filters.append({"type": "substance", "label": s})
    if thresholds:
        for col, spec in thresholds.items():
            cname = CLUSTER_DISPLAY_NAMES.get(col, col)
            lo = spec.get("min")
            hi = spec.get("max")
            active_filters.append({
                "type": "cluster",
                "key": col,
                "label": describe_threshold(col, spec),
                "cluster_name": cname,
                "min": format_threshold_value(lo) if lo is not None else None,
                "max": format_threshold_value(hi) if hi is not None else None,
            })
    if has_conc_filter:
        active_filters.append({
            "type": "concentration",
            "key": "conc",
            "label": conc_desc,
            "min": format_conc_value(min_conc) if min_conc is not None else None,
            "max": format_conc_value(max_conc) if max_conc is not None else None,
        })

    active_filter_count = len(active_filters)

    # Canonical search state used to rebuild URLs and hidden form fields without
    # dropping any active filter when sorting, changing page size, or paging.
    search_state = {}
    if inp:
        search_state["nm"] = inp
    if substances:
        search_state["substances"] = ",".join(substances)
    if thresholds:
        for col, spec in thresholds.items():
            search_state["cluster"] = col
            search_state["min_threshold_" + col] = format_threshold_value(spec.get("min"))
            search_state["max_threshold_" + col] = format_threshold_value(spec.get("max"))
    if min_conc is not None:
        search_state["min_conc"] = format_conc_value(min_conc)
    if max_conc is not None:
        search_state["max_conc"] = format_conc_value(max_conc)
    if skip_svg:
        search_state["skip_svg"] = "1"

    def _page_url(target_page: int) -> str:
        params = dict(search_state)
        params["per_page"] = per_page
        if sort_by:
            params["sort_by"] = sort_by
            params["order"] = sort_order
        params["page"] = target_page
        return url_for("search", **params)

    has_prev = page > 1
    has_next = page < total_pages
    pagination = {
        "page": page,
        "per_page": per_page,
        "total_results": total_results,
        "total_pages": total_pages,
        "has_prev": has_prev,
        "has_next": has_next,
        "prev_url": _page_url(page - 1) if has_prev else "",
        "next_url": _page_url(page + 1) if has_next else "",
        "page_start": (page - 1) * per_page + 1 if total_results else 0,
        "page_end": min(page * per_page, total_results),
    }

    cluster_sort_key = next(iter(thresholds), None) if thresholds else None
    cluster_sort_label = CLUSTER_DISPLAY_NAMES.get(cluster_sort_key, "") if cluster_sort_key else ""

    session["last_search"] = {
        "query": inp if inp else None,
        "substances": substances if substances else None,
        "thresholds": thresholds if thresholds else None,
        "min_conc": min_conc,
        "max_conc": max_conc,
        "order_by_cluster": order_by_cluster,
        "limit": limit,
        "sort_by": sort_by,
        "sort_order": sort_order,
        "skip_svg": True,  # Text export never needs SVG
        "display_name": display_query,
    }

    return render_template(
        "main.html",
        output=output,
        counter=len(output),
        search_query=inp,
        display_query=display_query,
        active_filters=active_filters,
        active_filter_count=active_filter_count,
        substances=substances,
        thresholds=thresholds,
        min_conc=min_conc,
        max_conc=max_conc,
        conc_min_value=format_conc_value(min_conc) if min_conc is not None else "0.2",
        conc_max_value=format_conc_value(max_conc) if max_conc is not None else "50",
        min_threshold=min_threshold,
        max_threshold=max_threshold,
        skip_svg=skip_svg,
        tmpfile_url="",
        max_reached=False,
        results_length=total_results,
        elapsed_ms=elapsed_ms,
        fname=display_query,
        sort_by=sort_by,
        order=sort_order,
        page=page,
        per_page=per_page,
        per_page_options=PER_PAGE_OPTIONS,
        total_pages=total_pages,
        pagination=pagination,
        search_state=search_state,
        cluster_sort_key=cluster_sort_key,
        cluster_sort_label=cluster_sort_label,
    )


@app.route("/download", methods=["GET", "POST"])
@app.route("/download/<path:fname>", methods=["GET", "POST"])
def download(fname: Optional[str] = None):
    """Generate and stream search result text export directly in-memory."""
    # Determine the query from route parameter or query string
    query = request.args.get("q") or fname or ""
    # Strip any trailing extension if present in the URL parameter
    if query.endswith(".txt"):
        query = query[:-4]
    query = query.strip()

    last_search = session.get("last_search")
    if last_search and (not query or query == last_search.get("display_name")):
        result = find_compounds(
            query=last_search.get("query"),
            substances=last_search.get("substances"),
            thresholds=last_search.get("thresholds"),
            min_conc=last_search.get("min_conc"),
            max_conc=last_search.get("max_conc"),
            skip_svg=True,
            order_by_cluster=last_search.get("order_by_cluster"),
            limit=last_search.get("limit"),
            sort_by=last_search.get("sort_by"),
            sort_order=last_search.get("sort_order") or "asc",
        )
        safe_filename = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in last_search.get("display_name", "search_results")) or "search_results"
    else:
        if not query:
            return redirect("/")
        result = find_compounds(query=query, skip_svg=True)
        safe_filename = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in query) or "search_results"

    if not result or result["total_results"] <= 0 or len(result["output"]) <= 1:
        return redirect("/error")

    content = export_to_text(result["output"])

    return Response(
        content,
        mimetype="text/plain; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_filename}.txt"',
            "Content-Type": "text/plain; charset=utf-8",
        },
    )


@app.route("/contact")
def contact():
    return render_template("contact.html")


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/versions")
def versions():
    return render_template("versions.html")


@app.route("/setup")
def setup():
    today = time.strftime("%Y-%m-%d")
    session["count"] = [today, 0]
    return redirect("/")


@app.route("/error")
def error():
    return render_template("error.html")


@app.route("/reset")
def reset():
    session.clear()
    return redirect("/")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8081))
    app.run(host="0.0.0.0", port=port, debug=False)
