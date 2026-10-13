import json

from life_load.core_engine import LifeLoadCore
from life_load.demo import run_demo


def test_fresh_demo_preserves_generic_profile_and_canonical_truth(tmp_path):
    result = run_demo(tmp_path)
    selected = json.loads((tmp_path / 'demo-profile.json').read_text())
    assert selected['active_profile_id'] == 'general_balance'
    store = LifeLoadCore(tmp_path)
    canonical = store.fetch_one('SELECT * FROM daily_log WHERE date = ?', ('2026-10-12',))
    assert canonical['sleep_ok'] == 1
    assert canonical['stress'] == 5
    assert store.fetch_one('SELECT COUNT(*) AS n FROM draft_entry')['n'] == 0
    assert result['generic_profile_bridge']['profile_id'] == 'general_balance'
    assert result['clinical_validity_established'] is False
    assert result['native_android_sync_performed'] is False
