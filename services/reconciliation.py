"""Reconcile ResFinder phenotypes with AMRFinderPlus genotypic corroboration."""

from __future__ import annotations

from services.species import SpeciesPanel
from services.tools.amrfinderplus import AmrfinderHit, AmrfinderResult
from services.tools.base import slugify
from services.tools.resfinder import ResFinderHit, ResFinderPhenotype, ResFinderResult
from schemas import (
    AntimicrobialCall,
    EvidenceAgreement,
    ResistanceEvidence,
    SourceAssessment,
    SusceptibilityLabel,
    ToolRun,
)


def _normalize_drug(name: str) -> str:
    return " ".join(name.strip().lower().replace("_", " ").split())


def _drug_id(name: str) -> str:
    return slugify(name)


CLASS_HINTS = {
    "ciprofloxacin": "fluoroquinolone",
    "levofloxacin": "fluoroquinolone",
    "nalidixic acid": "fluoroquinolone",
    "ampicillin": "beta-lactam",
    "amoxicillin": "beta-lactam",
    "ceftriaxone": "cephalosporin",
    "cefotaxime": "cephalosporin",
    "ceftazidime": "cephalosporin",
    "cefoxitin": "cephamycin",
    "oxacillin": "beta-lactam",
    "meropenem": "carbapenem",
    "imipenem": "carbapenem",
    "gentamicin": "aminoglycoside",
    "streptomycin": "aminoglycoside",
    "vancomycin": "glycopeptide",
    "linezolid": "oxazolidinone",
    "erythromycin": "macrolide",
    "azithromycin": "macrolide",
    "clindamycin": "lincosamide",
    "tetracycline": "tetracycline",
    "chloramphenicol": "phenicol",
    "trimethoprim": "folate pathway antagonist",
    "sulfamethoxazole": "folate pathway antagonist",
    "trimethoprim-sulfamethoxazole": "folate pathway antagonist",
    "nitrofurantoin": "nitrofuran",
    "rifampicin": "rifamycin",
    "fusidic acid": "fusidane",
    "isoniazid": "anti-tb",
    "ethambutol": "anti-tb",
    "pyrazinamide": "anti-tb",
}


def evidence_from_resfinder(hits: list[ResFinderHit]) -> list[ResistanceEvidence]:
    out: list[ResistanceEvidence] = []
    for hit in hits:
        out.append(
            ResistanceEvidence(
                evidence_id=hit.evidence_id,
                gene=hit.gene,
                mutation=hit.mutation,
                identity=hit.identity,
                coverage=hit.coverage,
                source=hit.source,  # type: ignore[arg-type]
                associated_drugs=hit.phenotype_drugs,
                contig=hit.contig,
                start=hit.start,
                end=hit.end,
                accession=hit.accession,
                associated_phenotype=hit.phenotype_label,  # type: ignore[arg-type]
                notes=hit.notes,
            )
        )
    return out


def evidence_from_amrfinder(hits: list[AmrfinderHit]) -> list[ResistanceEvidence]:
    out: list[ResistanceEvidence] = []
    for hit in hits:
        associated = []
        if hit.subclass:
            associated.append(hit.subclass)
        if hit.drug_class:
            associated.append(hit.drug_class)
        out.append(
            ResistanceEvidence(
                evidence_id=hit.evidence_id,
                gene=hit.gene,
                mutation=hit.mutation,
                identity=hit.identity,
                coverage=hit.coverage,
                source="amrfinderplus",
                associated_drugs=associated,
                drug_class=hit.drug_class,
                subclass=hit.subclass,
                method=hit.method,
                contig=hit.contig,
                start=hit.start,
                end=hit.end,
                strand=hit.strand,
                accession=hit.accession,
                associated_phenotype="R",
                notes=hit.notes,
            )
        )
    return out


def _amr_supports_drug(hit: AmrfinderHit, drug: str) -> bool:
    needle = _normalize_drug(drug)
    haystacks = [
        _normalize_drug(hit.subclass or ""),
        _normalize_drug(hit.drug_class or ""),
        _normalize_drug(hit.gene),
        _normalize_drug(hit.notes or ""),
    ]
    if needle in haystacks:
        return True
    # Common class-level matches
    if "quinolone" in needle or "ciprofloxacin" in needle:
        return any("quinolone" in h or "fluoroquinolone" in h for h in haystacks)
    if "beta-lactam" in " ".join(haystacks) or "betalactam" in " ".join(haystacks):
        if any(x in needle for x in ("ampicillin", "oxacillin", "penicillin")):
            return True
    if any(needle.split()[0] in h for h in haystacks if h):
        return True
    return False


