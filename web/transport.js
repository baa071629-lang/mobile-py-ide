/* Couche de transport : serveur HTTP/WebSocket (Termux, PC) ou pont Android natif.
 *
 * Le reste du frontend continue d'appeler `api("/api/…")`. Cette couche traduit
 * chaque route REST en opération native quand l'app tourne dans Android, et
 * laisse passer la requête HTTP sinon.
 */
"use strict";

const PyTransport = (() => {
  const bridge = (typeof window.PyAndroid !== "undefined" && window.PyAndroid
    && typeof window.PyAndroid.call === "function") ? window.PyAndroid : null;

  const state = {
    native: !!bridge,
    token: "",
    runHandlers: new Map(),
    pickers: new Map(),
    pending: new Map(),
    seq: 0,
  };

  // Opérations longues (réseau, pip) : exécutées hors du fil JavaScript.
  const LONG_OPS = new Set([
    "packages.install", "packages.uninstall", "packages.search",
    "packages.info", "ai.ask",
  ]);

  /* ---------- événements poussés par Android ---------- */
  window.PyIdeEvent = function (raw) {
    let event;
    try { event = JSON.parse(String(raw)); } catch (_) { return; }
    if (!event || typeof event !== "object") return;

    if (event.type === "resume") {
      if (typeof window.PyIdeOnResume === "function") window.PyIdeOnResume();
      return;
    }
    if (event.type === "response") {
      const waiter = state.pending.get(String(event.reqId));
      if (!waiter) return;
      state.pending.delete(String(event.reqId));
      const data = event.data;
      if (data && data.error) {
        const error = new Error(data.error);
        error.status = data.status || 500;
        waiter.reject(error);
      } else {
        waiter.resolve(data);
      }
      return;
    }
    if (event.type === "picked") {
      const resolve = state.pickers.get(event.purpose || "files");
      if (resolve) {
        state.pickers.delete(event.purpose || "files");
        resolve(event);
      }
      return;
    }
    const key = String(event.runId ?? 0);
    const handler = state.runHandlers.get(key);
    if (handler) handler(event);
  };

  /* ---------- opérations natives ---------- */
  function nativeCall(op, params = {}) {
    let raw;
    try {
      raw = bridge.call(JSON.stringify({ op, ...params }));
    } catch (error) {
      throw new Error(`Pont Android indisponible : ${error}`);
    }
    let data;
    try { data = JSON.parse(raw); } catch (_) { throw new Error("Réponse native illisible"); }
    if (data && data.error) {
      const error = new Error(data.error);
      error.status = data.status || 500;
      throw error;
    }
    return data;
  }

  function nativeCallAsync(op, params = {}) {
    return new Promise((resolve, reject) => {
      state.seq += 1;
      const requestId = String(state.seq);
      state.pending.set(requestId, { resolve, reject });
      try {
        bridge.callAsync(JSON.stringify({ op, ...params }), requestId);
      } catch (error) {
        state.pending.delete(requestId);
        reject(new Error(`Pont Android indisponible : ${error}`));
      }
    });
  }

  const ROUTES = [
    [/^\/api\/health$/, { GET: "health" }],
    [/^\/api\/places$/, { GET: "places" }],
    [/^\/api\/places\/add$/, { POST: "places.add" }],
    [/^\/api\/places\/remove$/, { POST: "places.remove" }],
    [/^\/api\/info$/, { GET: "info" }],
    [/^\/api\/tree$/, { GET: "tree" }],
    [/^\/api\/file$/, { GET: "file.read", POST: "file.save" }],
    [/^\/api\/exists$/, { GET: "exists" }],
    [/^\/api\/mkdir$/, { POST: "mkdir" }],
    [/^\/api\/rename$/, { POST: "rename" }],
    [/^\/api\/delete$/, { POST: "delete" }],
    [/^\/api\/search$/, { GET: "search" }],
    [/^\/api\/files$/, { GET: "files" }],
    [/^\/api\/format$/, { POST: "format" }],
    [/^\/api\/complete$/, { POST: "complete" }],
    [/^\/api\/hover$/, { POST: "hover" }],
    [/^\/api\/signature$/, { POST: "signature" }],
    [/^\/api\/definition$/, { POST: "definition" }],
    [/^\/api\/diagnose$/, { POST: "diagnose" }],
    [/^\/api\/packages$/, { GET: "packages.list" }],
    [/^\/api\/packages\/install$/, { POST: "packages.install" }],
    [/^\/api\/packages\/uninstall$/, { POST: "packages.uninstall" }],
    [/^\/api\/packages\/catalog$/, { GET: "packages.catalog" }],
    [/^\/api\/packages\/search$/, { GET: "packages.search" }],
    [/^\/api\/packages\/info$/, { GET: "packages.info" }],
    [/^\/api\/snippets$/, { GET: "snippets" }],
    [/^\/api\/ai\/status$/, { GET: "ai.status" }],
    [/^\/api\/ai$/, { POST: "ai.ask" }],
    [/^\/api\/import$/, { POST: "import" }],
  ];

  function splitPath(path) {
    const [pathname, query = ""] = String(path).split("?", 2);
    const params = {};
    new URLSearchParams(query).forEach((value, key) => { params[key] = value; });
    if ("hidden" in params) params.hidden = ["1", "true", "yes"].includes(params.hidden);
    return { pathname, params };
  }

  async function request(path, options = {}) {
    const method = (options.method || "GET").toUpperCase();
    if (state.native) {
      const { pathname, params } = splitPath(path);
      const rule = ROUTES.find(([pattern]) => pattern.test(pathname));
      if (!rule) throw new Error(`Route inconnue : ${pathname}`);
      const op = rule[1][method];
      if (!op) throw new Error(`Méthode ${method} non gérée pour ${pathname}`);
      if (options.body) {
        try { Object.assign(params, JSON.parse(options.body)); }
        catch (_) { throw new Error("Corps JSON invalide"); }
      }
      if (LONG_OPS.has(op)) return nativeCallAsync(op, params);
      return nativeCall(op, params);
    }

    const headers = { ...(options.headers || {}) };
    if (options.body && !(options.body instanceof FormData)) {
      headers["Content-Type"] = "application/json";
    }
    if (state.token) headers["X-Pyide-Token"] = state.token;
    let response;
    try {
      response = await fetch(path, { cache: "no-store", ...options, method, headers });
    } catch (_) {
      throw new Error("Serveur injoignable. Lance « start.sh » dans Termux.");
    }
    const text = await response.text();
    let data = null;
    if (text) {
      try { data = JSON.parse(text); } catch (_) { data = null; }
    }
    if (!response.ok) {
      const message = (data && data.detail) || `Erreur HTTP ${response.status}`;
      const error = new Error(message);
      error.status = response.status;
      throw error;
    }
    return data;
  }

  /* ---------- exécution : WebSocket ou pont natif ---------- */
  function run(payload, handlers = {}) {
    if (state.native) return nativeRun(payload, handlers);
    return socketRun(payload, handlers);
  }

  function nativeRun(payload, handlers) {
    const body = {
      code: payload.code ?? null,
      path: payload.path ?? null,
      args: payload.args || [],
      timeout: payload.timeout || 30,
      repl: !!payload.repl,
    };
    let runId = "0";
    let finished = false;
    const emit = (event) => {
      if (event.type === "exit" || event.type === "error") finished = true;
      if (handlers.onEvent) handlers.onEvent(event);
    };
    try {
      runId = String(bridge.startRun(JSON.stringify(body)) || "0");
    } catch (error) {
      setTimeout(() => emit({ type: "error", message: String(error) }), 0);
      return { input() {}, closeInput() {}, stop() {} };
    }
    state.runHandlers.set(runId, emit);
    return {
      runId,
      input(text) {
        try { bridge.runInput(runId, String(text)); } catch (_) { /* ignoré */ }
      },
      gfx(event) {
        try { bridge.gfxEvent(runId, JSON.stringify(event)); } catch (_) { /* ignoré */ }
      },
      closeInput() {
        try { bridge.runCloseInput(runId); } catch (_) { /* ignoré */ }
      },
      stop() {
        try { bridge.stopRun(runId); } catch (_) { /* ignoré */ }
      },
      dispose() {
        state.runHandlers.delete(runId);
        if (!finished) { try { bridge.stopRun(runId); } catch (_) { /* ignoré */ } }
      },
    };
  }

  function socketRun(payload, handlers) {
    let socket = null;
    let closed = false;
    let opened = false;
    let fallback = false;
    const pending = [];
    const emit = (event) => { if (handlers.onEvent) handlers.onEvent(event); };

    const flush = () => {
      if (!socket || socket.readyState !== WebSocket.OPEN) return;
      while (pending.length) socket.send(JSON.stringify(pending.shift()));
    };

    const send = (message) => {
      if (socket && socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify(message));
      else if (message.type === "stdin") pending.push(message);
    };

    const runFallback = async () => {
      if (fallback) return;
      fallback = true;
      emit({ type: "stdin_unavailable" });
      try {
        const data = await request("/api/run", {
          method: "POST",
          body: JSON.stringify({
            path: payload.path || null,
            code: payload.code !== undefined ? payload.code : null,
            args: payload.args || [],
            timeout: payload.timeout || 30,
            repl: !!payload.repl,
          }),
        });
        if (closed) return;
        if (data.stdout) emit({ type: "stdout", data: data.stdout });
        if (data.stderr) emit({ type: "stderr", data: data.stderr });
        emit({
          type: "exit", code: data.code, duration: data.duration || 0,
          timedOut: data.timedOut, truncated: data.truncated,
        });
      } catch (error) {
        emit({ type: "error", message: error.message });
      }
    };

    try {
      const protocol = location.protocol === "https:" ? "wss" : "ws";
      const query = state.token ? `?token=${encodeURIComponent(state.token)}` : "";
      socket = new WebSocket(`${protocol}://${location.host}/ws/run${query}`);
    } catch (_) {
      runFallback();
      return { input() {}, closeInput() {}, stop() {} };
    }

    socket.addEventListener("open", () => {
      opened = true;
      const message = {
        type: "start",
        path: payload.path || null,
        args: payload.args || [],
        timeout: payload.timeout || 30,
        repl: !!payload.repl,
      };
      if (payload.code !== undefined) message.code = payload.code;
      socket.send(JSON.stringify(message));
      flush();
    });

    socket.addEventListener("message", (event) => {
      let message;
      try { message = JSON.parse(event.data); } catch (_) { return; }
      emit(message);
    });

    socket.addEventListener("error", () => {
      if (!opened) runFallback();
    });

    socket.addEventListener("close", () => {
      if (closed) return;
      closed = true;
      state.runHandlers.delete("0");
      if (!opened) { runFallback(); return; }
      emit({ type: "disconnected" });
    });

    return {
      input(text) { send({ type: "stdin", data: String(text) }); },
      gfx(event) { send({ type: "gfx_input", event }); },
      closeInput() { send({ type: "close_stdin" }); },
      stop() { send({ type: "stop" }); },
      dispose() {
        if (socket && socket.readyState === WebSocket.OPEN) {
          try { socket.close(); } catch (_) { /* ignoré */ }
        }
      },
    };
  }

  /* ---------- services spécifiques à Android ---------- */
  function pick(kind) {
    if (!state.native) return Promise.reject(new Error("Sélecteur natif indisponible"));
    return new Promise((resolve) => {
      state.pickers.set(kind, resolve);
      try {
        if (kind === "folder") bridge.pickFolder();
        else bridge.pickFiles(kind);
      } catch (error) {
        state.pickers.delete(kind);
        resolve({ entries: [], error: String(error) });
      }
    });
  }

  return {
    mode: state.native ? "native" : "http",
    get native() { return state.native; },
    setToken(token) { state.token = token || ""; },
    request,
    call: nativeCall,
    run,
    pickFiles: () => pick("files"),
    pickFolder: () => pick("folder"),
    requestStorage() {
      if (state.native) { try { bridge.requestStorage(); } catch (_) { /* ignoré */ } }
    },
    setImmersive(enabled, landscape) {
      if (!state.native) return;
      try { bridge.setImmersive(!!enabled, !!landscape); } catch (_) { /* ignoré */ }
    },
    deviceInfo() {
      if (!state.native) return { native: false, platform: navigator.platform || "web" };
      try { return JSON.parse(bridge.deviceInfo()); } catch (_) { return { native: true }; }
    },
    onMenu(callback) {
      window.PyIdeMenu = callback;
    },
  };
})();
