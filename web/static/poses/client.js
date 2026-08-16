/* poses/client.js — Sélection client (jalon 1).
   Sélection de poses, notes, poses perso, autosave débattu, validation.
   Vanilla JS, aucune dépendance. Cache-bust via ?v=N dans le template. */
(function () {
  "use strict";

  var body = document.body;
  var LOCKED = body.getAttribute("data-locked") === "1";
  var SAVE_URL = body.getAttribute("data-save-url");
  var VALIDATE_URL = body.getAttribute("data-validate-url");
  var GROUPS_URL = body.getAttribute("data-groups-url");

  // --- État initial ---------------------------------------------------------
  var state = { selections: [], notes: {}, custom: [], validated: false };
  try {
    var raw = document.getElementById("poses-state").textContent;
    var parsed = JSON.parse(raw) || {};
    state.selections = Array.isArray(parsed.selections) ? parsed.selections : [];
    state.notes = (parsed.notes && typeof parsed.notes === "object") ? parsed.notes : {};
    state.custom = Array.isArray(parsed.custom) ? parsed.custom : [];
    state.groups = Array.isArray(parsed.groups) ? parsed.groups : [];
    state.validated = !!parsed.validated;
  } catch (e) { /* état vierge */ }

  var selectedSet = {};
  state.selections.forEach(function (id) { selectedSet[id] = true; });
  var customState = state.custom.slice();
  var groupsState = (state.groups || []).map(function (g) {
    return { id: g.id, title: g.title || "", people: (g.people || []).slice() };
  });

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
        applyFilter();
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

  // --- Photos de groupe -----------------------------------------------------
  var groupsList = document.getElementById("groupsList");
  var groupsCount = document.getElementById("groupsCount");
  var rosterList = document.getElementById("rosterList");
  var groupsTimer = null;

  function saveGroups() {
    if (LOCKED) return;
    if (groupsTimer) clearTimeout(groupsTimer);
    groupsTimer = setTimeout(function () {
      fetch(GROUPS_URL, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ groups: groupsState })
      }).then(function (r) {
        if (r && r.ok) { showSave("Enregistré ✓", true); resetValidated(); }
        else { showSave("Erreur d'enregistrement", false); }
      }).catch(function () { showSave("Hors ligne — réessai plus tard", false); });
    }, 700);
  }

  function updateRoster() {
    var seen = {}, names = [];
    groupsState.forEach(function (g) {
      (g.people || []).forEach(function (nm) {
        var k = nm.toLowerCase();
        if (!seen[k]) { seen[k] = 1; names.push(nm); }
      });
    });
    names.sort(function (a, b) { return a.localeCompare(b); });
    if (rosterList) {
      rosterList.innerHTML = "";
      names.forEach(function (nm) { var o = document.createElement("option"); o.value = nm; rosterList.appendChild(o); });
    }
    if (groupsCount) {
      groupsCount.textContent = groupsState.length + (names.length ? " · " + names.length + " pers." : "");
    }
  }

  function randomGid() { return "grp_" + Math.random().toString(36).slice(2, 8); }

  function makeChip(g, nm, chipsEl) {
    var chip = document.createElement("span");
    chip.className = "person-chip";
    chip.appendChild(document.createTextNode(nm));
    if (!LOCKED) {
      var x = document.createElement("button");
      x.type = "button"; x.textContent = "×"; x.setAttribute("aria-label", "Retirer");
      x.addEventListener("click", function () {
        var i = g.people.indexOf(nm);
        if (i !== -1) g.people.splice(i, 1);
        if (chip.parentNode) chip.parentNode.removeChild(chip);
        updateRoster(); saveGroups();
      });
      chip.appendChild(x);
    }
    chipsEl.appendChild(chip);
  }

  function addPerson(g, raw, chipsEl) {
    (raw || "").split(",").forEach(function (part) {
      var nm = part.trim();
      if (nm && g.people.indexOf(nm) === -1) { g.people.push(nm); makeChip(g, nm, chipsEl); }
    });
    updateRoster(); saveGroups();
  }

  function renderGroups() {
    if (!groupsList) return;
    groupsList.innerHTML = "";
    groupsState.forEach(function (g) {
      var card = document.createElement("div"); card.className = "group-card";
      var head = document.createElement("div"); head.className = "group-head";
      if (LOCKED) {
        var h = document.createElement("div"); h.className = "group-title-static";
        h.textContent = g.title || "(sans titre)"; head.appendChild(h);
      } else {
        var ti = document.createElement("input");
        ti.type = "text"; ti.className = "group-title"; ti.value = g.title || ""; ti.maxLength = 140;
        ti.placeholder = "Titre du groupe";
        ti.addEventListener("input", function () { g.title = ti.value; saveGroups(); });
        head.appendChild(ti);
        var rm = document.createElement("button");
        rm.type = "button"; rm.className = "group-remove"; rm.textContent = "✕"; rm.title = "Supprimer le groupe";
        rm.addEventListener("click", function () {
          groupsState = groupsState.filter(function (x) { return x !== g; });
          renderGroups(); updateRoster(); saveGroups();
        });
        head.appendChild(rm);
      }
      card.appendChild(head);

      var chips = document.createElement("div"); chips.className = "chips";
      (g.people || []).forEach(function (nm) { makeChip(g, nm, chips); });
      card.appendChild(chips);

      if (!LOCKED) {
        var pin = document.createElement("input");
        pin.type = "text"; pin.className = "person-add"; pin.setAttribute("list", "rosterList");
        pin.placeholder = "Prénom + Entrée";
        pin.addEventListener("keydown", function (e) {
          if (e.key === "Enter" || e.key === ",") { e.preventDefault(); addPerson(g, pin.value, chips); pin.value = ""; }
        });
        pin.addEventListener("blur", function () { if (pin.value.trim()) { addPerson(g, pin.value, chips); pin.value = ""; } });
        card.appendChild(pin);
      }
      groupsList.appendChild(card);
    });
  }

  if (!LOCKED && document.getElementById("newGroupBtn")) {
    var newGroupBtn = document.getElementById("newGroupBtn");
    var newGroupTitle = document.getElementById("newGroupTitle");
    var addGroup = function () {
      var t = (newGroupTitle.value || "").trim();
      if (!t) { newGroupTitle.focus(); return; }
      groupsState.push({ id: randomGid(), title: t.slice(0, 140), people: [] });
      newGroupTitle.value = "";
      renderGroups(); updateRoster(); saveGroups();
    };
    newGroupBtn.addEventListener("click", addGroup);
    newGroupTitle.addEventListener("keydown", function (e) { if (e.key === "Enter") addGroup(); });
  }

  // --- Filtres : type + « Ma sélection » ------------------------------------
  var typebar = document.getElementById("typebar");
  var phaseEls = Array.prototype.slice.call(document.querySelectorAll(".phase[data-category]"));
  var currentCat = "all";
  var selectedOnly = false;

  function applyFilter() {
    phaseEls.forEach(function (ph) {
      var cat = ph.getAttribute("data-category");
      if (currentCat !== "all" && cat !== currentCat) { ph.style.display = "none"; return; }
      var cards = ph.querySelectorAll(".pose[data-pose-id]");
      if (!selectedOnly) {
        cards.forEach(function (c) { c.style.display = ""; });
        ph.style.display = "";
        return;
      }
      // mode récap : ne montrer que les poses cochées
      var anyVisible = false;
      cards.forEach(function (c) {
        var sel = c.classList.contains("selected");
        c.style.display = sel ? "" : "none";
        if (sel) anyVisible = true;
      });
      // les sections « idées perso » et « photos de groupe » n'ont pas de .pose -> gardées en mode récap
      if (cat === "__custom__" || cat === "__groups__") { ph.style.display = ""; return; }
      ph.style.display = anyVisible ? "" : "none";
    });
  }

  if (typebar) {
    typebar.addEventListener("click", function (e) {
      var b = e.target.closest(".chip");
      if (!b) return;
      if (b.hasAttribute("data-sel-toggle")) {
        selectedOnly = !selectedOnly;
        b.classList.toggle("active", selectedOnly);
      } else {
        currentCat = b.getAttribute("data-cat");
        typebar.querySelectorAll(".chip:not([data-sel-toggle])").forEach(function (c) { c.classList.remove("active"); });
        b.classList.add("active");
      }
      applyFilter();
      window.scrollTo(0, 0);
    });
  }

  // --- Init -----------------------------------------------------------------
  renderCustom();
  renderGroups();
  updateRoster();
  renderValidated();
  updateCounts();
  applyFilter();
})();
