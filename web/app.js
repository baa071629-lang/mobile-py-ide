/* Mobile Py IDE 2.0 — frontend Monaco, mobile-first, offline. */
"use strict";

const $ = (id) => document.getElementById(id);
const SETTINGS_KEY = "pyide.settings.v2";
const TOKEN_KEY = "pyide.token";

const DEFAULT_SETTINGS = {
  fontSize: 14,
  tabSize: 4,
  wordWrap: true,
  autosave: 0,
  lint: true,
  showHidden: false,
  theme: "dark",
  runTimeout: 30,
  keybar: true,
};

const WELCOME = `# Bienvenue dans Mobile Py IDE 2.0
#
# ☰  fichiers et dossiers
# ▶  exécuter le fichier
# Ctrl+K  palette de commandes
# Ctrl+P  ouverture rapide
#
# Les erreurs de syntaxe et les avertissements
# apparaissent dans l'onglet « Problèmes ».

print("Salut !")
`;

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function loadSettings() {
  const defaults = { ...DEFAULT_SETTINGS };
  try {
    const raw = JSON.parse(localStorage.getItem(SETTINGS_KEY) || "{}");
    const settings = { ...defaults, ...raw };
    settings.fontSize = clamp(Number(settings.fontSize) || 14, 11, 24);
    settings.tabSize = [2, 4, 8].includes(Number(settings.tabSize)) ? Number(settings.tabSize) : 4;
    settings.autosave = [0, 1, 3, 5].includes(Number(settings.autosave)) ? Number(settings.autosave) : 0;
    settings.runTimeout = clamp(Number(settings.runTimeout) || 30, 5, 300);
    settings.wordWrap = settings.wordWrap !== false;
    settings.lint = settings.lint !== false;
    settings.showHidden = settings.showHidden === true;
    settings.keybar = settings.keybar !== false;
    settings.theme = settings.theme === "light" ? "light" : "dark";
    return settings;
  } catch (_) {
    return defaults;
  }
}

const state = {
  editor: null,
  entries: new Map(),
  tabs: [],
  active: null,
  currentDir: "",
  currentTree: null,
  untitled: 0,
  settings: loadSettings(),
  token: localStorage.getItem(TOKEN_KEY) || "",
  monacoReady: false,
  health: null,
  aiStatus: null,
  diagSeq: new Map(),
  running: false,
  repl: false,
  runId: 0,
  ws: null,
  run: null,
  places: [],
  place: null,
  splitSize: null,
  splitVertical: false,
  lastPrompt: "",
  stdinHistory: [],
  stdinHistoryIndex: -1,
  gfx: null,
  pendingStdin: [],
  panel: "terminal",
  aiText: "",
  lastArgs: "",
  modalOpen: false,
  authPrompted: false,
};

/* ---------- utilitaires ---------- */

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key.startsWith("on") && typeof value === "function") {
      node.addEventListener(key.slice(2).toLowerCase(), value);
    } else if (value === true) node.setAttribute(key, "");
    else node.setAttribute(key, value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.appendChild(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

function basename(path) {
  return (path || "").split("/").filter(Boolean).pop() || "";
}

function dirname(path) {
  const index = (path || "").lastIndexOf("/");
  return index < 0 ? "" : path.slice(0, index);
}

function joinPath(dir, name) {
  const clean = (name || "").replace(/^\/+/, "");
  if (!dir) return clean ? `/${clean}` : "";
  if (!clean) return dir;
  return `${dir.replace(/\/+$/, "")}/${clean}`;
}

function normalizePath(value, dir = state.currentDir) {
  let path = (value || "").trim().replace(/\\/g, "/");
  if (!path) return "";
  if (path.startsWith("/")) return path.replace(/\/+$/, "") || "/";
  return joinPath(dir, path);
}

function formatSize(bytes) {
  if (!bytes) return "";
  if (bytes < 1024) return `${bytes} o`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} Ko`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} Mo`;
}

function fileIcon(entry) {
  if (entry.isDir) return "📁";
  const ext = (entry.name.split(".").pop() || "").toLowerCase();
  if (ext === "py") return "🐍";
  if (["md", "txt", "rst"].includes(ext)) return "📄";
  if (["json", "toml", "yaml", "yml", "ini", "cfg"].includes(ext)) return "⚙";
  if (["png", "jpg", "jpeg", "gif", "webp", "svg"].includes(ext)) return "🖼";
  if (["html", "css", "js"].includes(ext)) return "🌐";
  return "📄";
}

/* ---------- API ---------- */

async function api(path, options = {}) {
  try {
    return await PyTransport.request(path, options);
  } catch (error) {
    if (error.status === 401 && !state.authPrompted) {
      state.authPrompted = true;
      setTimeout(() => {
        toast("Jeton d'accès requis ou invalide", 4200);
        showSettings();
      }, 0);
    }
    throw error;
  }
}

function placeForPath(path) {
  let best = null;
  for (const place of state.places) {
    if (path === place.path || path.startsWith(`${place.path.replace(/\/+$/, "")}/`)) {
      if (!best || place.path.length > best.path.length) best = place;
    }
  }
  return best;
}

function displayPath(path) {
  const place = placeForPath(path);
  if (!place) return path || "";
  const rel = path.slice(place.path.length).replace(/^\/+/, "");
  return rel ? `${place.label}/${rel}` : place.label;
}

function tokenSuffix() {
  return state.token ? `?token=${encodeURIComponent(state.token)}` : "";
}

/* ---------- toast / chargement ---------- */

let toastTimer = null;
function toast(message, duration = 2400) {
  const node = $("toast");
  node.textContent = message;
  node.classList.remove("hidden");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => node.classList.add("hidden"), duration);
}

let loadingVisible = false;
function showLoading(text = "Chargement…") {
  $("loading-text").textContent = text;
  $("loading").classList.remove("hidden");
  loadingVisible = true;
}
function hideLoading() {
  if (!loadingVisible) return;
  $("loading").classList.add("hidden");
  loadingVisible = false;
}

/* ---------- modales ---------- */

let modalCloseCallback = null;

function closeModal() {
  const root = $("modal-root");
  if (root.classList.contains("hidden")) return;
  root.classList.add("hidden");
  root.classList.remove("sheet", "wide");
  $("modal-title").textContent = "";
  $("modal-body").textContent = "";
  $("modal-footer").textContent = "";
  state.modalOpen = false;
  const callback = modalCloseCallback;
  modalCloseCallback = null;
  if (callback) callback();
}

function openModal(options) {
  const {
    title = "",
    body = "",
    footer = [],
    sheet = false,
    wide = false,
    onClose = null,
  } = options;

  const root = $("modal-root");
  if (!root.classList.contains("hidden")) closeModal();

  $("modal-title").textContent = title;
  const bodyNode = $("modal-body");
  bodyNode.textContent = "";
  if (typeof body === "string") bodyNode.textContent = body;
  else if (body instanceof Node) bodyNode.appendChild(body);

  const footerNode = $("modal-footer");
  footerNode.textContent = "";
  for (const item of footer) {
    const button = el("button", {
      class: `text-btn${item.primary ? " primary" : ""}${item.danger ? " danger" : ""}`,
      text: item.label,
      type: "button",
    });
    button.addEventListener("click", item.onClick || (() => closeModal()));
    if (item.disabled) button.disabled = true;
    footerNode.appendChild(button);
  }

  root.classList.toggle("sheet", !!sheet);
  root.classList.toggle("wide", !!wide);
  root.classList.remove("hidden");
  modalCloseCallback = onClose;
  state.modalOpen = true;
}

function modalPrompt(options) {
  const {
    title = "Valeur",
    label = "",
    value = "",
    placeholder = "",
    confirmLabel = "Valider",
    hint = "",
  } = options;

  return new Promise((resolve) => {
    let settled = false;
    const input = el("input", {
      type: "text",
      value,
      placeholder,
      autocomplete: "off",
      autocapitalize: "off",
      spellcheck: "false",
    });
    const form = el("form", {},
      el("div", { class: "field" },
        el("label", { text: label || title }),
        input,
        hint ? el("div", { class: "hint", text: hint }) : null,
      ),
      el("button", { type: "submit", class: "hidden" }),
    );

    const finish = (result) => {
      if (settled) return;
      settled = true;
      modalCloseCallback = null;
      closeModal();
      resolve(result);
    };

    form.addEventListener("submit", (event) => {
      event.preventDefault();
      const result = input.value.trim();
      if (!result) {
        input.focus();
        return;
      }
      finish(result);
    });

    openModal({
      title,
      body: form,
      onClose: () => finish(null),
      footer: [
        { label: "Annuler", onClick: () => finish(null) },
        { label: confirmLabel, primary: true, onClick: () => form.requestSubmit() },
      ],
    });
    setTimeout(() => {
      input.focus();
      input.select();
    }, 60);
  });
}

function modalConfirm(options) {
  const { title = "Confirmer", message = "", confirmLabel = "Confirmer", danger = false } = options;
  return new Promise((resolve) => {
    let settled = false;
    const finish = (value) => {
      if (settled) return;
      settled = true;
      modalCloseCallback = null;
      closeModal();
      resolve(value);
    };
    openModal({
      title,
      body: el("p", { text: message }),
      onClose: () => finish(false),
      footer: [
        { label: "Annuler", onClick: () => finish(false) },
        { label: confirmLabel, danger, primary: !danger, onClick: () => finish(true) },
      ],
    });
  });
}

async function askSave(entry) {
  return new Promise((resolve) => {
    let settled = false;
    const finish = (value) => {
      if (settled) return;
      settled = true;
      modalCloseCallback = null;
      closeModal();
      resolve(value);
    };
    openModal({
      title: "Modifications non enregistrées",
      body: el("p", {}, `« ${entry.name} » a été modifié. Que veux-tu faire ?`),
      onClose: () => finish("cancel"),
      footer: [
        { label: "Annuler", onClick: () => finish("cancel") },
        { label: "Ne pas enregistrer", danger: true, onClick: () => finish("discard") },
        { label: "Enregistrer", primary: true, onClick: () => finish("save") },
      ],
    });
  });
}

function showSheet(title, items) {
  const list = el("div", { class: "sheet-list" });
  for (const item of items) {
    const button = el("button", {
      class: `sheet-item${item.danger ? " danger" : ""}`,
      type: "button",
    },
      el("span", { class: "ico", text: item.icon || "•" }),
      el("span", {},
        el("span", { text: item.label }),
        item.description ? el("small", { text: item.description }) : null,
      ),
    );
    button.addEventListener("click", () => {
      closeModal();
      if (item.run) setTimeout(() => item.run(), 0);
    });
    list.appendChild(button);
  }
  openModal({ title, body: list, sheet: true });
}

/* ---------- démarrage / Monaco ---------- */

function bootError(message) {
  $("boot").classList.add("failed");
  $("boot-msg").textContent = message;
}

function bootDone() {
  $("boot").classList.add("hidden");
}

function defineThemes() {
  monaco.editor.defineTheme("pyide-dark", {
    base: "vs-dark",
    inherit: true,
    rules: [
      { token: "comment", foreground: "7f849c", fontStyle: "italic" },
      { token: "string", foreground: "a6e3a1" },
      { token: "keyword", foreground: "cba6f7" },
      { token: "number", foreground: "fab387" },
      { token: "type", foreground: "89b4fa" },
    ],
    colors: {
      "editor.background": "#1e1e2e",
      "editor.foreground": "#cdd6f4",
      "editorLineNumber.foreground": "#585b70",
      "editorLineNumber.activeForeground": "#9399b2",
      "editorGutter.background": "#1e1e2e",
      "editor.selectionBackground": "#585b70",
      "editor.inactiveSelectionBackground": "#45475a",
      "editor.lineHighlightBackground": "#181825",
      "editorCursor.foreground": "#f5e0dc",
      "editorWidget.background": "#181825",
      "editorWidget.border": "#45475a",
      "editorSuggestWidget.background": "#181825",
      "editorSuggestWidget.selectedBackground": "#313244",
      "editorHoverWidget.background": "#181825",
      "editorIndentGuide.background1": "#313244",
      "editorIndentGuide.activeBackground1": "#585b70",
    },
  });
  monaco.editor.defineTheme("pyide-light", {
    base: "vs",
    inherit: true,
    rules: [
      { token: "comment", foreground: "8c8fa1", fontStyle: "italic" },
      { token: "string", foreground: "40a02b" },
      { token: "keyword", foreground: "8839ef" },
      { token: "number", foreground: "fe640b" },
      { token: "type", foreground: "1e66f5" },
    ],
    colors: {
      "editor.background": "#eff1f5",
      "editor.foreground": "#4c4f69",
      "editorLineNumber.foreground": "#9ca0b0",
      "editorLineNumber.activeForeground": "#4c4f69",
      "editorGutter.background": "#eff1f5",
      "editor.selectionBackground": "#ccd0da",
      "editor.lineHighlightBackground": "#e6e9ef",
      "editorWidget.background": "#e6e9ef",
      "editorSuggestWidget.background": "#e6e9ef",
      "editorHoverWidget.background": "#e6e9ef",
    },
  });
}

