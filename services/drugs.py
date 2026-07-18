from schemas import AlternativeDrug, SusceptibilityLabel


CIPRO_ALTERNATIVES: list[AlternativeDrug] = [
    AlternativeDrug(
        name="nitrofurantoin",
        class_name="nitrofuran",
        rationale="Often retained activity for uncomplicated lower UTI when local susceptibility supports use.",
        caution="Not for pyelonephritis or systemic infection.",
    ),
    AlternativeDrug(
        name="fosfomycin",
        class_name="phosphonic acid",
        rationale="Single-dose option for uncomplicated cystitis in many guidelines.",
        caution="Confirm local resistance epidemiology.",
    ),
    AlternativeDrug(
        name="amoxicillin-clavulanate",
        class_name="beta-lactam / beta-lactamase inhibitor",
        rationale="Consider when beta-lactamase profile and local antibiogram support susceptibility.",
        caution="Not inferred from ciprofloxacin genotype alone.",
    ),
    AlternativeDrug(
        name="ceftriaxone",
        class_name="third-generation cephalosporin",
        rationale="Possible parenteral option for systemic infection if ESBL markers are absent.",
        caution="Requires independent ESBL / cephalosporin assessment.",
    ),
]


def alternatives_for(label: SusceptibilityLabel) -> list[AlternativeDrug]:
    if label == "R":
        return CIPRO_ALTERNATIVES
    return [
        AlternativeDrug(
            name="ciprofloxacin",
            class_name="fluoroquinolone",
            rationale="Genomic profile does not indicate fluoroquinolone resistance markers.",
            caution="Phenotypic confirmation still required before clinical use.",
        )
    ]
