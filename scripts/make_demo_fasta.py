from pathlib import Path


def make_seq(n: int, motifs: tuple[str, ...] = ()) -> str:
    seq = []
    for i in range(n):
        # Roughly 50% GC alternating blocks.
        if (i // 2) % 2 == 0:
            seq.append("G" if i % 2 == 0 else "C")
        else:
            seq.append("A" if i % 2 == 0 else "T")
    s = "".join(seq)
    for idx, motif in enumerate(motifs):
        pos = 300 + idx * 250
        s = s[:pos] + motif + s[pos + len(motif) :]
    return s


def write_fasta(path: Path, header: str, sequence: str) -> None:
    lines = [sequence[i : i + 80] for i in range(0, len(sequence), 80)]
    path.write_text(">" + header + "\n" + "\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    motifs = (
        "GCGCGTACTTTACGCCGAT",
        "ATGAGCGATATGGCAGAG",
        "ATGGAAACCTACAATCATAC",
        "ATGAGCAACGCAAAAACAAAGTTA",
    )
    resistant = make_seq(6000, motifs)
    susceptible = make_seq(6000, ())
    root = Path("data/samples")
    root.mkdir(parents=True, exist_ok=True)
    write_fasta(root / "demo_ecoli_cipro_r.fasta", "demo_ecoli_cipro_resistant", resistant)
    write_fasta(root / "demo_ecoli_cipro_s.fasta", "demo_ecoli_cipro_susceptible", susceptible)
    print("wrote", len(resistant), len(susceptible))


if __name__ == "__main__":
    main()
