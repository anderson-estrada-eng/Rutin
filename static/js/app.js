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
  };

  function toast(msg) {
    els.toast.textContent = msg;
    els.toast.classList.remove("hidden");
    clearTimeout(toast._t);
    toast._t = setTimeout(() => els.toast.classList.add("hidden"), 1800);
  }

  async function api(path, opts = {}) {
    const res = await fetch(path, {
      headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
      ...opts,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || res.statusText);
    return data;
  }

  function sheet() {
    return workbook?.sheets?.[activeId];
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

      const name = document.createElement("input");
      name.className = "tab-name";
      name.value = sh.name || id;
      name.title = "Doble clic para renombrar";
      name.readOnly = true;
      name.addEventListener("dblclick", (e) => {
        e.stopPropagation();
        name.readOnly = false;
        name.focus();
        name.select();
      });
      name.addEventListener("blur", () => {
        name.readOnly = true;
        const next = name.value.trim() || sh.name;
        if (next !== sh.name) {
          sh.name = next;
          scheduleSave();
        }
        renderTabs();
      });
      name.addEventListener("keydown", (e) => {
        if (e.key === "Enter") name.blur();
        e.stopPropagation();
      });
      name.addEventListener("click", (e) => e.stopPropagation());

      const close = document.createElement("span");
      close.className = "tab-close";
      close.textContent = "×";
      close.title = "Cerrar hoja";
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

      btn.appendChild(name);
      btn.appendChild(close);
      btn.addEventListener("click", async () => {
        if (id === activeId) return;
        if (dirty) await saveAll();
        activeId = id;
        await api(`/api/active/${id}`, { method: "POST", body: "{}" });
        render();
      });
      els.tabs.appendChild(btn);
    }
  }

  function makeInput(value, className, onCommit) {
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
        })
      );

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
        })
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

      tr.append(tdHandle, tdNum, tdTask, tdTimed, tdDur, tdStart, tdEnd, tdNotes, tdDel);
      els.body.appendChild(tr);
    });
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
        body: JSON.stringify({ task: "", timed: true, duration: 30, notes: "" }),
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

  window.addEventListener("beforeunload", (e) => {
    if (dirty) {
      e.preventDefault();
      e.returnValue = "";
    }
  });

  boot().catch((err) => toast("No se pudo cargar: " + err.message));
})();
