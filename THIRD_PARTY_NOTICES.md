# Third-party notices

First-party code/tests: MIT, Copyright (c) 2026 Jean-Francois Dufour. First-party launcher vector/source resources are retained; original branding PNGs, diary datasets and private research documents are excluded.

The Gradle 8.9 launcher and official wrapper JAR retain upstream Apache-2.0 terms; the complete license is at third_party/gradle/LICENSE. The wrapper is checksum verified and the distribution SHA-256 is pinned in gradle-wrapper.properties. No SDK, dependency cache, downloaded library JAR/AAR, Python wheel or APK is bundled.

Python dependencies and build/test tools are referenced with exact wheel hashes. Full upstream license/copyright texts are retained under third_party/<package>/. These texts do not relicense those packages.

| Package | Version | License |
| --- | --- | --- |
| cffi | 2.1.1 | MIT-0 |
| cryptography | 46.0.7 | Apache-2.0 OR BSD-3-Clause |
| iniconfig | 2.3.1 | MIT |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause |
| pluggy | 1.6.0 | MIT |
| pycparser | 3.11 | BSD-3-Clause |
| pygments | 2.21.0 | BSD-2-Clause |
| pytest | 9.0.2 | MIT |
| setuptools | 84.0.0 | MIT |
| wheel | 0.48.0 | MIT |

AndroidX/Compose, Kotlin/coroutines and OkHttp are externally resolved under Apache-2.0 terms. JVM/instrumentation tests reference JUnit (EPL-1.0), Robolectric (MIT), JSON-java (public domain), and other external dependencies. Gradle's app lockfile pins 168 resolved coordinates for the documented debug/test configurations; private evidence reviews their actual POM metadata. Missing/inherited POM notices are not a blanket binary-redistribution clearance. Before distributing a built app, review the exact resulting binary, embedded library notices and source obligations independently. This release distributes source and its official wrapper only.
