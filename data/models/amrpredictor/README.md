# AMRpredictor weights

Download pretrained ESKAPEE models from:

https://zenodo.org/records/16213507

Recommended:

1. Download `models_and_ShapValues.zip`
2. Extract the E. coli / ciprofloxacin XGBoost artifact into this directory
3. Optionally add `feature_names.txt` listing feature columns one per line

Expected filenames (any one works):

- `ecoli_ciprofloxacin_xgb.json`
- any file matching `*cipro*`

Without weights, the API uses the transparent heuristic + marker-scan fallback and still returns the full report schema.
