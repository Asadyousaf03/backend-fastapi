"""Supported organism panels for ResFinder phenotype + AMRFinderPlus corroboration."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SpeciesPanel:
    organism_id: str
    scientific_name: str
    aliases: tuple[str, ...]
    resfinder_species: str
    amrfinder_organism: str
    point_mutations: bool = True
    drug_panel: tuple[str, ...] = field(default_factory=tuple)
    notes: str = ""


# Species-specific phenotype panels documented for ResFinder 4.7.2.
# Drug panels list clinically/surveillance-relevant compounds commonly reported
# by ResFinder species tables; exact call set still comes from tool output.
_SPECIES: tuple[SpeciesPanel, ...] = (
    SpeciesPanel(
        organism_id="escherichia_coli",
        scientific_name="Escherichia coli",
        aliases=("e. coli", "e coli", "ecoli", "escherichia"),
        resfinder_species="Escherichia coli",
        amrfinder_organism="Escherichia",
        drug_panel=(
            "ciprofloxacin",
            "ampicillin",
            "ceftriaxone",
            "cefotaxime",
            "ceftazidime",
            "gentamicin",
            "trimethoprim",
            "sulfamethoxazole",
            "trimethoprim-sulfamethoxazole",
            "meropenem",
            "imipenem",
            "nitrofurantoin",
            "tetracycline",
            "chloramphenicol",
            "azithromycin",
        ),
    ),
    SpeciesPanel(
        organism_id="salmonella",
        scientific_name="Salmonella",
        aliases=("salmonella spp", "salmonella enterica"),
        resfinder_species="Salmonella",
        amrfinder_organism="Salmonella",
        drug_panel=(
            "ciprofloxacin",
            "ampicillin",
            "ceftriaxone",
            "gentamicin",
            "trimethoprim",
            "sulfamethoxazole",
            "tetracycline",
            "chloramphenicol",
            "azithromycin",
            "meropenem",
        ),
    ),
    SpeciesPanel(
        organism_id="campylobacter_jejuni",
        scientific_name="Campylobacter jejuni",
        aliases=("c. jejuni", "campylobacter"),
        resfinder_species="Campylobacter jejuni",
        amrfinder_organism="Campylobacter",
        drug_panel=(
            "ciprofloxacin",
            "erythromycin",
            "tetracycline",
            "gentamicin",
        ),
    ),
    SpeciesPanel(
        organism_id="campylobacter_coli",
        scientific_name="Campylobacter coli",
        aliases=("c. coli",),
        resfinder_species="Campylobacter coli",
        amrfinder_organism="Campylobacter",
        drug_panel=(
            "ciprofloxacin",
            "erythromycin",
            "tetracycline",
            "gentamicin",
        ),
    ),
    SpeciesPanel(
        organism_id="enterococcus_faecium",
        scientific_name="Enterococcus faecium",
        aliases=("e. faecium",),
        resfinder_species="Enterococcus faecium",
        amrfinder_organism="Enterococcus_faecium",
        drug_panel=(
            "ampicillin",
            "vancomycin",
            "linezolid",
            "ciprofloxacin",
            "gentamicin",
            "tetracycline",
        ),
    ),
    SpeciesPanel(
        organism_id="enterococcus_faecalis",
        scientific_name="Enterococcus faecalis",
        aliases=("e. faecalis",),
        resfinder_species="Enterococcus faecalis",
        amrfinder_organism="Enterococcus_faecalis",
        drug_panel=(
            "ampicillin",
            "vancomycin",
            "linezolid",
            "ciprofloxacin",
            "gentamicin",
            "tetracycline",
        ),
    ),
    SpeciesPanel(
        organism_id="staphylococcus_aureus",
        scientific_name="Staphylococcus aureus",
        aliases=("s. aureus", "staph aureus", "mrsa", "mssa"),
        resfinder_species="Staphylococcus aureus",
        amrfinder_organism="Staphylococcus_aureus",
        drug_panel=(
            "oxacillin",
            "cefoxitin",
            "vancomycin",
            "ciprofloxacin",
            "erythromycin",
            "clindamycin",
            "linezolid",
            "tetracycline",
            "trimethoprim",
            "gentamicin",
            "rifampicin",
            "fusidic acid",
        ),
    ),
    SpeciesPanel(
        organism_id="mycobacterium_tuberculosis",
        scientific_name="Mycobacterium tuberculosis",
        aliases=("m. tuberculosis", "mtb", "tb"),
        resfinder_species="Mycobacterium tuberculosis",
        amrfinder_organism="Mycobacterium_tuberculosis",
        drug_panel=(
            "isoniazid",
            "rifampicin",
            "ethambutol",
            "pyrazinamide",
            "streptomycin",
            "fluoroquinolones",
        ),
        notes="TB panel is research-surveillance oriented; interpret with specialist frameworks.",
    ),
)


def list_species() -> list[SpeciesPanel]:
    return list(_SPECIES)


def get_species(organism_id_or_name: str) -> SpeciesPanel | None:
    key = organism_id_or_name.strip().lower()
    if not key:
        return None
    for panel in _SPECIES:
        if key in {
            panel.organism_id,
            panel.scientific_name.lower(),
            panel.resfinder_species.lower(),
            *panel.aliases,
        }:
            return panel
    return None


def require_species(organism_id_or_name: str) -> SpeciesPanel:
    panel = get_species(organism_id_or_name)
    if panel is None:
        supported = ", ".join(p.scientific_name for p in _SPECIES)
        raise ValueError(
            f"Unsupported or missing organism '{organism_id_or_name}'. "
            f"Supported ResFinder phenotype panels: {supported}"
        )
    return panel


def capabilities_payload() -> list[dict[str, object]]:
    return [
        {
            "organism_id": panel.organism_id,
            "scientific_name": panel.scientific_name,
            "aliases": list(panel.aliases),
            "resfinder_species": panel.resfinder_species,
            "amrfinder_organism": panel.amrfinder_organism,
            "point_mutations": panel.point_mutations,
            "drug_panel": list(panel.drug_panel),
            "notes": panel.notes,
        }
        for panel in _SPECIES
    ]
