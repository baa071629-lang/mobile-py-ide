plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("com.chaquo.python")
}

val repoRoot: File = rootProject.projectDir.parentFile

// Les ressources générées restent dans build/ (jamais dans src/, Gradle strict).
val stagedAssets = layout.buildDirectory.dir("stagedAssets")

val stageWeb = tasks.register<Copy>("stageWebAssets") {
    from(File(repoRoot, "web")) { into("web") }
    into(stagedAssets)
    includeEmptyDirs = false
}

// Moteur Python partagé, livré en asset puis extrait au premier lancement.
val stagePython = tasks.register<Zip>("stagePythonSources") {
    archiveFileName.set("python-src.zip")
    destinationDirectory.set(stagedAssets)
    from(File(repoRoot, "server")) { into("server") }
    from(File(repoRoot, "pyide_gui.py"))
    from(File(repoRoot, "pyide_native.py"))
    from(File(repoRoot, "sitecustomize.py"))
    includeEmptyDirs = false
}

android {
    namespace = "dev.pyide.mobile"
    compileSdk = 34

    defaultConfig {
        applicationId = "dev.pyide.mobile"
        minSdk = 26
        targetSdk = 34
        versionCode = 300
        versionName = "3.0.0"

        ndk {
            abiFilters += listOf("arm64-v8a", "x86_64")
        }
    }

    sourceSets["main"].assets.srcDir(stagedAssets)

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }

    buildTypes {
        getByName("debug") {
            isMinifyEnabled = false
            applicationIdSuffix = ".debug"
            versionNameSuffix = "-debug"
        }
        getByName("release") {
            isMinifyEnabled = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
            )
        }
    }

    packaging {
        resources.excludes += setOf("META-INF/AL2.0", "META-INF/LGPL2.1")
    }

    lint {
        abortOnError = false
    }
}

chaquopy {
    defaultConfig {
        version = "3.11"
        buildPython("python3.11")
        pip {
            install("jedi")
            install("pyflakes")
            install("autopep8")
        }
    }
}

tasks.named("preBuild") { dependsOn(stageWeb, stagePython) }

dependencies {
    implementation("androidx.webkit:webkit:1.11.0")
    implementation("androidx.core:core-ktx:1.13.1")
}
