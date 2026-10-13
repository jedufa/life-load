# Build and test

Experimental Android/Python source prerelease. Verified Linux/Python 3.14.4, Temurin Java 17.0.18, Android SDK 35/build tools 34.0.0, Gradle 8.9, AGP 8.5.2, Kotlin 1.9.24; the declared Python 3.11 minimum is not separately tested. A debug build is development output, not a signed production release.

Use the exact README setup. Test dependencies/build tools are pinned with wheel SHA-256 hashes; runtime cryptography/cffi/pycparser pins are also in requirements-runtime.txt. The app wheel includes all three adjacent JSON resources. Optional `object-store`, `garmin` and `postgres` extras are unverified and unnecessary for the default demo. No system services or original runtime state are required.

525 Python tests pass, including ten scoring-contract tests. The initial reduced-scope run had 518 passes and ten failures tied to omitted private documentation/server/intent-closeout surfaces or absent historical research ZIPs. Two structural whole-repo test files are omitted; the private intent-report helper and its two tests, plus two static doc/developer-server assertions, are excluded. Four archive tests now generate independent synthetic fixtures; report writers use their own temp paths. Scoring/guidance thresholds were not weakened.

All 350 original applicable Android JVM tests pass. Three expectations were adapted from disabled personal defaults to the intentional enabled generic beta profile. Root ignore rules are anchored so Kotlin packages named `data` remain tracked. The first native snapshot failure and all retry logs are retained privately. Native launcher APIs have deprecation warnings; these do not establish future SDK compatibility.

## Real Android workflow

On a new disposable API 35 emulator only, build/install the app and test APKs. Do not run this fixture against a phone containing real data. Select the explicit emulator serial; clear only its disposable Life Load app before the first method.

```sh
adb -s <disposable-emulator> install -r -t app/build/outputs/apk/debug/app-debug.apk
adb -s <disposable-emulator> install -r -t app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk
adb -s <disposable-emulator> shell pm clear com.life.lifeload.debug
adb -s <disposable-emulator> shell am instrument -w -r -e class 'com.life.lifeload.ui.OpenSourceLocalWorkflowInstrumentedTest#createSyntheticCheckIn' com.life.lifeload.debug.test/androidx.test.runner.AndroidJUnitRunner
adb -s <disposable-emulator> shell am force-stop com.life.lifeload.debug
adb -s <disposable-emulator> shell am instrument -w -r -e class 'com.life.lifeload.ui.OpenSourceLocalWorkflowInstrumentedTest#verifyRestartAndDeleteThroughUi' com.life.lifeload.debug.test/androidx.test.runner.AndroidJUnitRunner
```

Both methods drive actual Compose controls and independently inspect SQLite. The first starts with no saved entries, selects General Balance, stores sleep/nutrition choices, checks pending outbox/empty canonical score, and captures actual native screens including dialogs. The second verifies persistence across a separate application process, then presses the expanded Privacy delete/confirm controls and checks empty storage/outbox. Private host-side SQLite copies independently verify persisted consequences. Check `OK (1 test)` and instrumentation success, not ADB exit status alone.

These are bounded synthetic Screen-to-Store engineering checks, not clinical validation or full device Qualification. Physical-device permissions, reminder delivery, pickers/export round trips, full native approved scoring/sync, real integrations and production security remain unverified. Coverage percentage is not measured. The native offline screen truthfully shows guidance pending/insufficient approved history; the Python demo computes a canonical compatibility score separately.