function initMonaco() {
  state.monacoReady = true;
  defineThemes();

  state.editor = monaco.editor.create($("editor"), {
    model: null,
    theme: state.settings.theme === "light" ? "pyide-light" : "pyide-dark",
    fontSize: state.settings.fontSize,
    minimap: { enabled: false },
    scrollBeyondLastLine: false,
    automaticLayout: true,
    tabSize: state.settings.tabSize,
    insertSpaces: true,
    wordWrap: state.settings.wordWrap ? "on" : "off",
    padding: { top: 10, bottom: 20 },
    quickSuggestions: { other: true, comments: false, strings: false },
    suggestOnTriggerCharacters: true,
    parameterHints: { enabled: true },
    lineNumbersMinChars: 3,
    glyphMargin: false,
    folding: true,
    renderWhitespace: "none",
    scrollbar: { verticalScrollbarSize: 6, horizontalScrollbarSize: 6 },
    suggest: { showWords: false },
    fixedOverflowWidgets: true,
    cursorBlinking: "smooth",
    smoothScrolling: true,
  });

  state.editor.onDidChangeCursorPosition(updateCursor);
  state.editor.onDidChangeCursorSelection(updateCursor);
  // Les raccourcis sont gérés une seule fois dans onKeyDown (phase capture),
  // sinon Monaco et le gestionnaire global se répondent (double sauvegarde,
  // exécution immédiatement arrêtée par un second Ctrl+Entrée).

  registerProviders();
  createEntry({ content: WELCOME, name: "sans-titre.py", activate: true });
  applySettings();
  bootDone();
  if (window.matchMedia("(min-width: 900px)").matches) {
    $("sidebar").classList.remove("hidden");
    $("sidebar").setAttribute("aria-hidden", "false");
  }

  if (window.matchMedia("(min-width: 900px)").matches) {
    document.body.classList.remove("panel-hidden");
  }
  loadHealth().then(loadPlaces).then(() => {
    const start = (state.place && state.place.path) || "";
    loadTree(start);
  });
  refreshAIStatus();
}

/* ---------- thème / paramètres ---------- */

function saveSettings() {
  try {
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(state.settings));
  } catch (_) { /* stockage indisponible */ }
}

function applySettings() {
  const settings = state.settings;
  document.body.dataset.theme = settings.theme;
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute("content", settings.theme === "light" ? "#eff1f5" : "#1e1e2e");
  $("keybar").classList.toggle("hidden", !settings.keybar);
  $("status-indent").textContent = `Espaces : ${settings.tabSize}`;
  state.splitSize = Number(settings.splitSize) || null;
  layoutSplit();

  if (!state.monacoReady || !state.editor) return;
  monaco.editor.setTheme(settings.theme === "light" ? "pyide-light" : "pyide-dark");
  state.editor.updateOptions({
    fontSize: settings.fontSize,
    wordWrap: settings.wordWrap ? "on" : "off",
  });
  for (const entry of state.entries.values()) {
    entry.model.updateOptions({ tabSize: settings.tabSize, insertSpaces: true });
  }
  if (!settings.lint) {
    for (const entry of state.entries.values()) {
      entry.markers = [];
      monaco.editor.setModelMarkers(entry.model, "pyide", []);
    }
    renderProblems([]);
  } else {
    for (const entry of state.entries.values()) {
      entry.diagCode = null;
      scheduleDiagnose(entry);
    }
  }
}

/* ---------- onglets / modèles ---------- */

function activeEntry() {
  return state.active ? state.entries.get(state.active) : null;
}

function findEntryByPath(path) {
  for (const entry of state.entries.values()) {
    if (entry.path === path) return entry;
  }
  return null;
}

function entryForModel(model) {
  for (const entry of state.entries.values()) {
    if (entry.model === model) return entry;
  }
  return null;
}

function createEntry({ content = "", path = null, name = null, activate = true, focus = false }) {
  if (path) {
    const existing = findEntryByPath(path);
    if (existing) {
      if (activate) activateEntry(existing.key, { focus });
      return existing;
    }
  }
  const key = path || `untitled:${++state.untitled}`;
  const uri = monaco.Uri.parse(`inmemory://pyide/${encodeURIComponent(key)}`);
  const model = monaco.editor.createModel(content, "python", uri);
  const entry = {
    key,
    path,
    name: name || (path ? basename(path) : `sans-titre-${state.untitled}.py`),
    model,
    viewState: null,
    dirty: false,
    savedVersion: model.getAlternativeVersionId(),
    markers: [],
    diagCode: null,
    diagTimer: null,
    autosaveTimer: null,
  };
  state.entries.set(key, entry);
  state.tabs.push(key);
  model.onDidChangeContent(() => onContentChanged(entry));
  renderTabs();
  if (activate) activateEntry(key, { focus });
  return entry;
}

function activateEntry(key, { focus = false } = {}) {
  const entry = state.entries.get(key);
  if (!entry) return;
  if (state.active === key) {
    if (focus) state.editor.focus();
    return;
  }
  const previous = state.entries.get(state.active);
  if (previous && state.editor.getModel() === previous.model) {
    previous.viewState = state.editor.saveViewState();
  }
  state.active = key;
  state.editor.setModel(entry.model);
  if (entry.viewState) {
    state.editor.restoreViewState(entry.viewState);
  } else {
    state.editor.setPosition({ lineNumber: 1, column: 1 });
    state.editor.setScrollTop(0);
  }
  renderTabs();
  updateCursor();
  renderProblems(entry.markers);
  updateStatus();
  highlightActiveFile();
  if (state.settings.lint) scheduleDiagnose(entry);
  if (focus) state.editor.focus();
  ensureTabVisible(key);
}

function disposeEntry(key) {
  const entry = state.entries.get(key);
  if (!entry) return;
  const wasActive = state.active === key;
  const index = state.tabs.indexOf(key);
  if (wasActive) {
    state.active = null;
    state.editor.setModel(null);
  }
  state.entries.delete(key);
  if (index >= 0) state.tabs.splice(index, 1);
  clearTimeout(entry.diagTimer);
  clearTimeout(entry.autosaveTimer);
  try { entry.model.dispose(); } catch (_) { /* déjà libéré */ }
  if (wasActive) {
    if (state.tabs.length) {
      const next = state.tabs[Math.min(index, state.tabs.length - 1)];
      activateEntry(next);
    } else {
      createEntry({ content: WELCOME, name: "sans-titre.py", activate: true });
    }
  } else {
    renderTabs();
    updateStatus();
  }
}

async function closeEntry(key) {
  const entry = state.entries.get(key);
  if (!entry) return;
  if (entry.dirty) {
    const choice = await askSave(entry);
    if (choice === "cancel" || choice === null) return;
    if (choice === "save") {
      const saved = await saveEntry(entry);
      if (!saved) return;
    }
  }
  disposeEntry(key);
}

function renderTabs() {
  const bar = $("tabbar");
  bar.textContent = "";
  for (const key of state.tabs) {
    const entry = state.entries.get(key);
    if (!entry) continue;
    const tab = el("div", {
      class: `tab${state.active === key ? " active" : ""}`,
      role: "tab",
      title: entry.path || entry.name,
      "aria-selected": state.active === key ? "true" : "false",
    },
      el("span", { class: "tab-name", text: entry.name }),
      entry.dirty ? el("span", { class: "tab-dot", text: "●", title: "Non enregistré" }) : null,
      el("button", {
        class: "tab-close", type: "button", title: "Fermer", "aria-label": `Fermer ${entry.name}`,
        text: "×",
        onClick: (event) => {
          event.stopPropagation();
          closeEntry(key);
        },
      }),
    );
    tab.addEventListener("click", () => {
      if (tab._pyideLongPress) {
        tab._pyideLongPress = false;
        return;
      }
      activateEntry(key);
    });
    bindLongPress(tab, () => showTabActions(entry));
    bar.appendChild(tab);
  }
  ensureTabVisible(state.active);
}

function ensureTabVisible(key) {
  const bar = $("tabbar");
  const active = bar.querySelector(".tab.active");
  if (active) active.scrollIntoView({ block: "nearest", inline: "nearest" });
  else if (key === null) bar.scrollLeft = 0;
}

function onContentChanged(entry) {
  entry.dirty = entry.model.getAlternativeVersionId() !== entry.savedVersion;
  renderTabs();
  updateStatus();
  if (state.settings.lint && state.active === entry.key) scheduleDiagnose(entry);
  if (state.settings.autosave && entry.path) {
    clearTimeout(entry.autosaveTimer);
    entry.autosaveTimer = setTimeout(() => {
      if (entry.dirty) saveEntry(entry, { silent: true });
    }, state.settings.autosave * 1000);
  }
}

/* ---------- diagnostics ---------- */

function scheduleDiagnose(entry) {
  if (!state.settings.lint || !entry) return;
  clearTimeout(entry.diagTimer);
  entry.diagTimer = setTimeout(() => diagnoseEntry(entry), 500);
}

async function diagnoseEntry(entry) {
  if (!state.settings.lint || !entry) return;
  const code = entry.model.getValue();
  if (entry.diagCode === code) return;

  const key = entry.key;
  const sequence = (state.diagSeq.get(key) || 0) + 1;
  state.diagSeq.set(key, sequence);

  let data;
  try {
    data = await api("/api/diagnose", {
      method: "POST",
      body: JSON.stringify({ code, path: entry.path }),
    });
  } catch (_) {
    return;
  }
  if (state.entries.get(key) !== entry || state.diagSeq.get(key) !== sequence) return;

  entry.diagCode = code;
  entry.markers = data.markers || [];
  monaco.editor.setModelMarkers(entry.model, "pyide", entry.markers);
  if (state.active === key) {
    renderProblems(entry.markers);
    updateStatus();
  }
}

function renderProblems(markers) {
  const list = $("problems-list");
  const empty = $("problems-empty");
  list.textContent = "";
  const sorted = [...(markers || [])].sort(
    (a, b) => a.startLineNumber - b.startLineNumber || a.startColumn - b.startColumn
  );

  if (!sorted.length) {
    empty.classList.remove("hidden");
  } else {
    empty.classList.add("hidden");
    for (const marker of sorted) {
      const severity = marker.severity === 8 ? "error" : "warning";
      const item = el("li", {},
        el("span", { class: `sev-${severity}`, text: marker.severity === 8 ? "●" : "◐" }),
        el("span", { class: "loc", text: `${marker.startLineNumber}:${marker.startColumn}` }),
        el("span", { class: "msg", text: marker.message }),
      );
      item.addEventListener("click", () => goToMarker(marker));
      list.appendChild(item);
    }
  }

  const errors = sorted.filter((marker) => marker.severity === 8).length;
  const warnings = sorted.length - errors;
  $("problems-badge").textContent = String(sorted.length);
  const panelTab = document.querySelector('.panel-tab[data-panel="problems"]');
  if (panelTab) panelTab.classList.toggle("has-errors", errors > 0);
  updateStatus();
}

function goToMarker(marker) {
  const entry = activeEntry();
  if (!entry) return;
  state.editor.setPosition({ lineNumber: marker.startLineNumber, column: marker.startColumn });
  state.editor.revealPositionInCenterIfOutsideViewport();
  state.editor.focus();
}

function updateCursor() {
  if (!state.editor) return;
  const position = state.editor.getPosition();
  if (!position) {
    $("status-pos").textContent = "Ln 1, Col 1";
    return;
  }
  const selection = state.editor.getSelection();
  let text = `Ln ${position.lineNumber}, Col ${position.column}`;
  if (selection && !selection.isEmpty()) {
    const lines = selection.endLineNumber - selection.startLineNumber + 1;
    if (lines > 1) text += ` · ${lines} lignes`;
  }
  $("status-pos").textContent = text;
}

function updateStatus() {
  const entry = activeEntry();
  const markers = entry ? entry.markers : [];
  const errors = markers.filter((marker) => marker.severity === 8).length;
  const warnings = markers.length - errors;
  const status = $("status-problems");
  status.textContent = errors ? `✗ ${errors}` : warnings ? `⚠ ${warnings}` : "✓ 0";
  status.classList.toggle("has-errors", errors > 0);
  $("problems-badge").textContent = String(markers.length);
  const panelTab = document.querySelector('.panel-tab[data-panel="problems"]');
  if (panelTab) panelTab.classList.toggle("has-errors", errors > 0);

  if (!entry) {
    $("status-save").textContent = "";
    document.title = "Mobile Py IDE";
    return;
  }
  if (entry.dirty) $("status-save").textContent = "● Non enregistré";
  else if (entry.path) $("status-save").textContent = "✓ Enregistré";
  else $("status-save").textContent = "Sans titre";
  document.title = `${entry.dirty ? "● " : ""}${entry.name} — Mobile Py IDE`;
}

/* ---------- providers Monaco ---------- */

