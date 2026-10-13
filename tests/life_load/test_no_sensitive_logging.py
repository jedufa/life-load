from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
ANDROID_MAIN = REPO_ROOT / "app" / "mobile" / "android" / "app" / "src" / "main" / "java"
DEVELOPER_SERVER = REPO_ROOT / "developer" / "server" / "app.py"
ANDROID_GRADLE = REPO_ROOT / "app" / "mobile" / "android" / "app" / "build.gradle.kts"


def test_android_logging_goes_through_app_logger() -> None:
    offenders: list[str] = []
    for path in ANDROID_MAIN.rglob("*.kt"):
        if path.name == "AppLogger.kt":
            continue
        text = path.read_text(encoding="utf-8")
        if "android.util.Log" in text or "Log." in text or "println(" in text:
            offenders.append(str(path.relative_to(REPO_ROOT)))

    assert offenders == []


def test_app_logger_does_not_pass_raw_throwable_to_logcat() -> None:
    text = (ANDROID_MAIN / "com" / "life" / "lifeload" / "util" / "AppLogger.kt").read_text(encoding="utf-8")

    assert "Log.e(TAG, message, t)" not in text
    assert "Log.w(TAG, message, t)" not in text
    assert "Log.i(TAG, message, t)" not in text
    assert "sanitizeForLog(stackTrace(it))" in text


def test_app_logger_knows_local_first_sensitive_keys() -> None:
    text = (ANDROID_MAIN / "com" / "life" / "lifeload" / "util" / "AppLogger.kt").read_text(encoding="utf-8")

    for key in (
        "entry_json",
        "payload_json",
        "raw_json",
        "structured_json",
        "family_stress",
        "garmin_email",
    ):
        assert key in text




def test_android_has_no_crash_reporting_sdk_enabled() -> None:
    text = ANDROID_GRADLE.read_text(encoding="utf-8").lower()

    forbidden_dependencies = (
        "firebase-crashlytics",
        "com.google.firebase.crashlytics",
        "sentry-android",
        "bugsnag",
    )
    for dependency in forbidden_dependencies:
        assert dependency not in text
