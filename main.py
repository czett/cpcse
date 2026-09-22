import base64
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
from rdkit import Chem
from rdkit.Chem.Draw import rdMolDraw2D

# Constants
DATASET_FILENAME = "2612.txt"
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


def _load_dataset() -> Tuple[List[str], List[List[str]]]:
    """Pre-load and parse the compound dataset at application startup."""
    dataset_path = op.join(app.root_path, DATASET_FILENAME)
    if not op.exists(dataset_path):
        return [], []

    with open(dataset_path, "r", encoding="latin-1") as f:
        raw_lines = [line.strip() for line in f if line.strip()]

    if not raw_lines:
        return [], []

    header = raw_lines[0].split(DELIMITER)
    header.insert(4, "Structure")

    rows = [line.split(DELIMITER) for line in raw_lines[1:]]
    return header, rows


DATASET_HEADER, DATASET_ROWS = _load_dataset()


def smiletob64(smile: str) -> str:
    """Convert a SMILES string to a base64 encoded PNG image string."""
    if not smile:
        return ""
    try:
        mol = Chem.MolFromSmiles(smile)
        if mol is None:
            return ""
        drawer = rdMolDraw2D.MolDraw2DCairo(500, 500)
        drawer.SetFontSize(10)
        drawer.DrawMolecule(mol)
        drawer.FinishDrawing()
        drawing_text = drawer.GetDrawingText()
        return base64.b64encode(drawing_text).decode("utf-8")
    except Exception:
        return ""


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
        # Data rows omit the raw base64 image (index 4) for text export
        for row in data[1:]:
            clean_row = row[:4] + row[5:]
            f.write(DELIMITER.join(map(str, clean_row)) + "\n")


def find_compounds(query: str) -> Optional[List[List[Union[str, float]]]]:
    """Search dataset for compounds matching query in trivial name or SMILES."""
    if not query:
        return None

    query_lower = query.lower()
    matching_rows: List[List[Union[str, float]]] = []

    for line in DATASET_ROWS:
        if len(line) < 2:
            continue
        name_match = query_lower in line[0].lower()
        smiles_match = query_lower in line[1].lower()

        if name_match or smiles_match:
            modified_line: List[Union[str, float]] = list(line)
            # Insert base64 structure image at index 4
            modified_line.insert(4, smiletob64(line[1]))

            # Convert numeric strings to floats
            for i in range(len(modified_line)):
                try:
                    modified_line[i] = float(modified_line[i])  # type: ignore
                except (ValueError, TypeError):
                    pass

            matching_rows.append(modified_line)

    if not matching_rows:
        return None

    # Sort matching rows by Batch No (index 2) then Conc uM (index 3)
    matching_rows.sort(key=lambda x: (x[2], x[3]))

    output: List[List[Union[str, float]]] = [list(DATASET_HEADER)]
    output.extend(matching_rows)
    return output


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
    app.run(host="0.0.0.0", port=port)