function registerProviders() {
  monaco.languages.registerCompletionItemProvider("python", {
    triggerCharacters: [".", "(", '"', "'"],
    async provideCompletionItems(model, position, context, token) {
      const entry = entryForModel(model);
      if (!entry) return { suggestions: [] };
      const controller = new AbortController();
      token.onCancellationRequested(() => controller.abort());
      let data;
      try {
        data = await api("/api/complete", {
          method: "POST",
          signal: controller.signal,
          body: JSON.stringify({
            code: model.getValue(),
            line: position.lineNumber,
            column: position.column - 1,
            path: entry.path,
          }),
        });
      } catch (_) {
        return { suggestions: [] };
      }
      if (token.isCancellationRequested) return { suggestions: [] };
      const word = model.getWordUntilPosition(position);
      const range = {
        startLineNumber: position.lineNumber,
        startColumn: word.startColumn,
        endLineNumber: position.lineNumber,
        endColumn: word.endColumn,
      };
      return {
        suggestions: (data.items || []).map((item) => ({
          label: item.label,
          kind: item.kind,
          insertText: item.insertText,
          detail: item.detail,
          filterText: item.filterText,
          documentation: item.documentation || undefined,
          sortText: item.sortText,
          range,
        })),
      };
    },
  });

  monaco.languages.registerHoverProvider("python", {
    async provideHover(model, position) {
      const entry = entryForModel(model);
      if (!entry) return null;
      let data;
      try {
        data = await api("/api/hover", {
          method: "POST",
          body: JSON.stringify({
            code: model.getValue(),
            line: position.lineNumber,
            column: position.column - 1,
            path: entry.path,
          }),
        });
      } catch (_) {
        return null;
      }
      if (!data.markdown) return null;
      const word = model.getWordAtPosition(position);
      const range = word
        ? new monaco.Range(position.lineNumber, word.startColumn, position.lineNumber, word.endColumn)
        : new monaco.Range(position.lineNumber, position.column, position.lineNumber, position.column + 1);
      return { contents: [{ value: data.markdown }], range };
    },
  });

  monaco.languages.registerSignatureHelpProvider("python", {
    signatureHelpTriggerCharacters: ["(", ","],
    signatureHelpRetriggerCharacters: [","],
    async provideSignatureHelp(model, position) {
      const entry = entryForModel(model);
      if (!entry) return null;
      try {
        const data = await api("/api/signature", {
          method: "POST",
          body: JSON.stringify({
            code: model.getValue(),
            line: position.lineNumber,
            column: position.column - 1,
            path: entry.path,
          }),
        });
        return data.signature || null;
      } catch (_) {
        return null;
      }
    },
  });

  monaco.languages.registerDefinitionProvider("python", {
    async provideDefinition(model, position) {
      const entry = entryForModel(model);
      if (!entry) return null;
      let data;
      try {
        data = await api("/api/definition", {
          method: "POST",
          body: JSON.stringify({
            code: model.getValue(),
            line: position.lineNumber,
            column: position.column - 1,
            path: entry.path,
          }),
        });
      } catch (_) {
        return null;
      }
      const locations = data.locations || [];
      const results = [];
      for (const location of locations) {
        if (!location.path && location.line) {
          results.push({
            uri: model.uri,
            range: new monaco.Range(location.line, location.column, location.line, location.column + 1),
          });
        } else if (location.rel) {
          if (location.rel === entry.path) {
            results.push({
              uri: model.uri,
              range: new monaco.Range(location.line, location.column, location.line, location.column + 1),
            });
          } else {
            const target = await openFile(location.rel, {
              line: location.line,
              column: location.column,
              focus: true,
            });
            if (target) {
              results.push({
                uri: target.model.uri,
                range: new monaco.Range(location.line, location.column, location.line, location.column + 1),
              });
            }
          }
        } else {
          toast(`Définition externe : ${location.name || basename(location.path)}:${location.line}`, 3500);
        }
      }
      return results.length ? results : null;
    },
  });
}

/* ---------- barre latérale / fichiers ---------- */

async function loadHealth() {
  try {
    state.health = await api("/api/health");
    const python = (state.health.python || "").split(".").slice(0, 2).join(".");
    const native = state.health.native || PyTransport.native;
    $("status-python").textContent = python ? `Python ${python}${native ? " · Android" : ""}` : "Python";
    $("projects-root").textContent = state.health.root || "";
    if (state.health.authRequired && !state.token) {
      toast("Jeton d'accès requis : ouvre les paramètres ⚙", 5000);
      setTimeout(() => showSettings(), 400);
    }
  } catch (error) {
    toast(`Serveur : ${error.message}`, 5000);
  }
}

async function loadPlaces() {
  try {
    const data = await api("/api/places");
    state.places = data.places || [];
  } catch (_) {
    state.places = [];
  }
  const select = $("place-select");
  select.textContent = "";
  for (const place of state.places) {
    select.appendChild(el("option", { value: place.path, text: place.label }));
  }
  const current = placeForPath(state.currentDir) || state.places[0] || null;
  state.place = current;
  if (current) select.value = current.path;
  return state.places;
}

async function addPlaceDialog() {
  if (PyTransport.native) {
    PyTransport.requestStorage();
    const picked = await PyTransport.pickFolder();
    if (!picked || !picked.entries || !picked.entries.length) return;
    const path = picked.entries[0].path;
    try {
      const data = await api("/api/places/add", {
        method: "POST",
        body: JSON.stringify({ path, label: picked.entries[0].name || path }),
      });
      await loadPlaces();
      await loadTree(data.place.path);
      toast(`Dossier ajouté : ${data.place.label}`, 2600);
    } catch (error) {
      toast(error.message, 3600);
    }
    return;
  }
  const value = await modalPrompt({
    title: "Ouvrir un dossier",
    label: "Chemin absolu du dossier",
    value: "/",
    placeholder: "/storage/emulated/0/MesProjets",
    confirmLabel: "Ouvrir",
    hint: "Sur Termux : ~/storage/shared/… donne accès au stockage du téléphone.",
  });
  if (!value) return;
  try {
    const data = await api("/api/places/add", {
      method: "POST",
      body: JSON.stringify({ path: value.trim() }),
    });
    await loadPlaces();
    await loadTree(data.place.path);
    toast(`Dossier ajouté : ${data.place.label}`, 2600);
  } catch (error) {
    toast(error.message, 3600);
  }
}

async function loadTree(dir = null, { silent = false } = {}) {
  if (dir === null || dir === undefined) dir = state.currentDir || (state.place && state.place.path) || "";
  let data;
  try {
    data = await api(`/api/tree?dir=${encodeURIComponent(dir || "")}&hidden=${state.settings.showHidden ? 1 : 0}`);
  } catch (error) {
    const fallback = (state.places[0] && state.places[0].path) || "";
    if (dir && fallback && dir !== fallback) {
      try {
        data = await api(`/api/tree?dir=${encodeURIComponent(fallback)}&hidden=${state.settings.showHidden ? 1 : 0}`);
      } catch (inner) {
        if (!silent) toast(`Dossier : ${inner.message}`);
        return;
      }
    } else {
      if (!silent) toast(`Dossier : ${error.message}`);
      return;
    }
  }

  state.currentDir = data.dir || "";
  state.currentTree = data;
  $("projects-root").textContent = data.dir || data.root || "";
  state.place = placeForPath(state.currentDir) || state.place;
  if (state.place && $("place-select")) $("place-select").value = state.place.path;
  renderBreadcrumb(state.currentDir);

  const list = $("file-list");
  list.textContent = "";

  if (data.parent !== null) {
    const parent = el("li", {},
      el("span", { class: "dir-icon", text: "↰" }),
      el("span", { class: "file-name", text: ".." }),
    );
    parent.addEventListener("click", () => loadTree(data.parent || ""));
    list.appendChild(parent);
  }

  if (!data.entries.length) {
    list.appendChild(el("li", { class: "empty", text: "Dossier vide" }));
  }

  for (const entry of data.entries) {
    const item = el("li", { "data-path": entry.path },
      el("span", { class: "dir-icon", text: fileIcon(entry) }),
      el("span", { class: "file-name", text: entry.name }),
      !entry.isDir && entry.size ? el("span", { class: "file-size", text: formatSize(entry.size) }) : null,
    );
    item.addEventListener("click", () => {
      if (item._pyideLongPress) {
        item._pyideLongPress = false;
        return;
      }
      if (entry.isDir) loadTree(entry.path);
      else openFile(entry.path);
    });
    bindLongPress(item, () => showFileActions(entry));
    list.appendChild(item);
  }
  highlightActiveFile();
}

function renderBreadcrumb(dir) {
  const crumbs = $("breadcrumb");
  crumbs.textContent = "";
  const place = placeForPath(dir) || state.place;
  const root = place ? place.path : "";
  const rootLink = el("a", { href: "#", text: place ? place.label : "racine" });
  rootLink.addEventListener("click", (event) => {
    event.preventDefault();
    loadTree(root);
  });
  crumbs.appendChild(rootLink);
  if (!dir || !root || dir === root) return;

  const rel = dir.slice(root.length).replace(/^\/+/, "");
  let accumulated = root;
  for (const part of rel.split("/").filter(Boolean)) {
    accumulated = joinPath(accumulated, part);
    crumbs.appendChild(el("span", { class: "sep", text: " / " }));
    const link = el("a", { href: "#", text: part });
    const target = accumulated;
    link.addEventListener("click", (event) => {
      event.preventDefault();
      loadTree(target);
    });
    crumbs.appendChild(link);
  }
}

function highlightActiveFile() {
  const entry = activeEntry();
  for (const item of $("file-list").querySelectorAll("li[data-path]")) {
    item.classList.toggle("active", !!entry && entry.path === item.dataset.path);
  }
}

function bindLongPress(node, handler) {
  let timer = null;
  let fired = false;
  let startX = 0;
  let startY = 0;
  const clear = () => {
    clearTimeout(timer);
    timer = null;
  };
  node.addEventListener("pointerdown", (event) => {
    if (event.pointerType === "mouse" && event.button !== 0) return;
    fired = false;
    node._pyideLongPress = false;
    startX = event.clientX;
    startY = event.clientY;
    clear();
    timer = setTimeout(() => {
      fired = true;
      node._pyideLongPress = true;
      handler();
    }, 520);
  });
  node.addEventListener("pointerup", clear);
  node.addEventListener("pointercancel", clear);
  node.addEventListener("pointermove", (event) => {
    // Un léger tremblement du doigt ne doit pas annuler l'appui long.
    if (Math.abs(event.clientX - startX) > 10 || Math.abs(event.clientY - startY) > 10) {
      clear();
    }
  });
  node.addEventListener("contextmenu", (event) => {
    event.preventDefault();
    fired = false;
    node._pyideLongPress = true;
    handler();
  });
  node.addEventListener("click", () => {
    if (fired) {
      fired = false;
      node._pyideLongPress = true;
    }
  }, true);
}

function openSidebar() {
  $("sidebar").classList.remove("hidden");
  $("backdrop").classList.remove("hidden");
  $("sidebar").setAttribute("aria-hidden", "false");
  loadTree(state.currentDir, { silent: true });
}

function closeSidebar() {
  $("sidebar").classList.add("hidden");
  $("backdrop").classList.add("hidden");
  $("sidebar").setAttribute("aria-hidden", "true");
}

function toggleSidebar() {
  if ($("sidebar").classList.contains("hidden")) openSidebar();
  else closeSidebar();
}

async function openFile(path, { line = null, column = null, focus = false } = {}) {
  const existing = findEntryByPath(path);
  if (existing) {
    activateEntry(existing.key, { focus: focus || line !== null });
    if (line) {
      state.editor.setPosition({ lineNumber: line, column: column || 1 });
      state.editor.revealPositionInCenterIfOutsideViewport();
    }
    closeSidebar();
    return existing;
  }

  let data;
  try {
    data = await api(`/api/file?path=${encodeURIComponent(path)}`);
  } catch (error) {
    toast(`Ouverture impossible : ${error.message}`, 3500);
    return null;
  }

  const entry = createEntry({
    content: data.content,
    path: data.path,
    activate: true,
    focus: false,
  });
  if (line) {
    state.editor.setPosition({ lineNumber: line, column: column || 1 });
    state.editor.revealPositionInCenterIfOutsideViewport();
  }
  if (focus) state.editor.focus();
  closeSidebar();
  return entry;
}

async function fileExists(path) {
  const data = await api(`/api/exists?path=${encodeURIComponent(path)}`);
  return !!data.exists;
}

function showFileActions(entry) {
  const actions = [];
  if (entry.isDir) {
    actions.push(
      { icon: "📂", label: "Ouvrir le dossier", run: () => loadTree(entry.path) },
      { icon: "＋", label: "Nouveau fichier ici", run: () => newFileDialog(entry.path) },
      { icon: "🗀", label: "Nouveau dossier ici", run: () => newFolderDialog(entry.path) },
      { icon: "✏️", label: "Renommer", run: () => renameEntry(entry) },
      { icon: "📋", label: "Copier le chemin", run: () => copyText(entry.path) },
      { icon: "🗑", label: "Supprimer", danger: true, run: () => deleteEntry(entry) },
    );
  } else {
    actions.push(
      { icon: "📂", label: "Ouvrir", run: () => openFile(entry.path, { focus: true }) },
      { icon: "✏️", label: "Renommer", run: () => renameEntry(entry) },
      { icon: "⬇", label: "Télécharger", run: () => downloadEntry(entry) },
      { icon: "📋", label: "Copier le chemin", run: () => copyText(entry.path) },
      { icon: "🗑", label: "Supprimer", danger: true, run: () => deleteEntry(entry) },
    );
  }
  showSheet(entry.name, actions);
}

async function newFileDialog(dir = state.currentDir) {
  const value = await modalPrompt({
    title: "Nouveau fichier",
    label: "Chemin du fichier",
    value: joinPath(dir, "script.py"),
    confirmLabel: "Créer",
    hint: "Tu peux créer des sous-dossiers avec /.",
  });
  if (!value) return;
  let path = normalizePath(value, dir);
  if (!/\.[^/]+$/.test(path)) path += ".py";

  try {
    if (await fileExists(path)) {
      const overwrite = await modalConfirm({
        title: "Fichier existant",
        message: `« ${path} » existe déjà. Le remplacer ?`,
        confirmLabel: "Remplacer",
        danger: true,
      });
      if (!overwrite) return;
    }
    await api("/api/file", {
      method: "POST",
      body: JSON.stringify({ path, content: "" }),
    });
    await loadTree(state.currentDir, { silent: true });
    await openFile(path, { focus: true });
    toast("Fichier créé ✓");
  } catch (error) {
    toast(`Création impossible : ${error.message}`, 3500);
  }
}

