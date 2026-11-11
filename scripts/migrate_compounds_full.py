"""Create and populate the ``compounds_full`` table from the reference TSV.

The new table keeps every column and column name of the original ``compounds``
table (so existing queries in ``main.py`` keep working unchanged) and adds the
extra columns present in ``temp/ds_refs_sim_to_clusters_webapp.tsv``.

The script is idempotent: it creates the table and indexes if needed, fills in
missing structure SVGs, then reloads ``compounds_full`` from the TSV.
"""

import csv
import os
import re
import sys

import dotenv
import psycopg2
from psycopg2.extras import execute_values

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

from svg_render_helper import smiles_to_svg  # noqa: E402

TSV_PATH = os.path.join(ROOT_DIR, "temp", "ds_refs_sim_to_clusters_webapp.tsv")
TABLE_NAME = "compounds_full"

CREATE_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
    id SERIAL PRIMARY KEY,
    trivial_name TEXT,
    smiles TEXT,
    batch_no NUMERIC,
    conc_um NUMERIC,
    relative_cell_count NUMERIC,
    induction NUMERIC,
    cluster_akt_pi3k_mtor NUMERIC,
    cluster_aurora NUMERIC,
    cluster_bet NUMERIC,
    cluster_dna_synthesis NUMERIC,
    cluster_hdac NUMERIC,
    cluster_hsp90 NUMERIC,
    cluster_l_ch NUMERIC,
    cluster_mitostress NUMERIC,
    cluster_na_k_atpase NUMERIC,
    cluster_protein_synthesis NUMERIC,
    cluster_pyrimidine_synthesis NUMERIC,
    cluster_tubulin NUMERIC,
    cluster_uncoupling NUMERIC,
    compound_id BIGINT,
    well_id TEXT,
    is_ref BOOLEAN,
    cluster_high TEXT,
    cluster_sim NUMERIC,
    known_act TEXT,
    chiral BOOLEAN
);
"""

INDEX_SQL = [
    f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_smiles ON {TABLE_NAME} (smiles);",
    f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_trivial_name ON {TABLE_NAME} (LOWER(trivial_name));",
    f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_compound_id ON {TABLE_NAME} (compound_id);",
    f"CREATE UNIQUE INDEX IF NOT EXISTS idx_{TABLE_NAME}_well_id ON {TABLE_NAME} (well_id);",
]

# TSV header -> compounds_full column, in insert order.
COLUMN_MAP = [
    ("Compound_Id", "compound_id"),
    ("Batch_No", "batch_no"),
    ("Well_Id", "well_id"),
    ("Is_Ref", "is_ref"),
    ("Conc_uM", "conc_um"),
    ("Rel_Cell_Count", "relative_cell_count"),
    ("Induction", "induction"),
    ("Cluster_AKT_PI3K_MTOR", "cluster_akt_pi3k_mtor"),
    ("Cluster_Aurora", "cluster_aurora"),
    ("Cluster_BET", "cluster_bet"),
    ("Cluster_DNA_Synth", "cluster_dna_synthesis"),
    ("Cluster_HDAC", "cluster_hdac"),
    ("Cluster_HSP90", "cluster_hsp90"),
    ("Cluster_LCH", "cluster_l_ch"),
    ("Cluster_MitoStress", "cluster_mitostress"),
    ("Cluster_Na_K-ATPase", "cluster_na_k_atpase"),
    ("Cluster_Protein_Synth", "cluster_protein_synthesis"),
    ("Cluster_Pyrimidine_Synth", "cluster_pyrimidine_synthesis"),
    ("Cluster_Tubulin", "cluster_tubulin"),
    ("Cluster_Uncoupler", "cluster_uncoupling"),
    ("Cluster_High", "cluster_high"),
    ("Cluster_Sim", "cluster_sim"),
    ("Trivial_Name", "trivial_name"),
    ("Known_Act", "known_act"),
    ("Chiral", "chiral"),
    ("Smiles", "smiles"),
]

NUMERIC_COLUMNS = {
    "batch_no",
    "conc_um",
    "relative_cell_count",
    "induction",
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
    "cluster_sim",
}
INTEGER_COLUMNS = {"compound_id"}
BOOLEAN_COLUMNS = {"is_ref", "chiral"}


def _clean(value):
    """Normalise a TSV field to None or a stripped string."""
    if value is None:
        return None
    value = value.strip()
    return value or None


def _as_bool(value):
    if value is None:
        return None
    return value.lower() in {"true", "t", "1", "yes", "y"}


def read_tsv(path):
    with open(path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="|")
        rows = list(reader)
    missing = [src for src, _ in COLUMN_MAP if src not in (reader.fieldnames or [])]
    if missing:
        raise RuntimeError(f"TSV is missing expected columns: {missing}")
    return rows


def convert_row(row):
    values = []
    for source, target in COLUMN_MAP:
        value = _clean(row.get(source))
        if value is None:
            values.append(None)
        elif target in BOOLEAN_COLUMNS:
            values.append(_as_bool(value))
        elif target in INTEGER_COLUMNS:
            values.append(int(value))
        elif target in NUMERIC_COLUMNS:
            values.append(float(value))
        else:
            values.append(value)
    return tuple(values)


def main():
    dotenv.load_dotenv(os.path.join(ROOT_DIR, ".env"))
    db_string = os.getenv("DB_STRING")
    if not db_string:
        raise SystemExit("DB_STRING is not set; cannot run migration.")

    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", TABLE_NAME):
        raise SystemExit(f"Unsafe table name: {TABLE_NAME!r}")

    rows = read_tsv(TSV_PATH)
    print(f"Read {len(rows)} rows from {TSV_PATH}")

    conn = psycopg2.connect(db_string)
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            print(f"Creating table {TABLE_NAME} if needed...")
            cur.execute(CREATE_TABLE_SQL)
            for statement in INDEX_SQL:
                cur.execute(statement)

            # Fill in structure SVGs that are not in compound_structures yet.
            cur.execute("SELECT smiles FROM compound_structures")
            existing_smiles = {r[0] for r in cur.fetchall()}
            needed_smiles = sorted(
                {row["Smiles"].strip() for row in rows if row.get("Smiles")}
            )
            missing_smiles = [
                smiles for smiles in needed_smiles if smiles not in existing_smiles
            ]
            print(
                f"Structures: {len(needed_smiles)} distinct SMILES in TSV, "
                f"{len(missing_smiles)} missing."
            )

            generated = 0
            failed = []
            for smiles in missing_smiles:
                svg = smiles_to_svg(smiles)
                if not svg:
                    failed.append(smiles)
                    continue
                cur.execute(
                    "INSERT INTO compound_structures (smiles, svg) VALUES (%s, %s) "
                    "ON CONFLICT (smiles) DO NOTHING",
                    (smiles, svg),
                )
                generated += 1
            print(f"Inserted {generated} new structure SVG(s).")
            if failed:
                print(f"WARNING: {len(failed)} SMILES could not be rendered:")
                for smiles in failed:
                    print(f"  {smiles}")

            # Reload the table so repeated runs always match the TSV exactly.
            cur.execute(f"TRUNCATE {TABLE_NAME} RESTART IDENTITY")
            insert_columns = [target for _, target in COLUMN_MAP]
            insert_sql = (
                f"INSERT INTO {TABLE_NAME} ({', '.join(insert_columns)}) VALUES %s"
            )
            execute_values(cur, insert_sql, [convert_row(row) for row in rows], page_size=500)
            print(f"Inserted {len(rows)} rows into {TABLE_NAME}.")

            cur.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}")
            count = cur.fetchone()[0]
            cur.execute(
                f"SELECT COUNT(*) FROM {TABLE_NAME} c "
                "LEFT JOIN compound_structures cs ON c.smiles = cs.smiles "
                "WHERE cs.smiles IS NULL"
            )
            without_svg = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM compounds")
            old_count = cur.fetchone()[0]

        conn.commit()
        print(
            f"Done. {TABLE_NAME}: {count} rows, {without_svg} without SVG. "
            f"Original compounds table untouched ({old_count} rows)."
        )
        if without_svg:
            raise SystemExit(1)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
