# Cell Painting Cluster Subprofile Explorer (CPCSE)

Web tool and database viewer for querying and comparing bioactivity cluster profiles from Cell Painting assays, developed for and maintained in collaboration with the **Max Planck Institute of Molecular Physiology (COMAS)**.

**Live Deployment:** [cpcse-mpi.vercel.app](https://cpcse-mpi.vercel.app)

---

## Overview

The Subprofile Explorer provides access to 1,883 reference landmark compounds across 13 defined bioactivity clusters (including AKT/PI3K/MTOR, DNA synthesis, HDAC, MitoStress, and Tubulin).

### Key Features
- **Compound Search & Matrix View:** Query compounds by name or SMILES string and compare cluster values side by side in a structured data grid.
- **2D Structure Visualization:** Chemical structures rendered as SVGs (precomputed with RDKit) directly alongside compound metadata.
- **Result Export:** Download query results as delimited text files for local analysis.
- **Lightweight Backend:** Flask application backed by PostgreSQL (Neon), deployed serverlessly on Vercel.

---

## Tech Stack

- **Backend:** Python / Flask
- **Cheminformatics:** RDKit (SMILES parsing and SVG generation)
- **Database:** PostgreSQL (Neon)
- **Hosting:** Vercel
- **Data Source:** Pahl et al. (2023) *Cell Chem Biol*, DOI: [10.1016/j.chembiol.2023.06.003]

---

## Citation & Publications

The underlying dataset and screening methodology are published in:
> Pahl et al. (2023). *Cell Chemical Biology*, [doi:10.1016/j.chembiol.2023.06.003](https://doi.org/10.1016/j.chembiol.2023.06.003)
> Adariani et al. (2023). bioRxiv, [doi:10.1101/2023.11.08.565491](https://doi.org/10.1101/2023.11.08.565491)
