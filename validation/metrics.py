from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class BinaryMetrics:
    auc: float | None
    balanced_accuracy: float
    mcc: float
    sensitivity: float
    specificity: float
    precision: float
    f1: float
    tp: int
    tn: int
    fp: int
    fn: int
    ece: float | None


def confusion(y_true: list[int], y_pred: list[int]) -> tuple[int, int, int, int]:
    tp = sum(1 for t, p in zip(y_true, y_pred, strict=True) if t == 1 and p == 1)
    tn = sum(1 for t, p in zip(y_true, y_pred, strict=True) if t == 0 and p == 0)
    fp = sum(1 for t, p in zip(y_true, y_pred, strict=True) if t == 0 and p == 1)
    fn = sum(1 for t, p in zip(y_true, y_pred, strict=True) if t == 1 and p == 0)
    return tp, tn, fp, fn


def mcc(tp: int, tn: int, fp: int, fn: int) -> float:
    denom = math.sqrt((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn))
    if denom == 0:
        return 0.0
    return ((tp * tn) - (fp * fn)) / denom


def roc_auc(y_true: list[int], y_score: list[float]) -> float | None:
    pairs = sorted(zip(y_score, y_true, strict=True), reverse=True)
    positives = sum(y_true)
    negatives = len(y_true) - positives
    if positives == 0 or negatives == 0:
        return None
    tp = 0
    fp = 0
    prev_score = None
    auc = 0.0
    prev_tp = 0
    prev_fp = 0
    for score, label in pairs + [(None, None)]:
        if score != prev_score and prev_score is not None:
            auc += (fp - prev_fp) * (tp + prev_tp) / 2.0
            prev_tp, prev_fp = tp, fp
        if score is None:
            break
        if label == 1:
            tp += 1
        else:
            fp += 1
        prev_score = score
    auc += (negatives - prev_fp) * (positives + prev_tp) / 2.0
    return auc / (positives * negatives)


def expected_calibration_error(
    y_true: list[int],
    y_score: list[float],
    bins: int = 10,
) -> float | None:
    if not y_true:
        return None
    bucket_totals = [0] * bins
    bucket_correct = [0.0] * bins
    bucket_confidence = [0.0] * bins
    for label, score in zip(y_true, y_score, strict=True):
        idx = min(bins - 1, int(score * bins))
        bucket_totals[idx] += 1
        bucket_correct[idx] += label
        bucket_confidence[idx] += score
    ece = 0.0
    n = len(y_true)
    for total, correct, confidence in zip(
        bucket_totals, bucket_correct, bucket_confidence, strict=True
    ):
        if total == 0:
            continue
        acc = correct / total
        conf = confidence / total
        ece += (total / n) * abs(acc - conf)
    return ece


def compute_metrics(y_true: list[int], y_score: list[float], threshold: float = 0.5) -> BinaryMetrics:
    y_pred = [1 if score >= threshold else 0 for score in y_score]
    tp, tn, fp, fn = confusion(y_true, y_pred)
    sensitivity = tp / (tp + fn) if (tp + fn) else 0.0
    specificity = tn / (tn + fp) if (tn + fp) else 0.0
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    f1 = (
        2 * precision * sensitivity / (precision + sensitivity)
        if (precision + sensitivity)
        else 0.0
    )
    return BinaryMetrics(
        auc=roc_auc(y_true, y_score),
        balanced_accuracy=(sensitivity + specificity) / 2,
        mcc=mcc(tp, tn, fp, fn),
        sensitivity=sensitivity,
        specificity=specificity,
        precision=precision,
        f1=f1,
        tp=tp,
        tn=tn,
        fp=fp,
        fn=fn,
        ece=expected_calibration_error(y_true, y_score),
    )
