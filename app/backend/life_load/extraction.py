"""Diary extraction proposals for Life Load."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Mapping

from life_load.codex_runtime import (
    _apply_model_to_codex_command,
    _apply_reasoning_effort_to_codex_command,
    codex_turn_command_from_env,
    run_codex_oneshot,
)
from life_load.sqlite_core import DEFAULT_ROOT_REL, HealthObservabilityStore

EXTRACTOR_VERSION = "heuristic_diary_v0_1"
CODEX_EXTRACTOR_VERSION = "codex_diary_v0_2"
CODEX_MODEL = "gpt-5.4-mini"
CODEX_REASONING_EFFORT = "low"
CODEX_TIMEOUT_S = 30
OUTPUT_CONTRACT_VERSION = "life_load_diary_extraction_contract_v0_2"
ALLOWED_RED_FLAGS = {
    "alcohol",
    "binge",
    "late_phone",
    "project_overrun",
    "migraine_warning",
    "sleep_drift",
    "nutrition_drift",
    "pain_flare",
}
ALLOWED_FIELDS = {
    "sleep_ok",
    "nutrition_ok",
    "alcohol",
    "binge",
    "mood",
    "stress",
    "energy",
    "coffee_cups",
    "foot_pain",
    "shoulder_pain",
    "migraine_warning",
    "decompression_done",
    "shutdown_done",
    "phone_after_21",
    "project_overrun",
    "primary_activity_type",
    "activity_duration_min",
    "rehab_done",
    "other_symptoms",
    "work_intensity",
    "family_stress",
    "home_office",
    "alone_home",
    "homework_done",
    "after_work_decompression_done",
    "evening_chain_broken",
    "wife_conflict_count",
    "wife_conflict_school",
    "wife_conflict_chores",
    "wife_conflict_other",
    "tags",
}

BOOLEAN_FIELDS = {
    "sleep_ok",
    "nutrition_ok",
    "alcohol",
    "binge",
    "migraine_warning",
    "decompression_done",
    "shutdown_done",
    "phone_after_21",
    "project_overrun",
    "home_office",
    "alone_home",
    "rehab_done",
    "after_work_decompression_done",
    "evening_chain_broken",
    "wife_conflict_school",
    "wife_conflict_chores",
    "wife_conflict_other",
}
SCORE_FIELDS = {"mood", "stress", "energy", "foot_pain", "shoulder_pain", "family_stress"}
COUNT_FIELDS = {"wife_conflict_count"}
RANGE_FIELDS = {"coffee_cups": (0, 8)}
ACTIVITY_TYPES = {"", "walk", "bike_commute", "bike", "run", "crossfit", "rehab", "meditation", "other"}
WORK_INTENSITIES = {"normal", "heavy"}
RED_FLAG_SEVERITIES = {"yellow", "orange", "red"}

OUTPUT_CONTRACT: Dict[str, Any] = {
    "schema_version": OUTPUT_CONTRACT_VERSION,
    "return": "one JSON object only; no markdown; no prose",
    "top_level_required": ["date", "fields", "summary", "red_flags", "next_action", "status"],
    "top_level_allowed": [
        "date",
        "fields",
        "summary",
        "red_flags",
        "next_action",
        "status",
        "extraction_notes",
    ],
    "field_contract": {
        "booleans": sorted(BOOLEAN_FIELDS),
        "scores_0_to_10_integers": sorted(SCORE_FIELDS),
        "bounded_integer_fields": {"coffee_cups": "integer 0..8; number of coffees during the day if explicitly mentioned"},
        "count_fields": {"wife_conflict_count": "integer 0..12"},
        "activity_duration_min": "integer minutes, 0..1440, only if explicit duration is mentioned",
        "primary_activity_type": sorted(ACTIVITY_TYPES - {""}),
        "other_symptoms": "short string, only concrete physical symptoms",
        "work_intensity": sorted(WORK_INTENSITIES),
        "alone_home": "true if the diary says the user was alone at home; false only if explicitly not alone",
        "homework_done": "true, false, or null only when diary explicitly mentions homework/support",
        "after_work_decompression_done": "true if transition/decompression happened soon after work or arriving home; false if explicitly skipped",
        "evening_chain_broken": "true if the after-work/evening sequence went off rails: no decompression then food/video/project/binge/alcohol spiral",
        "wife_conflict_count": "integer 0..12; count explicit fights/conflicts/arguments with wife",
        "wife_conflict_school": "true if wife conflict involved son's school/homework",
        "wife_conflict_chores": "true if wife conflict involved chores/housework",
        "wife_conflict_other": "true if wife conflict involved another/random topic",
        "tags": "array of short kebab-case strings derived from extracted fields",
    },
    "red_flag_contract": {
        "type": sorted(ALLOWED_RED_FLAGS),
        "severity": sorted(RED_FLAG_SEVERITIES),
        "evidence": "short phrase copied or tightly paraphrased from diary",
    },
    "conversion_rules": [
        "Omit unsupported fields instead of guessing.",
        "Never encode unknown as false. False requires explicit evidence of no/failed/not done.",
        "alcohol=true only if alcohol was consumed or alcohol at home happened; 'no alcohol' means alcohol=false.",
        "phone_after_21=true for late phone/videos/doomscrolling after 21:00; explicit no late phone means false.",
        "project_overrun=true for project/work spillover into protected evening time.",
        "sleep_ok=false for poor/short/late sleep; true for slept well/on-time bedtime.",
        "nutrition_ok=true for clean/keto/low-carb/whole-food day; false for junk/sugar/chips/binge/food drift.",
        "work_intensity=heavy for heavy/very heavy/overloaded work; otherwise omit or normal only if explicit normal day.",
        "alone_home=true when alone at home, alone in the house, wife/kids away, or similar isolation at home is explicitly mentioned.",
        "If diary says fight/argument/conflict with wife, set wife_conflict_count to the number mentioned or 1 if count is implicit.",
        "Classify wife conflict themes: school/homework/son school -> wife_conflict_school; chores/housework -> wife_conflict_chores; otherwise wife_conflict_other.",
        "after_work_decompression_done=false when the diary explicitly says no decompression/reset/transition after work or coming home.",
        "evening_chain_broken=true when no decompression leads into bad evening decisions such as binge, alcohol, late phone, junk food, or project overrun.",
        "Map running/jog/run to primary_activity_type=run; bike commute/commuting by bike/cycling to work to bike_commute; sport cycling/bike ride/training ride to bike; CrossFit to crossfit; rehab/physio/mobility to rehab.",
        "Extract activity_duration_min only from explicit durations such as '35 min run' or 'walked 45 minutes'.",
        "Pain values must be 0..10 integers; parse forms like 'foot pain 6/10'.",
        "summary should be one concise sentence, not a JSON dump.",
    ],
}


def _stable_proposal_id(date: str, diary_text: str, prefix: str) -> tuple[str, str]:
    digest = hashlib.sha256(str(diary_text or "").encode("utf-8")).hexdigest()
    return f"prop_{prefix}_{date.replace('-', '')}_{digest[:12]}", digest


def _contains(text: str, patterns: List[str]) -> bool:
    return any(re.search(pattern, text) for pattern in patterns)


def _says_no_alcohol(text: str) -> bool:
    negative = [
        r"\bno alcohol\b",
        r"\bno beer\b",
        r"\bno wine\b",
        r"didn.t have alcohol",
        r"did not have alcohol",
        r"didn.t drink",
        r"did not drink",
        r"\bwithout alcohol\b",
        r"\balcohol[- ]free\b",
        r"\bzero alcohol\b",
    ]
    positive = [
        r"\bhad alcohol\b",
        r"\bdrank alcohol\b",
        r"\bdrank beer\b",
        r"\bdrank wine\b",
        r"\bbeer at home\b",
        r"\bwine at home\b",
        r"\balcohol at home\b",
    ]
    return _contains(text, negative) and not _contains(text, positive)


def _score_from_pattern(text: str, field_name: str) -> int | None:
    patterns = [
        rf"{field_name}\s*[:=]?\s*([0-9]{{1,2}})",
        rf"{field_name}\s*([0-9]{{1,2}})/10",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            try:
                value = int(match.group(1))
            except Exception:
                continue
            return max(0, min(10, value))
    return None


def _boolish_or_none(value: Any) -> bool | None:
    if value in (True, False):
        return bool(value)
    text = str(value or "").strip().lower()
    if text in {"true", "yes", "y", "1", "done", "ok"}:
        return True
    if text in {"false", "no", "n", "0", "missed", "not_done", "not done", "failed"}:
        return False
    return None


def _score_or_none(value: Any) -> int | None:
    if isinstance(value, (int, float)):
        return max(0, min(10, int(round(float(value)))))
    text = str(value or "").strip().lower()
    match = re.search(r"([0-9]{1,2})(?:\s*/\s*10)?", text)
    if not match:
        return None
    return max(0, min(10, int(match.group(1))))


def _minutes_or_none(value: Any) -> int | None:
    if isinstance(value, (int, float)):
        return max(0, min(24 * 60, int(round(float(value)))))
    text = str(value or "").strip().lower()
    match = re.search(r"([0-9]{1,4})", text)
    if not match:
        return None
    return max(0, min(24 * 60, int(match.group(1))))


def _count_or_none(value: Any, *, maximum: int = 12) -> int | None:
    if isinstance(value, (int, float)):
        return max(0, min(maximum, int(round(float(value)))))
    text = str(value or "").strip().lower()
    word_counts = {
        "zero": 0,
        "one": 1,
        "once": 1,
        "two": 2,
        "twice": 2,
        "three": 3,
        "four": 4,
        "five": 5,
        "several": 3,
        "many": 4,
        "multiple": 3,
    }
    for word, count in word_counts.items():
        if re.search(rf"\b{word}\b", text):
            return max(0, min(maximum, count))
    match = re.search(r"([0-9]{1,2})", text)
    if not match:
        return None
    return max(0, min(maximum, int(match.group(1))))


def _normalize_activity_type(value: Any) -> str | None:
    text = str(value or "").strip().lower().replace(" ", "_").replace("-", "_")
    aliases = {
        "none": "",
        "walking": "walk",
        "walked": "walk",
        "jog": "run",
        "jogging": "run",
        "running": "run",
        "cycling": "bike",
        "biking": "bike",
        "bike_commute": "bike_commute",
        "commute_bike": "bike_commute",
        "bike_to_work": "bike_commute",
        "physio": "rehab",
        "mobility": "rehab",
        "mobility_work": "rehab",
    }
    normalized = aliases.get(text, text)
    return normalized if normalized in ACTIVITY_TYPES else None


def _normalize_tags(value: Any) -> List[str]:
    raw = value if isinstance(value, list) else [value]
    tags: List[str] = []
    for item in raw:
        tag = str(item or "").strip().lower().replace("_", "-").replace(" ", "-")
        tag = re.sub(r"[^a-z0-9-]+", "", tag).strip("-")
        if tag and tag not in tags:
            tags.append(tag[:48])
    return tags


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def _extract_json_object(text: str) -> Dict[str, Any]:
    raw = str(text or "").strip()
    if not raw:
        raise ValueError("empty Codex extraction response")
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", raw, flags=re.DOTALL | re.IGNORECASE)
    candidate = fenced.group(1).strip() if fenced else raw
    if not candidate.startswith("{"):
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start >= 0 and end > start:
            candidate = candidate[start:end + 1]
    parsed = json.loads(candidate)
    if not isinstance(parsed, dict):
        raise ValueError("Codex extraction response must be a JSON object")
    return parsed


def _heuristic_analyze_diary_entry(*, date: str, diary_text: str) -> Dict[str, Any]:
    text = str(diary_text or "").strip()
    lowered = text.lower()
    proposal_id, digest = _stable_proposal_id(date, text, "heur")

    fields: Dict[str, Any] = {}
    tags: List[str] = []
    red_flags: List[Dict[str, str]] = []

    if _contains(lowered, [r"bad sleep", r"poor sleep", r"awake.*night", r"late night", r"sleep collapse"]):
        fields["sleep_ok"] = False
        red_flags.append({"type": "sleep_drift", "severity": "yellow", "evidence": "Diary text indicates poor or late sleep."})
        tags.append("sleep-drift")
    elif _contains(lowered, [r"good sleep", r"slept well", r"in bed on time", r"sleep was good"]):
        fields["sleep_ok"] = True

    if _contains(lowered, [r"junk food", r"chips", r"ate badly", r"binged on food", r"processed food", r"sweets"]):
        fields["nutrition_ok"] = False
        red_flags.append({"type": "nutrition_drift", "severity": "yellow", "evidence": "Diary text indicates food drift or junk intake."})
        tags.append("nutrition-drift")
    elif _contains(lowered, [r"clean food", r"ate well", r"low carb", r"keto", r"clean eating"]):
        fields["nutrition_ok"] = True

    if _says_no_alcohol(lowered):
        fields["alcohol"] = False
    elif _contains(lowered, [r"\bbeer\b", r"\bwine\b", r"\balcohol\b", r"\bdrank\b"]):
        fields["alcohol"] = True
        red_flags.append({"type": "alcohol", "severity": "orange", "evidence": "Diary text mentions alcohol."})
        tags.append("alcohol")

    if _contains(lowered, [r"\bbinge\b", r"overate", r"couldn.t stop eating", r"loss of control eating"]):
        fields["binge"] = True
        red_flags.append({"type": "binge", "severity": "orange", "evidence": "Diary text mentions a binge or loss-of-control eating."})
        tags.append("binge")

    if _contains(lowered, [r"phone after 21", r"videos after 21", r"doomscroll", r"watched videos late", r"late phone"]):
        fields["phone_after_21"] = True
        red_flags.append({"type": "late_phone", "severity": "yellow", "evidence": "Diary text indicates late phone or video use."})
        tags.append("late-phone")

    if _contains(lowered, [r"project spillover", r"worked too late", r"project overrun", r"computer project late"]):
        fields["project_overrun"] = True
        red_flags.append({"type": "project_overrun", "severity": "yellow", "evidence": "Diary text indicates project spillover into the evening."})
        tags.append("project-overrun")

    if _contains(lowered, [r"shutdown done", r"shut down on time", r"good shutdown"]):
        fields["shutdown_done"] = True
    elif _contains(lowered, [r"missed shutdown", r"no shutdown", r"late night spiral"]):
        fields["shutdown_done"] = False

    if _contains(lowered, [r"decompression walk", r"went for a walk", r"meditated", r"cooked to relax", r"decompress"]):
        fields["decompression_done"] = True
    if _contains(lowered, [r"after[- ]work decompression", r"decompressed after work", r"reset after work", r"transition after work", r"walk after work"]):
        fields["after_work_decompression_done"] = True
        tags.append("after-work-reset")
    if _contains(lowered, [r"no decompression after work", r"didn.t decompress after work", r"skipped decompression", r"came home and did not decompress", r"came back from work.*no decompression"]):
        fields["after_work_decompression_done"] = False
        tags.append("missed-after-work-reset")
    if _contains(lowered, [r"evening chain broke", r"evening went off rails", r"spiraled after work", r"no decompression.*(binge|junk|alcohol|phone|video|project)", r"came home.*(binge|junk|alcohol|phone|video|project).*no decompression"]):
        fields["evening_chain_broken"] = True
        tags.append("evening-chain-broken")

    wife_conflict_patterns = [
        r"\bfight(?:s|ing)? with (?:my )?wife\b",
        r"\bargument(?:s)? with (?:my )?wife\b",
        r"\bconflict(?:s)? with (?:my )?wife\b",
        r"\brow(?:s)? with (?:my )?wife\b",
        r"\bwife.*\b(fight|argument|conflict|row)\b",
    ]
    if _contains(lowered, wife_conflict_patterns):
        count_match = re.search(
            r"\b(zero|one|once|two|twice|three|four|five|several|many|multiple|[0-9]{1,2})\b\s+(?:fights?|arguments?|conflicts?|rows?)",
            lowered,
        )
        count = _count_or_none(count_match.group(1), maximum=12) if count_match else None
        fields["wife_conflict_count"] = count if count is not None else 1
        fields["wife_conflict_school"] = _contains(lowered, [r"school", r"homework", r"\bson\b", r"teacher", r"grades?"])
        fields["wife_conflict_chores"] = _contains(lowered, [r"chores?", r"housework", r"cleaning", r"kitchen", r"laundry", r"dishes"])
        fields["wife_conflict_other"] = not (fields["wife_conflict_school"] or fields["wife_conflict_chores"])
        tags.append("relationship-conflict")
        if fields["wife_conflict_school"]:
            tags.append("school-conflict")
        if fields["wife_conflict_chores"]:
            tags.append("chores-conflict")
    if _contains(lowered, [r"\bwalk\b", r"\bwalked\b"]):
        fields.setdefault("primary_activity_type", "walk")
    if _contains(lowered, [r"\bran\b", r"\brun\b"]):
        fields["primary_activity_type"] = "run"
    if _contains(lowered, [r"crossfit"]):
        fields["primary_activity_type"] = "crossfit"
    if _contains(lowered, [r"bike commute", r"commut(e|ed|ing).*bike", r"bike.*commut(e|ed|ing)", r"cycling to work", r"bike to work"]):
        fields["primary_activity_type"] = "bike_commute"
    elif _contains(lowered, [r"\bbike\b", r"\bcycling\b", r"\bbiked\b"]):
        fields.setdefault("primary_activity_type", "bike")
    if _contains(lowered, [r"rehab", r"physio", r"mobility work"]):
        fields["rehab_done"] = True

    if _contains(lowered, [r"migraine", r"headache warning", r"migraine warning"]):
        fields["migraine_warning"] = True
        red_flags.append({"type": "migraine_warning", "severity": "orange", "evidence": "Diary text mentions migraine symptoms or warning."})
        tags.append("migraine-warning")

    if _contains(lowered, [r"heavy work", r"long workday", r"intense work", r"overloaded at work"]):
        fields["work_intensity"] = "heavy"
        tags.append("work-heavy")

    if _contains(lowered, [r"home office", r"worked from home"]):
        fields["home_office"] = True
    if _contains(lowered, [r"alone at home", r"home alone", r"alone in the house", r"alone all evening", r"wife and kids (?:were )?away", r"family (?:was|were) away"]):
        fields["alone_home"] = True
        tags.append("alone-home")

    mood = _score_from_pattern(lowered, "mood")
    stress = _score_from_pattern(lowered, "stress")
    energy = _score_from_pattern(lowered, "energy")
    coffee_match = re.search(r"\b(?:coffee|coffees|espresso|espressos|caffeine)\s*(?:x|:|=)?\s*(\d+)\b|\b(\d+)\s*(?:coffee|coffees|espresso|espressos)\b", lowered)
    if coffee_match:
        fields["coffee_cups"] = min(8, max(0, int(coffee_match.group(1) or coffee_match.group(2))))
    foot_pain = _score_from_pattern(lowered, "foot_pain") or _score_from_pattern(lowered, "foot pain")
    shoulder_pain = _score_from_pattern(lowered, "shoulder_pain") or _score_from_pattern(lowered, "shoulder pain")
    family_stress = _score_from_pattern(lowered, "family_stress") or _score_from_pattern(lowered, "family stress")
    for field_name, value in (
        ("mood", mood),
        ("stress", stress),
        ("energy", energy),
        ("foot_pain", foot_pain),
        ("shoulder_pain", shoulder_pain),
        ("family_stress", family_stress),
    ):
        if value is not None:
            fields[field_name] = value

    if isinstance(fields.get("foot_pain"), int) and fields["foot_pain"] >= 5:
        red_flags.append({"type": "pain_flare", "severity": "orange", "evidence": "Diary text implies significant foot pain."})
        tags.append("foot-pain")
    if isinstance(fields.get("shoulder_pain"), int) and fields["shoulder_pain"] >= 5:
        red_flags.append({"type": "pain_flare", "severity": "orange", "evidence": "Diary text implies significant shoulder pain."})
        tags.append("shoulder-pain")

    if tags:
        fields["tags"] = sorted(set(tags))

    summary_parts: List[str] = []
    if fields.get("work_intensity") == "heavy":
        summary_parts.append("Heavy work")
    if fields.get("nutrition_ok") is True:
        summary_parts.append("Clean food")
    elif fields.get("nutrition_ok") is False:
        summary_parts.append("Food drift")
    if fields.get("alcohol") is True:
        summary_parts.append("Alcohol")
    if fields.get("decompression_done") is True:
        summary_parts.append("Decompression done")
    if fields.get("alone_home") is True:
        summary_parts.append("Alone at home")
    if fields.get("after_work_decompression_done") is False:
        summary_parts.append("No after-work decompression")
    if fields.get("wife_conflict_count"):
        summary_parts.append(f"Relationship stress x{fields['wife_conflict_count']}")
    if isinstance(fields.get("foot_pain"), int):
        summary_parts.append(f"Foot pain {fields['foot_pain']}/10")
    if fields.get("phone_after_21") is True:
        summary_parts.append("Late phone")
    summary = " · ".join(summary_parts) if summary_parts else "No strong structured extraction signals detected."

    if any(flag["type"] in {"alcohol", "binge", "migraine_warning", "pain_flare"} for flag in red_flags):
        next_action = "Protect recovery first and avoid adding extra training load."
    elif fields.get("alone_home") is True or fields.get("wife_conflict_count") or fields.get("after_work_decompression_done") is False or fields.get("evening_chain_broken") is True:
        next_action = "Release pressure first: use after-work decompression before adding evening ambition."
    elif any(flag["type"] in {"late_phone", "project_overrun", "sleep_drift"} for flag in red_flags):
        next_action = "Protect shutdown tonight and keep the next day simple."
    else:
        next_action = "Review the proposed fields and fill any unknowns before approval."

    return {
        "proposal_id": proposal_id,
        "date": date,
        "diary_text_hash": digest,
        "extractor_version": EXTRACTOR_VERSION,
        "fields": fields,
        "summary": summary,
        "red_flags": red_flags,
        "next_action": next_action,
        "status": "pending",
    }


def _codex_message(
    *,
    date: str,
    diary_text: str,
    existing_entry: Mapping[str, Any] | None,
    week_context: Mapping[str, Any] | None,
    rules_text: str,
    thresholds_text: str,
) -> str:
    payload = {
        "task": "life_load_diary_extraction",
        "selected_date": date,
        "diary_text": diary_text,
        "existing_entry": dict(existing_entry or {}),
        "current_week_context": dict(week_context or {}),
        "rules_yaml": rules_text,
        "thresholds_yaml": thresholds_text,
        "allowed_fields": sorted(ALLOWED_FIELDS),
        "allowed_red_flags": sorted(ALLOWED_RED_FLAGS),
        "output_contract": OUTPUT_CONTRACT,
        "json_shape_example": {
            "date": "YYYY-MM-DD",
            "fields": {
                "sleep_ok": True,
                "nutrition_ok": False,
                "alcohol": False,
                "binge": False,
                "mood": 6,
                "stress": 7,
                "energy": 5,
                "foot_pain": 3,
                "shoulder_pain": 2,
                "migraine_warning": False,
                "decompression_done": True,
                "shutdown_done": False,
                "phone_after_21": True,
                "project_overrun": False,
                "work_intensity": "heavy",
                "family_stress": 5,
                "home_office": False,
                "alone_home": True,
                "homework_done": None,
                "after_work_decompression_done": False,
                "evening_chain_broken": True,
                "wife_conflict_count": 2,
                "wife_conflict_school": True,
                "wife_conflict_chores": False,
                "wife_conflict_other": False,
                "tags": ["work-heavy", "evening-drift"],
            },
            "summary": "Short detected summary.",
            "red_flags": [{"type": "late_phone", "severity": "yellow", "evidence": "Watched videos after 21:00."}],
            "next_action": "Protect shutdown tonight and do not add extra training.",
        },
        "instructions": [
            "Return JSON only. No markdown fences. No prose before or after the JSON.",
            "Follow output_contract exactly.",
            "Use only allowed field names, activity types, work intensities, and red flag types.",
            "If the diary does not support a field, omit it from fields.",
            "Do not infer unknown as false. False requires explicit negative evidence.",
            "Do not ask follow-up questions.",
            "Do not mention repo inspection, tests, or code changes.",
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _codex_analyze_diary_entry(
    *,
    date: str,
    diary_text: str,
    existing_entry: Mapping[str, Any] | None,
    week_context: Mapping[str, Any] | None,
    repo_root: Path,
) -> Dict[str, Any]:
    root = Path(repo_root).resolve()
    store = HealthObservabilityStore(repo_root=root, root_rel=DEFAULT_ROOT_REL)
    rules_text = _read_text(store.config_root / "rules.yaml")
    thresholds_text = _read_text(store.config_root / "thresholds.yaml")
    message = _codex_message(
        date=date,
        diary_text=diary_text,
        existing_entry=existing_entry,
        week_context=week_context,
        rules_text=rules_text,
        thresholds_text=thresholds_text,
    )
    cmd = _apply_reasoning_effort_to_codex_command(
        _apply_model_to_codex_command(codex_turn_command_from_env(), model=CODEX_MODEL),
        reasoning_effort=CODEX_REASONING_EFFORT,
    )
    turn = run_codex_oneshot(
        worker_id=f"life-load::{date}::extractor",
        binding_type="life_load",
        binding_id=date,
        role="generalist",
        message=message,
        bootstrap_text=(
            "You are a structured Life Load diary extraction worker.\n"
            "Return JSON only.\n"
            "Do not inspect files, do not modify anything, and do not ask follow-up questions."
        ),
        cwd=root,
        timeout_s=CODEX_TIMEOUT_S,
        command=cmd,
    )
    if not bool(turn.get("ok")):
        raise ValueError(str(turn.get("stderr") or turn.get("content") or "Codex diary extraction needs attention"))
    parsed = _extract_json_object(str(turn.get("content") or ""))
    validated = validate_proposal(request_date=date, proposal=parsed)
    proposal_id, digest = _stable_proposal_id(date, diary_text, "codex")
    validated["proposal_id"] = proposal_id
    validated["diary_text_hash"] = digest
    validated["extractor_version"] = CODEX_EXTRACTOR_VERSION
    validated["extractor_model"] = CODEX_MODEL
    validated["extractor_timeout_s"] = CODEX_TIMEOUT_S
    return validated


def analyze_diary_entry(
    *,
    date: str,
    diary_text: str,
    existing_entry: Mapping[str, Any] | None = None,
    week_context: Mapping[str, Any] | None = None,
    repo_root: Path | None = None,
) -> Dict[str, Any]:
    if repo_root is None:
        raise ValueError("AI diary extraction requires repo_root for the background Codex worker")
    return _codex_analyze_diary_entry(
        date=date,
        diary_text=diary_text,
        existing_entry=existing_entry,
        week_context=week_context,
        repo_root=repo_root,
    )


def validate_proposal(*, request_date: str, proposal: Mapping[str, Any]) -> Dict[str, Any]:
    if str(proposal.get("date") or "") != str(request_date):
        raise ValueError("proposal date does not match request date")
    validated_fields: Dict[str, Any] = {}
    raw_fields = proposal.get("fields") or {}
    if not isinstance(raw_fields, Mapping):
        raise ValueError("proposal fields must be an object")
    validation_issues: List[str] = [
        str(item or "").strip()
        for item in list(proposal.get("validation_issues") or [])
        if str(item or "").strip()
    ]
    for key, value in dict(raw_fields).items():
        if key not in ALLOWED_FIELDS:
            validation_issues.append(f"unknown_field:{key}")
            continue
        if key in BOOLEAN_FIELDS:
            normalized_bool = _boolish_or_none(value)
            if normalized_bool is not None:
                validated_fields[key] = normalized_bool
            else:
                validation_issues.append(f"invalid_boolean:{key}")
            continue
        if key in SCORE_FIELDS:
            normalized_score = _score_or_none(value)
            if normalized_score is not None:
                validated_fields[key] = normalized_score
            else:
                validation_issues.append(f"invalid_score:{key}")
            continue
        if key in COUNT_FIELDS:
            normalized_count = _count_or_none(value, maximum=12)
            if normalized_count is not None:
                validated_fields[key] = normalized_count
            else:
                validation_issues.append(f"invalid_count:{key}")
            continue
        if key in RANGE_FIELDS:
            minimum, maximum = RANGE_FIELDS[key]
            normalized_range = _count_or_none(value, maximum=maximum)
            if normalized_range is not None and normalized_range >= minimum:
                validated_fields[key] = normalized_range
            else:
                validation_issues.append(f"invalid_range:{key}")
            continue
        if key == "activity_duration_min":
            minutes = _minutes_or_none(value)
            if minutes is not None:
                validated_fields[key] = minutes
            else:
                validation_issues.append("invalid_minutes:activity_duration_min")
            continue
        if key == "primary_activity_type":
            activity_type = _normalize_activity_type(value)
            if activity_type is not None:
                validated_fields[key] = activity_type
            else:
                validation_issues.append("invalid_activity_type:primary_activity_type")
            continue
        if key == "other_symptoms":
            text = str(value or "").strip()
            if text:
                validated_fields[key] = text[:240]
            continue
        if key == "work_intensity":
            text = str(value or "").strip().lower().replace("_", " ")
            if text in {"very heavy", "overloaded", "intense"}:
                text = "heavy"
            if text in WORK_INTENSITIES:
                validated_fields[key] = text
            else:
                validation_issues.append("invalid_work_intensity:work_intensity")
            continue
        if key == "homework_done":
            validated_fields[key] = _boolish_or_none(value)
            continue
        if key == "tags":
            tags = _normalize_tags(value)
            if tags:
                validated_fields[key] = tags
            continue
    red_flags: List[Dict[str, str]] = []
    raw_red_flags = proposal.get("red_flags") or []
    if not isinstance(raw_red_flags, list):
        validation_issues.append("invalid_red_flags:not_list")
        raw_red_flags = []
    for flag in list(raw_red_flags):
        if not isinstance(flag, Mapping):
            validation_issues.append("invalid_red_flag:not_object")
            continue
        flag_type = str(flag.get("type") or "").strip()
        if flag_type not in ALLOWED_RED_FLAGS:
            validation_issues.append(f"unknown_red_flag:{flag_type}")
            continue
        severity = str(flag.get("severity") or "yellow").strip().lower() or "yellow"
        if severity not in RED_FLAG_SEVERITIES:
            validation_issues.append(f"invalid_red_flag_severity:{severity}")
            severity = "yellow"
        red_flags.append(
            {
                "type": flag_type,
                "severity": severity,
                "evidence": str(flag.get("evidence") or "").strip(),
            }
        )
    return {
        "proposal_id": str(proposal.get("proposal_id") or ""),
        "date": request_date,
        "contract_version": OUTPUT_CONTRACT_VERSION,
        "diary_text_hash": str(proposal.get("diary_text_hash") or ""),
        "extractor_version": str(proposal.get("extractor_version") or EXTRACTOR_VERSION),
        "fields": validated_fields,
        "summary": str(proposal.get("summary") or "").strip(),
        "red_flags": red_flags,
        "next_action": str(proposal.get("next_action") or "").strip(),
        "status": str(proposal.get("status") or "pending").strip() or "pending",
        "validation_issues": validation_issues,
    }
