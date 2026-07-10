/* poses/field.js — Mode photographe jour J + OFFLINE (jalons 2-3).
   Cochage optimiste, progression, filtres, incontournables, verrou,
   et surtout : FILE DE SYNCHRO hors-ligne (localStorage) rejouée au retour réseau.
   Vanilla JS. Cache-bust via ?v=N. */
(function () {
  "use strict";

  var body = document.body;
  var TOKEN = body.getAttribute("data-token");
  var DONE_URL = body.getAttribute("data-done-url");
  var MH_URL = body.getAttribute("data-musthave-url");
  var LOCK_URL = body.getAttribute("data-lock-url");
  var locked = body.getAttribute("data-locked") === "1";

  var STORE_KEY = "posesField:" + TOKEN;
  var main = document.querySelector(".fwrap");
  var doneN = document.getElementById("doneN");
  var progressFill = document.getElementById("progressFill");
  var syncEl = document.getElementById("syncStatus");
  var lockBtn = document.getElementById("lockBtn");

  // ---- Persistance de la file --------------------------------------------
  function loadStore() {
    try { return JSON.parse(localStorage.getItem(STORE_KEY)) || { queue: [] }; }
    catch (e) { return { queue: [] }; }
  }
  function saveStore(s) {
    try { localStorage.setItem(STORE_KEY, JSON.stringify(s)); } catch (e) {}
  }
  var store = loadStore();
  if (!Array.isArray(store.queue)) store.queue = [];

  function opKey(op) { return op.t + ":" + (op.id || ""); }

  // Ajoute une op en écrasant une op précédente de même clé (final-state).
  function enqueue(op) {
    store.queue = store.queue.filter(function (o) { return opKey(o) !== opKey(op); });
    store.queue.push(op);
    saveStore(store);
    updateSync();
    flush();
  }

  // ---- Envoi réseau d'une op ---------------------------------------------
  function sendOp(op) {
    var url, payload;
    if (op.t === "done") { url = DONE_URL; payload = { pose_id: op.id, done: op.done }; }
    else if (op.t === "mh") { url = MH_URL; payload = { pose_id: op.id, add: op.add }; }
    else if (op.t === "lock") { url = LOCK_URL; payload = { locked: op.locked }; }
    else return Promise.resolve("drop");
    return fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    }).then(function (r) {
      if (r.ok) return "ok";
      if (r.status >= 400 && r.status < 500) return "drop"; // ex. 404 : inutile de réessayer
      throw new Error("retry");
    });
  }

  var flushing = false;
  function flush() {
    if (flushing) return;
    if (!navigator.onLine) { updateSync(); return; }
    if (!store.queue.length) { updateSync(); return; }
    flushing = true;
    (function step() {
      if (!store.queue.length) { flushing = false; updateSync(); return; }
      var op = store.queue[0];
      sendOp(op).then(function (res) {
        if (res === "ok" || res === "drop") {
          store.queue.shift();
          saveStore(store);
          updateSync();
          step();
        } else { flushing = false; updateSync(); }
      }).catch(function () { flushing = false; updateSync(); });
    })();
  }

  // ---- Indicateur de synchro ---------------------------------------------
  function updateSync() {
    var n = store.queue.length;
    syncEl.className = "sync";
    if (!navigator.onLine) {
      syncEl.hidden = false; syncEl.classList.add("offline");
      syncEl.textContent = n ? ("Hors ligne · " + n + " à synchroniser") : "Hors ligne";
    } else if (n > 0) {
      syncEl.hidden = false; syncEl.classList.add("pending");
      syncEl.textContent = n + " à synchroniser…";
    } else {
      syncEl.hidden = false; syncEl.classList.add("synced");
      syncEl.textContent = "Synchronisé ✓";
    }
  }

  // ---- Progression + filtres ---------------------------------------------
  function getRows() { return Array.prototype.slice.call(document.querySelectorAll(".row[data-pose-id]")); }

  function updateProgress() {
    var rows = getRows();
    var done = rows.filter(function (r) { return r.classList.contains("done"); }).length;
    doneN.textContent = done;
    document.getElementById("totalN").textContent = rows.length;
    progressFill.style.width = rows.length ? (100 * done / rows.length) + "%" : "0%";
    document.querySelectorAll(".fphase[data-phase-id]").forEach(function (ph) {
      var pid = ph.getAttribute("data-phase-id");
      var prs = ph.querySelectorAll(".row[data-pose-id]");
      var n = prs.length, d = 0;
      prs.forEach(function (r) { if (r.classList.contains("done")) d++; });
      var badge = ph.querySelector("[data-phase-count='" + pid + "']");
      if (badge) { badge.textContent = d + "/" + n; badge.classList.toggle("complete", n > 0 && d === n); }
    });
  }

  var currentFilter = "all";
  function applyFilter() {
    getRows().forEach(function (row) {
      var d = row.classList.contains("done");
      var show = currentFilter === "all" || (currentFilter === "done" && d) || (currentFilter === "todo" && !d);
      row.style.display = show ? "" : "none";
    });
    document.querySelectorAll(".fphase[data-phase-id]").forEach(function (ph) {
      var any = Array.prototype.slice.call(ph.querySelectorAll(".row")).some(function (r) { return r.style.display !== "none"; });
      ph.style.display = any ? "" : "none";
    });
  }

  document.getElementById("filters").addEventListener("click", function (e) {
    var b = e.target.closest(".filter");
    if (!b) return;
    currentFilter = b.getAttribute("data-filter");
    document.querySelectorAll(".filter").forEach(function (f) { f.classList.remove("active"); });
    b.classList.add("active");
    applyFilter();
  });

  // ---- Cochage (délégation : marche aussi sur les lignes injectées) -------
  main.addEventListener("click", function (e) {
    var btn = e.target.closest(".check");
    if (!btn) return;
    var row = btn.closest(".row[data-pose-id]");
    if (!row) return;
    var nowDone = !row.classList.contains("done");
    row.classList.toggle("done", nowDone);
    updateProgress();
    applyFilter();
    enqueue({ t: "done", id: row.getAttribute("data-pose-id"), done: nowDone });
  });

  // ---- Injection / retrait dynamique d'une ligne (incontournables) -------
  function makeRow(id, title, desc, done) {
    var row = document.createElement("div");
    row.className = "row" + (done ? " done" : "");
    row.setAttribute("data-pose-id", id);
    var check = document.createElement("button");
    check.type = "button"; check.className = "check"; check.setAttribute("aria-label", "Marquer comme fait");
    check.textContent = "✓";
    var bodyEl = document.createElement("div"); bodyEl.className = "row-body";
    var t = document.createElement("div"); t.className = "rtitle";
    t.innerHTML = "";
    t.appendChild(document.createTextNode(title + " "));
    var star = document.createElement("span"); star.className = "star"; star.title = "Incontournable"; star.textContent = "★";
    t.appendChild(star);
    bodyEl.appendChild(t);
    if (desc) { var dd = document.createElement("div"); dd.className = "rdesc"; dd.textContent = desc; bodyEl.appendChild(dd); }
    row.appendChild(check); row.appendChild(bodyEl);
    return row;
  }

  function ensureSection(phaseId, label, icon, order) {
    var sec = document.querySelector(".fphase[data-phase-id='" + phaseId + "']");
    if (sec) return sec;
    sec = document.createElement("section");
    sec.className = "fphase"; sec.setAttribute("data-phase-id", phaseId); sec.setAttribute("data-order", order);
    var head = document.createElement("div"); head.className = "fphase-head";
    head.innerHTML = '<span class="icon"></span><h2></h2><span class="fphase-count" data-phase-count="' + phaseId + '">0/0</span>';
    head.querySelector(".icon").textContent = icon;
    head.querySelector("h2").textContent = label;
    sec.appendChild(head);
    // insertion à la bonne place chronologique
    var sections = Array.prototype.slice.call(document.querySelectorAll(".fphase[data-order]"));
    var before = null;
    for (var i = 0; i < sections.length; i++) {
      if (parseInt(sections[i].getAttribute("data-order"), 10) > order) { before = sections[i]; break; }
    }
    if (before) before.parentNode.insertBefore(sec, before);
    else document.querySelector(".addpanel").parentNode.insertBefore(sec, document.querySelector(".addpanel"));
    return sec;
  }

  function addRowFromCheck(chk) {
    var id = chk.getAttribute("data-pose-id");
    if (document.querySelector(".row[data-pose-id='" + id + "']")) return; // déjà présent
    var sec = ensureSection(chk.getAttribute("data-phase-id"), chk.getAttribute("data-phase-label"),
                            chk.getAttribute("data-phase-icon"), parseInt(chk.getAttribute("data-phase-order"), 10) || 500);
    sec.appendChild(makeRow(id, chk.getAttribute("data-title"), chk.getAttribute("data-desc"), false));
  }

  function removeRow(id) {
    var row = document.querySelector(".row[data-pose-id='" + id + "']");
    if (!row) return;
    var sec = row.closest(".fphase");
    row.parentNode.removeChild(row);
    if (sec && sec.getAttribute("data-phase-id") !== "__custom__" && !sec.querySelector(".row")) {
      sec.parentNode.removeChild(sec);
    }
  }

  document.querySelectorAll(".mh-check").forEach(function (chk) {
    if (chk.disabled) return;
    chk.addEventListener("change", function () {
      var add = chk.checked;
      if (add) addRowFromCheck(chk); else removeRow(chk.getAttribute("data-pose-id"));
      updateProgress(); applyFilter();
      enqueue({ t: "mh", id: chk.getAttribute("data-pose-id"), add: add });
    });
  });

  // ---- Verrou ------------------------------------------------------------
  function renderLock() {
    lockBtn.classList.toggle("locked", locked);
    lockBtn.textContent = locked ? "🔓 Déverrouiller la sélection" : "🔒 Verrouiller la sélection";
  }
  lockBtn.addEventListener("click", function () {
    locked = !locked; renderLock();
    enqueue({ t: "lock", locked: locked });
  });

  // ---- Hydratation initiale (serveur + file en attente) ------------------
  function hydrate() {
    var doneSet = {};
    try {
      var st = JSON.parse(document.getElementById("field-state").textContent) || {};
      (st.done || []).forEach(function (id) { doneSet[id] = true; });
    } catch (e) {}
    // Rejoue les ops en attente PAR-DESSUS le snapshot serveur (offline compris)
    store.queue.forEach(function (op) {
      if (op.t === "done") doneSet[op.id] = op.done;
      else if (op.t === "mh") {
        var chk = document.querySelector(".mh-check[data-pose-id='" + op.id + "']");
        if (op.add && chk) { addRowFromCheck(chk); if (chk) chk.checked = true; }
        else if (!op.add) { removeRow(op.id); if (chk) chk.checked = false; }
      } else if (op.t === "lock") { locked = op.locked; }
    });
    getRows().forEach(function (row) {
      row.classList.toggle("done", !!doneSet[row.getAttribute("data-pose-id")]);
    });
    renderLock();
  }

  // ---- Réseau : rejoue au retour ------------------------------------------
  window.addEventListener("online", function () { updateSync(); flush(); });
  window.addEventListener("offline", updateSync);
  document.addEventListener("visibilitychange", function () { if (!document.hidden) flush(); });
  // Filet de sécurité : serveur qui refait surface sans événement `online`
  // (réseau instable en salle, onLine resté true) -> on retente régulièrement.
  setInterval(function () { if (store.queue.length && navigator.onLine) flush(); }, 15000);

  // ---- Init --------------------------------------------------------------
  hydrate();
  updateProgress();
  applyFilter();
  updateSync();
  flush();
})();