async function newFolderDialog(dir = state.currentDir) {
  const value = await modalPrompt({
    title: "Nouveau dossier",
    label: "Nom du dossier",
    value: "dossier",
    confirmLabel: "Créer",
  });
  if (!value) return;
  const path = joinPath(dir, value);
  try {
    await api("/api/mkdir", { method: "POST", body: JSON.stringify({ path }) });
    await loadTree(state.currentDir, { silent: true });
    toast("Dossier créé ✓");
  } catch (error) {
    toast(`Création impossible : ${error.message}`, 3500);
  }
}

async function renameEntry(entry) {
  const value = await modalPrompt({
    title: "Renommer",
    label: "Nouveau chemin",
    value: entry.rel,
    confirmLabel: "Renommer",
  });
  if (!value || value === entry.rel) return;
  try {
    const data = await api("/api/rename", {
      method: "POST",
      body: JSON.stringify({ path: entry.rel, newPath: value }),
    });
    for (const open of state.entries.values()) {
      if (open.path === entry.rel) {
        open.path = data.path;
        open.name = basename(data.path);
      } else if (open.path && open.path.startsWith(`${entry.rel}/`)) {
        open.path = `${data.path}/${open.path.slice(entry.rel.length + 1)}`;
      }
    }
    renderTabs();
    updateStatus();
    await loadTree(state.currentDir, { silent: true });
    toast("Renommé ✓");
  } catch (error) {
    toast(`Renommage impossible : ${error.message}`, 3500);
  }
}

async function deleteEntry(entry) {
  const what = entry.isDir ? "le dossier" : "le fichier";
  const ok = await modalConfirm({
    title: "Supprimer",
    message: `Supprimer définitivement ${what} « ${entry.name} » ?`,
    confirmLabel: "Supprimer",
    danger: true,
  });
  if (!ok) return;
  try {
    await api("/api/delete", {
      method: "POST",
      body: JSON.stringify({ path: entry.rel }),
    });
    const toClose = [];
    for (const open of state.entries.values()) {
      if (open.path === entry.rel || (open.path && open.path.startsWith(`${entry.rel}/`))) {
        toClose.push(open.key);
      }
    }
    for (const key of toClose) disposeEntry(key);
    await loadTree(state.currentDir, { silent: true });
    toast("Supprimé");
  } catch (error) {
    toast(`Suppression impossible : ${error.message}`, 3500);
  }
}

function downloadEntry(entry) {
  const anchor = document.createElement("a");
  if (PyTransport.native) {
    toast("Téléchargement indisponible dans l'application : le fichier est déjà sur le téléphone.", 4200);
    return;
  }
  anchor.href = `/api/download?path=${encodeURIComponent(entry.path || entry.rel)}${state.token ? `&token=${encodeURIComponent(state.token)}` : ""}`;
  anchor.download = entry.name;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
}

async function importFromDevice() {
  if (!PyTransport.native) {
    $("file-input").click();
    return;
  }
  PyTransport.requestStorage();
  const picked = await PyTransport.pickFiles();
  if (!picked || !picked.entries || !picked.entries.length) return;
  showLoading("Import…");
  let count = 0;
  try {
    for (const file of picked.entries) {
      await api("/api/import", {
        method: "POST",
        body: JSON.stringify({ source: file.path, dir: state.currentDir }),
      });
      count += 1;
    }
    await loadTree(state.currentDir, { silent: true });
    toast(`${count} fichier(s) importé(s) ✓`);
  } catch (error) {
    toast(`Import impossible : ${error.message}`, 3800);
  } finally {
    hideLoading();
  }
}

async function uploadFiles(files) {
  if (!files || !files.length) return;
  showLoading(`Envoi de ${files.length} fichier(s)…`);
  try {
    for (const file of files) {
      const form = new FormData();
      form.append("dir", state.currentDir);
      form.append("files", file);
      await api("/api/upload", { method: "POST", body: form });
    }
    await loadTree(state.currentDir, { silent: true });
    toast(`${files.length} fichier(s) importé(s) ✓`);
  } catch (error) {
    toast(`Import impossible : ${error.message}`, 3500);
  } finally {
    hideLoading();
  }
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    toast("Copié ✓");
    return;
  } catch (_) { /* fallback */ }
  const area = document.createElement("textarea");
  area.value = text;
  area.style.position = "fixed";
  area.style.opacity = "0";
  document.body.appendChild(area);
  area.select();
  try {
    document.execCommand("copy");
    toast("Copié ✓");
  } catch (_) {
    toast("Copie impossible");
  }
  area.remove();
}

/* ---------- enregistrement ---------- */

async function saveActive() {
  const entry = activeEntry();
  if (!entry) return false;
  return saveEntry(entry);
}

async function saveEntry(entry, { silent = false, saveAs = false } = {}) {
  if (!entry) return false;
  let path = saveAs ? null : entry.path;
  if (!path) {
    const suggested = entry.path || joinPath(state.currentDir, entry.name.startsWith("sans-titre") ? "script.py" : entry.name);
    const value = await modalPrompt({
      title: "Enregistrer sous",
      label: "Chemin du fichier",
      value: suggested,
      confirmLabel: "Enregistrer",
      hint: "Le fichier sera créé dans le dossier projets.",
    });
    if (!value) return false;
    path = normalizePath(value, state.currentDir);
    if (!/\.[^/]+$/.test(path)) path += ".py";
    if (path !== entry.path) {
      try {
        if (await fileExists(path)) {
          const overwrite = await modalConfirm({
            title: "Fichier existant",
            message: `« ${path} » existe déjà. Le remplacer ?`,
            confirmLabel: "Remplacer",
            danger: true,
          });
          if (!overwrite) return false;
        }
      } catch (_) { /* on tentera l'écriture */ }
    }
  }

  const content = entry.model.getValue();
  const version = entry.model.getAlternativeVersionId();
  try {
    const data = await api("/api/file", {
      method: "POST",
      body: JSON.stringify({ path, content }),
    });
    entry.path = data.path;
    entry.name = basename(data.path);
    entry.savedVersion = version;
    entry.dirty = entry.model.getAlternativeVersionId() !== version;
    entry.diagCode = null;
    renderTabs();
    updateStatus();
    highlightActiveFile();
    if (!silent) toast("Enregistré ✓");
    loadTree(state.currentDir, { silent: true });
    if (state.settings.lint) scheduleDiagnose(entry);
    return true;
  } catch (error) {
    toast(`Erreur d'enregistrement : ${error.message}`, 3500);
    return false;
  }
}

/* ---------- exécution / terminal ---------- */

function termClear() {
  $("terminal-body").textContent = "";
  state.lastPrompt = "";
}

function termAppend(text, className = "") {
  if (!text) return;
  const body = $("terminal-body");
  const nearBottom = body.scrollHeight - body.scrollTop - body.clientHeight < 48;
  const span = document.createElement("span");
  if (className) span.className = className;
  span.textContent = text;
  body.appendChild(span);
  while (body.textContent.length > 400000 && body.firstChild) {
    body.removeChild(body.firstChild);
  }
  if (nearBottom) body.scrollTop = body.scrollHeight;
}

function termStatus(text) {
  $("terminal-status").textContent = text;
}

/* ---------- mise en page éditeur / sortie ---------- */

function openPanel(tab = "terminal") {
  document.body.classList.remove("panel-hidden");
  state.panel = tab;
  document.querySelectorAll(".panel-tab").forEach((button) => {
    button.classList.toggle("active", button.dataset.panel === tab);
  });
  $("terminal-view").classList.toggle("hidden", tab !== "terminal");
  $("graphics-view").classList.toggle("hidden", tab !== "graphics");
  $("problems-view").classList.toggle("hidden", tab !== "problems");
  layoutSplit();
  if (tab === "graphics") gfxRender();
  if (tab === "terminal" && state.running) setTimeout(() => $("stdin-input").focus(), 60);
}

function closePanel() {
  document.body.classList.add("panel-hidden");
  layoutSplit();
}

function togglePanel() {
  if (document.body.classList.contains("panel-hidden")) openPanel(state.panel || "terminal");
  else closePanel();
}

function layoutSplit() {
  const main = $("main");
  const vertical = window.innerWidth >= 760 && window.innerWidth > window.innerHeight;
  state.splitVertical = vertical;
  main.dataset.split = vertical ? "v" : "h";
  $("splitter").setAttribute("aria-orientation", vertical ? "vertical" : "horizontal");
  const size = state.splitSize || (vertical ? 46 : 38);
  main.style.setProperty("--panel-size", `${size}%`);
  if (state.monacoReady) state.editor.layout();
}

function bindSplitter() {
  const splitter = $("splitter");
  const main = $("main");
  let dragging = false;

  const move = (event) => {
    if (!dragging) return;
    const rect = main.getBoundingClientRect();
    const point = event.touches ? event.touches[0] : event;
    let ratio;
    if (state.splitVertical) {
      ratio = ((rect.right - point.clientX) / rect.width) * 100;
    } else {
      ratio = ((rect.bottom - point.clientY) / rect.height) * 100;
    }
    ratio = clamp(ratio, 15, 82);
    state.splitSize = Math.round(ratio);
    main.style.setProperty("--panel-size", `${state.splitSize}%`);
    document.body.classList.remove("panel-hidden");
    state.settings.splitSize = state.splitSize;
    if (state.monacoReady) state.editor.layout();
  };

  const stop = () => {
    if (!dragging) return;
    dragging = false;
    document.body.classList.remove("dragging");
    saveSettings();
  };

  const startDrag = (event) => {
    dragging = true;
    document.body.classList.add("dragging");
    event.preventDefault();
  };

  splitter.addEventListener("pointerdown", startDrag);
  splitter.addEventListener("touchstart", startDrag, { passive: false });
  window.addEventListener("pointermove", move);
  window.addEventListener("touchmove", move, { passive: false });
  window.addEventListener("pointerup", stop);
  window.addEventListener("touchend", stop);
  splitter.addEventListener("dblclick", () => {
    state.splitSize = null;
    state.settings.splitSize = null;
    saveSettings();
    layoutSplit();
  });
  splitter.addEventListener("keydown", (event) => {
    if (event.key !== "ArrowUp" && event.key !== "ArrowDown") return;
    event.preventDefault();
    const delta = event.key === "ArrowUp" ? 4 : -4;
    state.splitSize = clamp((state.splitSize || 38) + delta, 15, 82);
    state.settings.splitSize = state.splitSize;
    main.style.setProperty("--panel-size", `${state.splitSize}%`);
    if (state.monacoReady) state.editor.layout();
  });
  window.addEventListener("resize", layoutSplit);
}

/* ---------- exécution / terminal ---------- */

function setRunning(running, { repl = false } = {}) {
  state.running = running;
  state.repl = repl;
  const button = $("btn-run");
  button.classList.toggle("busy", running);
  button.textContent = running ? "■" : "▶";
  button.title = running ? "Arrêter (Ctrl+C)" : "Exécuter (Ctrl+Entrée)";
  button.setAttribute("aria-label", running ? "Arrêter" : "Exécuter");
  $("stdin-form").classList.toggle("hidden", !running);
  $("btn-panel-stop").classList.toggle("hidden", !running);
  if (running) {
    $("stdin-prompt").textContent = repl ? ">>>" : "›";
    setTimeout(() => { if (state.running) $("stdin-input").focus(); }, 60);
  } else {
    state.pendingStdin = [];
    state.stdinHistoryIndex = -1;
    $("stdin-input").blur();
    $("stdin-input").value = "";
  }
}

function flushStdin() {
  if (!state.run) return;
  for (const data of state.pendingStdin.splice(0)) state.run.input(data);
}

/* L'invite affichée par le programme (« Votre nom ? ») devient l'invite du
 * champ de saisie : on se comporte comme le terminal intégré de PyramIDE. */
function trackPrompt(text) {
  if (!text) return;
  const lastLine = text.split("\n").pop();
  if (text.endsWith("\n")) {
    state.lastPrompt = "";
  } else if (lastLine !== undefined) {
    state.lastPrompt = lastLine.slice(-120);
  }
}

function showStdinPrompt() {
  const prompt = (state.lastPrompt || "").trim() || (state.repl ? ">>>" : "›");
  $("stdin-prompt").textContent = prompt;
  const input = $("stdin-input");
  input.placeholder = state.repl ? "Expression Python…" : "Réponse attendue par le programme…";
  if (!state.running) return;
  setTimeout(() => { if (state.running) input.focus(); }, 30);
}

function runActive() {
  const entry = activeEntry();
  if (!entry) return;
  if (state.running) {
    stopRun();
    return;
  }
  const payload = {};
  if (entry.path) payload.path = entry.path;
  if (!entry.path || entry.dirty) payload.code = entry.model.getValue();
  runPayload(payload, { label: entry.path || entry.name });
}

function runSelection() {
  const entry = activeEntry();
  if (!entry) return;
  if (state.running) {
    stopRun();
    return;
  }
  const selection = state.editor.getSelection();
  const code = selection && !selection.isEmpty()
    ? entry.model.getValueInRange(selection)
    : "";
  if (!code.trim()) {
    toast("Sélectionne d'abord du code à exécuter");
    return;
  }
  runPayload({ code, path: entry.path || null }, { label: "sélection" });
}

