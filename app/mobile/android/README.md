# Life Load Android

Native Android prototype for the Life Load daily closeout flow.

Current migration boundary:
- The installed app package is `com.life.lifeload.debug` for debug builds.
- The runtime app surface is Life Load-only.
- The Kotlin namespace is `com.life.lifeload`.
- The copied chat/admin/backlog source from the incubator app has been removed.

## Defaults

- Platform: Android
- Stack: Kotlin + Jetpack Compose
- Min SDK: 26
- Debug server base URL default: `http://127.0.0.1:8797`
- Trusted-demo/release server base URL default: `https://life-load-demo.invalid`
- Main-app backup/data extraction: disabled by manifest.
- Cleartext traffic: allowed only for debug builds; trusted-demo and release builds disable cleartext unless the build is reconfigured and re-reviewed.

Build-time configuration uses `LIFE_LOAD_*` properties:

```bash
./gradlew :app:assembleDebug \
  -PLIFE_LOAD_SERVER_BASE_URL=http://127.0.0.1:8797 \
  -PLIFE_LOAD_AUTH_TOKEN= \
  -PLIFE_LOAD_APP_VERSION_CODE=1 \
  -PLIFE_LOAD_APP_VERSION_NAME=0.1.2-dev
```

## Build

From this directory:

```bash
./gradlew :app:testDebugUnitTest
./gradlew :app:assembleDebug
./gradlew :app:assembleTrustedDemo
```

From the repo root, the developer APK builder publishes artifacts for the mobile update page:

```bash
developer/mobile/build_server_apk.sh debug
```

Published APKs are written under:

```text
runtime/artifacts/mobile_apk/
```

## Trusted Demo Build

The trusted-demo build uses the debug signing key for installability but has external-build network defaults:

```bash
./gradlew :app:assembleTrustedDemo
```

To test against a local backend, pass an explicit URL:

```bash
./gradlew :app:assembleTrustedDemo \
  -PLIFE_LOAD_SERVER_BASE_URL=https://your-reviewed-demo-host.example
```

Do not ship a trusted-demo build pointed at raw public HTTP.

## Signed Release Build

Signing uses `LIFE_LOAD_RELEASE_*`.
Do not commit keystores or secrets.

```bash
export LIFE_LOAD_RELEASE_STORE_FILE=/absolute/path/to/keystore.jks
export LIFE_LOAD_RELEASE_STORE_PASSWORD='***'
export LIFE_LOAD_RELEASE_KEY_ALIAS='***'
export LIFE_LOAD_RELEASE_KEY_PASSWORD='***'

./gradlew :app:assembleRelease \
  -PLIFE_LOAD_SERVER_BASE_URL=https://your-reviewed-release-host.example
```
