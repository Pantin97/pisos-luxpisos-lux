/* Pisos Lux — PWA. Lee listings.json (generado cada mañana por GitHub Actions),
   guarda "guardados/descartados" en este dispositivo y gestiona las notificaciones. */
(() => {
  "use strict";

  const KEY = "pisoslux:v1";
  const store = {
    load() { try { return JSON.parse(localStorage.getItem(KEY)) || {}; } catch { return {}; } },
    save(v) { try { localStorage.setItem(KEY, JSON.stringify(v)); } catch { /* sin almacenamiento */ } },
  };
  const persisted = store.load();
  const S = {
    data: null,
    loading: true,
    tab: initialTab(),
    sort: persisted.sort || "score",
    saved: persisted.saved || {},
    dropped: persisted.dropped || {},
    undo: null,
  };
  const persist = () => store.save({ saved: S.saved, dropped: S.dropped, sort: S.sort });

  function initialTab() {
    const q = new URLSearchParams(location.search).get("tab") || location.hash.replace("#", "");
    return ["revisar", "hoy", "guardados", "descartados", "mapa"].includes(q) ? (q === "hoy" ? "revisar" : q) : "revisar";
  }

  /* ── formato ── */
  const nf = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 0 });
  const nf1 = new Intl.NumberFormat("es-ES", { maximumFractionDigits: 1 });
  const eur = (n) => (n == null ? "—" : `${nf.format(n)} €`);
  const day = (iso) => new Intl.DateTimeFormat("es-ES", { day: "numeric", month: "short" }).format(new Date(iso));
  const when = (iso) => new Intl.DateTimeFormat("es-ES", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }).format(new Date(iso));
  const ord = (n) => (n === 0 ? "bajo" : n === 99 ? "último piso" : `${n}.ª planta`);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const scoreClass = (s) => (s >= 70 ? "s-good" : s >= 50 ? "s-mid" : "s-low");

  const ICON = {
    gear: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/></svg>',
    heart: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1-1.1a5.5 5.5 0 0 0-7.8 7.8l1 1.1L12 21l7.8-7.5 1-1.1a5.5 5.5 0 0 0 0-7.8z"/></svg>',
    heartFill: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1-1.1a5.5 5.5 0 0 0-7.8 7.8l1 1.1L12 21l7.8-7.5 1-1.1a5.5 5.5 0 0 0 0-7.8z"/></svg>',
    x: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M18 6 6 18M6 6l12 12"/></svg>',
    undo: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7v6h6"/><path d="M21 17a9 9 0 0 0-15-6.7L3 13"/></svg>',
    out: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><path d="M15 3h6v6M10 14 21 3"/></svg>',
  };

  /* ── datos ── */
  const all = () => (S.data ? S.data.listings : []);
  function sorted(list) {
    const by = {
      score: (a, b) => b.score - a.score || a.price - b.price,
      price: (a, b) => a.price - b.price,
      m2: (a, b) => a.eur_m2 - b.eur_m2,
      recent: (a, b) => b.last_seen.localeCompare(a.last_seen) || b.score - a.score,
      km: (a, b) => (a.km_to_work ?? 99) - (b.km_to_work ?? 99),
    }[S.sort];
    return [...list].sort(by);
  }
  const pending = () => all().filter((l) => !S.dropped[l.id]);
  const savedList = () => all().filter((l) => S.saved[l.id] && !S.dropped[l.id]);
  const droppedList = () => all().filter((l) => S.dropped[l.id]);

  /* ── render ── */
  const app = document.getElementById("app");

  function frame() {
    app.innerHTML = `
      <header class="top">
        <div class="brand">
          <div><h1>Pisos <span>Lux</span></h1><p id="subtitle">Cargando…</p></div>
          <button class="icon-btn" id="open-settings" aria-label="Ajustes y avisos">${ICON.gear}</button>
        </div>
        <p class="summary" id="summary"></p>
        <nav class="tabs" role="tablist" id="tabs"></nav>
      </header>
      <main id="main"></main>
      <p class="foot" id="foot"></p>
      <div id="sheet-root"></div>
      <div id="toast-root"></div>`;
    document.getElementById("open-settings").addEventListener("click", openSettings);
  }

  function renderHeader() {
    const d = S.data;
    document.getElementById("subtitle").textContent = d ? d.search.name : "Sin datos todavía";
    const s = d?.stats;
    document.getElementById("summary").innerHTML = d ? `
      <span><b>${s.count}</b> pisos</span>
      <span><b>${s.new_count}</b> nuevos</span>
      <span>mediana <b>${nf.format(s.median_eur_m2)} €/m²</b></span>
      <span>hasta <b>${eur(d.search.max_price)}</b></span>` : "";
    const tabs = [
      ["revisar", "Revisar", pending().length],
      ["guardados", "Guardados", savedList().length],
      ["mapa", "Mapa", null],
      ["descartados", "Descartados", droppedList().length],
    ];
    document.getElementById("tabs").innerHTML = tabs.map(([id, label, n]) => `
      <button class="tab" role="tab" data-tab="${id}" aria-selected="${S.tab === id}">${label}${n != null ? `<span class="n">${n}</span>` : ""}</button>`).join("");
    document.querySelectorAll(".tab").forEach((b) => b.addEventListener("click", () => {
      S.tab = b.dataset.tab; render(); window.scrollTo({ top: 0 });
    }));
    document.getElementById("foot").textContent = d
      ? `Actualizado ${when(d.generated_at)} · fuente: alertas de Immotop en tu Gmail`
      : "";
  }

  function toolbar(count) {
    return `<div class="toolbar">
      <p class="hint">${count} ${count === 1 ? "piso" : "pisos"} · desliza → guardar, ← descartar</p>
      <label for="sort">Ordenar
        <select id="sort">
          ${[["score", "Puntuación"], ["price", "Precio"], ["m2", "€/m²"], ["km", "Distancia"], ["recent", "Más recientes"]]
            .map(([v, l]) => `<option value="${v}" ${S.sort === v ? "selected" : ""}>${l}</option>`).join("")}
        </select>
      </label>
    </div>`;
  }

  function scoreRing(score) {
    const r = 24, c = 2 * Math.PI * r;
    return `<div class="score ${scoreClass(score)}" role="img" aria-label="Puntuación ${score} de 100">
      <svg viewBox="0 0 56 56" width="56" height="56"><circle class="track" cx="28" cy="28" r="${r}" fill="none" stroke-width="5"/>
      <circle class="arc" cx="28" cy="28" r="${r}" fill="none" stroke-width="5" stroke-dasharray="${(c * score) / 100} ${c}"/></svg>
      <b>${score}</b></div>`;
  }

  function chips(l) {
    const out = [];
    if (l.badges.includes("nuevo")) out.push('<span class="chip new">Nuevo</span>');
    if (l.badges.includes("bajada")) out.push('<span class="chip drop">Bajada de precio</span>');
    if (l.badges.includes("reanunciado"))
      out.push(`<span class="chip relist" title="Ha aparecido en ${l.alert_count} alertas distintas: lleva tiempo sin venderse">Reanunciado ×${l.alert_count}</span>`);
    if (l.badges.includes("duplicado")) out.push('<span class="chip">Varios anuncios</span>');
    if (S.saved[l.id]) out.push('<span class="chip drop">Guardado</span>');
    return out.length ? `<div class="chips">${out.join("")}</div>` : "";
  }

  function m2Bar(l) {
    if (!l.eur_m2_ref) return "";
    const delta = (l.eur_m2 - l.eur_m2_ref) / l.eur_m2_ref;
    const pct = Math.round(delta * 100);
    const pos = 50 + (Math.max(-0.3, Math.min(0.3, delta)) / 0.3) * 50;
    const cls = pct <= -3 ? "good" : pct >= 3 ? "bad" : "flat";
    const refLabel = l.ref_kind === "zona" ? `ref. ${l.zone}` : "mediana";
    const txt = pct === 0 ? `igual que la ${refLabel}` : `${pct > 0 ? "+" : "−"}${Math.abs(pct)} % vs ${refLabel}`;
    return `<div class="m2">
      <div class="m2-top"><span>${nf.format(l.eur_m2)} €/m²</span><span class="delta ${cls}">${txt}</span></div>
      <div class="m2-bar" aria-hidden="true"><span class="ref"></span><span class="dot" style="left:${pos}%"></span></div>
      <div class="m2-scale"><span>−30 %</span><span>${nf.format(l.eur_m2_ref)}</span><span>+30 %</span></div>
    </div>`;
  }

  function facts(l) {
    const f = [`${nf1.format(l.surface)} m²`];
    if (l.rooms != null) f.push(`${l.rooms} dorm.`);
    if (l.baths != null) f.push(`${l.baths} baño${l.baths > 1 ? "s" : ""}`);
    if (l.floor != null) f.push(ord(l.floor));
    return f.join(" · ");
  }

  function why(l) {
    const p = l.score_parts, w = S.data.weights || {};
    const wsum = Object.values(w).reduce((a, b) => a + b, 0) || 1;
    const rows = [
      ["value", "Precio/m²", `${nf.format(l.eur_m2)} vs ${nf.format(l.eur_m2_ref)}`],
      ["size", "Superficie", `${nf1.format(l.surface)} m²`],
      ["commute", "Trayecto", l.km_to_work != null ? `${nf1.format(l.km_to_work)} km` : "sin ubicar"],
      ["extras", "Extras", l.extras_reasons.length ? l.extras_reasons.join(", ") : "ninguno detectado"],
    ];
    return `<details class="why"><summary>Por qué ${l.score}</summary>
      <div class="parts">${rows.map(([k, label, detail]) => `
        <div class="part"><span>${label} <small>${Math.round((100 * (w[k] || 0)) / wsum)} %</small></span>
          <span class="bar"><i style="width:${p[k]}%"></i></span><b>${p[k]}</b></div>
        <div class="part" style="margin-top:-6px"><small style="grid-column:1/-1">${esc(detail)}</small></div>`).join("")}
      </div>
      <p class="note">Distancia en línea recta hasta ${esc(S.data.work.label)}, calculada ${l.geo_precision === "calle" ? "desde la calle" : "desde el centro del barrio"}.</p>
    </details>`;
  }

  function card(l) {
    const isSaved = !!S.saved[l.id], isDropped = !!S.dropped[l.id];
    const prices = l.price_history.map((p) => p.price).filter(Boolean);
    const old = prices.length > 1 && prices[0] > l.price ? `<span class="price-old">${eur(prices[0])}</span>` : "";
    const others = l.zones.length > 1 ? `<p class="also">También anunciado en ${l.zones.filter((z) => z !== l.zone).map(esc).join(", ")}: probablemente el mismo inmueble con otra agencia.</p>` : "";
    return `<article class="card ${isSaved ? "is-saved" : ""}" data-id="${esc(l.id)}">
      <div class="swipe-bg" aria-hidden="true"><span>♥ Guardar</span><span>Descartar ✕</span></div>
      <div class="card-body">
        <header class="c-head">
          <div><h3 class="zone">${esc(l.zone || "Sin zona")}</h3><p class="ctitle">${esc(l.title)}</p></div>
          ${scoreRing(l.score)}
        </header>
        ${chips(l)}
        <div class="price-row"><span class="price">${eur(l.price)}</span>${old}<span class="facts">${facts(l)}</span></div>
        ${m2Bar(l)}
        <dl class="meta">
          <div><dt>Trayecto</dt><dd>${l.km_to_work != null ? `${nf1.format(l.km_to_work)} km` : "—"}</dd></div>
          <div><dt>Visto desde</dt><dd>${day(l.first_seen)} · ${l.days_listed} d</dd></div>
          <div><dt>Alertas</dt><dd>${l.alert_count}${l.alert_count > 1 ? ` · última ${day(l.last_seen)}` : ""}</dd></div>
        </dl>
        ${others}
        ${why(l)}
        <div class="actions">
          ${isDropped
            ? `<button class="btn" data-act="restore">${ICON.undo} Recuperar</button>`
            : `<button class="btn ${isSaved ? "on-save" : ""}" data-act="save" aria-pressed="${isSaved}">${isSaved ? ICON.heartFill : ICON.heart} ${isSaved ? "Guardado" : "Guardar"}</button>
               <button class="btn quiet" data-act="drop">${ICON.x} Descartar</button>`}
          ${l.url ? `<a class="btn primary" href="${esc(l.url)}" target="_blank" rel="noopener">Ver anuncio ${ICON.out}</a>` : ""}
        </div>
      </div>
    </article>`;
  }

  function emptyState(title, text) {
    return `<div class="empty"><h3>${title}</h3><p>${text}</p></div>`;
  }

  function renderList(list, emptyTitle, emptyText) {
    if (!list.length) return emptyState(emptyTitle, emptyText);
    const items = sorted(list);
    if (S.tab === "revisar") {
      const fresh = items.filter((l) => l.is_new), rest = items.filter((l) => !l.is_new);
      return `${toolbar(items.length)}
        ${fresh.length ? `<p class="section-label">Nuevos hoy</p><div class="list">${fresh.map(card).join("")}</div>` : ""}
        ${rest.length ? `${fresh.length ? '<p class="section-label">Anteriores</p>' : ""}<div class="list">${rest.map(card).join("")}</div>` : ""}`;
    }
    return `${toolbar(items.length)}<div class="list">${items.map(card).join("")}</div>`;
  }

  function renderMap() {
    const d = S.data, list = pending().filter((l) => l.lat != null);
    if (!list.length) return emptyState("Nada que situar", "Los pisos aparecerán aquí cuando tengan ubicación.");
    const lat0 = d.work.lat, lon0 = d.work.lon, kx = 111.32 * Math.cos((lat0 * Math.PI) / 180), ky = 110.57;
    const proj = (lat, lon) => [(lon - lon0) * kx, -(lat - lat0) * ky];
    const city = [49.6116, 6.13];
    const pts = [[0, 0], proj(...city), ...list.map((l) => proj(l.lat, l.lon))];
    const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
    const pad = 2.2, minX = Math.min(...xs) - pad, maxX = Math.max(...xs) + pad, minY = Math.min(...ys) - pad, maxY = Math.max(...ys) + pad;
    const W = 360, scale = W / (maxX - minX), H = Math.max(200, (maxY - minY) * scale);
    const offY = (H - (maxY - minY) * scale) / 2;
    const P = ([x, y]) => [(x - minX) * scale, (y - minY) * scale + offY];
    const [wx, wy] = P([0, 0]);
    const rings = [5, 10, 15].map((km) => `<circle class="ring" cx="${wx}" cy="${wy}" r="${km * scale}"/>
      <text class="ring-label" x="${wx + km * scale * 0.71 + 3}" y="${wy - km * scale * 0.71 - 3}">${km} km</text>`).join("");
    const groups = new Map();
    list.forEach((l) => {
      const k = `${l.lat.toFixed(4)},${l.lon.toFixed(4)}`;
      (groups.get(k) || groups.set(k, []).get(k)).push(l);
    });
    const colorFor = (s) => (s >= 70 ? "var(--good)" : s >= 50 ? "var(--accent)" : "var(--muted)");
    const pins = [...groups.values()].map((g) => {
      const best = g.reduce((a, b) => (b.score > a.score ? b : a));
      const [x, y] = P(proj(best.lat, best.lon));
      const label = `${best.zone}${g.length > 1 ? ` ×${g.length}` : ""} · ${best.score}`;
      const anchorEnd = x > W * 0.55;
      return `<circle class="pin" cx="${x}" cy="${y}" r="${8 + Math.min(4, g.length)}" fill="${colorFor(best.score)}"/>
        <text class="pin-label" x="${x + (anchorEnd ? -14 : 14)}" y="${y + 4}" text-anchor="${anchorEnd ? "end" : "start"}">${esc(label)}</text>`;
    }).join("");
    const [cx, cy] = P(proj(...city));
    const rows = [...list].sort((a, b) => a.km_to_work - b.km_to_work).map((l) => `
      <button class="map-row" data-goto="${esc(l.id)}"><i style="background:${colorFor(l.score)}"></i>
        <span>${esc(l.zone)} · ${eur(l.price)}</span><span>${nf1.format(l.km_to_work)} km</span><span>${l.score}</span></button>`).join("");
    return `<p class="section-label">Distancia en línea recta a ${esc(d.work.label)}</p>
      <div class="map-wrap">
        <svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Mapa esquemático de los pisos respecto al trabajo">
          ${rings}
          <text class="city" x="${cx}" y="${cy + 30}" text-anchor="middle">LUXEMBOURG-VILLE</text>
          <rect class="work" x="${wx - 7}" y="${wy - 7}" width="14" height="14" rx="3"/>
          <text class="work-label" x="${wx + 12}" y="${wy + 22}">${esc(d.work.label)}</text>
          ${pins}
        </svg>
        <div class="map-legend">${rows}</div>
      </div>`;
  }

  function render() {
    renderHeader();
    const main = document.getElementById("main");
    if (S.loading) { main.innerHTML = emptyState("Cargando pisos…", "Leyendo la última actualización."); return; }
    if (!S.data) { main.innerHTML = emptyState("Sin datos", "No se ha podido cargar listings.json. Comprueba que la ejecución diaria ha terminado."); return; }
    if (S.tab === "revisar") main.innerHTML = renderList(pending(), "Todo revisado", "No queda ningún piso pendiente. Mañana por la mañana llegan los nuevos.");
    else if (S.tab === "guardados") main.innerHTML = renderList(savedList(), "Aún no has guardado ninguno", "Pulsa Guardar o desliza una tarjeta a la derecha para tenerla aquí.");
    else if (S.tab === "descartados") main.innerHTML = renderList(droppedList(), "Nada descartado", "Los pisos que descartes se quedan aquí por si cambias de idea.");
    else main.innerHTML = renderMap();
    const sel = document.getElementById("sort");
    if (sel) sel.addEventListener("change", () => { S.sort = sel.value; persist(); render(); });
    bindCards();
  }

  /* ── acciones ── */
  function act(id, what) {
    if (what === "save") { S.saved[id] ? delete S.saved[id] : (S.saved[id] = Date.now()); }
    if (what === "drop") { S.dropped[id] = Date.now(); delete S.saved[id]; toast("Descartado", () => { delete S.dropped[id]; persist(); render(); }); }
    if (what === "restore") delete S.dropped[id];
    persist(); render();
  }

  function bindCards() {
    document.querySelectorAll("[data-act]").forEach((b) => b.addEventListener("click", () => act(b.closest(".card").dataset.id, b.dataset.act)));
    document.querySelectorAll("[data-goto]").forEach((b) => b.addEventListener("click", () => {
      S.tab = "revisar"; render();
      const el = document.querySelector(`.card[data-id="${CSS.escape(b.dataset.goto)}"]`);
      if (el) el.scrollIntoView({ behavior: "smooth", block: "center" });
    }));
    if (S.tab === "descartados") return;
    document.querySelectorAll(".card").forEach(swipeable);
  }

  function swipeable(cardEl) {
    const body = cardEl.querySelector(".card-body");
    let x0 = 0, y0 = 0, dx = 0, active = false, locked = null;
    cardEl.addEventListener("touchstart", (e) => {
      if (e.target.closest("a,button,select,summary")) return;
      const t = e.touches[0]; x0 = t.clientX; y0 = t.clientY; dx = 0; active = true; locked = null;
    }, { passive: true });
    cardEl.addEventListener("touchmove", (e) => {
      if (!active) return;
      const t = e.touches[0]; const mx = t.clientX - x0, my = t.clientY - y0;
      if (locked === null && Math.abs(mx) + Math.abs(my) > 10) locked = Math.abs(mx) > Math.abs(my) ? "x" : "y";
      if (locked !== "x") return;
      dx = mx; cardEl.classList.add("dragging");
      cardEl.classList.toggle("dir-save", dx > 0); cardEl.classList.toggle("dir-drop", dx < 0);
      body.style.transform = `translateX(${dx}px) rotate(${dx / 60}deg)`;
    }, { passive: true });
    const end = () => {
      if (!active) return; active = false; cardEl.classList.remove("dragging");
      const id = cardEl.dataset.id;
      if (Math.abs(dx) > 96) {
        body.style.transform = `translateX(${dx > 0 ? 120 : -120}%)`; body.style.opacity = "0";
        setTimeout(() => act(id, dx > 0 ? "save" : "drop"), 180);
      } else {
        body.style.transform = ""; cardEl.classList.remove("dir-save", "dir-drop");
      }
    };
    cardEl.addEventListener("touchend", end); cardEl.addEventListener("touchcancel", end);
  }

  function toast(text, onUndo) {
    const root = document.getElementById("toast-root");
    clearTimeout(S.undo);
    root.innerHTML = `<div class="toast" role="status">${esc(text)}${onUndo ? '<button id="undo">Deshacer</button>' : ""}</div>`;
    if (onUndo) document.getElementById("undo").addEventListener("click", () => { root.innerHTML = ""; onUndo(); });
    S.undo = setTimeout(() => { root.innerHTML = ""; }, 4000);
  }

  /* ── ajustes y notificaciones ── */
  const isStandalone = () => window.matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;
  const pushSupported = () => "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;

  function b64ToBytes(b64) {
    const pad = "=".repeat((4 - (b64.length % 4)) % 4);
    const raw = atob((b64 + pad).replace(/-/g, "+").replace(/_/g, "/"));
    return Uint8Array.from(raw, (c) => c.charCodeAt(0));
  }

  async function currentSubscription() {
    try { const reg = await navigator.serviceWorker.ready; return await reg.pushManager.getSubscription(); } catch { return null; }
  }

  async function openSettings() {
    const root = document.getElementById("sheet-root");
    const key = S.data?.vapid_public_key;
    let pushBlock;
    if (!pushSupported()) {
      pushBlock = `<span class="status">No disponible en esta vista</span>
        <p>Las notificaciones funcionan cuando abres la app desde su dirección de GitHub Pages y la añades a la pantalla de inicio.</p>`;
    } else if (!isStandalone() && /iPhone|iPad/.test(navigator.userAgent)) {
      pushBlock = `<span class="status">Primero instálala</span>
        <ol><li>Abre esta página en Safari.</li><li>Pulsa Compartir y luego «Añadir a pantalla de inicio».</li><li>Abre Pisos Lux desde el icono y vuelve aquí.</li></ol>`;
    } else if (!key) {
      pushBlock = `<span class="status err">Falta la clave pública</span><p>Añade el secreto VAPID_PUBLIC_KEY en GitHub y espera a la siguiente ejecución.</p>`;
    } else {
      const sub = await currentSubscription();
      pushBlock = sub
        ? `<span class="status ok">Avisos activados en este dispositivo</span>
           <p>Copia esto en GitHub → Settings → Secrets → Actions, en el secreto <b>PUSH_SUBSCRIPTIONS</b>. Solo hace falta una vez.</p>
           <textarea id="sub-json" readonly>${esc(JSON.stringify(sub))}</textarea>
           <div class="row"><button class="btn primary" id="copy-sub" style="margin-left:0">Copiar</button><button class="btn" id="test-local">Probar aviso</button></div>`
        : `<span class="status">Avisos desactivados</span>
           <p>Recibe cada mañana cuántos pisos nuevos hay y cuál puntúa mejor.</p>
           <div class="row"><button class="btn primary" id="enable-push" style="margin-left:0">Activar avisos</button></div>`;
    }
    root.innerHTML = `<div class="sheet-backdrop" id="sheet-close"></div>
      <div class="sheet" role="dialog" aria-modal="true" aria-labelledby="sheet-title"><div class="sheet-inner">
        <div class="grabber"></div>
        <h2 id="sheet-title">Ajustes</h2>
        <section><h3>Avisos diarios</h3>${pushBlock}<p id="push-msg"></p></section>
        <section><h3>Tu búsqueda</h3>
          <p>${esc(S.data?.search.name || "")} · hasta ${eur(S.data?.search.max_price)} · ${S.data?.search.min_rooms}+ dormitorios · desde ${S.data?.search.min_surface} m².</p>
          <p>Los filtros, pesos y palabras clave se cambian en <b>config.yaml</b> del repositorio.</p></section>
        <section><h3>En este dispositivo</h3>
          <p>${Object.keys(S.saved).length} guardados · ${Object.keys(S.dropped).length} descartados. Se guardan solo en este navegador.</p>
          <div class="row" id="reset-row"><button class="btn" id="reset">Vaciar descartados</button></div></section>
        <button class="btn" id="sheet-done">Cerrar</button>
      </div></div>`;
    const close = () => { root.innerHTML = ""; };
    document.getElementById("sheet-close").addEventListener("click", close);
    document.getElementById("sheet-done").addEventListener("click", close);
    document.getElementById("reset").addEventListener("click", () => {
      document.getElementById("reset-row").innerHTML = `<span>¿Recuperar los ${Object.keys(S.dropped).length} descartados?</span>
        <button class="btn" id="reset-yes">Sí, recuperar</button><button class="btn quiet" id="reset-no">Cancelar</button>`;
      document.getElementById("reset-yes").addEventListener("click", () => { S.dropped = {}; persist(); close(); render(); toast("Descartados recuperados"); });
      document.getElementById("reset-no").addEventListener("click", openSettings);
    });
    const en = document.getElementById("enable-push");
    if (en) en.addEventListener("click", async () => {
      const msg = document.getElementById("push-msg");
      try {
        const perm = await Notification.requestPermission();
        if (perm !== "granted") { msg.textContent = "Permiso denegado. Actívalo en Ajustes del iPhone → Notificaciones → Pisos Lux."; return; }
        const reg = await navigator.serviceWorker.ready;
        await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64ToBytes(key) });
        openSettings();
      } catch (e) { msg.textContent = `No se pudo activar: ${e.message}`; }
    });
    const cp = document.getElementById("copy-sub");
    if (cp) cp.addEventListener("click", () => {
      const ta = document.getElementById("sub-json");
      navigator.clipboard.writeText(ta.value).then(() => toast("Copiado")).catch(() => { ta.focus(); ta.select(); toast("Selecciónalo y cópialo"); });
    });
    const tl = document.getElementById("test-local");
    if (tl) tl.addEventListener("click", async () => {
      const reg = await navigator.serviceWorker.ready;
      reg.showNotification("Pisos Lux", { body: "Así se verá el aviso de cada mañana.", icon: "icons/icon-192.png", tag: "prueba" });
    });
  }

  /* ── arranque ── */
  async function load() {
    try {
      const r = await fetch("listings.json", { cache: "no-store" });
      if (!r.ok) throw new Error(r.status);
      S.data = await r.json();
    } catch { S.data = S.data || null; }
    S.loading = false;
    render();
  }

  frame();
  render();
  load();
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("sw.js").catch(() => { /* vista previa: sin service worker */ });
  }
  document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") load(); });
})();
