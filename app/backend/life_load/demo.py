"""A deterministic, fictional check-in using the actual backend and SQLite."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path

from life_load.core_engine import LifeLoadCore, approve_payload, get_entry_payload, update_draft_payload
from life_load.selected_profile_config import build_selected_profile_config
from life_load.guidance_bridge import build_guidance_bridge_from_selected_profile_config


def run_demo(state_root: Path) -> dict:
    """Keep the generic profile and canonical compatibility score distinguishable."""
    state_root.mkdir(parents=True, exist_ok=True)
    profile = build_selected_profile_config("general_balance")
    (state_root / 'demo-profile.json').write_text(json.dumps(asdict(profile), indent=2))
    store = LifeLoadCore(state_root)
    store.migrate()
    day = "2026-10-12"
    fields = {"sleep_ok": True, "nutrition_ok": True, "stress": 5, "energy": 5,
              "shutdown_done": True, "decompression_done": True}
    update_draft_payload(store, {"date": day, "fields": fields,
        "diary_text": "Fictional check-in: a busy day followed by a quiet evening."})
    approved = approve_payload(store, {"date": day})
    signals = {"core.sleep_ok": True, "mental.stress": 5, "energy.energy": 5}
    bridge = build_guidance_bridge_from_selected_profile_config(profile,
        ({"signal_id": key, "value": value, "is_present": True} for key, value in signals.items()))
    persisted = get_entry_payload(LifeLoadCore(state_root), date_value=day)
    assert persisted['entry']['sleep_ok'] is True and persisted['draftEntry'] is None
    return {"synthetic_data_only": True, "profile_id": "general_balance",
        "canonical_checkin_saved": True, "canonical_compatibility_score": approved['summary'],
        "generic_profile_bridge": {"profile_id": bridge.active_profile_id,
            "present_signal_values": dict(bridge.present_signal_values),
            "missing_required_signal_ids": bridge.missing_required_signal_ids},
        "native_android_sync_performed": False, "clinical_validity_established": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-root', type=Path, default=Path('runtime/synthetic-demo'))
    print(json.dumps(run_demo(parser.parse_args().state_root), indent=2))


if __name__ == '__main__':
    main()
