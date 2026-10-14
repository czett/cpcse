from decimal import Decimal
import io
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
)
import psycopg2
from psycopg2 import pool

# Constants
DELIMITER = "|"
MAX_SEARCH_COUNT = 1000
MAX_SEARCH_TERMS = 5
MIN_TERM_LENGTH = 3
MIN_CLUSTER_THRESHOLD = 70
CLUSTER_TOP_RESULTS = 10

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
        token = token.strip()
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
        "limit": CLUSTER_TOP_RESULTS if (cluster_col and not has_keywords) else None,
    }


def find_compounds(
    query: Optional[str] = None,
    substances: Optional[List[str]] = None,
    thresholds: Optional[dict] = None,
    skip_svg: bool = False,
    order_by_cluster: Optional[str] = None,
    limit: Optional[int] = None,
) -> Optional[List[List[Union[str, float]]]]:
    """Search compounds from PostgreSQL matching query/substances and a cluster threshold.

    Optionally sorts descending by a single cluster score and caps the result set.
    """
    if not DB_STRING:
        return None

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

    # 3. Cluster threshold filtering (Option B: c.<cluster> >= threshold)
    if thresholds:
        for col_name, thresh_val in thresholds.items():
            if col_name in CLUSTER_COLUMNS:
                conditions.append(f"c.{col_name} >= %s")
                params.append(float(thresh_val))

    # If neither query, substances, nor thresholds are provided, return early
    if not conditions:
        return None

    where_clause = " WHERE " + " AND ".join(conditions)

    # Ordering: cluster-ranked searches sort strictly by the chosen cluster (DESC),
    # otherwise fall back to the default batch/conc ordering.
    if order_by_cluster in CLUSTER_COLUMNS:
        order_clause = f"ORDER BY c.{order_by_cluster} DESC NULLS LAST"
    else:
        order_clause = "ORDER BY c.batch_no, c.conc_um"

    # Optional cap (Case B: top N highest-scoring profiles).
    limit_clause = ""
    if isinstance(limit, int) and limit > 0:
        limit_clause = " LIMIT %s"

    # 4. Structure SVG selection (Option C: skip_svg)
    if skip_svg:
        svg_select = "'' AS svg"
        join_clause = ""
    else:
        svg_select = "cs.svg"
        join_clause = "LEFT JOIN compound_structures cs ON c.smiles = cs.smiles"

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
            c.cluster_uncoupling
        FROM compounds c
        {join_clause}
        {where_clause}
        {order_clause}{limit_clause};
    """

    if limit_clause:
        params.append(limit)

    conn = None
    try:
        if db_pool:
            conn = db_pool.getconn()
        else:
            conn = psycopg2.connect(DB_STRING)

        with conn.cursor() as cur:
            cur.execute(sql, tuple(params))
            rows = cur.fetchall()

        if not rows:
            return None

        matching_rows: List[List[Union[str, float]]] = []
        for row in rows:
            clean_row = [_sanitize_db_value(val) for val in row]
            if not clean_row[0] or str(clean_row[0]).strip() == "":
                clean_row[0] = "Unnamed Compound"
            matching_rows.append(clean_row)

        output: List[List[Union[str, float]]] = [list(DATASET_HEADER)]
        output.extend(matching_rows)
        return output

    except Exception as e:
        print(f"Error querying database: {e}")
        return None
    finally:
        if conn:
            if db_pool:
                db_pool.putconn(conn)
            else:
                conn.close()


@app.route("/")
def landing():
    if "count" in session:
        return render_template("search.html")
    return redirect("/setup")


@app.route("/search", methods=["POST"])
def search():
    start = time.time()
    inp = request.form.get("nm", "").strip()

    # Parse Advanced Search keywords. Input may be comma-, space-, or
    # newline-delimited; terms shorter than 3 chars and empty tokens are ignored,
    # and the list is capped at 5 terms.
    substances = normalize_search_terms(request.form.get("substances", ""))

    # Parse cluster threshold filters. Only a single cluster may be selected;
    # the first active cluster is honoured and its threshold is floored at 70%.
    thresholds = {}
    for col_name in CLUSTER_COLUMNS:
        t_val = request.form.get(f"threshold_{col_name}")
        if t_val is not None and t_val.strip() != "":
            try:
                thresholds[col_name] = max(MIN_CLUSTER_THRESHOLD, float(t_val.strip()))
            except ValueError:
                pass
            break

    # Parse skip_svg option
    skip_svg = bool(request.form.get("skip_svg"))

    # Validate that at least one filter criterion is active (Case D is invalid)
    if not inp and not substances and not thresholds:
        return redirect("/error")

    # If advanced search parameters (substances or thresholds) are present,
    # prioritize them and do not restrict by the main top input
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

    counter = session.get("count", [time.strftime("%Y-%m-%d"), 0])
    if counter[1] >= MAX_SEARCH_COUNT:
        return render_template("main.html", max_reached=True)

    today = time.strftime("%Y-%m-%d")
    if counter[0] != today:
        session["count"] = [today, 0]
    else:
        counter[1] += 1
        session["count"] = counter

    output = find_compounds(
        query=inp if inp else None,
        substances=substances if substances else None,
        thresholds=thresholds if thresholds else None,
        skip_svg=skip_svg,
        order_by_cluster=order_by_cluster,
        limit=limit,
    )
    if not output or len(output) <= 1:
        return redirect("/error")

    end = time.time()
    elapsed_ms = int((end - start) * 1000)

    # Determine informative display query label
    if substances:
        display_query = ", ".join(substances)
        if thresholds:
            thresh_desc = ", ".join([
                f"{CLUSTER_DISPLAY_NAMES.get(col, col)} (≥{int(v) if v.is_integer() else v}%)"
                for col, v in thresholds.items()
            ])
            display_query += f" + Cluster filter: {thresh_desc}"
    elif thresholds:
        # User searched purely by cluster thresholds
        thresh_desc = ", ".join([
            f"{CLUSTER_DISPLAY_NAMES.get(col, col)} (≥{int(v) if v.is_integer() else v}%)"
            for col, v in thresholds.items()
        ])
        display_query = f"Cluster filter: {thresh_desc}"
    else:
        display_query = inp

    # Case B (cluster-only) returns the top 10 highest-scoring profiles
    if limit:
        display_query += f" (Top {limit} by score)"

    active_filters = []
    if substances:
        for s in substances:
            active_filters.append({"type": "substance", "label": s})
    if thresholds:
        for col, v in thresholds.items():
            cname = CLUSTER_DISPLAY_NAMES.get(col, col)
            val_fmt = int(v) if v.is_integer() else v
            active_filters.append({
                "type": "cluster",
                "key": col,
                "label": f"{cname} ≥ {val_fmt}%",
                "cluster_name": cname,
                "val": val_fmt,
            })

    active_filter_count = len(active_filters)

    session["last_search"] = {
        "query": inp if inp else None,
        "substances": substances if substances else None,
        "thresholds": thresholds if thresholds else None,
        "order_by_cluster": order_by_cluster,
        "limit": limit,
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
        skip_svg=skip_svg,
        tmpfile_url="",
        max_reached=False,
        results_length=len(output) - 1,
        elapsed_ms=elapsed_ms,
        fname=display_query,
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
        results = find_compounds(
            query=last_search.get("query"),
            substances=last_search.get("substances"),
            thresholds=last_search.get("thresholds"),
            skip_svg=True,
            order_by_cluster=last_search.get("order_by_cluster"),
            limit=last_search.get("limit"),
        )
        safe_filename = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in last_search.get("display_name", "search_results")) or "search_results"
    else:
        if not query:
            return redirect("/")
        results = find_compounds(query=query, skip_svg=True)
        safe_filename = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in query) or "search_results"

    if not results or len(results) <= 1:
        return redirect("/error")

    content = export_to_text(results)
    safe_filename = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in query) or "search_results"

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
