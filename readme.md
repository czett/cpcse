# Cell Painting Cluster Subprofile Explorer (CPCSE)

Web tool for querying the profile similarity to predefined bioactivity clusters derived from the Cell Painting essays, developed for and maintained by the **Max Planck Institute for Molecular Physiology and the (Compound Management and Screening Center) COMAS**

**Live Deployment:** [cpcse-mpi.vercel.app](https://cpcse-mpi.vercel.app)

---

## Overview

The Subprofile Explorer provides access to the profile similarity of 1,883 reference landmark compounds to 13 defined bioactivity clusters.

### Key Features
- **Compound Search & Matrix View:** Query compounds by name or SMILES string and compare cluster biosimilarity values side by side in a structured data grid.
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
> - Pahl et al. (2023). *Cell Chemical Biology*, [https://doi.org/10.1016/j.chembiol.2023.06.003](https://doi.org/10.1016/j.chembiol.2023.06.003)
> - Adariani et al. (2023). [https://doi.org/10.1021/acs.jmedchem.4c01183](https://doi.org/10.1021/acs.jmedchem.4c01183)
