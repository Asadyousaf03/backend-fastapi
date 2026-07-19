from __future__ import annotations

from pathlib import Path

from config import get_settings
from schemas import ShapFeature, SusceptibilityCall, SusceptibilityLabel, VariantEvidence
from services.features import extract_feature_vector
from services.rules import rule_based_call


class MLInferenceResult:
    def __init__(
        self,
        call: SusceptibilityCall,
        shap_features: list[ShapFeature],
        used_pretrained: bool,
    ) -> None:
        self.call = call
        self.shap_features = shap_features
        self.used_pretrained = used_pretrained


def _load_amrpredictor_model(model_dir: Path):
    model_path = model_dir / "ecoli_ciprofloxacin_xgb.json"
    if not model_path.exists():
        model_path = model_dir / "ecoli_ciprofloxacin_xgb.ubj"
        if not model_path.exists():
            return None
    try:
        import xgboost as xgb
    except ImportError:
        return None

    booster = xgb.Booster()
    try:
        booster.load_model(str(model_path))
        return booster
    except Exception:
        return None


def _shap_from_features(
    features: dict[str, float],
    probability_resistant: float,
    variants: list[VariantEvidence],
) -> list[ShapFeature]:
    ranked: list[tuple[str, float]] = []
    for variant in variants:
        key = f"{variant.gene}:{variant.mutation or 'presence'}"
        ranked.append((key, 0.35 if probability_resistant >= 0.5 else -0.2))

    # Prefer biologically relevant kmers when present.
    for feature, value in features.items():
        if feature.startswith("k4_") and value > 0:
            weight = value * (1.0 if probability_resistant >= 0.5 else -1.0)
            ranked.append((feature, weight))

    ranked.sort(key=lambda item: abs(item[1]), reverse=True)
    shap_features: list[ShapFeature] = []
    for idx, (name, value) in enumerate(ranked[:12], start=1):
        direction: SusceptibilityLabel | str
        if value > 0.02:
            direction = "resistant"
        elif value < -0.02:
            direction = "susceptible"
        else:
            direction = "neutral"
        shap_features.append(
            ShapFeature(
                feature=name,
                shap_value=round(value, 5),
                direction=direction,  # type: ignore[arg-type]
                rank=idx,
            )
        )
    if not shap_features:
        shap_features.append(
            ShapFeature(
                feature="baseline_prior",
                shap_value=0.0,
                direction="neutral",
                rank=1,
            )
        )
    return shap_features


def _shap_from_model(names: list[str], contributions) -> list[ShapFeature]:
    ranked = sorted(
        zip(names, (float(value) for value in contributions[: len(names)]), strict=True),
        key=lambda item: abs(item[1]),
        reverse=True,
    )
    output: list[ShapFeature] = []
    for idx, (name, value) in enumerate(ranked[:12], start=1):
        direction = (
            "resistant" if value > 0.02 else "susceptible" if value < -0.02 else "neutral"
        )
        output.append(
            ShapFeature(
                feature=name,
                shap_value=round(value, 5),
                direction=direction,
                rank=idx,
            )
        )
    return output or [
        ShapFeature(
            feature="model_bias",
            shap_value=0.0,
            direction="neutral",
            rank=1,
        )
    ]


def _heuristic_probability(features: dict[str, float], variants: list[VariantEvidence]) -> float:
    base = 0.18
    if variants:
        base += min(0.7, 0.22 * len(variants))
    gc = features.get("gc_content", 0.5)
    if 0.49 <= gc <= 0.53:
        base += 0.05
    return max(0.01, min(0.99, base))


def predict_ciprofloxacin(
    assembly_path: Path,
    variants: list[VariantEvidence],
) -> MLInferenceResult:
    settings = get_settings()
    features = extract_feature_vector(assembly_path)
    model = _load_amrpredictor_model(Path(settings.amrpredictor_model_dir))
    used_pretrained = False
    probability: float
    shap_features: list[ShapFeature]

    if model is not None:
        try:
            import xgboost as xgb

            # Build a dense vector aligned to feature names when available.
            names_path = Path(settings.amrpredictor_model_dir) / "feature_names.txt"
            if names_path.exists():
                names = [line.strip() for line in names_path.read_text().splitlines() if line.strip()]
                row = [features.get(name, 0.0) for name in names]
            else:
                names = sorted(features)
                row = [features[name] for name in names]
            dmatrix = xgb.DMatrix([row], feature_names=names)
            probability = float(model.predict(dmatrix)[0])
            contributions = model.predict(dmatrix, pred_contribs=True)[0]
            shap_features = _shap_from_model(names, contributions)
            used_pretrained = True
        except Exception as exc:
            if not settings.enable_demo_fallback:
                raise RuntimeError(
                    "AMRpredictor model inference failed and demo fallback is disabled"
                ) from exc
            used_pretrained = False
            probability = _heuristic_probability(features, variants)
            shap_features = _shap_from_features(features, probability, variants)
    else:
        if not settings.enable_demo_fallback:
            raise RuntimeError(
                "AMRpredictor model is unavailable and demo fallback is disabled"
            )
        probability = _heuristic_probability(features, variants)
        shap_features = _shap_from_features(features, probability, variants)

    rule_label = rule_based_call(variants)
    if probability >= 0.5:
        label: SusceptibilityLabel = "R"
        source = "ml" if used_pretrained else "heuristic"
    else:
        label = "S"
        source = "ml" if used_pretrained else "heuristic"

    # Reconcile: if rules strongly indicate R and ML is borderline, prefer R.
    if rule_label == "R" and 0.35 <= probability < 0.55:
        label = "R"
        source = "reconciled"
        probability = max(probability, 0.62)
    elif rule_label == "R" and probability < 0.35:
        label = "R"
        source = "reconciled"
        probability = 0.7
    elif rule_label == "S" and probability > 0.8 and not variants:
        source = "ml"

    call = SusceptibilityCall(
        drug="ciprofloxacin",
        label=label,
        probability_resistant=round(probability, 4),
        calibrated_probability=round(probability, 4),
        source=source,  # type: ignore[arg-type]
        breakpoint_standard="EUCAST v16.1",
        confidence=round(min(0.98, abs(probability - 0.5) * 1.8 + 0.4), 4),
    )
    return MLInferenceResult(call=call, shap_features=shap_features, used_pretrained=used_pretrained)
