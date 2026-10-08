import argparse
import os
import sys
from typing import Optional
from rdkit import Chem
from rdkit.Chem.Draw import rdMolDraw2D


def smiles_to_svg(smiles: str, width: int = 500, height: int = 500, font_size: int = 10) -> str:
    """Convert a SMILES string to a clean, well-formed, single-line SVG string.
    
    The returned SVG is:
    - Well-formed XML (safe for DOM/XML parsing)
    - Stripped of XML prolog (ready for direct inline HTML inclusion or DB storage: TEXT/VARCHAR)
    - Whitespace-collapsed onto a single line (safe for pipe-delimited text/CSV/TSV files)
    - Background-transparent for flexible frontend styling
    """
    if not smiles or not isinstance(smiles, str) or not smiles.strip():
        return ""
    try:
        mol = Chem.MolFromSmiles(smiles.strip())
        if mol is None:
            return ""

        drawer = rdMolDraw2D.MolDraw2DSVG(width, height)
        drawer.SetFontSize(font_size)
        drawer.drawOptions().clearBackground = False
        drawer.DrawMolecule(mol)
        drawer.FinishDrawing()

        raw_svg = drawer.GetDrawingText()
        if not raw_svg:
            return ""

        # Remove XML declaration / prolog prior to <svg>
        start_idx = raw_svg.find("<svg")
        if start_idx != -1:
            raw_svg = raw_svg[start_idx:]

        # Remove RDKit header comments
        raw_svg = raw_svg.replace("<!-- END OF HEADER -->", "")

        # Collapse whitespace into single spaces to ensure attributes remain separated
        # while keeping the entire SVG string on a single line (no newlines).
        svg_single_line = " ".join(raw_svg.split())
        return svg_single_line
    except Exception:
        return ""


def _clean_split(line: str, delimiter: str = "|") -> list:
    """Split line by delimiter and remove trailing empty fields (e.g. from '||')."""
    cols = line.split(delimiter)
    # If the line ends with delimiter(s) producing trailing empty fields, strip them (e.g. cols[:-2])
    while len(cols) >= 2 and cols[-1] == "" and cols[-2] == "":
        cols = cols[:-2]
    if cols and cols[-1] == "":
        cols = cols[:-1]
    return cols


def process_dataset(
    input_file: str = "data.txt",
    output_file: Optional[str] = "data_with_svg.txt",
    delimiter: str = "|",
    structure_col_index: int = 4,
    limit: Optional[int] = None,
) -> None:
    """Read a delimited dataset, generate SVGs for SMILES, and write or preview rows."""
    if not os.path.exists(input_file):
        print(f"Error: {input_file} does not exist.")
        return

    with open(input_file, "r", encoding="utf-8", errors="replace") as f:
        lines = [line.rstrip("\r\n") for line in f if line.strip()]

    if not lines:
        print("Empty dataset.")
        return

    # Process header and strip trailing delimiters
    header_cols = _clean_split(lines[0], delimiter)
    # Check if header already has Structure column, otherwise insert
    if len(header_cols) <= structure_col_index or header_cols[structure_col_index] != "Structure":
        header_cols.insert(structure_col_index, "Structure")
    
    output_lines = [delimiter.join(header_cols)]
    
    total = len(lines) - 1
    processed_count = 0
    cache = {}

    print(f"Processing {min(total, limit) if limit else total} rows from {input_file}...")

    for i, line in enumerate(lines[1:], start=1):
        if limit is not None and i > limit:
            break

        cols = _clean_split(line, delimiter)
        # Column 1 is SMILES (0-indexed: 0=Trivial name, 1=Smiles)
        smiles = cols[1].strip() if len(cols) > 1 else ""

        if smiles in cache:
            svg = cache[smiles]
        else:
            svg = smiles_to_svg(smiles)
            cache[smiles] = cache_val = svg

        cols.insert(structure_col_index, svg)
        output_lines.append(delimiter.join(cols))
        processed_count += 1

        if processed_count % 500 == 0:
            print(f"  Processed {processed_count}/{total} rows (cached {len(cache)} unique SMILES)...")

    if output_file:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write("\n".join(output_lines) + "\n")
        print(f"Saved {processed_count} rows with SVG structures to {output_file}.")
    else:
        print(f"Finished processing {processed_count} rows.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Render SMILES to inline SVG for HTML/PostgreSQL.")
    parser.add_argument("--input", default="data.txt", help="Input dataset path (default: data.txt)")
    parser.add_argument("--output", default="data_with_svg.txt", help="Output dataset path (default: data_with_svg.txt)")
    parser.add_argument("--demo", action="store_true", help="Run a quick preview demo on data.txt")
    args = parser.parse_args()

    if args.demo:
        if os.path.exists(args.input):
            with open(args.input, "r", encoding="utf-8") as f:
                lines = [l.strip() for l in f if l.strip()]
            if len(lines) > 2:
                raw_split = lines[2].split("|")
                cleaned = raw_split[:-2] if len(raw_split) >= 2 and raw_split[-1] == "" and raw_split[-2] == "" else raw_split
                smilestr = cleaned[1]
                print("Vorher (Row 2):", cleaned)
                svgstr = smiles_to_svg(smilestr)
                cleaned.insert(4, svgstr)
                print("\nSVG Preview (first 120 chars):", svgstr[:120])
                print("\nNachher (Row 2, without trailing empty fields):", cleaned[:5] + ["<SVG>"] + cleaned[6:])
    else:
        process_dataset(args.input, args.output)


