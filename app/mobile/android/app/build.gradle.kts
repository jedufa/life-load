import org.gradle.api.tasks.testing.Test

plugins {
  id("com.android.application")
  id("org.jetbrains.kotlin.android")
}

fun projectPropOrEnv(name: String): String? {
  val p = (project.findProperty(name) as String?)?.trim()?.ifBlank { null }
  if (p != null) return p
  val e = System.getenv(name)?.trim()?.ifBlank { null }
  if (e != null) return e
  return null
}

val configuredServerBaseUrl =
  projectPropOrEnv("LIFE_LOAD_SERVER_BASE_URL")

val debugServerBaseUrl =
  configuredServerBaseUrl
    ?: "http://127.0.0.1:1"

val externalServerBaseUrl =
  configuredServerBaseUrl
    ?: "https://life-load-demo.invalid"

val releaseAllowCleartext =
  projectPropOrEnv("LIFE_LOAD_RELEASE_ALLOW_CLEARTEXT") == "true"

val authToken =
  projectPropOrEnv("LIFE_LOAD_AUTH_TOKEN")
    ?: ""

val explicitAppVersionCode =
  projectPropOrEnv("LIFE_LOAD_APP_VERSION_CODE")
    ?.toIntOrNull()

val explicitAppVersionName =
  projectPropOrEnv("LIFE_LOAD_APP_VERSION_NAME")

val profileSetupEnabled =
  projectPropOrEnv("LIFE_LOAD_PROFILE_SETUP_ENABLED") != "false"

val profileOnboardingEnabled =
  projectPropOrEnv("LIFE_LOAD_PROFILE_ONBOARDING_ENABLED") != "false"

val profileDrivenCheckInEnabled =
  projectPropOrEnv("LIFE_LOAD_PROFILE_DRIVEN_CHECKIN_ENABLED") != "false"

val lifeLoadBuildMode =
  projectPropOrEnv("LIFE_LOAD_BUILD_MODE")
    ?: if (profileSetupEnabled && profileOnboardingEnabled && profileDrivenCheckInEnabled) "beta_review" else "personal_legacy"

val defaultProfileId =
  projectPropOrEnv("LIFE_LOAD_DEFAULT_PROFILE_ID")
    ?: if (lifeLoadBuildMode == "beta_review") "general_balance" else "personal_legacy"

