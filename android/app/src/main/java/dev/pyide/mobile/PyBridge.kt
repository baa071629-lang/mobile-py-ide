package dev.pyide.mobile

import android.webkit.JavascriptInterface
import android.webkit.WebView
import com.chaquo.python.Python
import org.json.JSONArray
import org.json.JSONObject

/**
 * Pont JavaScript ⇄ Python.
 *
 * Côté web, tout passe par `window.PyAndroid` :
 *   - `call(json)`            opérations rapides, réponse immédiate ;
 *   - `callAsync(json, id)`   opérations longues (pip, PyPI, IA) ;
 *   - `startRun(json)`        exécution d'un programme, événements poussés
 *                             vers `window.PyIdeEvent(json)`.
 */
class PyBridge(private val activity: MainActivity, private val webView: WebView) {

    private val module = Python.getInstance().getModule("pyide_native")
    private val pending = ArrayDeque<String>()
    private var pageReady = false

    /* ---------- cycle de vie ---------- */

    fun onPageReady() {
        synchronized(pending) {
            pageReady = true
            while (pending.isNotEmpty()) {
                webView.evaluateJavascript(pending.removeFirst(), null)
            }
        }
    }

    fun notifyResume() {
        // Les permissions de stockage ont pu changer entre-temps.
        synchronized(pending) {
            if (pageReady) {
                webView.evaluateJavascript(
                    "window.PyIdeEvent('{\"type\":\"resume\"}');", null,
                )
            }
        }
    }

    private fun dispatchJs(payload: String) {
        val js = "window.PyIdeEvent(${JSONObject.quote(payload)});"
        synchronized(pending) {
            if (!pageReady) {
                if (pending.size > 2000) pending.removeFirst()
                pending.addLast(js)
                return
            }
        }
        webView.post { webView.evaluateJavascript(js, null) }
    }

    internal fun dispatchPicked(purpose: String, entries: List<Pair<String, String>>) {
        val array = JSONArray()
        for ((name, path) in entries) {
            array.put(JSONObject().put("name", name).put("path", path))
        }
        val event = JSONObject()
            .put("type", "picked")
            .put("purpose", purpose)
            .put("entries", array)
        dispatchJs(event.toString())
    }

    private fun errorJson(message: String?, status: Int = 500): String =
        JSONObject().put("error", message ?: "Erreur Python").put("status", status).toString()

    /* ---------- appels synchrones ---------- */

    @JavascriptInterface
    fun call(request: String): String {
        return try {
            module.callAttr("request", request).toString()
        } catch (error: Throwable) {
            errorJson(error.message ?: error.toString())
        }
    }

    /** Opération longue : la réponse arrive par un événement `response`. */
    @JavascriptInterface
    fun callAsync(request: String, requestId: String) {
        Thread {
            val result = try {
                module.callAttr("request", request).toString()
            } catch (error: Throwable) {
                errorJson(error.message ?: error.toString())
            }
            val payload = "{\"type\":\"response\",\"reqId\":" +
                JSONObject.quote(requestId) + ",\"data\":" + result + "}"
            dispatchJs(payload)
        }.start()
    }

    /* ---------- exécution ---------- */

    private inner class EventSink {
        @Suppress("unused")
        fun onEvent(runId: String, payload: String) {
            dispatchJs(payload)
        }
    }

    @JavascriptInterface
    fun startRun(request: String): String {
        val runId = System.nanoTime().toString()
        try {
            module.callAttr("start_run", request, runId, EventSink())
        } catch (error: Throwable) {
            val payload = JSONObject()
                .put("type", "error")
                .put("runId", runId)
                .put("message", error.message ?: error.toString())
            dispatchJs(payload.toString())
        }
        return runId
    }

    @JavascriptInterface
    fun runInput(runId: String, text: String) {
        try {
            module.callAttr("run_input", runId, text)
        } catch (_: Throwable) {
        }
    }

    @JavascriptInterface
    fun runCloseInput(runId: String) {
        try {
            module.callAttr("run_close_stdin", runId)
        } catch (_: Throwable) {
        }
    }

    @JavascriptInterface
    fun stopRun(runId: String) {
        try {
            module.callAttr("stop_run", runId)
        } catch (_: Throwable) {
        }
    }

    /* ---------- fichiers, permissions, appareil ---------- */

    @JavascriptInterface
    fun pickFiles(purpose: String) {
        activity.pickFiles(purpose)
    }

    @JavascriptInterface
    fun pickFolder() {
        activity.ensureStoragePermission()
        val root = activity.storageRoot()
        val entries = if (root.isNotEmpty()) {
            listOf("Stockage du téléphone" to root)
        } else {
            emptyList()
        }
        dispatchPicked("folder", entries)
    }

    @JavascriptInterface
    fun requestStorage() {
        activity.ensureStoragePermission()
    }

    @JavascriptInterface
    fun deviceInfo(): String {
        val info = JSONObject()
            .put("native", true)
            .put("platform", "android")
            .put("sdk", android.os.Build.VERSION.SDK_INT)
            .put("model", android.os.Build.MODEL)
            .put("version", activity.versionName())
        return info.toString()
    }

    @JavascriptInterface
    fun copyText(text: String) {
        activity.copyToClipboard(text)
    }

    @JavascriptInterface
    fun exitApp() {
        activity.finish()
    }
}
