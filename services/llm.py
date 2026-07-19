from __future__ import annotations

import json

from config import get_settings
from schemas import (
    AntimicrobialCall,
    ClinicalInterpretation,
    InterpretationReference,
    OrganismSelection,
    ResistanceEvidence,
    ToolRun,
)
from services.tools.versions import TOOL_PINNING


DISCLAIMER = (
    "Research use only. Not a clinical diagnostic. "
    "Confirm with phenotypic AST before any treatment decisions. "
    "AMRFinderPlus provides genotypic corroboration only and does not validate phenotype."
)

LAYPERSON_DISCLAIMER = (
    "This is a research tool, not a medical test. It does not diagnose an infection "
    "or tell you which medicine to take. Always talk to a doctor before making any "
    "treatment decision, and expect a lab to confirm these results with a different test."
)


SOURCE_LABELS = {
    "resfinder": "ResFinder",
    "amrfinderplus": "AMRFinderPlus",
    "pointfinder": "PointFinder (via ResFinder)",
    "reconciled": "Reconciled",
    "ml": "Model",
    "heuristic": "Heuristic",
}


def _reference_for_source(source: str, tool_runs: list[ToolRun]) -> InterpretationReference:
    label = SOURCE_LABELS.get(source, source)
    if source == "resfinder":
        return InterpretationReference(
            source=label,
            version=TOOL_PINNING.resfinder_version,
            database_version=TOOL_PINNING.resfinder_db_version,
            database_commit=TOOL_PINNING.resfinder_db_commit,
            role="primary genotype-to-phenotype inference",
        )
    if source == "pointfinder":
        return InterpretationReference(
            source=label,
            version=TOOL_PINNING.resfinder_version,
            database_version=TOOL_PINNING.pointfinder_db_version,
            database_commit=TOOL_PINNING.pointfinder_db_commit,
            role="chromosomal point-mutation detection",
        )
    if source == "amrfinderplus":
        return InterpretationReference(
            source=label,
            version=TOOL_PINNING.amrfinder_version,
            database_version=TOOL_PINNING.amrfinder_db_version,
            role="independent genotypic corroboration",
        )
    run = next((r for r in tool_runs if r.tool.lower() == source.lower()), None)
    return InterpretationReference(
        source=label,
        version=run.version if run else None,
        database_version=run.database_version if run else None,
        database_commit=run.database_commit if run else None,
    )


def _dedupe_refs(refs: list[InterpretationReference]) -> list[InterpretationReference]:
    seen: set[tuple] = set()
    out: list[InterpretationReference] = []
    for ref in refs:
        key = (ref.source, ref.version, ref.database_version)
        if key in seen:
            continue
        seen.add(key)
        out.append(ref)
    return out


def interpret_antibiogram(
    organism: OrganismSelection,
    antibiogram: list[AntimicrobialCall],
    evidence: list[ResistanceEvidence],
    tool_runs: list[ToolRun] | None = None,
) -> ClinicalInterpretation:
    tool_runs = tool_runs or []
    fallback = _deterministic(organism, antibiogram, evidence, tool_runs)
    settings = get_settings()
    if not settings.gemini_api_key:
        return fallback

    try:
        from google import genai

        client = genai.Client(api_key=settings.gemini_api_key)
        payload = {
            "organism": organism.model_dump(),
            "antibiogram": [c.model_dump() for c in antibiogram],
            "evidence": [e.model_dump() for e in evidence[:20]],
            "tool_versions": {
                "resfinder": TOOL_PINNING.resfinder_version,
                "resfinder_db": TOOL_PINNING.resfinder_db_version,
                "pointfinder_db": TOOL_PINNING.pointfinder_db_version,
                "amrfinderplus": TOOL_PINNING.amrfinder_version,
                "amrfinder_db": TOOL_PINNING.amrfinder_db_version,
            },
        }
        prompt = (
            "You are a clinical microbiology assistant for research-use-only genomic AST. "
            "Write a concise interpretation for TWO audiences. "
            "Return ONLY valid JSON with keys: "
            "summary (string, clinician-facing), "
            "clinician_summary (string: mechanism + gene/mutation evidence + breakpoint standard + confidence), "
            "layperson_summary (string: plain jargon-free language; what the bug is, what the result means, "
            "what to do/not do; include a 'not a clinical diagnostic' disclaimer), "
            "key_drivers (string array), limitations (string array). "
            "Do not recommend treatment doses. Emphasize phenotypic confirmation. Input:\n"
            f"{json.dumps(payload, default=str)}"
        )
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
        )
        text = (getattr(response, "text", None) or "").strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.startswith("json"):
                text = text[4:].strip()
        data = json.loads(text)
        summary = str(data.get("summary") or fallback.summary)
        clinician_summary = str(data.get("clinician_summary") or fallback.clinician_summary or "")
        layperson_summary = str(data.get("layperson_summary") or fallback.layperson_summary or "")
        drivers = [str(x) for x in (data.get("key_drivers") or fallback.key_drivers)][:10]
        limitations = [str(x) for x in (data.get("limitations") or fallback.limitations)][:10]
        if DISCLAIMER not in limitations:
            limitations.append(DISCLAIMER)
        return ClinicalInterpretation(
            summary=summary,
            key_drivers=drivers or fallback.key_drivers,
            limitations=limitations or fallback.limitations,
            alternative_drugs=[],
            disclaimer=DISCLAIMER,
            clinician_summary=clinician_summary or fallback.clinician_summary,
            layperson_summary=layperson_summary or fallback.layperson_summary,
            references=fallback.references,
        )
    except Exception:
        return fallback