android {
  namespace = "com.life.lifeload"
  compileSdk = 35

  defaultConfig {
    applicationId = "com.life.lifeload"
    minSdk = 26
    targetSdk = 35
    versionCode = explicitAppVersionCode ?: 1
    versionName = explicitAppVersionName ?: "0.1.2"

    testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    buildConfigField("String", "SERVER_BASE_URL", "\"${externalServerBaseUrl.replace("\"", "\\\"")}\"")
    buildConfigField("String", "AUTH_TOKEN", "\"${authToken.replace("\"", "\\\"")}\"")
    buildConfigField("boolean", "LIFE_LOAD_PROFILE_SETUP_ENABLED", profileSetupEnabled.toString())
    buildConfigField("boolean", "LIFE_LOAD_PROFILE_ONBOARDING_ENABLED", profileOnboardingEnabled.toString())
    buildConfigField("boolean", "LIFE_LOAD_PROFILE_DRIVEN_CHECKIN_ENABLED", profileDrivenCheckInEnabled.toString())
    buildConfigField("String", "LIFE_LOAD_BUILD_MODE", "\"${lifeLoadBuildMode.replace("\"", "\\\"")}\"")
    buildConfigField("String", "LIFE_LOAD_DEFAULT_PROFILE_ID", "\"${defaultProfileId.replace("\"", "\\\"")}\"")
    manifestPlaceholders["lifeLoadAllowBackup"] = "false"
    manifestPlaceholders["lifeLoadUsesCleartextTraffic"] = "false"
  }

  val releaseStoreFile =
    projectPropOrEnv("LIFE_LOAD_RELEASE_STORE_FILE")
  val releaseStorePassword =
    projectPropOrEnv("LIFE_LOAD_RELEASE_STORE_PASSWORD")
  val releaseKeyAlias =
    projectPropOrEnv("LIFE_LOAD_RELEASE_KEY_ALIAS")
  val releaseKeyPassword =
    projectPropOrEnv("LIFE_LOAD_RELEASE_KEY_PASSWORD")
  val hasReleaseSigning =
    !releaseStoreFile.isNullOrBlank() &&
      !releaseStorePassword.isNullOrBlank() &&
      !releaseKeyAlias.isNullOrBlank() &&
      !releaseKeyPassword.isNullOrBlank()

  signingConfigs {
    if (hasReleaseSigning) {
      create("release") {
        storeFile = file(releaseStoreFile!!)
        storePassword = releaseStorePassword
        keyAlias = releaseKeyAlias
        keyPassword = releaseKeyPassword
      }
    }
  }

  buildTypes {
    debug {
      applicationIdSuffix = ".debug"
      buildConfigField("String", "SERVER_BASE_URL", "\"${debugServerBaseUrl.replace("\"", "\\\"")}\"")
      manifestPlaceholders["lifeLoadUsesCleartextTraffic"] = "true"
      if (explicitAppVersionName == null) {
        versionNameSuffix = "-debug"
      }
    }
    create("trustedDemo") {
      initWith(getByName("debug"))
      applicationIdSuffix = ".trusted"
      isDebuggable = false
      signingConfig = signingConfigs.getByName("debug")
      matchingFallbacks += listOf("debug")
      buildConfigField("String", "SERVER_BASE_URL", "\"${externalServerBaseUrl.replace("\"", "\\\"")}\"")
      manifestPlaceholders["lifeLoadAllowBackup"] = "false"
      manifestPlaceholders["lifeLoadUsesCleartextTraffic"] = "false"
      if (explicitAppVersionName == null) {
        versionNameSuffix = "-trusted-demo"
      }
    }
    release {
      isMinifyEnabled = false
      buildConfigField("String", "SERVER_BASE_URL", "\"${externalServerBaseUrl.replace("\"", "\\\"")}\"")
      manifestPlaceholders["lifeLoadAllowBackup"] = "false"
      // Explicitly opt-in only for an internal LAN release bound to a private HTTP host.
      manifestPlaceholders["lifeLoadUsesCleartextTraffic"] = releaseAllowCleartext.toString()
      if (hasReleaseSigning) {
        signingConfig = signingConfigs.getByName("release")
      }
      proguardFiles(
        getDefaultProguardFile("proguard-android-optimize.txt"),
        "proguard-rules.pro",
      )
    }
  }

  compileOptions {
    sourceCompatibility = JavaVersion.VERSION_17
    targetCompatibility = JavaVersion.VERSION_17
  }
  kotlinOptions {
    jvmTarget = "17"
  }
  buildFeatures {
    compose = true
    buildConfig = true
  }
  composeOptions {
    kotlinCompilerExtensionVersion = "1.5.14"
  }
  packaging {
    resources {
      excludes += "/META-INF/{AL2.0,LGPL2.1}"
    }
  }

  testOptions {
    unitTests {
      isIncludeAndroidResources = true
    }
  }
}

dependencies {
  val composeBom = platform("androidx.compose:compose-bom:2024.09.01")

  implementation(composeBom)
  androidTestImplementation(composeBom)

  implementation("androidx.core:core-ktx:1.13.1")
  implementation("androidx.activity:activity-compose:1.9.2")
  implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.5")
  implementation("androidx.lifecycle:lifecycle-runtime-compose:2.8.5")
  implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.8.5")
  implementation("androidx.compose.ui:ui")
  implementation("androidx.compose.ui:ui-tooling-preview")
  implementation("androidx.compose.material3:material3")
  implementation("androidx.compose.material:material-icons-extended")
  implementation("androidx.compose.foundation:foundation")
  implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.8.1")
  implementation("com.squareup.okhttp3:okhttp:4.12.0")

  debugImplementation("androidx.compose.ui:ui-tooling")
  debugImplementation("androidx.compose.ui:ui-test-manifest")

  testImplementation("junit:junit:4.13.2")
  testImplementation("org.jetbrains.kotlinx:kotlinx-coroutines-test:1.8.1")
  testImplementation("com.squareup.okhttp3:mockwebserver:4.12.0")
  testImplementation("org.json:json:20240303")
  testImplementation("org.robolectric:robolectric:4.12.1")
  testImplementation("androidx.test:core-ktx:1.6.1")
  testImplementation(composeBom)
  testImplementation("androidx.compose.ui:ui-test-junit4")
  testImplementation("androidx.compose.ui:ui-test-manifest")

  androidTestImplementation("androidx.test.ext:junit:1.2.1")
  androidTestImplementation("androidx.test.espresso:espresso-core:3.6.1")
  androidTestImplementation("androidx.compose.ui:ui-test-junit4")
}

tasks.withType<Test>().configureEach {
  if (name == "testReleaseUnitTest") {
    // These Compose host-activity tests run under debug with ui-test-manifest.
    exclude("com/life/lifeload/ProfileDrivenCheckInRendererTest.class")
    exclude("com/life/lifeload/ProfileSetupUxTest.class")
  }
}

// Lock dependencies resolved by the documented debug build and tests.
dependencyLocking { lockAllConfigurations() }