def reconcile(
    panel: SpeciesPanel,
    resfinder: ResFinderResult,
    amrfinder: AmrfinderResult,
) -> tuple[list[AntimicrobialCall], list[ResistanceEvidence], list[ToolRun]]:
    evidence = [
        *evidence_from_resfinder(resfinder.hits),
        *evidence_from_amrfinder(amrfinder.hits),
    ]
    tool_runs = [
        ToolRun.model_validate(resfinder.tool_run),
        ToolRun.model_validate(amrfinder.tool_run),
    ]

    # Index ResFinder phenotype rows
    phenotype_by_drug: dict[str, ResFinderPhenotype] = {}
    for ph in resfinder.phenotypes:
        phenotype_by_drug[_normalize_drug(ph.drug)] = ph

    # Ensure panel drugs appear even if ResFinder omitted a row.
    drugs: list[str] = []
    seen: set[str] = set()
    for name in [*panel.drug_panel, *[p.drug for p in resfinder.phenotypes]]:
        key = _normalize_drug(name)
        if key not in seen:
            seen.add(key)
            drugs.append(name)

    calls: list[AntimicrobialCall] = []
    for drug in drugs:
        key = _normalize_drug(drug)
        ph = phenotype_by_drug.get(key)
        rf_ids = [
            h.evidence_id
            for h in resfinder.hits
            if any(_normalize_drug(d) == key for d in h.phenotype_drugs)
            or any(_normalize_drug(d) == key for d in [])
            or (ph and any(_normalize_drug(g) == _normalize_drug(h.gene) for g in ph.genes))
        ]
        # Also attach hits whose phenotype drugs fuzzy-match
        if not rf_ids:
            rf_ids = [
                h.evidence_id
                for h in resfinder.hits
                if any(key in _normalize_drug(d) or _normalize_drug(d) in key for d in h.phenotype_drugs)
            ]
        af_ids = [
            h.evidence_id
            for h in amrfinder.hits
            if _amr_supports_drug(h, drug)
        ]

        call = _build_call(
            drug=drug,
            resfinder_status=resfinder.status,
            amrfinder_status=amrfinder.status,
            phenotype=ph,
            rf_ids=rf_ids,
            af_ids=af_ids,
            panel_supported=key in {_normalize_drug(d) for d in panel.drug_panel}
            or ph is not None,
        )
        calls.append(call)

    # Stable sort: resistant first, then alpha
    rank = {"R": 0, "I": 1, "ATU": 2, "S": 3, None: 4, "unknown": 4}
    calls.sort(key=lambda c: (rank.get(c.label, 5), c.drug.lower()))
    return calls, evidence, tool_runs


