package dev.pyide.mobile

import android.Manifest
import android.app.Activity
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Environment
import android.provider.Settings
import android.view.View
import android.view.WindowManager
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.webkit.WebViewAssetLoader
import com.chaquo.python.PyObject
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import org.json.JSONObject
import java.io.File
import java.io.FileOutputStream
import java.util.zip.ZipInputStream

/**
 * Activité unique : elle héberge une WebView qui affiche l'interface de l'IDE
 * et démarre l'interpréteur Python embarqué (Chaquopy).
 */
class MainActivity : Activity() {

    private lateinit var webView: WebView
    private var bridge: PyBridge? = null
    private var pendingPurpose = "files"

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)

        if (!Python.isStarted()) {
            Python.start(AndroidPlatform(applicationContext))
        }

        webView = WebView(this)
        webView.setBackgroundColor(0xFF1E1E2E.toInt())
        setContentView(webView)
        configureWebView()

        val module = startPythonBridge()
        val info = JSONObject()
            .put("filesDir", filesDir.absolutePath)
            .put("cacheDir", cacheDir.absolutePath)
            .put("storage", storageRoot())
            .put("version", versionName())
        module.callAttr("init", info.toString())

        bridge = PyBridge(this, webView, module)
        webView.addJavascriptInterface(bridge as PyBridge, "PyAndroid")
        webView.loadUrl("https://appassets.androidplatform.net/assets/web/index.html")
    }

    /** Extrait le moteur Python livré en asset puis charge le pont. */
    private fun startPythonBridge(): PyObject {
        val home = File(filesDir, "pycode")
        home.mkdirs()
        try {
            assets.open("python-src.zip").use { raw ->
                ZipInputStream(raw).use { zip ->
                    var entry = zip.nextEntry
                    while (entry != null) {
                        val target = File(home, entry.name)
                        if (entry.isDirectory) {
                            target.mkdirs()
                        } else {
                            target.parentFile?.mkdirs()
                            FileOutputStream(target).use { output -> zip.copyTo(output) }
                        }
                        zip.closeEntry()
                        entry = zip.nextEntry
                    }
                }
            }
        } catch (error: Exception) {
            android.util.Log.e("PyIDE", "Extraction du moteur Python impossible", error)
        }
        val bootstrap = Python.getInstance().getModule("pyide_bootstrap")
        return bootstrap.callAttr("prepare", home.absolutePath)
    }

    private fun configureWebView() {
        val assetLoader = WebViewAssetLoader.Builder()
            .addPathHandler("/assets/", WebViewAssetLoader.AssetsPathHandler(this))
            .build()

        webView.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            databaseEnabled = true
            allowFileAccess = false
            allowContentAccess = false
            cacheMode = WebSettings.LOAD_DEFAULT
            mediaPlaybackRequiresUserGesture = false
            setSupportZoom(false)
            textZoom = 100
        }

        WebView.setWebContentsDebuggingEnabled(true)

        webView.webViewClient = object : WebViewClient() {
            override fun shouldInterceptRequest(
                view: WebView,
                request: WebResourceRequest,
            ): WebResourceResponse? {
                val response = assetLoader.shouldInterceptRequest(request.url)
                if (response != null) return response
                val url = request.url.toString()
                if (url.startsWith("https://appassets.androidplatform.net/")) return null
                // Lien externe : ouvre le navigateur plutôt que de casser l'IDE.
                try {
                    startActivity(Intent(Intent.ACTION_VIEW, request.url))
                } catch (_: Exception) {
                }
                return WebResourceResponse("text/plain", "utf-8", 204, "No Content", null, null)
            }

            override fun onPageFinished(view: WebView?, url: String?) {
                super.onPageFinished(view, url)
                bridge?.onPageReady()
            }
        }
        webView.setOnLongClickListener { true }
        webView.overScrollMode = View.OVER_SCROLL_NEVER
    }

    override fun onResume() {
        super.onResume()
        bridge?.notifyResume()
    }

    override fun onBackPressed() {
        webView.evaluateJavascript(
            "(function(){ if (window.PyIdeBack && window.PyIdeBack()) return '1'; return '0'; })()",
        ) { result ->
            if (result != "1") finish()
        }
    }

    /* ---------- stockage ---------- */

    fun storageRoot(): String {
        val external = Environment.getExternalStorageDirectory()
        return if (external != null && external.canRead()) external.absolutePath else ""
    }

    fun ensureStoragePermission() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            if (Environment.isExternalStorageManager()) return
            try {
                startActivity(
                    Intent(
                        Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION,
                        Uri.parse("package:$packageName"),
                    ),
                )
            } catch (_: Exception) {
                try {
                    startActivity(Intent(Settings.ACTION_MANAGE_ALL_FILES_ACCESS_PERMISSION))
                } catch (_: Exception) {
                }
            }
            return
        }
        val missing = mutableListOf<String>()
        for (permission in listOf(
            Manifest.permission.READ_EXTERNAL_STORAGE,
            Manifest.permission.WRITE_EXTERNAL_STORAGE,
        )) {
            if (checkSelfPermission(permission) != PackageManager.PERMISSION_GRANTED) {
                missing.add(permission)
            }
        }
        if (missing.isNotEmpty()) {
            requestPermissions(missing.toTypedArray(), REQUEST_STORAGE)
        }
    }

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<out String>,
        grantResults: IntArray,
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == REQUEST_STORAGE) {
            bridge?.dispatchPicked("folder", emptyList())
        }
    }

    /* ---------- import de fichiers (SAF) ---------- */

    fun pickFiles(purpose: String) {
        pendingPurpose = purpose
        val intent = Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
            addCategory(Intent.CATEGORY_OPENABLE)
            type = "*/*"
            putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true)
        }
        try {
            startActivityForResult(intent, REQUEST_OPEN)
        } catch (_: Exception) {
            bridge?.dispatchPicked(purpose, emptyList())
        }
    }

    @Deprecated("Activity result API non disponible sans AndroidX Activity")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode != REQUEST_OPEN) return
        if (resultCode != RESULT_OK || data == null) {
            bridge?.dispatchPicked(pendingPurpose, emptyList())
            return
        }
        val uris = mutableListOf<Uri>()
        data.clipData?.let { clip ->
            for (index in 0 until clip.itemCount) uris.add(clip.getItemAt(index).uri)
        }
        data.data?.let { uris.add(it) }
        val purpose = pendingPurpose
        val bridgeRef = bridge

        Thread {
            val entries = mutableListOf<Pair<String, String>>()
            val target = File(cacheDir, "import").apply { mkdirs() }
            for (uri in uris) {
                try {
                    val name = queryName(uri) ?: "fichier-${System.currentTimeMillis()}"
                    var destination = File(target, name)
                    var suffix = 1
                    while (destination.exists()) {
                        destination = File(target, "$suffix-$name")
                        suffix += 1
                    }
                    contentResolver.openInputStream(uri)?.use { input ->
                        FileOutputStream(destination).use { output -> input.copyTo(output) }
                    }
                    entries.add(name to destination.absolutePath)
                } catch (_: Exception) {
                }
            }
            runOnUiThread { bridgeRef?.dispatchPicked(purpose, entries) }
        }.start()
    }

    private fun queryName(uri: Uri): String? {
        return try {
            contentResolver.query(uri, null, null, null, null)?.use { cursor ->
                val index = cursor.getColumnIndex(android.provider.OpenableColumns.DISPLAY_NAME)
                if (index >= 0 && cursor.moveToFirst()) cursor.getString(index) else null
            }
        } catch (_: Exception) {
            null
        }
    }

    fun versionName(): String {
        return try {
            packageManager.getPackageInfo(packageName, 0).versionName ?: "3.0.0"
        } catch (_: Exception) {
            "3.0.0"
        }
    }

    fun copyToClipboard(text: String) {
        val clipboard = getSystemService(CLIPBOARD_SERVICE) as android.content.ClipboardManager
        clipboard.setPrimaryClip(android.content.ClipData.newPlainText("PyIDE", text))
    }

    companion object {
        private const val REQUEST_OPEN = 2001
        private const val REQUEST_STORAGE = 2002
    }
}
