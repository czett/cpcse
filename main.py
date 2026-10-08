from decimal import Decimal
import os
import os.path as op
import random
import string
import time
from typing import List, Optional, Tuple, Union

import dotenv
from flask import (
    Flask,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
)
import psycopg2
from psycopg2 import pool

# Constants
DELIMITER = "|"
MAX_SEARCH_COUNT = 1000
TMP_FILE_MAX_AGE = 600  # seconds (10 minutes)
TMP_FILE_MAX_COUNT = 100  # max .txt files per tmp directory

# Global cleanup tracking
LAST_CLEANUP_TIME = 0.0
CLEANUP_INTERVAL = 60.0  # throttle directory scans to once per 60 seconds

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


def gen_name(length: int = 24) -> str:
    """Generate a random lowercase string of specified length."""
    return "".join(random.choice(string.ascii_lowercase) for _ in range(length))


def cleanup_tmp_directories(
    max_age_seconds: int = TMP_FILE_MAX_AGE,
    max_files: int = TMP_FILE_MAX_COUNT,
    force: bool = False,
) -> None:
    """
    Clean up .txt files in temporary directories ('static/tmp' and 'tmp').

    - Deletes files older than max_age_seconds.
    - If total .txt files in a directory exceeds max_files, deletes the oldest files.
    - Throttled to execute at most once per CLEANUP_INTERVAL unless force=True.
    """
    global LAST_CLEANUP_TIME
    now = time.time()
    if not force and (now - LAST_CLEANUP_TIME < CLEANUP_INTERVAL):
        return
    LAST_CLEANUP_TIME = now

    tmp_dirs = [
        op.join(app.root_path, "static", "tmp"),
        op.join(app.root_path, "tmp"),
    ]

    for tmp_dir in tmp_dirs:
        if not op.exists(tmp_dir):
            os.makedirs(tmp_dir, exist_ok=True)
            continue

        txt_files: List[Tuple[str, float]] = []
        for f in os.listdir(tmp_dir):
            if f.endswith(".txt"):
                filepath = op.join(tmp_dir, f)
                if op.isfile(filepath):
                    try:
                        mtime = os.stat(filepath).st_mtime
                        txt_files.append((filepath, mtime))
                    except OSError:
                        pass

        # Sort files by modification time (oldest first)
        txt_files.sort(key=lambda item: item[1])

        # Remove files older than max_age_seconds
        surviving_files: List[Tuple[str, float]] = []
        for filepath, mtime in txt_files:
            if (now - mtime) > max_age_seconds:
                try:
                    os.remove(filepath)
                except OSError:
                    pass
            else:
                surviving_files.append((filepath, mtime))

        # Enforce max_files limit by deleting oldest remaining files
        if len(surviving_files) > max_files:
            num_to_delete = len(surviving_files) - max_files
            for filepath, _ in surviving_files[:num_to_delete]:
                try:
                    os.remove(filepath)
                except OSError:
                    pass


def write_data(data: List[List[Union[str, float]]], fname: str) -> None:
    """Write search result data to a pipe-delimited text file in static/tmp/."""
    out_dir = op.join(app.root_path, "static", "tmp")
    os.makedirs(out_dir, exist_ok=True)
    out_path = op.join(out_dir, f"{fname}.txt")

    with open(out_path, "w", encoding="utf-8") as f:
        # Header row includes 'Structure' column header
        if data:
            f.write(DELIMITER.join(map(str, data[0])) + "\n")
        # Data rows omit the raw structure SVG/image (index 4) for text export
        for row in data[1:]:
            clean_row = row[:4] + row[5:]
            f.write(DELIMITER.join(map(str, clean_row)) + "\n")


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

    filen = gen_name(24)
    write_data(output, filen)
    cleanup_tmp_directories()

    end = time.time()
    elapsed_ms = int((end - start) * 1000)

    return render_template(
        "main.html",
        output=output,
        counter=len(output),
        tmpfile_url="",
        max_reached=False,
        results_length=len(output) - 1,
        elapsed_ms=elapsed_ms,
        fname=filen,
    )


@app.route("/download/<fname>", methods=["GET", "POST"])
def download(fname: str):
    """Serve generated text files from static/tmp or tmp directories."""
    candidate_names = [f"{fname}.txt", fname] if not fname.endswith(".txt") else [fname]
    target_dirs = [
        op.join(app.root_path, "static", "tmp"),
        op.join(app.root_path, "tmp"),
    ]

    for target_dir in target_dirs:
        for name in candidate_names:
            if op.isfile(op.join(target_dir, name)):
                return send_from_directory(target_dir, name, as_attachment=True)

    return redirect("/")


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
