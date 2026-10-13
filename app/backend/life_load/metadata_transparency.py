"""Server-visible metadata transparency reports for P-INFRA rehearsals."""

from __future__ import annotations

import json
from typing import Any, Mapping

ALLOWED_METADATA_FIELDS = {
    "schema_version",
    "user_id_hash",
    "devices",
    "backup_objects",
    "recovery_package_exists",
    "trusted_device_request_count",
    "server_can_read_private_payloads",
    "plaintext_key_material_available",
    "forbidden_payload_fields_absent",
}
FORBIDDEN_METADATA_TERMS = {
    "diary_text",
    "check_in_answers",
    "mood",
    "stress",
    "pain",
    "garmin",
    "health_payload",
    "ai_prompt",
    "recovery_phrase",
    "recovery_key",
    "vault_key",
    "record_dek",
    "session_token",
    "password",
    "ciphertext",
}


def metadata_transparency_report(server_metadata: Mapping[str, Any], support_summary: Mapping[str, Any]) -> dict[str, Any]:
    metadata = dict(server_metadata)
    support = dict(support_summary)
    metadata_text = json.dumps({"server": metadata, "support": support}, sort_keys=True).lower()
    forbidden_hits = sorted(term for term in FORBIDDEN_METADATA_TERMS if term in metadata_text)
    disallowed_fields = sorted(set(metadata).difference(ALLOWED_METADATA_FIELDS))
    return {
        "schema_version": "life_load_metadata_transparency_report_v1",
        "allowed_server_metadata_fields": sorted(ALLOWED_METADATA_FIELDS),
        "observed_server_metadata_fields": sorted(metadata),
        "disallowed_server_metadata_fields": disallowed_fields,
        "forbidden_term_count": len(forbidden_hits),
        "server_can_read_private_payloads": bool(metadata.get("server_can_read_private_payloads")),
        "plaintext_key_material_available": bool(metadata.get("plaintext_key_material_available")),
        "support_can_decrypt_private_history": bool(support.get("support_can_decrypt_private_history")),
        "support_can_bypass_recovery_material": bool(support.get("support_can_bypass_recovery_material")),
        "ok": (
            not disallowed_fields
            and not forbidden_hits
            and metadata.get("server_can_read_private_payloads") is False
            and metadata.get("plaintext_key_material_available") is False
            and support.get("support_can_decrypt_private_history") is False
            and support.get("support_can_bypass_recovery_material") is False
        ),
        "redacted": True,
    }
