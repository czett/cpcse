# Cell Painting Cluster Subprofile Explorer (CPCSE)

Web tool for querying the profile similarity to predefined bioactivity clusters derived from the Cell Painting dataset from Pahl et al. (2023) *Cell Chem Biol*, DOI: [10.1016/j.chembiol.2023.06.003](https://doi.org/10.1016/j.chembiol.2023.06.003), developed and maintained by Colin Ziegler.

**Live Deployment:** [cpcse-mpi.vercel.app](https://cpcse-mpi.vercel.app)

---

## Overview

The Subprofile Explorer provides access to the profile similarity of 1,883 reference landmark compounds to 13 defined bioactivity clusters.

### Key Features
- **Compound Search & Matrix View:** Query compounds by name or SMILES string and compare cluster values side by side in a structured data grid.
- **Advanced Search:** Pick a single cluster threshold (min 70%) and/or search up to 5 keyword terms (each at least 3 characters) at once. Cluster-only queries return the top 10 highest-scoring profiles, sorted by the selected cluster.
- **2D Structure Visualization:** Chemical structures rendered as SVGs (precomputed with RDKit) directly alongside compound metadata.
- **Result Export:** Download query results as delimited text files for local analysis.
- **Lightweight Backend:** Flask application backed by PostgreSQL (Neon), deployed serverlessly on Vercel.

---

## Tech Stack

- **Backend:** Python / Flask
- **Cheminformatics:** RDKit (SMILES parsing and SVG generation)
- **Database:** PostgreSQL (Neon)
- **Hosting:** Vercel
- **Data Source:** Pahl et al. (2023) *Cell Chem Biol*, DOI:  [10.1016/j.chembiol.2023.06.003](https://doi.org/10.1016/j.chembiol.2023.06.003)

---

## Publications

The underlying dataset and screening methodology are published in:
> - Pahl et al. (2023) *Cell Chem Biol*, DOI: [10.1016/j.chembiol.2023.06.003](https://doi.org/10.1016/j.chembiol.2023.06.003)
> - Adariani et al. (2024) *J Med Chem*, DOI: [10.1021/acs.jmedchem.4c01183](https://doi.org/10.1021/acs.jmedchem.4c01183)
