from __future__ import annotations

from collections import Counter
from pathlib import Path


def load_assembly_sequence(path: Path) -> str:
    parts: list[str] = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if line.startswith(">"):
            continue
        parts.append(line.strip().upper())
    return "".join(parts)


def kmer_frequencies(sequence: str, k: int = 4) -> dict[str, float]:
    if len(sequence) < k:
        return {}
    counts: Counter[str] = Counter()
    total = len(sequence) - k + 1
    for i in range(total):
        kmer = sequence[i : i + k]
        if set(kmer) <= {"A", "C", "G", "T"}:
            counts[kmer] += 1
    return {kmer: count / total for kmer, count in counts.items()}


def extract_feature_vector(assembly_path: Path) -> dict[str, float]:
    sequence = load_assembly_sequence(assembly_path)
    features: dict[str, float] = {}
    for k in (3, 4, 5):
        for kmer, freq in kmer_frequencies(sequence, k).items():
            features[f"k{k}_{kmer}"] = freq
    features["seq_length"] = float(len(sequence))
    features["gc_content"] = (
        (sequence.count("G") + sequence.count("C")) / len(sequence) if sequence else 0.0
    )
    return features