async function runWithArgs() {
  const entry = activeEntry();
  if (!entry) return;
  const value = await modalPrompt({
    title: "Exécuter avec des arguments",
    label: "Arguments de la ligne de commande",
    value: state.lastArgs || "",
    placeholder: "ex: --verbose fichier.txt",
    confirmLabel: "Exécuter",
    hint: "Sépare les arguments par des espaces. Les guillemets sont acceptés.",
  });
  if (value === null) return;
  state.lastArgs = value;
  const args = parseArgs(value);
  const payload = {};
  if (entry.path) payload.path = entry.path;
  if (!entry.path || entry.dirty) payload.code = entry.model.getValue();
  runPayload(payload, { label: entry.path || entry.name, args });
}

function parseArgs(text) {
  const args = [];
  let current = "";
  let quote = null;
  let started = false;
  for (const char of (text || "")) {
    if (quote) {
      if (char === quote) quote = null;
      else current += char;
      continue;
    }
    if (char === '"' || char === "'") {
      quote = char;
      started = true;
      continue;
    }
    if (/\s/.test(char)) {
      if (started) {
        args.push(current);
        current = "";
        started = false;
      }
      continue;
    }
    current += char;
    started = true;
  }
  if (started) args.push(current);
  return args;
}

function startConsole() {
  runPayload({ repl: true }, { repl: true, label: "Console Python" });
}

function runPayload(payload, { repl = false, label = "Python", args = [] } = {}) {
  if (state.running) stopRun();
  if (state.run) {
    try { state.run.dispose(); } catch (_) { /* ignoré */ }
    state.run = null;
  }
  state.runId += 1;
  const runId = state.runId;
  state.pendingStdin = [];
  state.lastPrompt = "";
  state.stdinHistoryIndex = -1;
  const runArgs = Array.isArray(args) ? args : [];

  openPanel("terminal");
  termClear();
  const argText = runArgs.length
    ? ` ${runArgs.map((arg) => (/\s/.test(arg) ? JSON.stringify(arg) : arg)).join(" ")}`
    : "";
  termAppend(repl ? "$ python -i\n" : `$ python ${label}${argText}\n`, "system");
  termStatus(repl ? "Console Python — en cours" : `Exécution — ${label}`);
  $("terminal-cwd").textContent = "";
  setRunning(true, { repl });

  const controller = PyTransport.run({
    code: payload.code,
    path: payload.path || null,
    args: runArgs,
    repl,
    timeout: state.settings.runTimeout,
  }, {
    onEvent: (event) => handleRunEvent(event, { runId, repl, label }),
  });
  state.run = controller;
  flushStdin();
}

function handleRunEvent(event, ctx) {
  if (state.runId !== ctx.runId) return;
  const { repl } = ctx;
  switch (event.type) {
    case "started":
      if (event.cwd) $("terminal-cwd").textContent = event.cwd;
      if (event.repl) termStatus("Console Python — en cours");
      flushStdin();
      break;
    case "stdout":
      termAppend(event.data || "");
      trackPrompt(event.data || "");
      break;
    case "stderr": {
      let text = event.data || "";
      if (repl) text = text.replace(/(^|\n)(>>> |\.\.\. )/g, "$1");
      if (text) termAppend(text, "stderr");
      break;
    }
    case "input_echo":
      // L'interface écho déjà la ligne au moment de l'envoi : on évite un doublon.
      state.lastPrompt = "";
      break;
    case "need_input":
      showStdinPrompt();
      break;
    case "gfx":
      gfxHandle(event);
      break;
    case "image":
      gfxShowImage(event);
      break;
    case "stdin_unavailable":
      termAppend("\nL'entrée standard interactive nécessite la WebSocket "
        + "(mode HTTP de secours) : le programme ne peut pas lire input().\n", "stderr");
      $("stdin-form").classList.add("hidden");
      break;
    case "stopping":
      termStatus("Arrêt demandé…");
      break;
    case "exit": {
      const duration = (event.duration || 0).toFixed(2);
      const exitText = event.timedOut
        ? `\n— délai dépassé après ${duration} s —\n`
        : `\n— code de sortie ${event.code} · ${duration} s —\n`;
      termAppend(exitText, event.code === 0 ? "exit success" : "exit");
      if (event.truncated) termAppend("Sortie tronquée par le serveur.\n", "stderr");
      termStatus(event.timedOut ? "Délai dépassé" : `Terminé (code ${event.code})`);
      setRunning(false);
      $("btn-panel-stop").classList.add("hidden");
      break;
    }
    case "disconnected":
      termAppend("\n— connexion terminée —\n", "exit");
      termStatus("Terminé");
      setRunning(false);
      break;
    case "error":
      termAppend(`\nErreur : ${event.message}\n`, "stderr");
      termStatus("Erreur");
      setRunning(false);
      break;
    default:
      break;
  }
}

function stopRun() {
  if (!state.running) return;
  termStatus("Arrêt demandé…");
  if (state.run && typeof state.run.stop === "function") state.run.stop();
  else setRunning(false);
  setTimeout(() => { if (state.running) setRunning(false); }, 2500);
}

function sendStdin(event) {
  if (event) event.preventDefault();
  if (!state.running) return;
  const input = $("stdin-input");
  const value = input.value;
  input.value = "";
  if (value.trim()) {
    state.stdinHistory.push(value);
    if (state.stdinHistory.length > 100) state.stdinHistory.shift();
  }
  state.stdinHistoryIndex = -1;
  termAppend(`${value}\n`, "stdin-echo");
  state.lastPrompt = "";
  if (state.run) state.run.input(`${value}\n`);
  else state.pendingStdin.push(`${value}\n`);
  input.focus();
}

function sendEof() {
  if (!state.running) return;
  termAppend("^D\n", "stdin-echo");
  if (state.run) state.run.closeInput();
  $("stdin-input").focus();
}

function stdinHistory(event) {
  if (!state.stdinHistory.length) return;
  if (event.key === "ArrowUp") {
    event.preventDefault();
    state.stdinHistoryIndex = state.stdinHistoryIndex < 0
      ? state.stdinHistory.length - 1
      : Math.max(0, state.stdinHistoryIndex - 1);
    $("stdin-input").value = state.stdinHistory[state.stdinHistoryIndex];
  } else if (event.key === "ArrowDown") {
    event.preventDefault();
    if (state.stdinHistoryIndex < 0) return;
    state.stdinHistoryIndex += 1;
    if (state.stdinHistoryIndex >= state.stdinHistory.length) {
      state.stdinHistoryIndex = -1;
      $("stdin-input").value = "";
    } else {
      $("stdin-input").value = state.stdinHistory[state.stdinHistoryIndex];
    }
  }
}

/* ---------- écran graphique ---------- */

function gfxEnsure() {
  if (state.gfx) return state.gfx;
  const canvas = $("graphics-canvas");
  const ctx = canvas.getContext("2d");
  state.gfx = { canvas, ctx, width: 640, height: 400, background: "#101018", images: 0, drawn: false };
  return state.gfx;
}

function gfxReset() {
  const gfx = gfxEnsure();
  gfx.width = 640;
  gfx.height = 400;
  gfx.background = "#101018";
  gfx.canvas.width = gfx.width;
  gfx.canvas.height = gfx.height;
  gfx.images = 0;
  gfx.drawn = false;
  $("graphics-images").textContent = "";
  $("graphics-status").textContent = "Aucun affichage";
  gfxRender();
}

function gfxSetStatus(text) {
  $("graphics-status").textContent = text;
}

function gfxHandle(event) {
  const gfx = gfxEnsure();
  if (event.op === "open") {
    gfx.width = event.width || 640;
    gfx.height = event.height || 400;
    gfx.background = event.background || "#101018";
    gfx.canvas.width = gfx.width;
    gfx.canvas.height = gfx.height;
    gfx.images = 0;
    gfxRender();
    gfxSetStatus(`Canevas ${gfx.width}×${gfx.height}`);
    openPanel("graphics");
    return;
  }
  if (event.op === "clear") {
    gfx.background = event.color || gfx.background;
    gfxRender();
    openPanel("graphics");
    return;
  }
  gfx.drawn = true;
  gfxDrawOp(event);
  if (event.op === "present") openPanel("graphics");
  $("graphics-empty").classList.add("hidden");
}

function gfxDrawOp(op) {
  const gfx = gfxEnsure();
  const ctx = gfx.ctx;
  const scale = gfx.canvas.width / Math.max(gfx.width, 1);
  const scaleY = gfx.canvas.height / Math.max(gfx.height, 1);
  ctx.save();
  ctx.setTransform(scale, 0, 0, scaleY, 0, 0);
  switch (op.op) {
    case "rect":
      ctx.beginPath();
      ctx.rect(op.x, op.y, op.w, op.h);
      if (op.fill) { ctx.fillStyle = op.color || "#fff"; ctx.fill(); }
      else { ctx.lineWidth = op.width || 1; ctx.strokeStyle = op.color || "#fff"; ctx.stroke(); }
      break;
    case "circle":
      ctx.beginPath();
      ctx.arc(op.x, op.y, Math.max(op.r, 0), 0, Math.PI * 2);
      if (op.fill) { ctx.fillStyle = op.color || "#fff"; ctx.fill(); }
      else { ctx.lineWidth = op.width || 1; ctx.strokeStyle = op.color || "#fff"; ctx.stroke(); }
      break;
    case "line":
      ctx.beginPath();
      ctx.moveTo(op.x1, op.y1);
      ctx.lineTo(op.x2, op.y2);
      ctx.lineWidth = op.width || 1;
      ctx.strokeStyle = op.color || "#fff";
      ctx.stroke();
      break;
    case "polygon": {
      const points = op.points || [];
      if (points.length < 2) break;
      ctx.beginPath();
      ctx.moveTo(points[0][0], points[0][1]);
      for (const [x, y] of points.slice(1)) ctx.lineTo(x, y);
      ctx.closePath();
      if (op.fill) { ctx.fillStyle = op.color || "#fff"; ctx.fill(); }
      else { ctx.lineWidth = 1; ctx.strokeStyle = op.color || "#fff"; ctx.stroke(); }
      break;
    }
    case "text":
      ctx.fillStyle = op.color || "#fff";
      ctx.font = `${op.size || 14}px ui-monospace, monospace`;
      ctx.textBaseline = "top";
      ctx.fillText(String(op.value ?? ""), op.x, op.y);
      break;
    case "pixel":
      ctx.fillStyle = op.color || "#fff";
      ctx.fillRect(op.x, op.y, 1, 1);
      break;
    case "image":
      gfxBlit(op);
      break;
    default:
      break;
  }
  ctx.restore();
}

function gfxBlit(op) {
  const gfx = gfxEnsure();
  const image = new Image();
  image.onload = () => {
    const scale = gfx.canvas.width / Math.max(gfx.width, 1);
    gfx.ctx.drawImage(image, op.x || 0, op.y || 0,
      image.width * scale, image.height * scale);
  };
  image.src = `data:image/png;base64,${op.data}`;
}

function gfxShowImage(event) {
  const gfx = gfxEnsure();
  const wrap = el("div", { class: "gfx-image" },
    event.title ? el("div", { class: "gfx-image-title", text: event.title }) : null,
    el("img", { src: `data:image/png;base64,${event.data}`, alt: event.title || "image" }),
  );
  $("graphics-images").appendChild(wrap);
  gfx.images += 1;
  $("graphics-empty").classList.add("hidden");
  gfxSetStatus(event.title ? `Image : ${event.title}` : "Image affichée");
  openPanel("graphics");
}

function gfxRender() {
  const gfx = gfxEnsure();
  gfx.ctx.setTransform(1, 0, 0, 1, 0, 0);
  gfx.ctx.fillStyle = gfx.background || "#101018";
  gfx.ctx.fillRect(0, 0, gfx.canvas.width, gfx.canvas.height);
  const empty = !gfx.drawn && gfx.images === 0;
  $("graphics-empty").classList.toggle("hidden", !empty);
}

function gfxSavePng() {
  const gfx = gfxEnsure();
  const link = document.createElement("a");
  link.download = `pyide-canvas-${Date.now()}.png`;
  link.href = gfx.canvas.toDataURL("image/png");
  link.click();
}

/* ---------- formatage ---------- */

async function formatActive() {
  const entry = activeEntry();
  if (!entry) return;
  const before = entry.model.getValue();
  try {
    const data = await api("/api/format", {
      method: "POST",
      body: JSON.stringify({ code: before }),
    });
    if (activeEntry() !== entry || state.editor.getModel() !== entry.model) {
      toast("Formatage annulé : le fichier actif a changé", 3000);
      return;
    }
    if (entry.model.getValue() !== before) {
      toast("Formatage annulé : le code a été modifié entre-temps", 3000);
      return;
    }
    if (data.error && !data.changed) {
      toast(`Formatage : ${data.error}`, 3500);
      return;
    }
    if (!data.changed) {
      toast("Le code est déjà formaté ✓");
      return;
    }
    state.editor.pushUndoStop();
    state.editor.executeEdits("format", [{
      range: entry.model.getFullModelRange(),
      text: data.code,
      forceMoveMarkers: true,
    }]);
    state.editor.pushUndoStop();
    toast("Code formaté ✓");
  } catch (error) {
    toast(`Formatage impossible : ${error.message}`, 3500);
  }
}

/* ---------- palette / ouverture rapide ---------- */

