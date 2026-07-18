from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass
from pathlib import Path


@dataclass
class AstSample:
    sample_id: str
    lineage: str
    mic: float | None
    label: str  # R / S / ATU
    y: int  # 1 = R, 0 = S (ATU excluded from binary metrics)


def eucast_cipro_label(mic: float | None, declared: str | None = None) -> str:
    """Map MIC to EUCAST-oriented label with explicit ATU handling.

    EUCAST Enterobacterales ciprofloxacin ATU centers near MIC 0.5 mg/L.
    """
    if declared in {"R", "S", "I", "ATU"}:
        if declared == "I":
            return "ATU"
        return declared
    if mic is None:
        return "unknown"
    if mic <= 0.25:
        return "S"
    if abs(mic - 0.5) < 1e-9:
        return "ATU"
    return "R"


def load_ast_table(path: Path) -> list[AstSample]:
    samples: list[AstSample] = []
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            mic_raw = row.get("mic") or row.get("MIC") or row.get("measurement")
            mic = float(mic_raw) if mic_raw not in (None, "") else None
            declared = row.get("phenotype") or row.get("ast_label")
            label = eucast_cipro_label(mic, declared)
            if label not in {"R", "S", "ATU"}:
                continue
            y = 1 if label == "R" else 0
            if label == "ATU":
                # Keep for reporting but exclude from binary training metrics.
                y = -1
            samples.append(
                AstSample(
                    sample_id=row.get("sample_id") or row.get("biosample") or row["id"],
                    lineage=row.get("lineage") or row.get("st") or "unknown",
                    mic=mic,
                    label=label,
                    y=y,
                )
            )
    return samples


def lineage_aware_split(
    samples: list[AstSample],
    test_fraction: float = 0.2,
    seed: str = "hack-nation-ast",
) -> tuple[list[AstSample], list[AstSample]]:
    """Split by lineage hash to reduce clonal leakage across folds."""
    lineages = sorted({sample.lineage for sample in samples})
    scored = []
    for lineage in lineages:
        digest = hashlib.sha256(f"{seed}:{lineage}".encode()).hexdigest()
        bucket = int(digest[:8], 16) / 0xFFFFFFFF
        scored.append((bucket, lineage))
    scored.sort()

    target = max(1, int(round(len(lineages) * test_fraction)))
    test_lineages = {lineage for _, lineage in scored[:target]}

    train = [s for s in samples if s.lineage not in test_lineages]
    test = [s for s in samples if s.lineage in test_lineages]
    return train, test
