/* poses/client.js — Sélection client (jalon 1).
   Sélection de poses, notes, poses perso, autosave débattu, validation.
   Vanilla JS, aucune dépendance. Cache-bust via ?v=N dans le template. */
(function () {
  "use strict";

  var body = document.body;
  var LOCKED = body.getAttribute("data-locked") === "1";
  var SAVE_URL = body.getAttribute("data-save-url");
  var VALIDATE_URL = body.getAttribute("data-validate-url");

  // --- État initial ---------------------------------------------------------
  var state = { selections: [], notes: {}, custom: [], validated: false };
  try {
    var raw = document.getElementById("poses-state").textContent;
    var parsed = JSON.parse(raw) || {};
    state.selections = Array.isArray(parsed.selections) ? parsed.selections : [];
    state.notes = (parsed.notes && typeof parsed.notes === "object") ? parsed.notes : {};
    state.custom = Array.isArray(parsed.custom) ? parsed.custom : [];
    state.validated = !!parsed.validated;
  } catch (e) { /* état vierge */ }

  var selectedSet = {};
  state.selections.forEach(function (id) { selectedSet[id] = true; });
  var customState = state.custom.slice();

  // --- Éléments -------------------------------------------------------------
  var countN = document.getElementById("countN");
  var countS = document.getElementById("countS");
  var countS2 = document.getElementById("countS2");
  var saveState = document.getElementById("saveState");
  var customList = document.getElementById("customList");
  var customCount = document.getElementById("customCount");
  var btnValidate = document.getElementById("btnValidate");
  var validatedNote = document.getElementById("validatedNote");

  // --- Hydratation de la sélection existante --------------------------------
  var poseCards = Array.prototype.slice.call(document.querySelectorAll(".pose[data-pose-id]"));
  poseCards.forEach(function (card) {
    var id = card.getAttribute("data-pose-id");
    if (selectedSet[id]) card.classList.add("selected");
    var ta = card.querySelector(".pose-note");
    if (ta && state.notes[id]) {
      ta.value = state.notes[id];
      card.classList.add("has-note");
    }
  });

  // --- Compteurs ------------------------------------------------------------
  function updateCounts() {
    var n = 0;
    for (var k in selectedSet) { if (selectedSet[k]) n++; }
    countN.textContent = n;
    var plural = n > 1 ? "s" : "";
    countS.textContent = plural; countS2.textContent = plural;

    document.querySelectorAll(".phase[data-phase-id]").forEach(function (ph) {
      var pid = ph.getAttribute("data-phase-id");
      var cards = ph.querySelectorAll(".pose[data-pose-id]");
      var total = cards.length, sel = 0;
      cards.forEach(function (c) { if (c.classList.contains("selected")) sel++; });
      var badge = ph.querySelector("[data-phase-count='" + pid + "']");
      if (badge) {
        badge.textContent = sel + "/" + total;
        badge.classList.toggle("has", sel > 0);
      }
    });
    if (customCount) customCount.textContent = String(customState.length);
  }

  // --- Autosave débattu -----------------------------------------------------
  var saveTimer = null;
  function collectPayload() {
    var selections = [];
    for (var k in selectedSet) { if (selectedSet[k]) selections.push(k); }
    var notes = {};
    poseCards.forEach(function (card) {
      var ta = card.querySelector(".pose-note");
      if (ta) {
        var v = (ta.value || "").trim();
        if (v) notes[card.getAttribute("data-pose-id")] = v;
      }
    });
    return { selections: selections, notes: notes, custom: customState };
  }

  function showSave(msg, ok) {
    saveState.textContent = msg;
    saveState.classList.add("show");
    saveState.classList.toggle("ok", !!ok);
  }

  function doSave() {
    if (LOCKED) return;
    showSave("Enregistrement…", false);
    fetch(SAVE_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(collectPayload())
    }).then(function (r) {
      if (r.status === 409) { showSave("Verrouillé", false); return null; }
      return r.json();
    }).then(function (data) {
      if (data && data.ok) { showSave("Enregistré ✓", true); resetValidated(); }
      else if (data) { showSave("Erreur d'enregistrement", false); }
    }).catch(function () { showSave("Hors ligne — réessai plus tard", false); });
  }

  function scheduleSave() {
    if (LOCKED) return;
    if (saveTimer) clearTimeout(saveTimer);
    saveTimer = setTimeout(doSave, 800);
  }

  // Toute modif invalide une validation antérieure (les mariés ré-ajustent).
  function resetValidated() {
    if (state.validated) {
      state.validated = false;
      renderValidated();
    }
  }

  // --- Interactions poses ---------------------------------------------------
  if (!LOCKED) {
    poseCards.forEach(function (card) {
      var id = card.getAttribute("data-pose-id");
      var heart = card.querySelector(".heart");
      heart.addEventListener("click", function () {
        var now = !card.classList.contains("selected");
        card.classList.toggle("selected", now);
        selectedSet[id] = now;
        updateCounts();
        scheduleSave();
      });
      var noteToggle = card.querySelector(".note-toggle");
      var ta = card.querySelector(".pose-note");
      noteToggle.addEventListener("click", function () {
        card.classList.toggle("note-open");
        if (card.classList.contains("note-open") && ta) ta.focus();
      });
      if (ta) {
        ta.addEventListener("input", function () {
          card.classList.toggle("has-note", (ta.value || "").trim().length > 0);
          scheduleSave();
        });
      }
    });
  }

  // --- Poses perso ----------------------------------------------------------
  function randomId() {
    return "cust_" + Math.random().toString(36).slice(2, 8);
  }

  function renderCustom() {
    customList.innerHTML = "";
    customState.forEach(function (c) {
      var el = document.createElement("div");
      el.className = "custom-item";
      var title = document.createElement("div");
      title.className = "ptitle";
      title.textContent = c.title;
      el.appendChild(title);
      if (c.desc) {
        var d = document.createElement("div");
        d.className = "pdesc";
        d.textContent = c.desc;
        el.appendChild(d);
      }
      if (!LOCKED) {
        var rm = document.createElement("button");
        rm.className = "remove";
        rm.type = "button";
        rm.setAttribute("aria-label", "Retirer");
        rm.textContent = "✕";
        rm.addEventListener("click", function () {
          customState = customState.filter(function (x) { return x.id !== c.id; });
          renderCustom(); updateCounts(); scheduleSave();
        });
        el.appendChild(rm);
      }
      customList.appendChild(el);
    });
  }

  if (!LOCKED) {
    var addBtn = document.getElementById("customAddBtn");
    var titleInput = document.getElementById("customTitle");
    var descInput = document.getElementById("customDesc");
    var addCustom = function () {
      var title = (titleInput.value || "").trim();
      if (!title) { titleInput.focus(); return; }
      customState.push({
        id: randomId(),
        phaseId: null,
        title: title.slice(0, 120),
        desc: (descInput.value || "").trim().slice(0, 500)
      });
      titleInput.value = ""; descInput.value = "";
      renderCustom(); updateCounts(); scheduleSave();
      titleInput.focus();
    };
    addBtn.addEventListener("click", addCustom);
    descInput.addEventListener("keydown", function (e) { if (e.key === "Enter") addCustom(); });
    titleInput.addEventListener("keydown", function (e) { if (e.key === "Enter") addCustom(); });
  }

  // --- Validation -----------------------------------------------------------
  function renderValidated() {
    if (state.validated) {
      validatedNote.textContent = "✓ Sélection validée — merci !";
      btnValidate.textContent = "Sélection validée";
      btnValidate.classList.add("done");
    } else {
      validatedNote.textContent = "";
      btnValidate.textContent = "Valider ma sélection";
      btnValidate.classList.remove("done");
    }
  }

  if (!LOCKED) {
    btnValidate.addEventListener("click", function () {
      // On force d'abord un enregistrement de l'état courant, puis on valide.
      if (saveTimer) { clearTimeout(saveTimer); saveTimer = null; }
      fetch(SAVE_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(collectPayload())
      }).then(function () {
        return fetch(VALIDATE_URL, { method: "POST" });
      }).then(function (r) {
        if (r.status === 409) { showSave("Verrouillé", false); return null; }
        return r.json();
      }).then(function (data) {
        if (data && data.ok) { state.validated = true; renderValidated(); showSave("Enregistré ✓", true); }
      }).catch(function () { showSave("Hors ligne — réessayez", false); });
    });
  }

  // --- Filtre par type ------------------------------------------------------
  var typebar = document.getElementById("typebar");
  if (typebar) {
    var phaseEls = Array.prototype.slice.call(document.querySelectorAll(".phase[data-category]"));
    typebar.addEventListener("click", function (e) {
      var b = e.target.closest(".chip");
      if (!b) return;
      var cat = b.getAttribute("data-cat");
      typebar.querySelectorAll(".chip").forEach(function (c) { c.classList.remove("active"); });
      b.classList.add("active");
      phaseEls.forEach(function (ph) {
        var c = ph.getAttribute("data-category");
        ph.style.display = (cat === "all" || c === cat) ? "" : "none";
      });
      window.scrollTo(0, 0);
    });
  }

  // --- Init -----------------------------------------------------------------
  renderCustom();
  renderValidated();
  updateCounts();
})();