def _deterministic(
    organism: OrganismSelection,
    antibiogram: list[AntimicrobialCall],
    evidence: list[ResistanceEvidence],
    tool_runs: list[ToolRun] | None = None,
) -> ClinicalInterpretation:
    tool_runs = tool_runs or []
    resistant = [c for c in antibiogram if c.label == "R"]
    susceptible = [c for c in antibiogram if c.label == "S"]
    unknown = [c for c in antibiogram if c.call_status in {"unknown", "insufficient_evidence"}]
    conflicting = [c for c in antibiogram if c.call_status == "conflicting"]
    failed = [c for c in antibiogram if c.call_status == "tool_failed"]

    drivers = []
    for item in evidence[:12]:
        label = item.gene
        if item.mutation:
            label = f"{item.gene}:{item.mutation}"
        drivers.append(f"{label} ({item.source})")
    drivers = list(dict.fromkeys(drivers))[:8]

    parts = [
        f"Genomic antibiogram for user-selected {organism.scientific_name} "
        f"using ResFinder phenotype inference with AMRFinderPlus corroboration."
    ]
    if resistant:
        parts.append(
            "Predicted resistance signals: "
            + ", ".join(f"{c.drug} ({c.agreement})" for c in resistant[:8])
            + "."
        )
    if susceptible:
        parts.append(
            "Genotype-inferred susceptible calls: "
            + ", ".join(c.drug for c in susceptible[:8])
            + " (still require phenotypic confirmation)."
        )
    if unknown:
        parts.append(
            f"{len(unknown)} drug(s) remain unknown because no defensible call was available."
        )
    if conflicting:
        parts.append(
            "Conflicts between ResFinder and AMRFinderPlus were flagged for: "
            + ", ".join(c.drug for c in conflicting)
            + "."
        )
    if failed:
        parts.append(
            "Tool failure prevented calls for: "
            + ", ".join(c.drug for c in failed)
            + "."
        )

    summary = " ".join(parts)

    # Clinician-facing summary: mechanism + evidence + breakpoint standard + confidence.
    clinician_parts = [
        f"Organism: {organism.scientific_name} (user-selected; no taxonomic auto-detection).",
        f"Inference pipeline: ResFinder {TOOL_PINNING.resfinder_version} "
        f"(db {TOOL_PINNING.resfinder_db_version}) primary phenotype inference; "
        f"AMRFinderPlus {TOOL_PINNING.amrfinder_version} "
        f"(db {TOOL_PINNING.amrfinder_db_version}) genotypic corroboration. "
        f"Point mutations via PointFinder db {TOOL_PINNING.pointfinder_db_version} when applicable.",
    ]
    if resistant:
        clinician_parts.append(
            "Resistance calls (genotype-inferred, no clinical MIC breakpoint applied): "
            + "; ".join(
                f"{c.drug} = R ({c.confidence_category} confidence, {c.agreement})"
                for c in resistant[:8]
            )
            + "."
        )
    if susceptible:
        clinician_parts.append(
            "Susceptible calls (genotype-inferred, require phenotypic confirmation): "
            + ", ".join(c.drug for c in susceptible[:8])
            + "."
        )
    if conflicting:
        clinician_parts.append(
            "Discordant calls to review: " + ", ".join(c.drug for c in conflicting) + "."
        )
    mechanism_genes = ", ".join(
        list(dict.fromkeys(
            f"{e.gene}{(' ' + e.mutation) if e.mutation else ''} ({e.source})"
            for e in evidence[:8]
        )) or ["none detected"]
    )
    clinician_parts.append(f"Resistance determinants cited: {mechanism_genes}.")
    clinician_parts.append(
        "Breakpoint standard: genotype-inferred only; no EUCAST/CLSI MIC breakpoint was applied. "
        "Confidence reflects tool concordance, not phenotypic accuracy."
    )
    clinician_summary = " ".join(clinician_parts)

    # Layperson summary: plain language, no jargon, with disclaimer.
    lay_parts = [
        f"This sample was labelled as {organism.scientific_name} (a type of bacterium) by the person who uploaded it.",
        "The computer read the bacterium's DNA and looked for genes that can stop certain antibiotics from working.",
    ]
    if resistant:
        lay_parts.append(
            "It found signs that the bacterium may shrug off these medicines: "
            + ", ".join(c.drug for c in resistant[:8])
            + "."
        )
    else:
        lay_parts.append("It did not find strong signs of resistance to the medicines it checked.")
    if susceptible:
        lay_parts.append(
            "For some medicines it found no resistance genes, so they might still work "
            "(" + ", ".join(c.drug for c in susceptible[:8]) + ") — but this is not a guarantee."
        )
    if conflicting:
        lay_parts.append(
            "For some medicines the two tools disagreed, so the result is uncertain."
        )
    lay_parts.append(
        "What to do: share these results with a doctor. A lab still needs to run a different test "
        "(growing the bacterium with the medicine) to confirm which treatment will actually work."
    )
    lay_parts.append(LAYPERSON_DISCLAIMER)
    layperson_summary = " ".join(lay_parts)

    references = _dedupe_refs(
        [
            _reference_for_source("resfinder", tool_runs),
            _reference_for_source("pointfinder", tool_runs),
            _reference_for_source("amrfinderplus", tool_runs),
        ]
    )

    return ClinicalInterpretation(
        summary=summary,
        key_drivers=drivers or ["No resistance determinants reported."],
        limitations=[
            "Research-use-only prediction; not a clinical diagnostic.",
            "Phenotypic AST remains the reference standard.",
            "No taxonomic auto-detection in this release; organism must be selected by the user.",
            "Assembled FASTA only; read assembly is out of scope for this release.",
            "Absence of detected determinants is not proof of susceptibility.",
            "True accuracy validation requires independent genome + phenotypic AST/MIC datasets.",
        ],
        alternative_drugs=[],
        disclaimer=DISCLAIMER,
        clinician_summary=clinician_summary,
        layperson_summary=layperson_summary,
        references=references,
    )


