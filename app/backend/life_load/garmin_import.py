"""Import Garmin health export archives as passive evidence.

Garmin data is source-derived telemetry. It is useful for historical context and
trend detection, but it must not overwrite approved diary truth in ``daily_log``.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping
from zipfile import ZipFile

from life_load.sqlite_core import HealthObservabilityStore, utc_now_iso

CSV_ROOT = "garmin_health_platform_extract/csv/"

REQUIRED_CSVS = {
    "activities": CSV_ROOT + "activities.csv",
    "sleep_sessions": CSV_ROOT + "sleep_sessions.csv",
    "daily_wellness": CSV_ROOT + "daily_wellness.csv",
    "training_history": CSV_ROOT + "training_history.csv",
    "acute_training_load": CSV_ROOT + "acute_training_load.csv",
    "body_measurements": CSV_ROOT + "body_measurements.csv",
    "daily_joined_summary": CSV_ROOT + "daily_joined_summary.csv",
}

OPTIONAL_CSVS = {
    "source_manifest": CSV_ROOT + "source_manifest.csv",
    "uploaded_files_manifest": CSV_ROOT + "uploaded_files_inner_manifest.csv",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_csv(zip_file: ZipFile, member: str) -> list[dict[str, str]]:
    with zip_file.open(member) as fh:
        text = io.TextIOWrapper(fh, encoding="utf-8-sig", errors="replace", newline="")
        return [dict(row) for row in csv.DictReader(text)]


def _required_text(row: Mapping[str, Any], key: str) -> str:
    return str(row.get(key) or "").strip()


def _float_or_none(value: Any) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return float(text)
    except Exception:
        return None


def _int_or_none(value: Any) -> int | None:
    number = _float_or_none(value)
    if number is None:
        return None
    return int(round(number))


def _bool_int(value: Any) -> int:
    return 1 if str(value or "").strip().lower() in {"1", "true", "yes", "y"} else 0


def _raw(row: Mapping[str, Any]) -> str:
    return json.dumps(dict(row), ensure_ascii=False, sort_keys=True)


def _date_values(rows_by_name: Mapping[str, Iterable[Mapping[str, Any]]]) -> list[str]:
    dates: list[str] = []
    for rows in rows_by_name.values():
        for row in rows:
            date = _required_text(row, "date")
            if date:
                dates.append(date)
    return dates


def import_garmin_export_zip(store: HealthObservabilityStore, zip_path: Path) -> Dict[str, Any]:
    """Import a generated Garmin health export zip into passive evidence tables."""

    source_path = Path(zip_path).expanduser().resolve()
    if not source_path.exists():
        raise FileNotFoundError(source_path)

    source_sha256 = _sha256(source_path)
    store.migrate()
    now = utc_now_iso()

    with ZipFile(source_path) as zip_file:
        names = set(zip_file.namelist())
        missing = sorted(path for path in REQUIRED_CSVS.values() if path not in names)
        if missing:
            raise ValueError(f"Garmin export missing required CSVs: {missing}")

        rows = {name: _read_csv(zip_file, member) for name, member in REQUIRED_CSVS.items()}
        optional_rows = {
            name: _read_csv(zip_file, member)
            for name, member in OPTIONAL_CSVS.items()
            if member in names
        }

    dates = _date_values(rows)
    row_counts = {name: len(value) for name, value in {**rows, **optional_rows}.items()}

    with store.connect() as conn, conn:
        conn.executemany(
            """
            INSERT INTO garmin_activity(
                activity_id, date, start_time_local_iso, name, activity_type, sport_type,
                duration_min, moving_duration_min, distance_km, time_on_feet_min_est,
                impact_load_est, hard_session_est, calories, avg_hr, max_hr,
                aerobic_training_effect, anaerobic_training_effect, source_file,
                quality_flag, source_sha256, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(activity_id) DO UPDATE SET
                date=excluded.date,
                start_time_local_iso=excluded.start_time_local_iso,
                name=excluded.name,
                activity_type=excluded.activity_type,
                sport_type=excluded.sport_type,
                duration_min=excluded.duration_min,
                moving_duration_min=excluded.moving_duration_min,
                distance_km=excluded.distance_km,
                time_on_feet_min_est=excluded.time_on_feet_min_est,
                impact_load_est=excluded.impact_load_est,
                hard_session_est=excluded.hard_session_est,
                calories=excluded.calories,
                avg_hr=excluded.avg_hr,
                max_hr=excluded.max_hr,
                aerobic_training_effect=excluded.aerobic_training_effect,
                anaerobic_training_effect=excluded.anaerobic_training_effect,
                source_file=excluded.source_file,
                quality_flag=excluded.quality_flag,
                source_sha256=excluded.source_sha256,
                raw_json=excluded.raw_json
            """,
            [
                (
                    _required_text(row, "activity_id") or f"{source_sha256}:{idx}",
                    _required_text(row, "date"),
                    _required_text(row, "start_time_local_iso"),
                    _required_text(row, "name"),
                    _required_text(row, "activity_type"),
                    _required_text(row, "sport_type"),
                    _float_or_none(row.get("duration_min")),
                    _float_or_none(row.get("moving_duration_min")),
                    _float_or_none(row.get("distance_km")),
                    _float_or_none(row.get("time_on_feet_min_est")),
                    _float_or_none(row.get("impact_load_est")),
                    _bool_int(row.get("hard_session_est")),
                    _float_or_none(row.get("calories")),
                    _float_or_none(row.get("avg_hr")),
                    _float_or_none(row.get("max_hr")),
                    _float_or_none(row.get("aerobic_training_effect")),
                    _float_or_none(row.get("anaerobic_training_effect")),
                    _required_text(row, "source_file"),
                    _required_text(row, "quality_flag"),
                    source_sha256,
                    _raw(row),
                )
                for idx, row in enumerate(rows["activities"])
                if _required_text(row, "date")
            ],
        )
        conn.executemany(
            """
            INSERT INTO garmin_sleep_session(
                date, sleep_start_gmt, sleep_end_gmt, total_sleep_min, time_in_bed_min,
                deep_sleep_min, light_sleep_min, rem_sleep_min, awake_min,
                confirmation_type, source_file, quality_flag, source_sha256, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(date, sleep_start_gmt, source_file) DO UPDATE SET
                sleep_end_gmt=excluded.sleep_end_gmt,
                total_sleep_min=excluded.total_sleep_min,
                time_in_bed_min=excluded.time_in_bed_min,
                deep_sleep_min=excluded.deep_sleep_min,
                light_sleep_min=excluded.light_sleep_min,
                rem_sleep_min=excluded.rem_sleep_min,
                awake_min=excluded.awake_min,
                confirmation_type=excluded.confirmation_type,
                quality_flag=excluded.quality_flag,
                source_sha256=excluded.source_sha256,
                raw_json=excluded.raw_json
            """,
            [
                (
                    _required_text(row, "date"),
                    _required_text(row, "sleep_start_gmt"),
                    _required_text(row, "sleep_end_gmt"),
                    _float_or_none(row.get("total_sleep_min")),
                    _float_or_none(row.get("time_in_bed_min")),
                    _float_or_none(row.get("deep_sleep_min")),
                    _float_or_none(row.get("light_sleep_min")),
                    _float_or_none(row.get("rem_sleep_min")),
                    _float_or_none(row.get("awake_min")),
                    _required_text(row, "confirmation_type"),
                    _required_text(row, "source_file"),
                    _required_text(row, "quality_flag"),
                    source_sha256,
                    _raw(row),
                )
                for row in rows["sleep_sessions"]
                if _required_text(row, "date")
            ],
        )
        conn.executemany(
            """
            INSERT INTO garmin_sleep_session_raw(
                source_sha256, source_row_index, date, sleep_start_gmt, sleep_end_gmt, source_file, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_sha256, source_row_index) DO UPDATE SET
                date=excluded.date,
                sleep_start_gmt=excluded.sleep_start_gmt,
                sleep_end_gmt=excluded.sleep_end_gmt,
                source_file=excluded.source_file,
                raw_json=excluded.raw_json
            """,
            [
                (
                    source_sha256,
                    idx,
                    _required_text(row, "date"),
                    _required_text(row, "sleep_start_gmt"),
                    _required_text(row, "sleep_end_gmt"),
                    _required_text(row, "source_file"),
                    _raw(row),
                )
                for idx, row in enumerate(rows["sleep_sessions"])
            ],
        )
        conn.executemany(
            """
            INSERT INTO garmin_daily_wellness(
                date, steps, step_goal, total_distance_km, total_kcal, active_kcal,
                moderate_intensity_min, vigorous_intensity_min, active_min, resting_hr,
                avg_stress, max_stress, hydration_ml, source_file, quality_flag,
                source_sha256, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(date) DO UPDATE SET
                steps=excluded.steps,
                step_goal=excluded.step_goal,
                total_distance_km=excluded.total_distance_km,
                total_kcal=excluded.total_kcal,
                active_kcal=excluded.active_kcal,
                moderate_intensity_min=excluded.moderate_intensity_min,
                vigorous_intensity_min=excluded.vigorous_intensity_min,
                active_min=excluded.active_min,
                resting_hr=excluded.resting_hr,
                avg_stress=excluded.avg_stress,
                max_stress=excluded.max_stress,
                hydration_ml=excluded.hydration_ml,
                source_file=excluded.source_file,
                quality_flag=excluded.quality_flag,
                source_sha256=excluded.source_sha256,
                raw_json=excluded.raw_json
            """,
            [
                (
                    _required_text(row, "date"),
                    _int_or_none(row.get("steps")),
                    _int_or_none(row.get("step_goal")),
                    _float_or_none(row.get("total_distance_km")),
                    _float_or_none(row.get("total_kcal")),
                    _float_or_none(row.get("active_kcal")),
                    _int_or_none(row.get("moderate_intensity_min")),
                    _int_or_none(row.get("vigorous_intensity_min")),
                    _float_or_none(row.get("active_min")),
                    _float_or_none(row.get("resting_hr")),
                    _float_or_none(row.get("avg_stress")),
                    _float_or_none(row.get("max_stress")),
                    _float_or_none(row.get("hydration_ml")),
                    _required_text(row, "source_file"),
                    _required_text(row, "quality_flag"),
                    source_sha256,
                    _raw(row),
                )
                for row in rows["daily_wellness"]
                if _required_text(row, "date")
            ],
        )
        conn.executemany(
            """
            INSERT INTO garmin_training_history(
                date, timestamp, sport, sub_sport, weekly_training_load_sum,
                load_tunnel_min, load_tunnel_max, training_status, fitness_level_trend,
                load_level_trend, source_file, quality_flag, source_sha256, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(date, timestamp, sport, sub_sport) DO UPDATE SET
                weekly_training_load_sum=excluded.weekly_training_load_sum,
                load_tunnel_min=excluded.load_tunnel_min,
                load_tunnel_max=excluded.load_tunnel_max,
                training_status=excluded.training_status,
                fitness_level_trend=excluded.fitness_level_trend,
                load_level_trend=excluded.load_level_trend,
                source_file=excluded.source_file,
                quality_flag=excluded.quality_flag,
                source_sha256=excluded.source_sha256,
                raw_json=excluded.raw_json
            """,
            [
                (
                    _required_text(row, "date"),
                    _required_text(row, "timestamp"),
                    _required_text(row, "sport"),
                    _required_text(row, "sub_sport"),
                    _float_or_none(row.get("weekly_training_load_sum")),
                    _float_or_none(row.get("load_tunnel_min")),
                    _float_or_none(row.get("load_tunnel_max")),
                    _required_text(row, "training_status"),
                    _required_text(row, "fitness_level_trend"),
                    _required_text(row, "load_level_trend"),
                    _required_text(row, "source_file"),
                    _required_text(row, "quality_flag"),
                    source_sha256,
                    _raw(row),
                )
                for row in rows["training_history"]
                if _required_text(row, "date")
            ],
        )
        conn.executemany(
            """
            INSERT INTO garmin_acute_training_load(
                date, timestamp_iso, acwr_percent, acwr_status, daily_training_load_acute,
                daily_training_load_chronic, daily_acwr, source_file, quality_flag,
                source_sha256, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(date, timestamp_iso) DO UPDATE SET
                acwr_percent=excluded.acwr_percent,
                acwr_status=excluded.acwr_status,
                daily_training_load_acute=excluded.daily_training_load_acute,
                daily_training_load_chronic=excluded.daily_training_load_chronic,
                daily_acwr=excluded.daily_acwr,
                source_file=excluded.source_file,
                quality_flag=excluded.quality_flag,
                source_sha256=excluded.source_sha256,
                raw_json=excluded.raw_json
            """,
            [
                (
                    _required_text(row, "date"),
                    _required_text(row, "timestamp_iso"),
                    _float_or_none(row.get("acwr_percent")),
                    _required_text(row, "acwr_status"),
                    _float_or_none(row.get("daily_training_load_acute")),
                    _float_or_none(row.get("daily_training_load_chronic")),
                    _float_or_none(row.get("daily_acwr")),
                    _required_text(row, "source_file"),
                    _required_text(row, "quality_flag"),
                    source_sha256,
                    _raw(row),
                )
                for row in rows["acute_training_load"]
                if _required_text(row, "date")
            ],
        )
        conn.executemany(
            """
            INSERT INTO garmin_body_measurement(
                date, weight_kg_est_from_bmi, body_fat_pct, bmi, rhr,
                chronological_age, current_fitness_age, weight_data_last_entry_date,
                source_file, quality_flag, source_sha256, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(date, source_file, quality_flag) DO UPDATE SET
                weight_kg_est_from_bmi=excluded.weight_kg_est_from_bmi,
                body_fat_pct=excluded.body_fat_pct,
                bmi=excluded.bmi,
                rhr=excluded.rhr,
                chronological_age=excluded.chronological_age,
                current_fitness_age=excluded.current_fitness_age,
                weight_data_last_entry_date=excluded.weight_data_last_entry_date,
                source_sha256=excluded.source_sha256,
                raw_json=excluded.raw_json
            """,
            [
                (
                    _required_text(row, "date"),
                    _float_or_none(row.get("weight_kg_est_from_bmi")),
                    _float_or_none(row.get("body_fat_pct")),
                    _float_or_none(row.get("bmi")),
                    _float_or_none(row.get("rhr")),
                    _float_or_none(row.get("chronological_age")),
                    _float_or_none(row.get("current_fitness_age")),
                    _required_text(row, "weight_data_last_entry_date"),
                    _required_text(row, "source_file"),
                    _required_text(row, "quality_flag"),
                    source_sha256,
                    _raw(row),
                )
                for row in rows["body_measurements"]
            ],
        )
        conn.executemany(
            """
            INSERT INTO garmin_daily_passive_summary(
                date, has_garmin_data, wellness_steps, wellness_resting_hr,
                wellness_avg_stress, wellness_active_kcal, activity_count,
                activity_total_duration_min, activity_total_distance_km,
                activity_total_time_on_feet_min_est, activity_hard_session_count_est,
                sleep_total_sleep_min, sleep_time_in_bed_min, sleep_start_gmt,
                sleep_end_gmt, body_weight_kg_est_from_bmi, body_bmi,
                source_sha256, raw_json, updated_at
            ) VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(date) DO UPDATE SET
                has_garmin_data=1,
                wellness_steps=excluded.wellness_steps,
                wellness_resting_hr=excluded.wellness_resting_hr,
                wellness_avg_stress=excluded.wellness_avg_stress,
                wellness_active_kcal=excluded.wellness_active_kcal,
                activity_count=excluded.activity_count,
                activity_total_duration_min=excluded.activity_total_duration_min,
                activity_total_distance_km=excluded.activity_total_distance_km,
                activity_total_time_on_feet_min_est=excluded.activity_total_time_on_feet_min_est,
                activity_hard_session_count_est=excluded.activity_hard_session_count_est,
                sleep_total_sleep_min=excluded.sleep_total_sleep_min,
                sleep_time_in_bed_min=excluded.sleep_time_in_bed_min,
                sleep_start_gmt=excluded.sleep_start_gmt,
                sleep_end_gmt=excluded.sleep_end_gmt,
                body_weight_kg_est_from_bmi=excluded.body_weight_kg_est_from_bmi,
                body_bmi=excluded.body_bmi,
                source_sha256=excluded.source_sha256,
                raw_json=excluded.raw_json,
                updated_at=excluded.updated_at
            """,
            [
                (
                    _required_text(row, "date"),
                    _int_or_none(row.get("wellness_steps")),
                    _float_or_none(row.get("wellness_resting_hr")),
                    _float_or_none(row.get("wellness_avg_stress")),
                    _float_or_none(row.get("wellness_active_kcal")),
                    _int_or_none(row.get("activity_activity_count")),
                    _float_or_none(row.get("activity_total_duration_min")),
                    _float_or_none(row.get("activity_total_distance_km")),
                    _float_or_none(row.get("activity_total_time_on_feet_min_est")),
                    _int_or_none(row.get("activity_hard_session_count_est")),
                    _float_or_none(row.get("sleep_total_sleep_min")),
                    _float_or_none(row.get("sleep_time_in_bed_min")),
                    _required_text(row, "sleep_sleep_start_gmt"),
                    _required_text(row, "sleep_sleep_end_gmt"),
                    _float_or_none(row.get("body_weight_kg_est_from_bmi")),
                    _float_or_none(row.get("body_bmi")),
                    source_sha256,
                    _raw(row),
                    now,
                )
                for row in rows["daily_joined_summary"]
                if _required_text(row, "date")
            ],
        )

        if "source_manifest" in optional_rows:
            conn.executemany(
                """
                INSERT INTO garmin_source_manifest(
                    source_sha256, path, size_bytes, compressed_size_bytes, modified, kind
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_sha256, path) DO UPDATE SET
                    size_bytes=excluded.size_bytes,
                    compressed_size_bytes=excluded.compressed_size_bytes,
                    modified=excluded.modified,
                    kind=excluded.kind
                """,
                [
                    (
                        source_sha256,
                        _required_text(row, "path"),
                        _int_or_none(row.get("size_bytes")),
                        _int_or_none(row.get("compressed_size_bytes")),
                        _required_text(row, "modified"),
                        _required_text(row, "kind"),
                    )
                    for row in optional_rows["source_manifest"]
                    if _required_text(row, "path")
                ],
            )
        if "uploaded_files_manifest" in optional_rows:
            conn.executemany(
                """
                INSERT INTO garmin_uploaded_files_manifest(
                    source_sha256, outer_zip, path, size_bytes, kind
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(source_sha256, outer_zip, path) DO UPDATE SET
                    size_bytes=excluded.size_bytes,
                    kind=excluded.kind
                """,
                [
                    (
                        source_sha256,
                        _required_text(row, "outer_zip"),
                        _required_text(row, "path"),
                        _int_or_none(row.get("size_bytes")),
                        _required_text(row, "kind"),
                    )
                    for row in optional_rows["uploaded_files_manifest"]
                    if _required_text(row, "outer_zip") and _required_text(row, "path")
                ],
            )

        conn.execute(
            """
            INSERT INTO garmin_import_batch(
                source_sha256, source_path, imported_at, row_counts_json, date_min, date_max
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_sha256) DO UPDATE SET
                source_path=excluded.source_path,
                imported_at=excluded.imported_at,
                row_counts_json=excluded.row_counts_json,
                date_min=excluded.date_min,
                date_max=excluded.date_max
            """,
            (
                source_sha256,
                str(source_path),
                now,
                json.dumps(row_counts, sort_keys=True),
                min(dates) if dates else "",
                max(dates) if dates else "",
            ),
        )

    store.append_audit_event(
        "garmin_export_imported",
        {
            "source_sha256": source_sha256,
            "source_path": str(source_path),
            "row_counts": row_counts,
            "date_min": min(dates) if dates else "",
            "date_max": max(dates) if dates else "",
        },
    )
    return {
        "schema_version": "garmin_import_result_v1",
        "source_sha256": source_sha256,
        "source_path": str(source_path),
        "row_counts": row_counts,
        "date_min": min(dates) if dates else "",
        "date_max": max(dates) if dates else "",
    }


def main(argv: list[str] | None = None) -> int:
    import sys

    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        raise SystemExit("usage: python -m life_load.garmin_import <garmin_export.zip> [repo_root]")
    zip_path = Path(args[0])
    repo_root = Path(args[1]) if len(args) > 1 else Path.cwd()
    result = import_garmin_export_zip(HealthObservabilityStore(repo_root=repo_root), zip_path)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