function showPalette() {
  if (!state.monacoReady) return;
  const commands = buildCommands();
  const input = el("input", {
    type: "search",
    placeholder: "Tape une commande…",
    autocomplete: "off",
    autocapitalize: "off",
    spellcheck: "false",
  });
  const list = el("ul", { class: "list" });
  const wrap = el("div", {}, input, el("div", { style: "height:8px" }), list);

  let visible = [];
  let selected = 0;

  function render(query = "", preserveSelection = false) {
    const needle = query.trim().toLowerCase();
    visible = commands.filter((command) => {
      const haystack = `${command.title} ${command.hint || ""}`.toLowerCase();
      return !needle || haystack.includes(needle);
    });
    if (!preserveSelection) selected = 0;
    selected = visible.length ? clamp(selected, 0, visible.length - 1) : 0;
    list.textContent = "";
    if (!visible.length) {
      list.appendChild(el("li", { class: "empty-state", text: "Aucune commande" }));
      return;
    }
    visible.forEach((command, index) => {
      const item = el("li", { class: index === selected ? "selected" : "" },
        el("div", { class: "row-end" },
          el("span", { class: "title", text: command.title }),
          command.hint ? el("span", { class: "sub", text: command.hint }) : null,
        ),
      );
      item.addEventListener("click", () => execute(command));
      list.appendChild(item);
    });
    list.querySelector(".selected")?.scrollIntoView({ block: "nearest" });
  }

  function execute(command) {
    closeModal();
    setTimeout(() => {
      Promise.resolve(command.run()).catch((error) => toast(error.message, 3500));
    }, 0);
  }

  input.addEventListener("input", () => render(input.value));
  input.addEventListener("keydown", (event) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      selected = Math.min(selected + 1, visible.length - 1);
      render(input.value, true);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      selected = Math.max(selected - 1, 0);
      render(input.value, true);
    } else if (event.key === "Enter") {
      event.preventDefault();
      if (visible[selected]) execute(visible[selected]);
    }
  });

  openModal({ title: "Palette de commandes", body: wrap, wide: true });
  render();
  setTimeout(() => input.focus(), 50);
}

function buildCommands() {
  const commands = [
    { title: "Enregistrer", hint: "Ctrl+S", run: () => saveActive() },
    { title: "Enregistrer sous…", run: () => saveEntry(activeEntry(), { saveAs: true }) },
    { title: "Nouveau fichier", hint: "＋", run: () => newFileDialog() },
    { title: "Nouveau dossier", run: () => newFolderDialog() },
    { title: "Ouvrir un fichier…", hint: "Ctrl+P", run: () => showQuickOpen() },
    { title: "Rechercher dans les fichiers…", hint: "Ctrl+Maj+F", run: () => showSearch() },
    { title: "Exécuter le fichier", hint: "Ctrl+Entrée", run: () => runActive() },
    { title: "Exécuter la sélection", run: () => runSelection() },
    { title: "Exécuter avec des arguments…", run: () => runWithArgs() },
    { title: "Arrêter l'exécution", run: () => stopRun() },
    { title: "Console Python interactive", run: () => startConsole() },
    { title: "Aide sur le symbole (documentation)", run: () => runEditorAction("editor.action.showHover") },
    { title: "Aller à la définition", run: () => runEditorAction("editor.action.revealDefinition") },
    { title: "Formater le code (autopep8)", run: () => formatActive() },
    { title: "Basculer le terminal", run: () => (state.panel === "terminal" && !$("panel").classList.contains("hidden") ? closePanel() : openPanel("terminal")) },
    { title: "Voir les problèmes", run: () => openPanel("problems") },
    { title: "Afficher / masquer les fichiers", hint: "Ctrl+Maj+E", run: () => toggleSidebar() },
    { title: "Exemples de code", run: () => showSnippets() },
    { title: "Paquets Python (pip)", run: () => showPackages() },
    { title: "Assistant IA", run: () => showAI() },
    { title: "Paramètres", run: () => showSettings() },
    { title: "Basculer le thème clair / sombre", run: () => toggleTheme() },
    { title: "Aller à la ligne…", run: () => goToLine() },
    { title: "Commenter la ligne", run: () => runEditorAction("editor.action.commentLine") },
    { title: "Rechercher dans le fichier", hint: "Ctrl+F", run: () => runEditorAction("actions.find") },
    { title: "Fermer l'onglet", hint: "Ctrl+W", run: () => state.active && closeEntry(state.active) },
    { title: "À propos", run: () => showAbout() },
  ];
  return commands;
}

function showQuickOpen() {
  if (!state.monacoReady) return;
  let allFiles = [];
  let filtered = [];
  let selected = 0;

  const input = el("input", {
    type: "search",
    placeholder: "Nom du fichier…",
    autocomplete: "off",
    autocapitalize: "off",
    spellcheck: "false",
  });
  const list = el("ul", { class: "list" });
  const status = el("div", { class: "empty-state", text: "Chargement…" });
  const body = el("div", {}, input, el("div", { style: "height:8px" }), status, list);

  function render(query = "", preserveSelection = false) {
    const needle = query.trim().toLowerCase();
    filtered = allFiles.filter((file) => !needle || file.path.toLowerCase().includes(needle)).slice(0, 300);
    if (!preserveSelection) selected = 0;
    selected = filtered.length ? clamp(selected, 0, filtered.length - 1) : 0;
    list.textContent = "";
    status.classList.toggle("hidden", filtered.length > 0);
    if (!filtered.length) status.textContent = "Aucun fichier";
    filtered.forEach((file, index) => {
      const item = el("li", { class: index === selected ? "selected" : "" },
        el("div", { class: "title", text: file.name }),
        el("div", { class: "sub", text: file.path }),
      );
      item.addEventListener("click", () => choose(file));
      list.appendChild(item);
    });
    list.querySelector(".selected")?.scrollIntoView({ block: "nearest" });
  }

  function choose(file) {
    closeModal();
    openFile(file.path, { focus: true });
  }

  input.addEventListener("input", () => render(input.value));
  input.addEventListener("keydown", (event) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      selected = Math.min(selected + 1, filtered.length - 1);
      render(input.value, true);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      selected = Math.max(selected - 1, 0);
      render(input.value, true);
    } else if (event.key === "Enter") {
      event.preventDefault();
      if (filtered[selected]) choose(filtered[selected]);
    }
  });

  openModal({ title: "Ouvrir un fichier", body, wide: true });
  setTimeout(() => input.focus(), 50);

  api("/api/files")
    .then((data) => {
      allFiles = data.files || [];
      status.textContent = "Aucun fichier";
      render();
    })
    .catch((error) => {
      status.textContent = error.message;
    });
}

function showSearch() {
  const input = el("input", {
    type: "search",
    placeholder: "Rechercher dans les fichiers…",
    autocomplete: "off",
    autocapitalize: "off",
    spellcheck: "false",
  });
  const status = el("div", { class: "empty-state", text: "Tape au moins 1 caractère." });
  const list = el("ul", { class: "list" });
  const body = el("div", {}, input, el("div", { style: "height:8px" }), status, list);

  let timer = null;
  let sequence = 0;

  async function search() {
    const query = input.value.trim();
    if (!query) {
      list.textContent = "";
      status.classList.remove("hidden");
      status.textContent = "Tape au moins 1 caractère.";
      return;
    }
    const current = ++sequence;
    status.classList.remove("hidden");
    status.textContent = "Recherche…";
    list.textContent = "";
    let data;
    try {
      data = await api(`/api/search?q=${encodeURIComponent(query)}&dir=${encodeURIComponent(state.currentDir)}&hidden=${state.settings.showHidden ? 1 : 0}`);
    } catch (error) {
      if (current !== sequence) return;
      status.textContent = error.message;
      return;
    }
    if (current !== sequence) return;
    const results = data.results || [];
    status.classList.toggle("hidden", results.length > 0);
    status.textContent = "Aucun résultat";
    results.forEach((result) => {
      const item = el("li", { class: "search-result" },
        el("div", { class: "path", text: `${result.path}:${result.line}` }),
        el("div", { class: "sub" }, highlight(result.text, query)),
      );
      item.addEventListener("click", () => {
        closeModal();
        openFile(result.path, { line: result.line, focus: true });
      });
      list.appendChild(item);
    });
  }

  input.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(search, 300);
  });
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      clearTimeout(timer);
      search();
    }
  });

  openModal({ title: "Rechercher dans les fichiers", body, wide: true });
  setTimeout(() => input.focus(), 50);
}

function highlight(text, query) {
  const fragment = document.createDocumentFragment();
  if (!query) {
    fragment.appendChild(document.createTextNode(text));
    return fragment;
  }
  const lower = text.toLowerCase();
  const needle = query.toLowerCase();
  let index = 0;
  while (index < text.length) {
    const found = lower.indexOf(needle, index);
    if (found < 0) {
      fragment.appendChild(document.createTextNode(text.slice(index)));
      break;
    }
    if (found > index) fragment.appendChild(document.createTextNode(text.slice(index, found)));
    fragment.appendChild(el("mark", { text: text.slice(found, found + query.length) }));
    index = found + query.length;
  }
  return fragment;
}

/* ---------- snippets / exemples ---------- */

async function showSnippets() {
  let data;
  try {
    data = await api("/api/snippets");
  } catch (error) {
    toast(`Exemples : ${error.message}`, 3500);
    return;
  }
  const snippets = data.snippets || [];
  const input = el("input", {
    type: "search",
    placeholder: "Filtrer les exemples…",
    autocomplete: "off",
    spellcheck: "false",
  });
  const list = el("ul", { class: "list" });
  const body = el("div", {}, input, el("div", { style: "height:8px" }), list);

  function render(query = "") {
    const needle = query.trim().toLowerCase();
    list.textContent = "";
    const filtered = snippets.filter((snippet) =>
      !needle || `${snippet.title} ${snippet.description} ${snippet.category}`.toLowerCase().includes(needle)
    );
    if (!filtered.length) {
      list.appendChild(el("li", { class: "empty-state", text: "Aucun exemple" }));
      return;
    }
    for (const snippet of filtered) {
      const insert = el("button", { class: "text-btn primary", text: "Insérer", type: "button" });
      insert.addEventListener("click", (event) => {
        event.stopPropagation();
        closeModal();
        insertCode(snippet.code);
        toast(`Exemple « ${snippet.title} » inséré`);
      });
      const create = el("button", { class: "text-btn", text: "Fichier", type: "button" });
      create.addEventListener("click", async (event) => {
        event.stopPropagation();
        closeModal();
        await createFileWithContent(snippet.filename, snippet.code);
      });
      const item = el("li", {},
        el("div", { class: "row-end" },
          el("span", { class: "title", text: snippet.title }),
          el("span", { class: "sub", text: snippet.category }),
        ),
        el("div", { class: "sub", text: snippet.description }),
        el("div", { class: "btn-row", style: "margin-top:7px" }, insert, create),
      );
      list.appendChild(item);
    }
  }

  input.addEventListener("input", () => render(input.value));
  openModal({ title: "Exemples de code", body, wide: true });
  render();
  setTimeout(() => input.focus(), 50);
}

function insertCode(code) {
  if (!state.editor) return;
  const selection = state.editor.getSelection();
  if (!selection) return;
  const text = code.endsWith("\n") ? code : `${code}\n`;
  state.editor.pushUndoStop();
  state.editor.executeEdits("snippet", [{
    range: selection,
    text,
    forceMoveMarkers: true,
  }]);
  state.editor.pushUndoStop();
  state.editor.focus();
}

async function createFileWithContent(filename, content) {
  const value = await modalPrompt({
    title: "Créer un fichier",
    label: "Chemin du fichier",
    value: joinPath(state.currentDir, filename),
    confirmLabel: "Créer",
  });
  if (!value) return;
  const path = normalizePath(value, state.currentDir);
  try {
    if (await fileExists(path)) {
      const overwrite = await modalConfirm({
        title: "Fichier existant",
        message: `« ${path} » existe déjà. Le remplacer ?`,
        confirmLabel: "Remplacer",
        danger: true,
      });
      if (!overwrite) return;
    }
    await api("/api/file", {
      method: "POST",
      body: JSON.stringify({ path, content }),
    });
    await loadTree(state.currentDir, { silent: true });
    await openFile(path, { focus: true });
    toast("Fichier créé ✓");
  } catch (error) {
    toast(`Création impossible : ${error.message}`, 3500);
  }
}

/* ---------- paquets ---------- */