def _label_text(label: str | None) -> str:
    if label == "R":
        return "Resistant (R)"
    if label == "S":
        return "Susceptible (S)"
    if label == "I":
        return "Intermediate (I)"
    if label == "ATU":
        return "Area of technical uncertainty (ATU)"
    return "No call (unknown)"


def annotate_antibiogram(
    antibiogram: list[AntimicrobialCall],
    evidence: list[ResistanceEvidence],
    tool_runs: list[ToolRun],
) -> list[AntimicrobialCall]:
    """Attach clinician/layperson rationale + traceable references to each call."""
    evidence_by_id = {e.evidence_id: e for e in evidence}
    annotated: list[AntimicrobialCall] = []
    for call in antibiogram:
        linked = [evidence_by_id[i] for i in call.evidence_ids if i in evidence_by_id]
        refs = _dedupe_refs(
            [_reference_for_source(e.source, tool_runs) for e in linked]
            or [_reference_for_source("resfinder", tool_runs)]
        )

        if call.label == "R":
            mech = "; ".join(
                f"{e.gene}{(' ' + e.mutation) if e.mutation else ''} "
                f"({e.source}, identity {(e.identity * 100):.1f}% "
                f"coverage {(e.coverage * 100):.1f}%)"
                if e.identity is not None and e.coverage is not None
                else f"{e.gene}{(' ' + e.mutation) if e.mutation else ''} ({e.source})"
                for e in linked
            ) or "no specific determinant linked"
            clinician = (
                f"{call.drug} = {_label_text(call.label)}; {call.confidence_category} confidence "
                f"({call.agreement}). Mechanism evidence: {mech}. "
                f"Breakpoint standard: genotype-inferred (no clinical MIC breakpoint applied). "
                f"References: {', '.join(r.source for r in refs)}."
            )
            lay = (
                f"The DNA test found genes that usually let this bacterium survive {call.drug}. "
                f"It looked at {len(linked)} matching gene(s) from "
                f"{', '.join(r.source for r in refs)}. "
                f"This means {call.drug} probably will not work well, but a lab must confirm it."
            )
        elif call.label == "S":
            clinician = (
                f"{call.drug} = {_label_text(call.label)}; {call.confidence_category} confidence "
                f"({call.agreement}). No resistance determinants were detected; "
                f"this is genotype-inferred susceptibility, not phenotypic confirmation."
            )
            lay = (
                f"No genes that usually defeat {call.drug} were found, so it might still work. "
                f"This is not a guarantee — a lab still needs to confirm it with a different test."
            )
        else:
            clinician = (
                f"{call.drug}: {_label_text(call.label)}; call_status={call.call_status}, "
                f"agreement={call.agreement}. "
                f"{' '.join(call.warnings) if call.warnings else 'No defensible call could be issued.'}"
            )
            lay = (
                f"The result for {call.drug} is uncertain. "
                f"A lab test would be needed before relying on this medicine either way."
            )

        annotated.append(
            call.model_copy(
                update={
                    "clinician_rationale": clinician,
                    "layperson_rationale": lay,
                    "references": refs,
                }
            )
        )
    return annotated
