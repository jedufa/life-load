<div align="center">

# 🌿 Life Load

### Some days feel heavier. Start noticing why.

**A small space to check in with yourself, and a transparent model to explore the patterns behind everyday load.**

**Notice · Record · Reflect**

[**See the Android experience ↓**](#a-look-inside) &nbsp;·&nbsp; [**Try the Python demo →**](#explore-the-scoring-model) &nbsp;·&nbsp; [**Build the Android app →**](#build-the-android-prototype)

<br>

![Android](https://img.shields.io/badge/Android-Kotlin%20%2B%20Compose-3d795c?style=flat-square)
![Backend](https://img.shields.io/badge/Python-explainable%20scoring-3776ab?style=flat-square)
![Privacy](https://img.shields.io/badge/demo-local--first-456069?style=flat-square)
![MIT](https://img.shields.io/badge/license-MIT-24836b?style=flat-square)

</div>

---

## A look inside

**Four moments from the real Android prototype.**

<table>
  <tr>
    <td align="center" width="50%">
      <a href="docs/screenshots/onboarding.png"><img src="docs/screenshots/onboarding.png" alt="Actual Android emulator capture showing General Balance onboarding" width="325"></a>
    </td>
    <td align="center" width="50%">
      <a href="docs/screenshots/checkin.png"><img src="docs/screenshots/checkin.png" alt="Actual Android emulator capture showing a fictional sleep and nutrition check-in" width="325"></a>
    </td>
  </tr>
  <tr>
    <td align="center"><strong>01 · Choose your focus</strong><br><sub>Begin with the generic General Balance profile.</sub></td>
    <td align="center"><strong>02 · Check in</strong><br><sub>Record a few signals without pretending to know everything.</sub></td>
  </tr>
  <tr>
    <td align="center">
      <a href="docs/screenshots/saved.png"><img src="docs/screenshots/saved.png" alt="Actual Android emulator capture confirming locally stored pending check-in" width="325"></a>
    </td>
    <td align="center">
      <a href="docs/screenshots/interpretation.png"><img src="docs/screenshots/interpretation.png" alt="Actual Android emulator capture explaining why guidance is unavailable without approved history" width="325"></a>
    </td>
  </tr>
  <tr>
    <td align="center"><strong>03 · Keep your history local</strong><br><sub>Pending entries survive an application restart.</sub></td>
    <td align="center"><strong>04 · See the uncertainty</strong><br><sub>Insufficient data is a real answer, not a reason to invent a score.</sub></td>
  </tr>
</table>

<sub>All four images are authentic API 35 Android emulator screenshots using fictional inputs, not concept renders or real personal records.</sub>

> **An important boundary:** The Android demo saves **pending** local check-ins. It does **not** generate approved daily scores or populated weekly guidance. The Python demo separately demonstrates canonical approval and scoring in its own SQLite database. **They are not synchronized in this release.**

---

## Why Life Load exists

A poor night's sleep, a stressful day, or the feeling that your energy has run out can be easy to notice in isolation. Seeing how several everyday signals fit together is harder.

Life Load explores a simple idea: **make the inputs visible, make the rules inspectable, and never treat missing information as certainty.**

| | |
|:--|:--|
| **🧭 Start with a profile** | Use the generic General Balance configuration rather than somebody else's personal setup. |
| **📝 Make a small check-in** | Record what you know about the day and leave genuinely missing information missing. |
| **🏡 Keep the prototype local** | Save pending Android entries on the device and delete them through the privacy controls. |
| **🔍 See how the model reasons** | Inspect the independent Python scoring engine, its component contributions and deterministic examples. |

**Life Load is a software and self-reflection experiment, not a medical device.** Its scoring model is not clinically validated and cannot diagnose, treat or predict a health condition.

## Two real demonstrations, two different boundaries

<table>
<tr>
<td width="50%" valign="top">

### 📱 Android
**A local check-in experience**

Open a native Compose app, select General Balance, enter fictional sleep/nutrition information, save it, restart, and delete it through Settings.

- Native Kotlin / Jetpack Compose
- Local SQLite/preferences
- Pending entries, not approved scores
- No Internet permission in the tested Android build

[**Build Android →**](#build-the-android-prototype)

</td>
<td width="50%" valign="top">

### 🧮 Python
**A transparent scoring experiment**

Create a synthetic check-in, approve it through the backend contract, calculate its compatibility score and reasons, then confirm persistence in SQLite.

- Real first-party scoring logic
- Inspectable contract and golden cases
- Independent local database
- No provider, account or hosted service required

[**Try Python →**](#explore-the-scoring-model)

</td>
</tr>
</table>

These paths are intentionally described separately. The Android UI does **not** silently borrow evidence from the Python-only workflow.

## Explore the scoring model

The simplest technical entry point is the deterministic Python example.

**Requirements:** Python 3.11+ declared; Linux / Python 3.14.4 actually verified.

```sh
git clone https://github.com/jedufa/life-load.git
cd life-load
python3 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements-dev.txt
.venv/bin/python -m pip install --no-build-isolation --no-deps .
.venv/bin/python -m life_load.demo --state-root runtime/synthetic-demo
```

The demonstration uses fictional data, creates a generic profile, saves an approved backend check-in and prints the **actual compatibility score and reasons**. It does not access your diary, connect to Garmin, or configure the Android app.

[Explore the scoring implementation →](app/backend/life_load/) &nbsp;·&nbsp; [Read the build and test guide →](docs/BUILD_AND_TEST.md)

## Build the Android prototype

**Requirements:** Java 17, Android SDK 35, build tools 34.0.0 and the included Gradle 8.9 wrapper.

```sh
cd app/mobile/android
./gradlew --no-daemon :app:assembleDebug :app:testDebugUnitTest :app:assembleDebugAndroidTest
```

Install the generated **debug** APK on a disposable emulator, then follow the check-in, restart and privacy-deletion workflow documented in [BUILD_AND_TEST.md](docs/BUILD_AND_TEST.md).

No APK, app-store listing, or signed production application is provided in this GitHub release.

## Built to be questioned

**This is more than a collection of screens.** The published source retains extensive regression tests and reproducibility checks.

| Verified engineering check | Reported result |
|:--|--:|
| Python tests | **525 passed** |
| Android JVM tests | **350 passed** |
| Real Android instrumentation methods | **2 passed** |
| Fresh wheel/resource installation | **Passed** |
| Check-in persistence and deletion, cross-checked via SQLite | **Passed** |

The Android tests exercised real Compose controls on an API 35 emulator. A fresh Python install independently verified synthetic approval, score computation, and storage. The release reports no percentage coverage, clinical validation or production security certification.

[Technical validation →](docs/BUILD_AND_TEST.md) &nbsp;·&nbsp; [Release history →](CHANGELOG.md)

## Private by design, with honest limits

The verified Android variant has **no Internet permission** and no account is required for the demonstrated offline flow. The repository excludes real diaries, historic research datasets, original personal records and private Git history.

However, ordinary SQLite/preferences and local Python files are **not an encrypted vault**. Optional Garmin, AI/Codex extraction, cloud storage and other integration code is experimental, not part of the verified demo.

**Not yet demonstrated:** physical-device behavior, reminders and permissions, full Android approval/scoring/sync, real providers, export/import round trips, clinical efficacy, or production hosting.

[Security and privacy notes →](SECURITY.md)

## Continue the experiment

Life Load is an **experimental, source-only project** shared so others can study the models, question the assumptions, adapt the UI or carry the work further.

The project is **unmaintained and looking for a maintainer**. Independent forks are welcome; issues, pull-request review, security updates and future releases are not guaranteed.

[**Fork Life Load →**](https://github.com/jedufa/life-load/fork) &nbsp;·&nbsp; [**Contributing guide →**](CONTRIBUTING.md) &nbsp;·&nbsp; [**Source prerelease →**](https://github.com/jedufa/life-load/releases/tag/v0.1.2-oss.1)

First-party code and tests: **[MIT License](LICENSE)** · Copyright © 2026 Jean-Francois Dufour. [Third-party notices](THIRD_PARTY_NOTICES.md) retain their original terms.

---

<div align="center">

### A clearer picture begins with a small check-in.

*Understand your load. Notice your patterns.*

</div>
