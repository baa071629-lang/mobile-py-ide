plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("com.chaquo.python")
}

val repoRoot: File = rootProject.projectDir.parentFile

/** Les ressources générées vont dans build/, jamais dans src/ (Gradle strict). */
val stagedAssetsDir: File = layout.buildDirectory.dir("stagedAssets").get().asFile
stagedAssetsDir.mkdirs()

/** Interface web (Monaco inclus) copiée dans les assets de l'APK. */
val stageWeb by tasks.registering(Copy::class) {
    from(File(repoRoot, "web")) { into("web") }
    into(stagedAssetsDir)
    includeEmptyDirs = false
}

/** Moteur Python partagé, compressé dans un asset extrait au premier lancement. */
val stagePython by tasks.registering(Zip::class) {
    archiveFileName.set("python-src.zip")
    destinationDirectory.set(stagedAssetsDir)
    from(File(repoRoot, "server")) { into("server") }
    from(File(repoRoot, "pyide_gui.py"))
    from(File(repoRoot, "pyide_native.py"))
    from(File(repoRoot, "sitecustomize.py"))
    includeEmptyDirs = false
}

android {
    namespace = "dev.pyide.mobile"
    compileSdk = 34
    buildToolsVersion = "34.0.0"

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

    sourceSets["main"].assets.srcDir(stagedAssetsDir)

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

tasks.matching {
    (it.name.contains("Assets") || it.name.contains("Python")) &&
        it.name != "stageWeb" && it.name != "stagePython"
}.configureEach { dependsOn(stageWeb, stagePython) }
tasks.named("preBuild") { dependsOn(stageWeb, stagePython) }

dependencies {
    implementation("androidx.webkit:webkit:1.11.0")
    implementation("androidx.core:core-ktx:1.13.1")
}
