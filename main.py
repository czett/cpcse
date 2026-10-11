from decimal import Decimal
import io
import os
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


def find_compounds(query: str) -> Optional[List[List[Union[str, float]]]]:
    """Search compounds from PostgreSQL matching query in trivial name or SMILES."""
    if not query or not DB_STRING:
        return None

    query_param = f"%{query.strip()}%"
    sql = """
        SELECT
            trivial_name, smiles, batch_no, conc_um, structure, relative_cell_count,
            induction, cluster_akt_pi3k_mtor, cluster_aurora, cluster_bet,
            cluster_dna_synthesis, cluster_hdac, cluster_hsp90, cluster_l_ch,
            cluster_mitostress, cluster_na_k_atpase, cluster_protein_synthesis,
            cluster_pyrimidine_synthesis, cluster_tubulin, cluster_uncoupling
        FROM compounds
        WHERE LOWER(trivial_name) LIKE LOWER(%s) OR LOWER(smiles) LIKE LOWER(%s)
        ORDER BY batch_no, conc_um;
    """

    conn = None
    try:
        if db_pool:
            conn = db_pool.getconn()
        else:
            conn = psycopg2.connect(DB_STRING)

        with conn.cursor() as cur:
            cur.execute(sql, (query_param, query_param))
            rows = cur.fetchall()

        if not rows:
            return None

        matching_rows: List[List[Union[str, float]]] = []
        for row in rows:
            clean_row = [_sanitize_db_value(val) for val in row]
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

    if not inp:
        return redirect("/error")

    counter = session.get("count", [time.strftime("%Y-%m-%d"), 0])
    if counter[1] >= MAX_SEARCH_COUNT:
        return render_template("main.html", max_reached=True)

    today = time.strftime("%Y-%m-%d")
    if counter[0] != today:
        session["count"] = [today, 0]
    else:
        counter[1] += 1
        session["count"] = counter

    output = find_compounds(inp)
    if not output or len(output) <= 1:
        return redirect("/error")

    end = time.time()
    elapsed_ms = int((end - start) * 1000)

    return render_template(
        "main.html",
        output=output,
        counter=len(output),
        query=inp,
        tmpfile_url="",
        max_reached=False,
        results_length=len(output) - 1,
        elapsed_ms=elapsed_ms,
        fname=inp,
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

    if not query:
        return redirect("/")

    results = find_compounds(query)
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
    app.run(host="0.0.0.0", port=port, debug=True)
