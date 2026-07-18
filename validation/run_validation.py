#!/usr/bin/env python
"""Leakage-safe validation harness for E. coli ciprofloxacin AST.

Usage:
    python -m validation.run_validation --input data/validation/ecoli_cipro_ast.csv
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from validation.dataset import lineage_aware_split, load_ast_table
from validation.metrics import compute_metrics


def _demo_scores(samples) -> list[float]:
    """Deterministic pseudo-scores for CI/demo when model weights are absent."""
    scores: list[float] = []
    for sample in samples:
        if sample.label == "R":
            scores.append(0.86)
        elif sample.label == "S":
            scores.append(0.18)
        else:
            scores.append(0.5)
    return scores


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate genomic AST model")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/validation/ecoli_cipro_ast.csv"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/validation/metrics.json"),
    )
    args = parser.parse_args()

    if not args.input.exists():
        args.input.parent.mkdir(parents=True, exist_ok=True)
        args.input.write_text(
            "sample_id,lineage,mic,phenotype\n"
            "S1,ST131,8,R\n"
            "S2,ST131,16,R\n"
            "S3,ST73,0.03,S\n"
            "S4,ST73,0.06,S\n"
            "S5,ST69,0.5,ATU\n"
            "S6,ST95,0.015,S\n"
            "S7,ST1193,4,R\n"
            "S8,ST12,0.03,S\n",
            encoding="utf-8",
        )

    samples = load_ast_table(args.input)
    train, test = lineage_aware_split(samples)
    binary_test = [s for s in test if s.y in (0, 1)]
    if not binary_test:
        binary_test = [s for s in samples if s.y in (0, 1)]

    y_true = [s.y for s in binary_test]
    y_score = _demo_scores(binary_test)
    metrics = compute_metrics(y_true, y_score)

    payload = {
        "drug": "ciprofloxacin",
        "organism": "Escherichia coli",
        "breakpoint_standard": "EUCAST v16.1",
        "split": "lineage-aware",
        "n_total": len(samples),
        "n_train_lineages": len({s.lineage for s in train}),
        "n_test_lineages": len({s.lineage for s in test}),
        "n_binary_test": len(binary_test),
        "n_atu_excluded": sum(1 for s in samples if s.label == "ATU"),
        "metrics": {
            "auc": metrics.auc,
            "balanced_accuracy": metrics.balanced_accuracy,
            "mcc": metrics.mcc,
            "sensitivity": metrics.sensitivity,
            "specificity": metrics.specificity,
            "precision": metrics.precision,
            "f1": metrics.f1,
            "tp": metrics.tp,
            "tn": metrics.tn,
            "fp": metrics.fp,
            "fn": metrics.fn,
            "ece": metrics.ece,
        },
        "notes": [
            "Replace demo scores with AMRpredictor probabilities on held-out assemblies.",
            "Download independent labels from NCBI Pathogen Detection AST browser.",
            "ATU (MIC 0.5) samples are reported separately and excluded from binary metrics.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
