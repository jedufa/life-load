from pathlib import Path

from life_load.optional_packs import (
    ClinicalBoundary,
    GuidanceEffect,
    OPTIONAL_PACK_TEMPLATES,
    SIGNAL_INFLUENCE_POLICIES,
    SensitivityClass,
)
from life_load.profile_templates import PROFILE_TEMPLATE_METADATA
from life_load.selected_profile_config import build_selected_profile_config
from life_load.signal_registry import SIGNALS_BY_ID


ROOT = Path(__file__).resolve().parents[2]
SCORING_SOURCE_PATHS = (
    ROOT / "app" / "backend" / "life_load" / "core_engine.py",
    ROOT / "app" / "backend" / "life_load" / "scoring.py",
)
FORBIDDEN_PUBLIC_LABELS = (
    "addiction",
    "bulimia",
    "eating disorder",
    "relapse",
    "treatment",
    "disorder",
    "diagnosis",
)


def test_optional_pack_ids_unique():
    pack_ids = [pack.id for pack in OPTIONAL_PACK_TEMPLATES.values()]

    assert len(pack_ids) == len(set(pack_ids))


def test_optional_pack_signal_references_exist_or_are_documented_placeholders():
    for pack in OPTIONAL_PACK_TEMPLATES.values():
        for signal_id in pack.signal_ids:
            assert signal_id in SIGNALS_BY_ID
        for placeholder_signal_id in pack.placeholder_signal_ids:
            assert placeholder_signal_id.startswith("placeholder.")
            assert placeholder_signal_id not in SIGNALS_BY_ID


def test_pattern_awareness_pack_is_sensitive_and_opt_in():
    pack = OPTIONAL_PACK_TEMPLATES["pattern_awareness_pack"]

    assert pack.sensitive is True
    assert pack.requires_explicit_opt_in is True
    assert pack.default_enabled is False


def test_pattern_awareness_pack_avoids_clinical_public_labels():
    pack = OPTIONAL_PACK_TEMPLATES["pattern_awareness_pack"]
    searchable = " ".join((pack.name, pack.description, *pack.placeholder_signal_ids)).lower()

    for forbidden in FORBIDDEN_PUBLIC_LABELS:
        assert forbidden not in searchable


def test_life_load_pack_is_not_default_enabled_unless_explicitly_decided():
    assert OPTIONAL_PACK_TEMPLATES["life_load_pack"].default_enabled is False


def test_guidance_effect_values_are_limited():
    assert {effect.value for effect in GuidanceEffect} == {
        "track_only",
        "light",
        "normal",
        "strong",
        "guardrail",
    }


def test_sensitive_pattern_policies_are_private_plus_or_private():
    pack = OPTIONAL_PACK_TEMPLATES["pattern_awareness_pack"]

    for signal_id in pack.signal_ids:
        policy = SIGNAL_INFLUENCE_POLICIES[signal_id]
        assert policy.sensitivity_class in (SensitivityClass.PRIVATE, SensitivityClass.PRIVATE_PLUS)


def test_sensitive_pattern_policies_do_not_allow_treatment_boundary():
    pack = OPTIONAL_PACK_TEMPLATES["pattern_awareness_pack"]

    for signal_id in pack.signal_ids:
        policy = SIGNAL_INFLUENCE_POLICIES[signal_id]
        assert policy.clinical_boundary in (
            ClinicalBoundary.NEVER_SUGGEST_TREATMENT,
            ClinicalBoundary.OUT_OF_SCOPE_IF_URGENT,
        )


def test_body_signal_policies_have_out_of_scope_boundary_if_urgent():
    for signal_id in ("body.foot_pain", "body.shoulder_pain", "body.migraine_warning"):
        assert SIGNAL_INFLUENCE_POLICIES[signal_id].clinical_boundary == ClinicalBoundary.OUT_OF_SCOPE_IF_URGENT


def test_profile_allowed_pack_ids_match_defined_optional_packs():
    known_pack_ids = set(OPTIONAL_PACK_TEMPLATES)

    for profile in PROFILE_TEMPLATE_METADATA.values():
        assert set(profile.allowed_optional_pack_ids) <= known_pack_ids


def test_selected_profile_config_accepts_allowed_pack_ids():
    config = build_selected_profile_config("general_balance", optional_pack_ids=("life_load_pack",))

    assert config.optional_pack_ids == ("life_load_pack",)


def test_selected_profile_config_rejects_unallowed_pack_ids():
    try:
        build_selected_profile_config("custom_stub", optional_pack_ids=("life_load_pack",))
    except ValueError as error:
        assert "Optional pack id(s) not allowed for profile 'custom_stub'" in str(error)
    else:
        raise AssertionError("Expected unallowed optional pack to fail")


def test_influence_policy_not_consumed_by_scoring():
    for path in SCORING_SOURCE_PATHS:
        source = path.read_text(encoding="utf-8")
        assert "optional_packs" not in source
        assert "SignalInfluencePolicy" not in source
        assert "GuidanceEffect" not in source
