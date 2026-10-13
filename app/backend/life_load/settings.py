"""Runtime Life Load settings shared by backend, web, and Android clients."""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any, Dict, Mapping

from life_load import fsio

SETTINGS_CONTRACT_VERSION = "life_load_settings_contract_v1"
SETTINGS_PAYLOAD_VERSION = "life_load_settings_v1"
SETTINGS_SCHEMA_PATH = Path(__file__).with_name("life_load_settings_schema.json")
SETTINGS_REL_PATH = Path("runtime/config/life_load/settings.json")


def _load_schema() -> Dict[str, Any]:
    payload = json.loads(SETTINGS_SCHEMA_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != SETTINGS_CONTRACT_VERSION:
        raise RuntimeError(f"Invalid Life Load settings schema: {SETTINGS_SCHEMA_PATH}")
    return payload


SETTINGS_SCHEMA: Dict[str, Any] = _load_schema()


def _schema_defaults() -> Dict[str, Any]:
    defaults: Dict[str, Any] = {}
    for section in SETTINGS_SCHEMA.get("sections", []):
        if not isinstance(section, Mapping):
            continue
        section_key = str(section.get("key") or "")
        if not section_key:
            continue
        defaults[section_key] = {}
        for field in section.get("fields", []):
            if not isinstance(field, Mapping):
                continue
            key = str(field.get("key") or "")
            if key and "default" in field:
                defaults[section_key][key] = copy.deepcopy(field["default"])
    return defaults


DEFAULT_SETTINGS: Dict[str, Any] = _schema_defaults()


def settings_path(repo_root: Path) -> Path:
    override = os.environ.get("LIFE_LOAD_SETTINGS_PATH")
    if override:
        return Path(override).expanduser()
    return repo_root / SETTINGS_REL_PATH


def _deep_merge(base: Mapping[str, Any], updates: Mapping[str, Any]) -> Dict[str, Any]:
    merged = copy.deepcopy(dict(base))
    for key, value in updates.items():
        if isinstance(value, Mapping) and isinstance(merged.get(key), Mapping):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _field_spec(section_key: str, field_key: str) -> Mapping[str, Any] | None:
    for section in SETTINGS_SCHEMA.get("sections", []):
        if not isinstance(section, Mapping) or section.get("key") != section_key:
            continue
        for field in section.get("fields", []):
            if isinstance(field, Mapping) and field.get("key") == field_key:
                return field
    return None


def _coerce_field(section_key: str, field_key: str, value: Any) -> Any:
    spec = _field_spec(section_key, field_key)
    if spec is None:
        return None
    field_type = spec.get("type")
    if field_type == "boolean":
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.lower() in {"true", "false"}:
            return value.lower() == "true"
        return copy.deepcopy(spec.get("default", False))
    if field_type == "integer":
        try:
            number = int(value)
        except (TypeError, ValueError):
            number = int(spec.get("default", 0))
        if "min" in spec:
            number = max(number, int(spec["min"]))
        if "max" in spec:
            number = min(number, int(spec["max"]))
        return number
    if field_type == "enum":
        values = [str(item) for item in spec.get("values", [])]
        text = str(value or "")
        return text if text in values else copy.deepcopy(spec.get("default", values[0] if values else ""))
    if field_type == "string_array":
        values = [str(item) for item in spec.get("values", [])]
        if not isinstance(value, list):
            return copy.deepcopy(spec.get("default", []))
        normalized = []
        for item in value:
            text = str(item or "")
            if text and (not values or text in values) and text not in normalized:
                normalized.append(text)
        return normalized
    if field_type in {"string", "secret"}:
        return str(value or "")
    return copy.deepcopy(value)


def normalize_settings(raw: Mapping[str, Any]) -> Dict[str, Any]:
    merged = _deep_merge(DEFAULT_SETTINGS, raw)
    normalized: Dict[str, Any] = {}
    for section in SETTINGS_SCHEMA.get("sections", []):
        if not isinstance(section, Mapping):
            continue
        section_key = str(section.get("key") or "")
        section_values = merged.get(section_key, {})
        if not isinstance(section_values, Mapping):
            section_values = {}
        normalized[section_key] = {}
        for field in section.get("fields", []):
            if not isinstance(field, Mapping):
                continue
            field_key = str(field.get("key") or "")
            if not field_key:
                continue
            default = copy.deepcopy(field.get("default", ""))
            value = section_values.get(field_key, default)
            normalized[section_key][field_key] = _coerce_field(section_key, field_key, value)
    return normalized


def public_settings(settings: Mapping[str, Any]) -> Dict[str, Any]:
    public = normalize_settings(settings)
    garmin = public.setdefault("garmin", {})
    password = str(garmin.get("password") or "")
    garmin["password_set"] = bool(password)
    garmin.pop("password", None)
    return public


def _settings_backup_path(path: Path) -> Path:
    return path.with_name(f"{path.name}.bak")


def _decode_settings(path: Path) -> Dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise RuntimeError(f"Invalid Life Load settings JSON: {path}: root must be an object")
    return normalize_settings(raw.get("settings", raw))


def load_settings(repo_root: Path) -> Dict[str, Any]:
    path = settings_path(repo_root)
    with fsio.file_lock(path):
        if not path.exists():
            backup = _settings_backup_path(path)
            if backup.exists():
                return _decode_settings(backup)
            return normalize_settings({})
        try:
            return _decode_settings(path)
        except (OSError, json.JSONDecodeError, RuntimeError) as primary_error:
            # An interrupted write must not strand the application with an
            # unreadable settings file when the last complete version is still
            # available beside it.
            backup = _settings_backup_path(path)
            if backup.exists():
                try:
                    return _decode_settings(backup)
                except (OSError, json.JSONDecodeError, RuntimeError):
                    pass
            if isinstance(primary_error, json.JSONDecodeError):
                raise RuntimeError(f"Invalid Life Load settings JSON: {path}: {primary_error}") from primary_error
            raise


def save_settings(repo_root: Path, updates: Mapping[str, Any]) -> Dict[str, Any]:
    path = settings_path(repo_root)
    with fsio.file_lock(path):
        current = load_settings(repo_root)
        incoming = updates.get("settings", updates)
        if not isinstance(incoming, Mapping):
            raise ValueError("settings payload must be an object")
        merged = _deep_merge(current, incoming)
        normalized = normalize_settings(merged)
        payload = {
            "schema_version": SETTINGS_PAYLOAD_VERSION,
            "settings": normalized,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        backup = _settings_backup_path(path)
        if path.exists():
            # Keep a complete previous document for recovery if a later
            # process is terminated during replacement. The backup write is
            # atomic too, so it never becomes a second truncated file.
            try:
                previous = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(previous, dict):
                    fsio.write_json_atomic(backup, previous)
            except (OSError, json.JSONDecodeError):
                fsio.write_json_atomic(backup, {"schema_version": SETTINGS_PAYLOAD_VERSION, "settings": current})
        fsio.write_json_atomic(path, payload)
        if not backup.exists():
            fsio.write_json_atomic(backup, payload)
        try:
            os.chmod(path, 0o600)
            if backup.exists():
                os.chmod(backup, 0o600)
        except OSError:
            pass
        return normalized


def settings_payload(repo_root: Path) -> Dict[str, Any]:
    settings = load_settings(repo_root)
    return {
        "schema_version": SETTINGS_PAYLOAD_VERSION,
        "contract_schema_version": SETTINGS_CONTRACT_VERSION,
        "settings_path": str(settings_path(repo_root)),
        "settings": public_settings(settings),
        "schema": copy.deepcopy(SETTINGS_SCHEMA),
    }
