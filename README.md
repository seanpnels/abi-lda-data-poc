# ABI LDA — OSM Data Engine POC (stage 1)

This is a **separate, experimental extraction workflow**. It does not modify the existing Streamlit app or produce compliance decisions.

## Run it

1. In the new private GitHub repo, upload the contents of this package, preserving `.github/workflows/ny-osm-poc.yml` and `scripts/manifest.py`.
2. Commit to the default branch.
3. Open **Actions** → **NYC OSM facility extraction POC** → **Run workflow**.
4. When the job finishes, open its run page and download the **ny-osm-facility-candidates** artifact.
5. Inspect `manifest.json`, `source-info.txt`, and `candidates-info.txt`. Share the workflow outcome and these *non-sensitive* reports if you want help interpreting them.

## What it does

Downloads Geofabrik's daily New York State OSM PBF, selects a broad set of candidate restricted facilities, and keeps geometry dependencies in a smaller PBF. It reports file sizes and OSM metadata.

## What it does NOT do

This is not a finished NYC-only dataset, daily refresh pipeline, persistent cloud database, or compliance screening engine. The candidate filter requires careful refinement, especially for substance-use facilities, university polygons, and building/facility associations. No green/red status should be derived from these files yet.

The full New York State download is several hundred MB and may take time. GitHub Actions artifact storage is temporary and is **not** the production database.

Data © OpenStreetMap contributors, ODbL 1.0. Review Geofabrik terms for your intended commercial use before scaling.
