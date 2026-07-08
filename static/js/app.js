(() => {
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

  let workbook = null;
  let activeId = null;
  let saveTimer = null;
  let dirty = false;
  let dragFrom = null;

  const els = {
    body: $("#sheet-body"),
    tabs: $("#tabs-list"),
    dayStart: $("#day-start"),
    dayEnd: $("#day-end"),
    statEnd: $("#stat-end"),
    statFree: $("#stat-free"),
    overflow: $("#stat-overflow"),
    toast: $("#toast"),
    help: $("#help-dialog"),
    popover: $("#cell-popover"),
    popPreview: $("#cell-popover-preview"),
    popEdit: $("#cell-popover-edit"),
    popLabel: $("#cell-popover-label"),
    popActions: $("#cell-popover-actions"),
    popHint: $("#cell-popover-hint"),
    popSave: $("#cell-popover-save"),
    popCancel: $("#cell-popover-cancel"),
  };

  let popoverState = null; // { input, onCommit, hideTimer }
  let popoverPinned = false;

  function toast(msg) {
    els.toast.textContent = msg;
    els.toast.classList.remove("hidden");
    clearTimeout(toast._t);
    toast._t = setTimeout(() => els.toast.classList.add("hidden"), 1800);
  }

  async function api(path, opts = {}) {
    const res = await fetch(path, {
      headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
      credentials: "same-origin",
      ...opts,
    });
    if (res.status === 401) {
      window.location.href = "/login";
      throw new Error("Sesión expirada");
    }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || res.statusText);
    return data;
  }

  function sheet() {
    return workbook?.sheets?.[activeId];
  }

  function findSheetId(target) {
    if (!workbook?.sheets || !target) return null;
    const t = String(target).trim().toLowerCase();
    if (workbook.sheets[t]) return t;
    for (const [id, sh] of Object.entries(workbook.sheets)) {
      if (id.toLowerCase() === t) return id;
      if ((sh.name || "").trim().toLowerCase() === t) return id;
    }
    return null;
  }

  /** Clasifica el vínculo: hoja interna, URL/documento externo, o vacío. */
  function parseLink(raw) {
    const s = String(raw || "").trim();
    if (!s) return { kind: "empty", value: "" };

    const lower = s.toLowerCase();
    if (lower.startsWith("sheet:")) {
      const target = s.slice(6).trim();
      const id = findSheetId(target);
      return id
        ? { kind: "sheet", value: id, label: workbook.sheets[id].name || id }
        : { kind: "missing", value: target };
    }
    if (s.startsWith("#") && !s.startsWith("#http")) {
      const target = s.slice(1).trim();
      const id = findSheetId(target);
      return id
        ? { kind: "sheet", value: id, label: workbook.sheets[id].name || id }
        : { kind: "missing", value: target };
    }

    // URL o documento externo
    if (/^https?:\/\//i.test(s) || /^mailto:/i.test(s)) {
      return { kind: "external", value: s };
    }
    // Archivo / drive / www sin protocolo → abrir como https o ruta relativa en nueva pestaña
    if (
      /^www\./i.test(s) ||
      /\.(pdf|docx?|xlsx?|pptx?|txt|md|csv)(\?|#|$)/i.test(s) ||
      /drive\.google|docs\.google|dropbox|onedrive|notion\.so/i.test(s)
    ) {
      const href = /^www\./i.test(s) ? `https://${s}` : (/^https?:\/\//i.test(s) ? s : s);
      return { kind: "external", value: href.startsWith("http") || href.startsWith("/") ? href : `https://${href}` };
    }

    // Si coincide con el id o nombre de una hoja → vínculo interno (como Google Sheets)
    const sheetId = findSheetId(s);
    if (sheetId) {
      return { kind: "sheet", value: sheetId, label: workbook.sheets[sheetId].name || sheetId };
    }

    // Texto libre desconocido: tratar como URL si parece dominio, si no intentar hoja
    if (s.includes(".") && !s.includes(" ")) {
      return { kind: "external", value: `https://${s}` };
    }
    return { kind: "missing", value: s };
  }

  async function goToSheet(sheetId) {
    if (!sheetId || !workbook.sheets[sheetId]) {
      toast("Hoja no encontrada");
      return;
    }
    if (sheetId === activeId) return;
    if (dirty) await saveAll();
    activeId = sheetId;
    try {
      await api(`/api/active/${sheetId}`, { method: "POST", body: "{}" });
    } catch (_) {
      /* ignore */
    }
    render();
    toast("Hoja: " + (workbook.sheets[sheetId].name || sheetId));
  }

  function openLink(raw) {
    const info = parseLink(raw);
    if (info.kind === "sheet") {
      goToSheet(info.value);
      return;
    }
    if (info.kind === "external") {
      window.open(info.value, "_blank", "noopener,noreferrer");
      return;
    }
    if (info.kind === "missing") {
      toast("No se encontró la hoja o el enlace: " + info.value);
    }
  }

  function scheduleSave() {
    dirty = true;
    clearTimeout(saveTimer);
    saveTimer = setTimeout(saveAll, 500);
  }

  async function saveAll() {
    if (!workbook) return;
    workbook.active_sheet_id = activeId;
    try {
      workbook = await api("/api/workbook", {
        method: "PUT",
        body: JSON.stringify(workbook),
      });
      activeId = workbook.active_sheet_id;
      dirty = false;
      render();
      toast("Guardado");
    } catch (err) {
      toast("Error al guardar: " + err.message);
    }
  }

  function updateMeta() {
    const s = sheet();
    if (!s) return;
    els.dayStart.value = s.day_start || "6:00 AM";
    els.dayEnd.value = s.day_end || "4:00 PM";
    els.statEnd.textContent = s.timeline_end || "—";
    els.statFree.textContent = s.remaining_label || "—";
    els.overflow.classList.toggle("hidden", !s.overflow);
  }

  function renderTabs() {
    els.tabs.innerHTML = "";
    for (const [id, sh] of Object.entries(workbook.sheets)) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "tab" + (id === activeId ? " active" : "");
      btn.dataset.id = id;
      btn.title = "Abrir hoja";

      const label = document.createElement("span");
      label.className = "tab-label";
      label.textContent = sh.name || id;

      const renameBtn = document.createElement("span");
      renameBtn.className = "tab-rename";
      renameBtn.textContent = "✎";
      renameBtn.title = "Renombrar hoja";
      renameBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        startRenameTab(id, sh, btn, label);
      });

      const close = document.createElement("span");
      close.className = "tab-close";
      close.textContent = "×";
      close.title = "Eliminar hoja";
      close.addEventListener("click", async (e) => {
        e.stopPropagation();
        if (Object.keys(workbook.sheets).length <= 1) {
          toast("Debes tener al menos una hoja");
          return;
        }
        if (!confirm(`¿Eliminar la hoja "${sh.name}"?`)) return;
        try {
          workbook = await api(`/api/sheets/${id}`, { method: "DELETE" });
          activeId = workbook.active_sheet_id;
          render();
          toast("Hoja eliminada");
        } catch (err) {
          toast(err.message);
        }
      });

      btn.append(label, renameBtn, close);
      btn.addEventListener("click", () => goToSheet(id));
      btn.addEventListener("dblclick", (e) => {
        e.preventDefault();
        e.stopPropagation();
        startRenameTab(id, sh, btn, label);
      });
      els.tabs.appendChild(btn);
    }
  }

  function startRenameTab(id, sh, btn, label) {
    if (btn.querySelector("input.tab-name")) return;
    const input = document.createElement("input");
    input.type = "text";
    input.className = "tab-name";
    input.value = sh.name || id;
    input.maxLength = 40;
    label.replaceWith(input);
    input.focus();
    input.select();

    let done = false;
    const finish = async (save) => {
      if (done) return;
      done = true;
      const next = input.value.trim() || sh.name || id;
      if (save && next !== sh.name) {
        sh.name = next;
        try {
          await api(`/api/sheets/${id}`, {
            method: "PATCH",
            body: JSON.stringify({ name: next, rows: sh.rows }),
          });
          toast("Hoja renombrada");
        } catch (err) {
          toast(err.message);
        }
      }
      renderTabs();
    };

    input.addEventListener("click", (e) => e.stopPropagation());
    input.addEventListener("mousedown", (e) => e.stopPropagation());
    input.addEventListener("keydown", (e) => {
      e.stopPropagation();
      if (e.key === "Enter") {
        e.preventDefault();
        finish(true);
      }
      if (e.key === "Escape") {
        e.preventDefault();
        finish(false);
      }
    });
    input.addEventListener("blur", () => finish(true));
  }

  function isTruncated(input) {
    if (!input) return false;
    const val = input.value || "";
    if (!val) return false;
    // inputs a veces no reportan scrollWidth bien; prueba real + heurística
    if (input.scrollWidth > input.clientWidth + 1) return true;
    try {
      const style = window.getComputedStyle(input);
      const canvas = isTruncated._c || (isTruncated._c = document.createElement("canvas"));
      const ctx = canvas.getContext("2d");
      ctx.font = `${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
      const textW = ctx.measureText(val).width;
      const padL = parseFloat(style.paddingLeft) || 0;
      const padR = parseFloat(style.paddingRight) || 0;
      return textW > input.clientWidth - padL - padR - 2;
    } catch (_) {
      return val.length > 28;
    }
  }

  function shouldOfferPopover(input) {
    const val = (input?.value || "").trim();
    if (!val) return false;
    return isTruncated(input) || val.length > 24;
  }

  function hidePopover(force = false) {
    if (popoverPinned && !force) return;
    clearTimeout(popoverState?.hideTimer);
    popoverPinned = false;
    popoverState = null;
    els.popover.classList.add("hidden");
    els.popover.setAttribute("aria-hidden", "true");
    els.popEdit.classList.add("hidden");
    els.popPreview.classList.remove("hidden");
    els.popActions.classList.add("hidden");
    els.popHint.classList.remove("hidden");
    els.popEdit.value = "";
  }

  function placePopover(anchor) {
    const rect = anchor.getBoundingClientRect();
    const pop = els.popover;
    pop.classList.remove("hidden");
    pop.setAttribute("aria-hidden", "false");
    const pad = 8;
    let top = rect.bottom + pad;
    let left = rect.left;
    const pw = pop.offsetWidth || 320;
    const ph = pop.offsetHeight || 120;
    if (left + pw > window.innerWidth - 12) left = window.innerWidth - pw - 12;
    if (left < 12) left = 12;
    if (top + ph > window.innerHeight - 12) top = rect.top - ph - pad;
    if (top < 12) top = 12;
    pop.style.top = `${Math.round(top)}px`;
    pop.style.left = `${Math.round(left)}px`;
  }

  function showPopoverPreview(input, onCommit, label) {
    if (popoverPinned) return;
    if (!shouldOfferPopover(input)) {
      hidePopover(true);
      return;
    }
    clearTimeout(popoverState?.hideTimer);
    popoverState = { input, onCommit, hideTimer: null };
    popoverPinned = false;
    els.popLabel.textContent = label || "Texto completo";
    els.popPreview.textContent = input.value || "";
    els.popEdit.classList.add("hidden");
    els.popPreview.classList.remove("hidden");
    els.popActions.classList.add("hidden");
    els.popHint.classList.remove("hidden");
    placePopover(input);
  }

  function openPopoverEditor() {
    if (!popoverState?.input) return;
    popoverPinned = true;
    clearTimeout(popoverState.hideTimer);
    const text = popoverState.input.value || "";
    els.popPreview.classList.add("hidden");
    els.popHint.classList.add("hidden");
    els.popEdit.classList.remove("hidden");
    els.popActions.classList.remove("hidden");
    els.popEdit.value = text;
    placePopover(popoverState.input);
    els.popEdit.focus();
    els.popEdit.setSelectionRange(text.length, text.length);
  }

  function savePopoverEdit() {
    if (!popoverState?.input) {
      hidePopover(true);
      return;
    }
    const next = els.popEdit.value;
    const { input, onCommit } = popoverState;
    if (next !== input.value) {
      input.value = next;
      onCommit(next);
    }
    hidePopover(true);
  }

  function attachOverflowPopover(input, onCommit, label) {
    input.addEventListener("mouseenter", () => {
      if (document.activeElement === input) return;
      showPopoverPreview(input, onCommit, label);
    });
    input.addEventListener("mouseleave", () => {
      if (popoverPinned) return;
      if (popoverState) {
        clearTimeout(popoverState.hideTimer);
        popoverState.hideTimer = setTimeout(() => hidePopover(false), 180);
      }
    });
    input.addEventListener("click", (e) => {
      if (!shouldOfferPopover(input)) return;
      e.preventDefault();
      popoverState = { input, onCommit, hideTimer: null };
      els.popLabel.textContent = label || "Texto completo";
      placePopover(input);
      openPopoverEditor();
    });
    input.addEventListener("focus", () => {
      if (!popoverPinned) hidePopover(true);
    });
  }

  function makeInput(value, className, onCommit, popoverLabel) {
    const input = document.createElement("input");
    input.type = "text";
    input.className = "cell-input " + (className || "");
    input.value = value ?? "";
    let last = input.value;
    const commit = () => {
      if (input.value === last) return;
      last = input.value;
      onCommit(input.value);
    };
    input.addEventListener("change", commit);
    input.addEventListener("blur", commit);
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        input.blur();
      }
    });
    if (popoverLabel) {
      attachOverflowPopover(input, (v) => {
        last = v;
        onCommit(v);
      }, popoverLabel);
    }
    return input;
  }

  function renderRows() {
    const s = sheet();
    els.body.innerHTML = "";
    if (!s) return;

    (s.rows || []).forEach((row, index) => {
      const tr = document.createElement("tr");
      tr.draggable = true;
      tr.dataset.index = String(index);
      if (row.overflow) tr.classList.add("overflow");

      tr.addEventListener("dragstart", (e) => {
        dragFrom = index;
        tr.classList.add("dragging");
        e.dataTransfer.effectAllowed = "move";
        e.dataTransfer.setData("text/plain", String(index));
      });
      tr.addEventListener("dragend", () => {
        tr.classList.remove("dragging");
        $$(".row-drag-over", els.body).forEach((r) => r.classList.remove("row-drag-over"));
        dragFrom = null;
      });
      tr.addEventListener("dragover", (e) => {
        e.preventDefault();
        e.dataTransfer.dropEffect = "move";
        tr.classList.add("row-drag-over");
      });
      tr.addEventListener("dragleave", () => tr.classList.remove("row-drag-over"));
      tr.addEventListener("drop", async (e) => {
        e.preventDefault();
        tr.classList.remove("row-drag-over");
        const from = dragFrom ?? Number(e.dataTransfer.getData("text/plain"));
        const to = index;
        if (Number.isNaN(from) || from === to) return;
        try {
          const updated = await api(`/api/sheets/${activeId}/move`, {
            method: "POST",
            body: JSON.stringify({ from, to }),
          });
          workbook.sheets[activeId] = updated;
          dirty = false;
          render();
          toast("Reordenado · horarios actualizados");
        } catch (err) {
          toast(err.message);
        }
      });

      const tdHandle = document.createElement("td");
      const handle = document.createElement("span");
      handle.className = "handle";
      handle.textContent = "≡";
      handle.title = "Arrastra para reordenar";
      tdHandle.appendChild(handle);

      const tdNum = document.createElement("td");
      tdNum.className = "row-num";
      tdNum.textContent = String(index + 1);

      const tdTask = document.createElement("td");
      tdTask.appendChild(
        makeInput(row.task, "", (v) => {
          row.task = v;
          scheduleSave();
        }, "Tarea")
      );

      const tdLink = document.createElement("td");
      const linkWrap = document.createElement("div");
      linkWrap.className = "link-cell";
      if (row.link == null) row.link = "";
      const linkInput = makeInput(row.link, "", (v) => {
        row.link = v.trim();
        scheduleSave();
        refreshLinkButton(goBtn, row.link);
      }, "Vínculo");
      linkInput.placeholder = "sheet:semana o https://...";
      linkInput.title =
        "Hoja interna: sheet:id o nombre de pestaña. Externo/documento: https://... o archivo.pdf";
      const goBtn = document.createElement("button");
      goBtn.type = "button";
      goBtn.className = "link-go";
      goBtn.title = "Abrir vínculo";
      refreshLinkButton(goBtn, row.link);
      goBtn.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        openLink(row.link || linkInput.value);
      });
      linkWrap.append(linkInput, goBtn);
      tdLink.appendChild(linkWrap);

      const tdTimed = document.createElement("td");
      tdTimed.className = "timed-check";
      const check = document.createElement("input");
      check.type = "checkbox";
      check.checked = !!row.timed;
      check.title = "Si está activo, entra en el horario";
      check.addEventListener("change", async () => {
        row.timed = check.checked;
        try {
          const updated = await api(`/api/sheets/${activeId}/rows/${index}`, {
            method: "PATCH",
            body: JSON.stringify({ timed: row.timed }),
          });
          workbook.sheets[activeId] = updated;
          render();
        } catch (err) {
          toast(err.message);
        }
      });
      tdTimed.appendChild(check);

      const tdDur = document.createElement("td");
      const durInput = makeInput(row.duration_label || row.duration || "", "", async (v) => {
        try {
          const updated = await api(`/api/sheets/${activeId}/rows/${index}`, {
            method: "PATCH",
            body: JSON.stringify({ duration: v }),
          });
          workbook.sheets[activeId] = updated;
          render();
        } catch (err) {
          toast(err.message);
        }
      });
      durInput.disabled = !row.timed;
      if (!row.timed) durInput.placeholder = "—";
      tdDur.appendChild(durInput);

      const tdStart = document.createElement("td");
      tdStart.className = "time-cell" + (row.timed ? "" : " empty");
      tdStart.textContent = row.timed ? row.start || "—" : "—";

      const tdEnd = document.createElement("td");
      tdEnd.className = "time-cell" + (row.timed ? "" : " empty");
      tdEnd.textContent = row.timed ? row.end || "—" : "—";

      const tdNotes = document.createElement("td");
      tdNotes.appendChild(
        makeInput(row.notes, "", (v) => {
          row.notes = v;
          scheduleSave();
        }, "Notas")
      );

      const tdDel = document.createElement("td");
      const del = document.createElement("button");
      del.type = "button";
      del.className = "btn danger";
      del.textContent = "✕";
      del.title = "Eliminar fila";
      del.addEventListener("click", async () => {
        try {
          const updated = await api(`/api/sheets/${activeId}/rows/${index}`, {
            method: "DELETE",
          });
          workbook.sheets[activeId] = updated;
          render();
        } catch (err) {
          toast(err.message);
        }
      });
      tdDel.appendChild(del);

      tr.append(tdHandle, tdNum, tdTask, tdLink, tdTimed, tdDur, tdStart, tdEnd, tdNotes, tdDel);
      els.body.appendChild(tr);
    });
  }

  function refreshLinkButton(btn, raw) {
    const info = parseLink(raw);
    btn.classList.remove("is-empty", "is-sheet");
    if (info.kind === "empty") {
      btn.classList.add("is-empty");
      btn.textContent = "↗";
      btn.title = "Sin vínculo";
      return;
    }
    if (info.kind === "sheet") {
      btn.classList.add("is-sheet");
      btn.textContent = "➝";
      btn.title = "Ir a hoja: " + (info.label || info.value);
      return;
    }
    if (info.kind === "missing") {
      btn.classList.add("is-empty");
      btn.textContent = "?";
      btn.title = "No encontrada: " + info.value;
      return;
    }
    btn.textContent = "↗";
    btn.title = "Abrir en otra pestaña: " + info.value;
  }

  function render() {
    renderTabs();
    updateMeta();
    renderRows();
  }

  async function boot() {
    workbook = await api("/api/workbook");
    activeId = workbook.active_sheet_id;
    render();
  }

  $("#btn-save").addEventListener("click", () => saveAll());
  $("#btn-help").addEventListener("click", () => els.help.showModal());

  $("#btn-add-row").addEventListener("click", async () => {
    try {
      const updated = await api(`/api/sheets/${activeId}/rows`, {
        method: "POST",
        body: JSON.stringify({ task: "", timed: true, duration: 30, notes: "", link: "" }),
      });
      workbook.sheets[activeId] = updated;
      render();
    } catch (err) {
      toast(err.message);
    }
  });

  $("#btn-add-sheet").addEventListener("click", async () => {
    const name = prompt("Nombre de la nueva hoja:", "Nueva hoja");
    if (!name) return;
    try {
      if (dirty) await saveAll();
      const res = await api("/api/sheets", {
        method: "POST",
        body: JSON.stringify({ name }),
      });
      workbook = res.workbook;
      activeId = res.id;
      render();
      toast("Hoja creada");
    } catch (err) {
      toast(err.message);
    }
  });

  async function patchBounds() {
    const s = sheet();
    if (!s) return;
    s.day_start = els.dayStart.value;
    s.day_end = els.dayEnd.value;
    try {
      const updated = await api(`/api/sheets/${activeId}`, {
        method: "PATCH",
        body: JSON.stringify({
          day_start: s.day_start,
          day_end: s.day_end,
          rows: s.rows,
        }),
      });
      workbook.sheets[activeId] = updated;
      render();
    } catch (err) {
      toast(err.message);
    }
  }

  els.dayStart.addEventListener("change", patchBounds);
  els.dayEnd.addEventListener("change", patchBounds);

  els.popover.addEventListener("mouseenter", () => {
    if (popoverState) clearTimeout(popoverState.hideTimer);
  });
  els.popover.addEventListener("mouseleave", () => {
    if (popoverPinned) return;
    if (popoverState) {
      clearTimeout(popoverState.hideTimer);
      popoverState.hideTimer = setTimeout(() => hidePopover(false), 160);
    }
  });
  els.popover.addEventListener("click", (e) => {
    if (popoverPinned) return;
    if (e.target.closest(".cell-popover-actions")) return;
    openPopoverEditor();
  });
  els.popSave.addEventListener("click", (e) => {
    e.stopPropagation();
    savePopoverEdit();
  });
  els.popCancel.addEventListener("click", (e) => {
    e.stopPropagation();
    hidePopover(true);
  });
  els.popEdit.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      e.preventDefault();
      hidePopover(true);
    }
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      savePopoverEdit();
    }
  });
  document.addEventListener("mousedown", (e) => {
    if (!popoverPinned) return;
    if (els.popover.contains(e.target)) return;
    if (popoverState?.input && popoverState.input.contains(e.target)) return;
    savePopoverEdit();
  });
  window.addEventListener("scroll", () => {
    if (!els.popover.classList.contains("hidden") && popoverState?.input) {
      placePopover(popoverState.input);
    }
  }, true);

  window.addEventListener("beforeunload", (e) => {
    if (dirty) {
      e.preventDefault();
      e.returnValue = "";
    }
  });

  boot().catch((err) => toast("No se pudo cargar: " + err.message));
})();