def _build_call(
    *,
    drug: str,
    resfinder_status: str,
    amrfinder_status: str,
    phenotype: ResFinderPhenotype | None,
    rf_ids: list[str],
    af_ids: list[str],
    panel_supported: bool,
) -> AntimicrobialCall:
    warnings: list[str] = []
    limitations = [
        "Research use only; not a clinical diagnostic.",
        "AMRFinderPlus is genotypic corroboration, not phenotypic validation.",
        "Absence of detected determinants is not proof of susceptibility.",
    ]

    rf_assessment = _source_assessment(
        source="resfinder",
        tool_status=resfinder_status,
        evidence_ids=rf_ids,
        phenotype_label=phenotype.label if phenotype else None,
    )
    af_assessment = _source_assessment(
        source="amrfinderplus",
        tool_status=amrfinder_status,
        evidence_ids=af_ids,
        phenotype_label="R" if af_ids else None,
    )

    if resfinder_status in {"failed", "unavailable"} and amrfinder_status in {
        "failed",
        "unavailable",
    }:
        return AntimicrobialCall(
            drug_id=_drug_id(drug),
            drug=drug,
            drug_class=CLASS_HINTS.get(_normalize_drug(drug)),
            label=None,
            call_status="tool_failed",
            agreement="tool_failure",
            evidence_ids=[],
            source_assessments=[rf_assessment, af_assessment],
            confidence_category="none",
            warnings=["Both primary inference and corroboration tools failed or are unavailable."],
            limitations=limitations,
        )

    if not panel_supported and phenotype is None:
        return AntimicrobialCall(
            drug_id=_drug_id(drug),
            drug=drug,
            drug_class=CLASS_HINTS.get(_normalize_drug(drug)),
            label=None,
            call_status="unsupported",
            agreement="not_assessed",
            evidence_ids=[],
            source_assessments=[rf_assessment, af_assessment],
            confidence_category="none",
            warnings=["Drug not in the selected species panel."],
            limitations=limitations,
        )

    rf_label: SusceptibilityLabel | None = None
    if phenotype and phenotype.label in {"R", "S", "I", "ATU"}:
        rf_label = phenotype.label  # type: ignore[assignment]
    elif rf_ids:
        rf_label = "R"

    af_resistant = bool(af_ids)

    if resfinder_status in {"failed", "unavailable"}:
        warnings.append(
            "ResFinder unavailable/failed; no primary phenotype call can be issued."
        )
        return AntimicrobialCall(
            drug_id=_drug_id(drug),
            drug=drug,
            drug_class=(phenotype.drug_class if phenotype else None)
            or CLASS_HINTS.get(_normalize_drug(drug)),
            label=None,
            call_status="tool_failed",
            agreement="tool_failure",
            evidence_ids=af_ids,
            source_assessments=[rf_assessment, af_assessment],
            confidence_category="none",
            warnings=warnings,
            limitations=limitations,
        )

    # Primary inference available
    if rf_label == "R" and af_resistant:
        agreement: EvidenceAgreement = "concordant"
        confidence = "high"
        call_status = "called"
        label: SusceptibilityLabel | None = "R"
    elif rf_label == "R" and not af_resistant:
        if amrfinder_status == "success":
            agreement = "single_source"
            confidence = "moderate"
            warnings.append(
                "ResFinder predicts resistance; AMRFinderPlus did not report matching determinants."
            )
        else:
            agreement = "single_source"
            confidence = "low"
            warnings.append("Corroboration tool did not contribute evidence.")
        call_status = "called"
        label = "R"
    elif rf_label == "S" and af_resistant:
        agreement = "discordant"
        confidence = "low"
        call_status = "conflicting"
        label = "unknown"
        warnings.append(
            "ResFinder susceptible phenotype conflicts with AMRFinderPlus resistance determinants."
        )
    elif rf_label == "S" and not af_resistant:
        agreement = "concordant" if amrfinder_status == "success" else "single_source"
        confidence = "moderate" if amrfinder_status == "success" else "low"
        call_status = "called"
        label = "S"
        warnings.append(
            "Susceptible call is genotype-inferred; confirm with phenotypic AST."
        )
    elif rf_label is None and af_resistant:
        agreement = "complementary"
        confidence = "low"
        call_status = "insufficient_evidence"
        label = "unknown"
        warnings.append(
            "AMRFinderPlus found determinants but ResFinder did not emit a phenotype for this drug."
        )
    else:
        agreement = "no_resistance_evidence"
        confidence = "none"
        call_status = "unknown"
        label = None
        warnings.append(
            "No reportable resistance evidence for this drug; unknown is not susceptible."
        )

    return AntimicrobialCall(
        drug_id=_drug_id(drug),
        drug=drug,
        drug_class=(phenotype.drug_class if phenotype else None)
        or CLASS_HINTS.get(_normalize_drug(drug)),
        label=label,
        call_status=call_status,  # type: ignore[arg-type]
        agreement=agreement,
        evidence_ids=[*dict.fromkeys([*rf_ids, *af_ids])],
        source_assessments=[rf_assessment, af_assessment],
        confidence_category=confidence,  # type: ignore[arg-type]
        breakpoint_standard=None,
        warnings=warnings,
        limitations=limitations,
    )


def _source_assessment(
    *,
    source: str,
    tool_status: str,
    evidence_ids: list[str],
    phenotype_label: str | None,
) -> SourceAssessment:
    if tool_status == "unavailable":
        status = "tool_unavailable"
    elif tool_status == "failed":
        status = "tool_failed"
    elif evidence_ids or phenotype_label == "R":
        status = "resistance_evidence"
    elif phenotype_label == "S":
        status = "no_reportable_evidence"
    elif tool_status == "success":
        status = "no_reportable_evidence"
    else:
        status = "not_assessed"
    label: SusceptibilityLabel | None = None
    if phenotype_label in {"R", "S", "I", "ATU"}:
        label = phenotype_label  # type: ignore[assignment]
    elif evidence_ids:
        label = "R"
    return SourceAssessment(
        source=source,  # type: ignore[arg-type]
        status=status,  # type: ignore[arg-type]
        label=label,
        evidence_ids=evidence_ids,
    )