async function showPackages() {
  const tabs = el("div", { class: "pkg-tabs" });
  const status = el("div", { class: "empty-state", text: "Chargement…" });
  const list = el("ul", { class: "list pkg-list" });
  const output = el("pre", { class: "code-preview hidden" });
  const searchRow = el("div", { class: "btn-row" });
  const searchInput = el("input", { type: "search", placeholder: "Rechercher sur PyPI (ex: requests)" });
  const searchButton = el("button", { class: "text-btn primary", type: "button", text: "Rechercher" });
  searchRow.append(searchInput, searchButton);

  const body = el("div", { class: "pkg-body" },
    status, searchRow, output, list,
  );

  let packages = [];
  let catalog = [];
  let backend = "pip";
  let mode = "installed";
  let results = [];

  function badge(text, kind = "") {
    return el("span", { class: `pkg-badge ${kind}`, text });
  }

  function setTab(next) {
    mode = next;
    document.querySelectorAll(".pkg-tabs button").forEach((button) => {
      button.classList.toggle("active", button.dataset.tab === next);
    });
    render();
  }

  async function install(spec, upgrade = false) {
    showLoading(`Installation de ${spec}…`);
    status.classList.remove("hidden");
    status.textContent = `Installation de ${spec}… (cela peut prendre plusieurs minutes)`;
    output.classList.add("hidden");
    try {
      const result = await api("/api/packages/install", {
        method: "POST",
        body: JSON.stringify({ name: spec, upgrade }),
      });
      output.textContent = result.output || "";
      output.classList.remove("hidden");
      status.textContent = result.ok
        ? `Installation terminée ✓`
        : "Échec de l'installation (détails ci-dessus)";
      if (result.ok) {
        state.health = null;
        await refresh();
      }
    } catch (error) {
      status.textContent = error.message;
    } finally {
      hideLoading();
    }
  }

  async function remove(pkg) {
    const ok = await modalConfirm({
      title: "Désinstaller",
      message: `Désinstaller ${pkg.name} ${pkg.version || ""} ?`,
      confirmLabel: "Désinstaller",
      danger: true,
    });
    if (!ok) return;
    showLoading(`Désinstallation de ${pkg.name}…`);
    try {
      const result = await api("/api/packages/uninstall", {
        method: "POST",
        body: JSON.stringify({ name: pkg.name }),
      });
      output.textContent = result.output || "";
      output.classList.remove("hidden");
      await refresh();
    } catch (error) {
      status.classList.remove("hidden");
      status.textContent = error.message;
    } finally {
      hideLoading();
    }
  }

  function renderInstalled() {
    list.textContent = "";
    if (!packages.length) {
      list.appendChild(el("li", { class: "empty-state", text: "Aucun paquet installé" }));
      return;
    }
    const needle = (searchInput.value || "").trim().toLowerCase();
    packages
      .filter((pkg) => !needle || mode !== "installed" || pkg.name.toLowerCase().includes(needle)
        || (pkg.source || "").includes("search"))
      .forEach((pkg) => {
        const actions = el("div", { class: "pkg-actions" },
          el("button", { class: "text-btn", type: "button", text: "Mettre à jour",
            onclick: () => install(`${pkg.name}`, true) }),
          el("button", { class: "text-btn danger", type: "button", text: "Retirer",
            onclick: () => remove(pkg) }),
        );
        list.appendChild(el("li", {},
          el("div", { class: "pkg-line" },
            el("span", { class: "title", text: pkg.name }),
            pkg.graphics ? badge("Graphique", "gfx") : null,
            el("span", { class: "pkg-version", text: pkg.version || "" }),
            actions,
          ),
        ));
      });
  }

  function renderCatalog() {
    list.textContent = "";
    catalog.forEach((item) => {
      const supported = item.supported !== false;
      const button = el("button", {
        class: "text-btn primary", type: "button",
        text: item.installed ? "Réinstaller" : "Installer",
      });
      button.disabled = !supported;
      button.addEventListener("click", () => install(item.name));
      list.appendChild(el("li", { class: "pkg-card" },
        el("div", { class: "pkg-line" },
          el("span", { class: "title", text: item.label || item.name }),
          item.graphics ? badge("Écran graphique", "gfx") : null,
          item.pure === false ? badge(backend === "wheels" ? "Native" : "Roue binaire", "native") : null,
          el("span", { class: "pkg-version", text: item.category || "" }),
        ),
        el("div", { class: "pkg-desc", text: item.description || "" }),
        el("div", { class: "pkg-actions" },
          supported ? button : el("span", { class: "hint", text: "Nécessite une compilation native : indisponible ici." }),
        ),
      ));
    });
  }

  function renderSearch() {
    list.textContent = "";
    if (!results.length) {
      list.appendChild(el("li", { class: "empty-state", text: "Aucun résultat" }));
      return;
    }
    results.forEach((item) => {
      const button = el("button", { class: "text-btn primary", type: "button", text: "Installer" });
      button.addEventListener("click", () => install(item.name));
      list.appendChild(el("li", { class: "pkg-card" },
        el("div", { class: "pkg-line" },
          el("span", { class: "title", text: item.name }),
          el("span", { class: "pkg-version", text: item.version || "" }),
          item.graphics ? badge("Graphique", "gfx") : null,
          item.pure ? badge("Pur Python", "pure") : null,
        ),
        el("div", { class: "pkg-desc", text: item.summary || "" }),
        el("div", { class: "pkg-actions" }, button),
      ));
    });
  }

  function render() {
    if (mode === "catalog") renderCatalog();
    else if (mode === "search") renderSearch();
    else renderInstalled();
  }

  async function refresh() {
    status.classList.remove("hidden");
    status.textContent = "Chargement des paquets…";
    try {
      const data = await api("/api/packages");
      packages = data.packages || [];
      backend = data.backend || "pip";
      if (data.error) {
        status.textContent = data.error;
      } else {
        status.classList.add("hidden");
      }
      const catalogData = await api("/api/packages/catalog");
      catalog = catalogData.catalog || [];
      render();
    } catch (error) {
      status.textContent = error.message;
    }
  }

  async function doSearch() {
    const query = searchInput.value.trim();
    if (!query) return;
    mode = "search";
    document.querySelectorAll(".pkg-tabs button").forEach((button) => {
      button.classList.toggle("active", button.dataset.tab === "search");
    });
    status.classList.remove("hidden");
    status.textContent = `Recherche de « ${query} » sur PyPI…`;
    try {
      const data = await api(`/api/packages/search?q=${encodeURIComponent(query)}`);
      results = data.results || [];
      status.classList.add("hidden");
      renderSearch();
    } catch (error) {
      status.textContent = error.message;
    }
  }

  ["installed:Installés", "catalog:Catalogue", "search:Rechercher"].forEach(([key, label]) => {
    const button = el("button", { type: "button", text: label, "data-tab": key });
    if (key === "installed") button.classList.add("active");
    button.addEventListener("click", () => setTab(key));
    tabs.appendChild(button);
  });
  searchButton.addEventListener("click", doSearch);
  searchInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") { event.preventDefault(); doSearch(); }
  });

  openModal({
    title: "Modules et paquets",
    body: el("div", {}, tabs, body),
    wide: true,
    footer: [{ label: "Fermer", primary: true, onClick: () => closeModal() }],
  });
  refresh();
}

/* ---------- assistant IA ---------- */

async function refreshAIStatus() {
  try {
    state.aiStatus = await api("/api/ai/status");
  } catch (_) {
    state.aiStatus = { available: false, hint: "Serveur injoignable" };
  }
}

async function showAI() {
  await refreshAIStatus();
  const status = state.aiStatus || {};

  if (!status.available) {
    const body = el("div", {},
      el("p", { text: "Aucun assistant IA n'est configuré sur le serveur." }),
      el("p", { class: "hint", style: "margin-top:8px", text: status.hint || "" }),
      el("p", { class: "hint", style: "margin-top:8px", text: "Astuce : Ollama fonctionne hors ligne sur le téléphone. Sinon, utilise une API compatible OpenAI via PYIDE_AI_URL." }),
    );
    openModal({
      title: "Assistant IA",
      body,
      footer: [
        { label: "Fermer", onClick: () => closeModal() },
        { label: "Paramètres", primary: true, onClick: () => { closeModal(); showSettings(); } },
      ],
    });
    return;
  }

  const mode = el("select", {},
    el("option", { value: "explain", text: "Expliquer le code" }),
    el("option", { value: "fix", text: "Corriger les bugs" }),
    el("option", { value: "tests", text: "Générer des tests" }),
    el("option", { value: "review", text: "Revue de code" }),
    el("option", { value: "optimize", text: "Optimiser" }),
    el("option", { value: "generate", text: "Générer du code" }),
  );
  const question = el("textarea", {
    placeholder: "Question ou description (facultatif)…",
    rows: "3",
  });
  const answer = el("pre", { class: "ai-answer hidden" });
  const info = el("div", { class: "ai-meta", text: `Modèle : ${status.model} (${status.provider})` });
  const runButton = el("button", { class: "text-btn primary", text: "Demander", type: "button" });
  const insertButton = el("button", { class: "text-btn hidden", text: "Insérer le code", type: "button" });
  const copyButton = el("button", { class: "text-btn hidden", text: "Copier", type: "button" });
  const body = el("div", {},
    info,
    el("div", { class: "field" }, el("label", { text: "Mode" }), mode),
    el("div", { class: "field" }, el("label", { text: "Question" }), question),
    el("div", { class: "btn-row" }, runButton, insertButton, copyButton),
    el("div", { style: "height:10px" }),
    answer,
    el("p", { class: "hint", style: "margin-top:8px", text: "Le code est envoyé au fournisseur configuré. Rien n'est envoyé sans ton clic." }),
  );

  runButton.addEventListener("click", async () => {
    const entry = activeEntry();
    let selection = "";
    if (entry && state.editor && state.editor.getModel()) {
      const range = state.editor.getSelection();
      if (range) selection = state.editor.getModel().getValueInRange(range);
    }
    runButton.disabled = true;
    answer.classList.remove("hidden");
    answer.textContent = "Réflexion en cours…";
    insertButton.classList.add("hidden");
    copyButton.classList.add("hidden");
    try {
      const data = await api("/api/ai", {
        method: "POST",
        body: JSON.stringify({
          mode: mode.value,
          question: question.value,
          code: entry ? entry.model.getValue().slice(0, 20000) : "",
          selection: selection && selection.length < 20000 ? selection : "",
          path: entry ? entry.path : null,
        }),
      });
      state.aiText = data.text || "";
      answer.textContent = state.aiText;
      insertButton.classList.remove("hidden");
      copyButton.classList.remove("hidden");
    } catch (error) {
      answer.textContent = `Erreur : ${error.message}`;
    } finally {
      runButton.disabled = false;
    }
  });

  insertButton.addEventListener("click", () => {
    const code = extractCode(state.aiText);
    if (!code) return;
    closeModal();
    insertCode(code);
    toast("Code inséré");
  });

  copyButton.addEventListener("click", () => copyText(state.aiText));

  openModal({ title: "Assistant IA", body, wide: true });
}

function extractCode(text) {
  const match = text.match(/```(?:python|py)?\s*\n([\s\S]*?)```/i);
  return (match ? match[1] : text).trim();
}

/* ---------- recherche / navigation ---------- */

async function goToLine() {
  const entry = activeEntry();
  if (!entry) return;
  const value = await modalPrompt({
    title: "Aller à la ligne",
    label: "Numéro de ligne",
    value: String(state.editor.getPosition()?.lineNumber || 1),
    confirmLabel: "Aller",
  });
  if (!value) return;
  const line = clamp(parseInt(value, 10) || 1, 1, entry.model.getLineCount());
  state.editor.setPosition({ lineNumber: line, column: 1 });
  state.editor.revealLineInCenter(line);
  state.editor.focus();
}

function runEditorAction(actionId) {
  if (!state.editor) return;
  state.editor.focus();
  const action = state.editor.getAction(actionId);
  if (action) {
    action.run().catch(() => {});
    return;
  }
  // Certaines commandes Monaco (définition, référence, renommage…) ne sont
  // pas exposées par getAction() alors qu'elles existent dans le registre.
  try {
    state.editor.trigger("pyide", actionId, null);
  } catch (_) {
    /* commande indisponible dans cette version de Monaco */
  }
}

function toggleTheme() {
  state.settings.theme = state.settings.theme === "light" ? "dark" : "light";
  saveSettings();
  applySettings();
  toast(state.settings.theme === "light" ? "Thème clair" : "Thème sombre");
}

/* ---------- paramètres / à propos ---------- */

function showSettings() {
  const settings = state.settings;
  const fontSize = el("input", { type: "number", min: "11", max: "24", value: settings.fontSize });
  const tabSize = el("select", {},
    el("option", { value: "2", text: "2 espaces" }),
    el("option", { value: "4", text: "4 espaces" }),
    el("option", { value: "8", text: "8 espaces" }),
  );
  tabSize.value = String(settings.tabSize);
  const theme = el("select", {},
    el("option", { value: "dark", text: "Sombre" }),
    el("option", { value: "light", text: "Clair" }),
  );
  theme.value = settings.theme;
  const autosave = el("select", {},
    el("option", { value: "0", text: "Désactivée" }),
    el("option", { value: "1", text: "Après 1 s" }),
    el("option", { value: "3", text: "Après 3 s" }),
    el("option", { value: "5", text: "Après 5 s" }),
  );
  autosave.value = String(settings.autosave);
  const timeout = el("input", { type: "number", min: "5", max: "300", value: settings.runTimeout });
  const token = el("input", { type: "password", value: state.token, placeholder: "Jeton PYIDE_TOKEN (facultatif)" });
  const wordWrap = el("input", { type: "checkbox" });
  wordWrap.checked = settings.wordWrap;
  const lint = el("input", { type: "checkbox" });
  lint.checked = settings.lint;
  const hidden = el("input", { type: "checkbox" });
  hidden.checked = settings.showHidden;
  const keybar = el("input", { type: "checkbox" });
  keybar.checked = settings.keybar;

  const body = el("div", {},
    el("div", { class: "settings-grid" },
      el("div", { class: "field" }, el("label", { text: "Taille de police" }), fontSize),
      el("div", { class: "field" }, el("label", { text: "Tabulation" }), tabSize),
      el("div", { class: "field" }, el("label", { text: "Thème" }), theme),
      el("div", { class: "field" }, el("label", { text: "Sauvegarde auto" }), autosave),
      el("div", { class: "field" }, el("label", { text: "Délai d'exécution (s)" }), timeout),
    ),
    el("div", { class: "field row" }, el("label", { text: "Retour à la ligne" }), wordWrap),
    el("div", { class: "field row" }, el("label", { text: "Diagnostics en direct (pyflakes)" }), lint),
    el("div", { class: "field row" }, el("label", { text: "Afficher les fichiers cachés" }), hidden),
    el("div", { class: "field row" }, el("label", { text: "Afficher le clavier rapide" }), keybar),
    el("div", { class: "field" },
      el("label", { text: "Jeton d'accès (serveur exposé sur le Wi-Fi)" }),
      token,
      el("div", { class: "hint", text: "Doit correspondre à PYIDE_TOKEN. Laisse vide en local." }),
    ),
    el("div", { class: "hint", style: "margin-top:10px" },
      `Projets : ${state.health?.root || "—"} · Version ${state.health?.version || "3.0.0"}`
      + ` · ${PyTransport.native ? "application Android" : "serveur local"}`),
  );

  openModal({
    title: "Paramètres",
    body,
    footer: [
      { label: "Annuler", onClick: () => closeModal() },
      { label: "Enregistrer", primary: true, onClick: () => {
        const previousHidden = settings.showHidden;
        state.settings = {
          ...settings,
          fontSize: clamp(Number(fontSize.value) || 14, 11, 24),
          tabSize: [2, 4, 8].includes(Number(tabSize.value)) ? Number(tabSize.value) : 4,
          theme: theme.value === "light" ? "light" : "dark",
          autosave: [0, 1, 3, 5].includes(Number(autosave.value)) ? Number(autosave.value) : 0,
          runTimeout: clamp(Number(timeout.value) || 30, 5, 300),
          wordWrap: wordWrap.checked,
          lint: lint.checked,
          showHidden: hidden.checked,
          keybar: keybar.checked,
          splitSize: state.splitSize,
        };
        state.token = token.value.trim();
        PyTransport.setToken(state.token);
        if (state.token) localStorage.setItem(TOKEN_KEY, state.token);
        else localStorage.removeItem(TOKEN_KEY);
        saveSettings();
        applySettings();
        closeModal();
        toast("Paramètres enregistrés ✓");
        if (previousHidden !== state.settings.showHidden) loadTree(state.currentDir, { silent: true });
        loadHealth();
      } },
    ],
  });
}

