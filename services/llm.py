from __future__ import annotations

from config import get_settings
from schemas import (
    ClinicalInterpretation,
    ShapFeature,
    SusceptibilityCall,
    VariantEvidence,
)
from services.drugs import alternatives_for


def _deterministic_interpretation(
    call: SusceptibilityCall,
    variants: list[VariantEvidence],
    shap_features: list[ShapFeature],
) -> ClinicalInterpretation:
    drivers = [f"{v.gene}{':' + v.mutation if v.mutation else ''}" for v in variants] or [
        f.feature for f in shap_features[:3]
    ]
    if call.label == "R":
        summary = (
            f"Genomic analysis predicts ciprofloxacin resistance "
            f"(P(R)={call.probability_resistant:.2f}). "
            f"Key supporting evidence: {', '.join(drivers[:4])}."
        )
    else:
        summary = (
            f"Genomic analysis predicts ciprofloxacin susceptibility "
            f"(P(R)={call.probability_resistant:.2f}). "
            "No high-confidence fluoroquinolone resistance markers dominated the signal."
        )
    return ClinicalInterpretation(
        summary=summary,
        key_drivers=drivers[:5],
        limitations=[
            "Research-use-only prediction; not a clinical diagnostic.",
            "Phenotypic AST remains the reference standard.",
            "EUCAST ciprofloxacin Area of Technical Uncertainty (MIC 0.5) is not resolved by genotype alone.",
            "Model performance can degrade on novel lineages not represented in training data.",
        ],
        alternative_drugs=alternatives_for(call.label),
    )


def interpret_clinically(
    call: SusceptibilityCall,
    variants: list[VariantEvidence],
    shap_features: list[ShapFeature],
) -> ClinicalInterpretation:
    settings = get_settings()
    fallback = _deterministic_interpretation(call, variants, shap_features)
    if not settings.gemini_api_key:
        return fallback

    try:
        from google import genai
        from google.genai import types
    except ImportError:
        return fallback

    prompt = (
        "You are a clinical genomics assistant. Using ONLY the provided evidence, "
        "write a concise research-use-only interpretation for E. coli ciprofloxacin AST. "
        "Do not invent genes, mutations, or drugs beyond the evidence and allowed alternatives.\n\n"
        f"Call: {call.model_dump_json()}\n"
        f"Variants: {[v.model_dump() for v in variants]}\n"
        f"Top SHAP: {[s.model_dump() for s in shap_features[:8]]}\n"
        f"Allowed alternatives: {[d.model_dump() for d in fallback.alternative_drugs]}\n"
    )

    try:
        client = genai.Client(api_key=settings.gemini_api_key)
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_json_schema=ClinicalInterpretation.model_json_schema(),
            ),
        )
        if getattr(response, "parsed", None) is not None:
            parsed = response.parsed
            if isinstance(parsed, ClinicalInterpretation):
                return parsed
            return ClinicalInterpretation.model_validate(parsed)
        if response.text:
            return ClinicalInterpretation.model_validate_json(response.text)
    except Exception:
        return fallback

    return fallback
