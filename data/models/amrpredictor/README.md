# AMRpredictor assets

Source dataset:

https://zenodo.org/records/16213507

The upstream `models_and_ShapValues.zip` archive is about 5.17 GB. Do not
download the whole archive for this project. Fetch only the E. coli /
ciprofloxacin artifacts with:

```powershell
python scripts/download_amrpredictor_assets.py
```

The script uses verified ZIP range extraction and writes:

- `ecoli_ciprofloxacin_xgb.pkl`
- `feature_names.txt`
- upstream E. coli metrics and training output

Important: the upstream model features are annotation-derived protein,
promoter, and rRNA k-mers. They are **not** the raw assembly k-mer frequencies
currently produced by `services/features.py`. The downloaded pickle is
therefore retained as a provenance/reference asset and is not automatically
used for inference.

The API only enables pretrained inference when a compatible, converted
`ecoli_ciprofloxacin_xgb.json` or `.ubj` and its exact preprocessing pipeline
are available. Until that integration is completed, `ENABLE_DEMO_FALLBACK=true`
uses the transparent heuristic path and the UI labels results as demo output.
Set `ENABLE_DEMO_FALLBACK=false` to fail closed instead of returning a
heuristic prediction.