function showAbout() {
  const version = state.health?.version || "3.0.0";
  const python = state.health?.python || "—";
  const body = el("div", {},
    el("p", {}, el("strong", { text: `Mobile Py IDE ${version}` })),
    el("p", { class: "hint", style: "margin-top:4px", text: `Python ${python} · Monaco local (fonctionne hors ligne)` }),
    el("h3", { style: "margin:14px 0 6px;font-size:14px", text: "Fonctionnalités" }),
    el("ul", { style: "padding-left:18px;line-height:1.7;font-size:12.5px" },
      el("li", { text: "Édition multi-onglets, undo/redo, formatage autopep8" }),
      el("li", { text: "Complétion Jedi, signature, hover, go-to-definition" }),
      el("li", { text: "Diagnostics pyflakes en direct + liste des problèmes" }),
      el("li", { text: "Exécution avec terminal interactif, stdin, stop et timeout" }),
      el("li", { text: "Gestion de fichiers : créer, renommer, supprimer, importer, chercher" }),
      el("li", { text: "Éditeur et sortie séparés, redimensionnables (glisser la poignée)" }),
      el("li", { text: "Entrée interactive comme PyramIDE : input() s'écrit dans la sortie" }),
      el("li", { text: "Accès aux dossiers du téléphone, import de fichiers" }),
      el("li", { text: "Modules et paquets : catalogue, recherche PyPI, paquets graphiques" }),
      el("li", { text: "Écran graphique : pyide_gui, matplotlib, images Pillow" }),
      el("li", { text: "Exemples de code, assistant IA optionnel" }),
    ),
    el("h3", { style: "margin:14px 0 6px;font-size:14px", text: "Raccourcis" }),
    el("ul", { style: "padding-left:18px;line-height:1.7;font-size:12.5px" },
      el("li", { text: "Ctrl+S : enregistrer" }),
      el("li", { text: "Ctrl+Entrée : exécuter" }),
      el("li", { text: "Ctrl+K : palette de commandes" }),
      el("li", { text: "Ctrl+P : ouverture rapide" }),
      el("li", { text: "Ctrl+Maj+F : recherche dans les fichiers" }),
      el("li", { text: "Ctrl+W : fermer l'onglet" }),
    ),
    el("p", { class: "hint", style: "margin-top:14px", text: "Inspiré des IDE mobiles comme PyramIDE, avec un moteur Python Termux et une interface web locale." }),
  );
  openModal({ title: "À propos", body, footer: [{ label: "Fermer", primary: true, onClick: () => closeModal() }] });
}

/* ---------- menu / actions ---------- */

function showMoreMenu() {
  showSheet("Actions", [
    { icon: "▶", label: "Exécuter", run: () => runActive() },
    { icon: "✂", label: "Exécuter la sélection", run: () => runSelection() },
    { icon: "⚙", label: "Exécuter avec des arguments…", run: () => runWithArgs() },
    { icon: "⌨", label: "Console Python", run: () => startConsole() },
    { icon: "{ }", label: "Formater le code", run: () => formatActive() },
    { icon: "📚", label: "Exemples de code", run: () => showSnippets() },
    { icon: "🔎", label: "Rechercher dans les fichiers", run: () => showSearch() },
    { icon: "📦", label: "Modules et paquets", run: () => showPackages() },
    { icon: "🗂", label: "Ouvrir un dossier…", run: () => addPlaceDialog() },
    { icon: "⬆", label: "Importer un fichier du téléphone", run: () => importFromDevice() },
    { icon: "🖼", label: "Écran graphique", run: () => { openPanel("graphics"); gfxRender(); } },
    { icon: "🤖", label: "Assistant IA", run: () => showAI() },
    { icon: "⌘", label: "Palette de commandes", run: () => showPalette() },
    { icon: "⚙", label: "Paramètres", run: () => showSettings() },
    { icon: "ℹ", label: "À propos", run: () => showAbout() },
  ]);
}

function showTabActions(entry) {
  const actions = [
    { icon: "💾", label: "Enregistrer", run: () => saveEntry(entry) },
    { icon: "📄", label: "Enregistrer sous…", run: () => saveEntry(entry, { saveAs: true }) },
    { icon: "📋", label: "Copier le chemin", run: () => copyText(entry.path || entry.name) },
    { icon: "✕", label: "Fermer", run: () => closeEntry(entry.key) },
  ];
  const others = state.tabs.filter((key) => key !== entry.key);
  if (others.length) {
    actions.push({
      icon: "✕", label: "Fermer les autres", run: async () => {
        for (const key of others) await closeEntry(key);
      },
    });
  }
  showSheet(entry.name, actions);
}

/* ---------- raccourcis clavier / init ---------- */

function onKeyDown(event) {
  const target = event.target;
  const isModalInput = state.modalOpen;

  if (event.key === "Escape") {
    if (isModalInput) {
      event.preventDefault();
      closeModal();
      return;
    }
    if (!$("panel").classList.contains("hidden")) {
      closePanel();
      return;
    }
    if (!$("sidebar").classList.contains("hidden")) {
      closeSidebar();
      return;
    }
  }

  if (isModalInput) return;

  const typing = target && target.matches && target.matches("input, textarea, select")
    && !target.closest(".monaco-editor");
  if (typing) return;

  const modifier = event.ctrlKey || event.metaKey;
  if (!modifier) {
    if (event.key === "F1") {
      event.preventDefault();
      showPalette();
    }
    return;
  }

  const key = event.key.toLowerCase();
  if (key === "s") {
    event.preventDefault();
    saveActive();
  } else if (key === "enter") {
    event.preventDefault();
    runActive();
  } else if (key === "k") {
    event.preventDefault();
    showPalette();
  } else if (key === "p" && !event.shiftKey) {
    event.preventDefault();
    showQuickOpen();
  } else if (key === "p" && event.shiftKey) {
    event.preventDefault();
    showPalette();
  } else if (key === "f" && event.shiftKey) {
    event.preventDefault();
    showSearch();
  } else if (key === "w") {
    event.preventDefault();
    if (state.active) closeEntry(state.active);
  } else if (key === "e" && event.shiftKey) {
    event.preventDefault();
    toggleSidebar();
  }
}

function bindKeybar() {
  $("keybar").addEventListener("click", (event) => {
    const button = event.target.closest("button");
    if (!button || !state.editor) return;
    const key = button.dataset.key;
    const action = button.dataset.action;
    const editor = state.editor;
    const model = editor.getModel();
    if (!model) return;
    const selection = editor.getSelection();

    if (key === "tab") {
      if (selection && !selection.isEmpty() && selection.startLineNumber !== selection.endLineNumber) {
        editor.getAction("editor.action.indentLines")?.run();
      } else {
        const position = editor.getPosition();
        const spaces = state.settings.tabSize - ((position.column - 1) % state.settings.tabSize);
        editor.executeEdits("keybar", [{
          range: selection,
          text: " ".repeat(spaces),
          forceMoveMarkers: true,
        }]);
      }
    } else if (key === "outdent") {
      editor.getAction("editor.action.outdentLines")?.run();
    } else if (["(", '"', "'"].includes(key)) {
      const close = key === "(" ? ")" : key;
      if (selection && !selection.isEmpty()) {
        const selected = model.getValueInRange(selection);
        editor.executeEdits("keybar", [{ range: selection, text: `${key}${selected}${close}`, forceMoveMarkers: true }]);
      } else {
        editor.executeEdits("keybar", [{
          range: selection,
          text: `${key}${close}`,
          forceMoveMarkers: true,
        }]);
        const position = editor.getPosition();
        editor.setPosition({ lineNumber: position.lineNumber, column: position.column - 1 });
      }
    } else if (key) {
      editor.executeEdits("keybar", [{ range: selection, text: key, forceMoveMarkers: true }]);
    } else if (action === "undo") {
      model.undo();
    } else if (action === "redo") {
      model.redo();
    } else if (action === "comment") {
      editor.getAction("editor.action.commentLine")?.run();
    } else if (action === "find") {
      editor.getAction("actions.find")?.run();
    } else if (action === "keyboard") {
      state.settings.keybar = false;
      saveSettings();
      applySettings();
      toast("Clavier rapide masqué (réactivable dans Paramètres)");
    }
    editor.focus();
  });
}

function bindUI() {
  $("btn-sidebar").addEventListener("click", toggleSidebar);
  $("btn-sidebar-close").addEventListener("click", closeSidebar);
  $("backdrop").addEventListener("click", closeSidebar);
  $("btn-new-file").addEventListener("click", () => newFileDialog());
  $("btn-new-folder").addEventListener("click", () => newFolderDialog());
  $("btn-refresh").addEventListener("click", () => loadTree(state.currentDir));
  $("btn-import").addEventListener("click", importFromDevice);
  $("file-input").addEventListener("change", (event) => {
    const files = [...(event.target.files || [])];
    event.target.value = "";
    uploadFiles(files);
  });
  $("btn-sidebar-settings").addEventListener("click", showSettings);

  $("btn-save").addEventListener("click", saveActive);
  $("btn-run").addEventListener("click", runActive);
  $("btn-split").addEventListener("click", togglePanel);
  $("btn-more").addEventListener("click", showMoreMenu);
  $("btn-console").addEventListener("click", startConsole);
  $("btn-terminal-clear").addEventListener("click", termClear);
  $("btn-panel-close").addEventListener("click", closePanel);
  $("btn-panel-stop").addEventListener("click", stopRun);
  $("btn-graphics-clear").addEventListener("click", gfxReset);
  $("btn-graphics-save").addEventListener("click", gfxSavePng);
  $("place-select").addEventListener("change", (event) => loadTree(event.target.value));
  $("btn-add-place").addEventListener("click", addPlaceDialog);
  $("btn-up").addEventListener("click", () => {
    const parent = state.currentTree && state.currentTree.parent;
    if (parent) loadTree(parent);
    else toast("Déjà à la racine de cet emplacement");
  });
  bindSplitter();
  layoutSplit();

  document.querySelectorAll(".panel-tab").forEach((button) => {
    button.addEventListener("click", () => openPanel(button.dataset.panel));
  });
  $("stdin-form").addEventListener("submit", sendStdin);
  $("btn-stdin-eof").addEventListener("click", sendEof);
  $("stdin-input").addEventListener("keydown", stdinHistory);
  $("status-pos").addEventListener("click", goToLine);
  $("status-problems").addEventListener("click", () => openPanel("problems"));
  $("status-settings").addEventListener("click", showSettings);

  $("modal-close").addEventListener("click", closeModal);
  $("modal-backdrop").addEventListener("click", closeModal);

  bindKeybar();
  document.addEventListener("keydown", onKeyDown, true);
  window.addEventListener("beforeunload", (event) => {
    const dirty = [...state.entries.values()].some((entry) => entry.dirty);
    if (dirty) {
      event.preventDefault();
      event.returnValue = "";
    }
  });
}

/* ---------- démarrage ---------- */

PyTransport.setToken(state.token);
bindUI();

const MONACO_BASE = new URL("vendor/monaco/vs", document.baseURI).href;

if (typeof require === "undefined") {
  bootError("Monaco n'a pas pu être chargé. Vérifie le dossier web/vendor/monaco/vs.");
} else {
  require.config({ paths: { vs: MONACO_BASE } });
  require(["vs/editor/editor.main"], initMonaco, () => {
    bootError("Monaco n'a pas pu démarrer. Le dossier web/vendor/monaco/vs est-il complet ?");
  });
  setTimeout(() => {
    if (!state.monacoReady) {
      bootError("L'éditeur met trop de temps à démarrer. Recharge la page ou vérifie le serveur.");
    }
  }, 20000);
}
