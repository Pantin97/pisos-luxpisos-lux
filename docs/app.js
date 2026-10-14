/* Pisos Lux — PWA (Liquid Glass).
   Lee listings.json, guarda guardados/descartados en el dispositivo, lanza escaneos
   bajo demanda en GitHub Actions y gestiona las notificaciones push. */
(() => {
  "use strict";

  /* ───────────── estado ───────────── */
  const KEY = "pisoslux:v2";
  const store = {
    load() { try { return JSON.parse(localStorage.getItem(KEY)) || {}; } catch { return {}; } },
    save(v) { try { localStorage.setItem(KEY, JSON.stringify(v)); } catch { /* sin almacenamiento */ } },
  };
  const P = store.load();
  const S = {
    data: null, loading: true,
    view: initialView(),
    filter: "todos",
    sort: P.sort || "score",
    saved: P.saved || {}, dropped: P.dropped || {},
    token: P.token || "",
    shown: 20,
    scan: null,
    map: null,
  };
  const persist = () => store.save({ saved: S.saved, dropped: S.dropped, sort: S.sort, token: S.token });

  function initialView() {
    const q = new URLSearchParams(location.search).get("tab") || location.hash.replace("#", "");
    if (q === "nuevos") { return "inicio"; }
    return ["inicio", "mapa", "guardados", "ajustes"].includes(q) ? q : "inicio";
  }

  /* ───────────── formato ───────────── */
  const nf = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 0 });
  const nf1 = new Intl.NumberFormat("es-ES", { maximumFractionDigits: 1 });
  const eur = (n) => (n == null ? "—" : `${nf.format(n)} €`);
  const kEur = (n) => (n >= 1e6 ? `${nf1.format(n / 1e6)} M` : `${Math.round(n / 1000)}k`);
  const day = (iso) => new Intl.DateTimeFormat("es-ES", { day: "numeric", month: "short" }).format(new Date(iso));
  const when = (iso) => new Intl.DateTimeFormat("es-ES", { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }).format(new Date(iso));
  const ago = (iso) => {
    const m = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
    if (m < 1) return "ahora"; if (m < 60) return `hace ${m} min`;
    const h = Math.round(m / 60); if (h < 24) return `hace ${h} h`;
    return `hace ${Math.round(h / 24)} d`;
  };
  const floorTxt = (n) => (n === 0 ? "bajo" : n >= 90 ? "último piso" : `${n}.ª planta`);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const safeUrl = (u) => (/^https?:\/\//i.test(u || "") ? u : null);

  /* ───────────── iconos (trazo tipo SF Symbols) ───────────── */
  const I = {
    house: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V20a1 1 0 0 0 1 1h4v-6h4v6h4a1 1 0 0 0 1-1V9.5"/></svg>',
    map: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="m9 4-6 2.5v13L9 17l6 2.5 6-2.5v-13L15 6.5z"/><path d="M9 4v13M15 6.5v13"/></svg>',
    heart: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1-1.1a5.5 5.5 0 0 0-7.8 7.8l1 1.1L12 21l7.8-7.5 1-1.1a5.5 5.5 0 0 0 0-7.8z"/></svg>',
    heartFill: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1-1.1a5.5 5.5 0 0 0-7.8 7.8l1 1.1L12 21l7.8-7.5 1-1.1a5.5 5.5 0 0 0 0-7.8z"/></svg>',
    gear: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3.2"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/></svg>',
    scan: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-2.64-6.36"/><path d="M21 4v5h-5"/></svg>',
    x: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M18 6 6 18M6 6l12 12"/></svg>',
    out: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 4h6v6"/><path d="M10 14 20 4"/><path d="M19 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h5"/></svg>',
    pin: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 21s-7-6.1-7-11.5a7 7 0 0 1 14 0C19 14.9 12 21 12 21z"/><circle cx="12" cy="9.5" r="2.5"/></svg>',
    photo: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="5" width="18" height="14" rx="3"/><circle cx="9" cy="10" r="1.8"/><path d="m21 16-5-5-8 8"/></svg>',
    sort: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 4v16M3 16l4 4 4-4M17 20V4M13 8l4-4 4 4"/></svg>',
  };

  /* ───────────── datos derivados ───────────── */
  const all = () => (S.data ? S.data.listings : []);
  const byId = (id) => all().find((l) => l.id === id);
  const FILTERS = [
    ["todos", "Todos", (l) => l.active],
    ["nuevos", "Nuevos", (l) => l.is_new],
    ["bajadas", "Bajadas", (l) => l.badges.includes("bajada")],
    ["exclusivos", "Solo en agencia", (l) => l.badges.includes("exclusivo")],
    ["multi", "En varios portales", (l) => l.badges.includes("multi")],
    ["obra", "Obra nueva", (l) => l.badges.includes("obra nueva")],
  ];
  const SORTS = [["score", "Puntuación"], ["price", "Precio"], ["m2", "€/m²"], ["km", "Distancia"], ["recent", "Más recientes"]];
  const sortFns = {
    score: (a, b) => b.score - a.score || a.price - b.price,
    price: (a, b) => a.price - b.price,
    m2: (a, b) => a.eur_m2 - b.eur_m2,
    km: (a, b) => (a.km_to_work ?? 99) - (b.km_to_work ?? 99),
    recent: (a, b) => b.first_seen.localeCompare(a.first_seen) || b.score - a.score,
  };
  const pool = () => all().filter((l) => !S.dropped[l.id]);
  function feedList() {
    const f = FILTERS.find((x) => x[0] === S.filter) || FILTERS[0];
    return pool().filter((l) => l.active && f[2](l)).sort(sortFns[S.sort]);
  }
  const savedList = () => all().filter((l) => S.saved[l.id]).sort(sortFns[S.sort]);
  const repo = () => S.data?.repo || (() => {
    const owner = location.hostname.split(".")[0];
    const name = location.pathname.split("/").filter(Boolean)[0];
    return owner && name && location.hostname.endsWith("github.io") ? `${owner}/${name}` : null;
  })();

  /* ───────────── esqueleto ───────────── */
  const root = document.getElementById("app");
  function frame() {
    root.innerHTML = `
      <div class="aurora" aria-hidden="true"><i></i><i></i><i></i></div>
      <header class="navbar glass" id="navbar"><b id="nav-title">Pisos</b></header>
      <main class="app" id="main"></main>
      <nav class="dock" aria-label="Secciones">
        <div class="tabbar glass" role="tablist" id="tabbar"></div>
        <button class="scan-btn glass" id="scan-btn" aria-label="Escanear ahora">${I.scan}</button>
      </nav>
      <div id="sheet-root"></div><div id="toast-root"></div>`;
    document.getElementById("scan-btn").addEventListener("click", openScan);
  }

  function renderTabs() {
    const tabs = [["inicio", "Pisos", I.house], ["mapa", "Mapa", I.map], ["guardados", "Guardados", I.heart], ["ajustes", "Ajustes", I.gear]];
    const bar = document.getElementById("tabbar");
    bar.innerHTML = tabs.map(([id, label, icon]) =>
      `<button class="tab" role="tab" data-view="${id}" aria-selected="${S.view === id}">${icon}<span>${label}</span></button>`).join("");
    bar.querySelectorAll(".tab").forEach((b) => b.addEventListener("click", () => {
      if (S.view === b.dataset.view) { window.scrollTo({ top: 0, behavior: "smooth" }); return; }
      S.view = b.dataset.view; S.shown = 20; render(); window.scrollTo({ top: 0 });
    }));
    document.getElementById("scan-btn").classList.toggle("busy", !!(S.scan && !S.scan.done));
  }

  function largeTitle(title, sub, actions = "") {
    return `<div class="large-title"><div><h1 id="lt">${esc(title)}</h1>${sub ? `<p>${sub}</p>` : ""}</div>
      <div class="title-actions">${actions}</div></div>`;
  }

  function watchTitle(title) {
    document.getElementById("nav-title").textContent = title;
    const nav = document.getElementById("navbar"), h1 = document.getElementById("lt");
    if (!h1 || !("IntersectionObserver" in window)) return;
    new IntersectionObserver(([e]) => nav.classList.toggle("show", !e.isIntersecting), { rootMargin: "-40px 0px 0px 0px" }).observe(h1);
  }

  /* ───────────── tarjetas ───────────── */
  function tags(l) {
    const t = [];
    if (l.badges.includes("retirado")) t.push('<span class="tag gone">Retirado</span>');
    if (l.is_new) t.push('<span class="tag new">Nuevo</span>');
    if (l.badges.includes("bajada")) t.push('<span class="tag drop">↓ Bajada</span>');
    if (l.badges.includes("exclusivo")) t.push(`<span class="tag excl">Solo en ${esc(l.only_on || "agencia")}</span>`);
    if (l.badges.includes("reanunciado")) t.push('<span class="tag relist">Reanunciado</span>');
    if (l.badges.includes("obra nueva")) t.push('<span class="tag">Obra nueva</span>');
    return t.join("");
  }

  function gallery(l, cls = "") {
    if (!l.photos.length) return `<div class="noimg">${I.photo}</div>`;
    return `<div class="gallery ${cls}">${l.photos.map((p, i) =>
      `<img src="${esc(p)}" alt="Foto ${i + 1} de ${esc(l.zone || "el piso")}" loading="${i ? "lazy" : "lazy"}" decoding="async" referrerpolicy="no-referrer">`).join("")}</div>`;
  }

  function m2Bar(l) {
    if (!l.eur_m2_ref) return "";
    const d = (l.eur_m2 - l.eur_m2_ref) / l.eur_m2_ref, pct = Math.round(d * 100);
    const pos = 50 + (Math.max(-0.3, Math.min(0.3, d)) / 0.3) * 50;
    const cls = pct <= -3 ? "good" : pct >= 3 ? "bad" : "flat";
    const ref = { barrio: `mediana de ${l.zone}`, ciudad: "mediana de la ciudad", config: "tu referencia" }[l.ref_kind] || "mediana";
    return `<div class="m2"><div class="m2-top"><span>${nf.format(l.eur_m2)} €/m²</span>
      <span class="${cls}">${pct === 0 ? "en la" : `${pct > 0 ? "+" : "−"}${Math.abs(pct)} % vs`} ${esc(ref)}</span></div>
      <div class="m2-bar" aria-hidden="true"><span class="mid"></span><span class="dot" style="left:${pos}%"></span></div></div>`;
  }

  function facts(l) {
    const f = [`<span><b>${nf1.format(l.surface)}</b> m²</span>`];
    if (l.rooms != null) f.push(`<span><b>${l.rooms}</b> dorm.</span>`);
    if (l.baths) f.push(`<span><b>${l.baths}</b> baño${l.baths > 1 ? "s" : ""}</span>`);
    if (l.floor != null) f.push(`<span>${floorTxt(l.floor)}</span>`);
    l.features.slice(0, 3).forEach((x) => f.push(`<span>${esc(x)}</span>`));
    return `<div class="facts">${f.join("")}</div>`;
  }

  function sourceLine(l) {
    const s = l.sources.map((x) => (x.key === "trovit" && l.vias.length ? `Trovit · ${esc(l.vias[0])}` : esc(x.name)));
    if (l.agencies[0]) s.push(esc(l.agencies[0]));
    return `<div class="src">${s.map((x) => `<span>${x}</span>`).join("")}</div>`;
  }

  function primaryUrl(l) {
    const pref = ["athome", "wortimmo", "immotop", "trovit"];
    for (const k of pref) { const s = l.sources.find((x) => x.key === k && safeUrl(x.url)); if (s) return s.url; }
    return null;
  }

  function card(l) {
    const saved = !!S.saved[l.id];
    const prices = l.price_history.map((p) => p.price).filter(Boolean);
    const old = prices.length > 1 && Math.max(...prices) > l.price ? `<span class="price-old">${eur(Math.max(...prices))}</span>` : "";
    const url = primaryUrl(l);
    return `<article class="card ${l.active ? "" : "retired"}" data-id="${esc(l.id)}">
      <div class="swipe-hint" aria-hidden="true"><span>♥ Guardar</span><span>Descartar ✕</span></div>
      <div class="card-inner" role="button" tabindex="0" aria-label="${esc(l.zone)}, ${eur(l.price)}">
        <div class="media">${gallery(l)}
          <div class="overlay-top"><div class="badges">${tags(l)}</div>
            <span class="score-pill ${l.score >= 70 ? "hi" : ""}" aria-label="Puntuación ${l.score}">${l.score}</span></div>
          <div class="overlay-bottom"><div><span class="price">${eur(l.price)}</span>${old}</div>
            ${l.photos.length > 1 ? `<div class="dots">${l.photos.map((_, i) => `<i class="${i ? "" : "on"}"></i>`).join("")}</div>` : ""}</div>
        </div>
        <div class="body">
          <div class="row1"><h3 class="zone">${esc(l.zone || "Luxemburgo")}</h3>
            ${l.km_to_work != null ? `<span class="km">${I.pin}${nf1.format(l.km_to_work)} km</span>` : ""}</div>
          ${facts(l)}${m2Bar(l)}${sourceLine(l)}
          <div class="actions">
            <button class="pill-btn ${saved ? "on" : ""}" data-act="save" aria-pressed="${saved}" aria-label="${saved ? "Quitar de guardados" : "Guardar"}">${saved ? I.heartFill : I.heart}</button>
            <button class="pill-btn" data-act="drop" aria-label="Descartar">${I.x}</button>
            ${url ? `<a class="pill-btn primary" href="${esc(url)}" target="_blank" rel="noopener">Ver anuncio ${I.out}</a>` : ""}
          </div>
        </div>
      </div>
    </article>`;
  }

  function emptyState(t, p) { return `<div class="empty glass"><h3>${t}</h3><p>${p}</p></div>`; }

  /* ───────────── vistas ───────────── */
  function viewInicio() {
    const d = S.data, s = d.stats, list = feedList();
    const counts = Object.fromEntries(FILTERS.map(([id, , fn]) => [id, pool().filter((l) => l.active && fn(l)).length]));
    const sub = `${esc(d.search.name)} · actualizado ${ago(d.generated_at)}`;
    const srcOk = (d.sources || []).filter((x) => !x.error).length;
    return `${largeTitle("Pisos", sub)}
      <div class="statline">
        <div class="stat glass"><b>${s.count}</b><span>activos</span></div>
        <div class="stat glass"><b>${s.new_count}</b><span>nuevos</span></div>
        <div class="stat glass"><b>${nf.format(s.median_eur_m2 || 0)}</b><span>€/m² mediana</span></div>
        <div class="stat glass"><b>${srcOk}/${(d.sources || []).length}</b><span>fuentes ok</span></div>
        <div class="stat glass"><b>${s.exclusive}</b><span>solo agencia</span></div>
      </div>
      <div class="chips" role="toolbar" aria-label="Filtros">${FILTERS.map(([id, label]) =>
        `<button class="chip glass" data-filter="${id}" aria-pressed="${S.filter === id}">${label}<span class="n">${counts[id]}</span></button>`).join("")}</div>
      <div class="sortbar"><span>${list.length} pisos</span>
        <label>${I.sort.replace("<svg", '<svg width="14" height="14" style="vertical-align:-2px;margin-right:4px"')}<select id="sort" aria-label="Ordenar">${SORTS.map(([v, t]) =>
          `<option value="${v}" ${S.sort === v ? "selected" : ""}>${t}</option>`).join("")}</select></label></div>
      ${list.length ? `<div class="feed">${list.slice(0, S.shown).map(card).join("")}</div>
        ${list.length > S.shown ? '<div class="more" id="more">Cargando más…</div>' : ""}`
        : emptyState("Nada por aquí", "Prueba otro filtro o lanza un escaneo con el botón de la derecha.")}`;
  }

  function viewGuardados() {
    const list = savedList();
    return `${largeTitle("Guardados", `${list.length} piso${list.length === 1 ? "" : "s"} en este dispositivo`)}
      ${list.length ? `<div class="feed" style="margin-top:14px">${list.map(card).join("")}</div>`
        : `<div style="margin-top:14px">${emptyState("Aún no has guardado ninguno", "Pulsa el corazón o desliza una tarjeta a la derecha.")}</div>`}`;
  }

  function viewMapa() {
    return `${largeTitle("Mapa", `Distancia a ${esc(S.data.work.label)}`)}
      <div class="map-wrap glass" style="margin-top:14px"><div id="map" role="application" aria-label="Mapa de pisos"></div>
        <div class="map-legend glass"><span><i style="background:var(--green)"></i>70+</span><span><i style="background:var(--tint)"></i>50–69</span><span><i style="background:#8a8f99"></i>&lt;50</span><span>■ trabajo</span></div></div>`;
  }

  function viewAjustes() {
    const d = S.data;
    const src = (d.sources || []).map((x) => `<div class="cell"><span class="k">${esc({ athome: "athome.lu", wortimmo: "wortimmo.lu", trovit: "Trovit", immotop: "Immotop (email)" }[x.name] || x.name)}</span>
      <span class="v">${x.error ? `<span class="status err">Error</span>` : `${x.items} anuncios${x.total_reported ? ` / ${nf.format(x.total_reported)}` : ""}`}</span></div>`).join("");
    const zones = (d.zones || []).slice(0, 12).map((z) => `<div class="cell"><span class="k">${esc(z.zone)}</span><span class="v">${nf.format(z.median_eur_m2)} €/m² · ${z.n}</span></div>`).join("");
    return `${largeTitle("Ajustes", "")}
      <p class="group-label">Escanear desde la app</p>
      <div class="group"><div class="cell stack" id="token-cell"></div></div>
      <p class="group-label">Avisos</p>
      <div class="group"><div class="cell stack" id="push-cell"><span class="status">Comprobando…</span></div></div>
      <p class="group-label">Fuentes · último escaneo ${d.mode === "quick" ? "rápido" : "completo"} ${ago(d.generated_at)}</p>
      <div class="group">${src}</div>
      <p class="note">Immotop bloquea las descargas automáticas: sus anuncios llegan por tus alertas de email y a través de Trovit.</p>
      <p class="group-label">€/m² por barrio</p>
      <div class="group">${zones}</div>
      <p class="group-label">Tu búsqueda</p>
      <div class="group">
        <div class="cell"><span class="k">Presupuesto</span><span class="v">${eur(d.search.min_price || 0)} – ${eur(d.search.max_price)}</span></div>
        <div class="cell"><span class="k">Dormitorios</span><span class="v">${d.search.min_rooms}+</span></div>
        <div class="cell"><span class="k">Superficie</span><span class="v">${d.search.min_surface}+ m²</span></div>
      </div>
      <p class="note">Filtros, pesos y fuentes se cambian en config.yaml del repositorio.</p>
      <p class="group-label">En este dispositivo</p>
      <div class="group">
        <div class="cell"><span class="k">Guardados</span><span class="v">${Object.keys(S.saved).length}</span></div>
        <div class="cell" id="reset-cell"><span class="k">Descartados</span><span class="v">${Object.keys(S.dropped).length} · <a href="#" id="reset">Recuperar</a></span></div>
      </div>`;
  }

  /* ───────────── render ───────────── */
  function render() {
    renderTabs();
    const main = document.getElementById("main");
    if (S.loading) { main.innerHTML = `${largeTitle("Pisos", "Cargando…")}`; return; }
    if (!S.data) { main.innerHTML = `${largeTitle("Pisos", "")}${emptyState("Sin datos", "No se ha podido cargar listings.json.")}`; return; }
    const views = { inicio: viewInicio, guardados: viewGuardados, mapa: viewMapa, ajustes: viewAjustes };
    main.innerHTML = views[S.view]();
    watchTitle({ inicio: "Pisos", mapa: "Mapa", guardados: "Guardados", ajustes: "Ajustes" }[S.view]);
    bind();
    if (S.view === "mapa") drawMap();
    if (S.view === "ajustes") { renderToken(); renderPush(); }
  }

  function bind() {
    document.querySelectorAll("[data-filter]").forEach((b) => b.addEventListener("click", () => { S.filter = b.dataset.filter; S.shown = 20; render(); }));
    const sel = document.getElementById("sort");
    if (sel) sel.addEventListener("change", () => { S.sort = sel.value; S.shown = 20; persist(); render(); });
    document.querySelectorAll(".card").forEach((c) => {
      c.querySelectorAll("[data-act]").forEach((b) => b.addEventListener("click", (e) => { e.stopPropagation(); act(c.dataset.id, b.dataset.act); }));
      const inner = c.querySelector(".card-inner");
      inner.addEventListener("click", (e) => { if (!e.target.closest("a,button")) openDetail(c.dataset.id); });
      inner.addEventListener("keydown", (e) => { if (e.key === "Enter") openDetail(c.dataset.id); });
      bindGallery(c);
      swipeable(c);
    });
    const more = document.getElementById("more");
    if (more && "IntersectionObserver" in window) {
      const io = new IntersectionObserver(([e]) => { if (e.isIntersecting) { io.disconnect(); S.shown += 20; const y = scrollY; render(); scrollTo(0, y); } }, { rootMargin: "600px" });
      io.observe(more);
    }
    const reset = document.getElementById("reset");
    if (reset) reset.addEventListener("click", (e) => { e.preventDefault(); const n = Object.keys(S.dropped).length; S.dropped = {}; persist(); render(); toast(`${n} pisos recuperados`); });
  }

  function bindGallery(scope) {
    const g = scope.querySelector(".gallery"), dots = scope.querySelectorAll(".dots i");
    if (!g || !dots.length) return;
    g.addEventListener("scroll", () => {
      const i = Math.round(g.scrollLeft / g.clientWidth);
      dots.forEach((d, k) => d.classList.toggle("on", k === i));
    }, { passive: true });
  }

  /* ───────────── acciones ───────────── */
  function act(id, what) {
    if (what === "save") {
      if (S.saved[id]) { delete S.saved[id]; } else { S.saved[id] = Date.now(); toast("Guardado"); }
    }
    if (what === "drop") {
      S.dropped[id] = Date.now(); delete S.saved[id];
      toast("Descartado", () => { delete S.dropped[id]; persist(); render(); });
    }
    persist(); const y = scrollY; render(); scrollTo(0, y);
  }

  function swipeable(c) {
    const inner = c.querySelector(".card-inner");
    let x0 = 0, y0 = 0, dx = 0, on = false, axis = null;
    c.addEventListener("touchstart", (e) => {
      if (e.target.closest(".media,a,button,select")) return;
      const t = e.touches[0]; x0 = t.clientX; y0 = t.clientY; dx = 0; on = true; axis = null;
    }, { passive: true });
    c.addEventListener("touchmove", (e) => {
      if (!on) return;
      const t = e.touches[0], mx = t.clientX - x0, my = t.clientY - y0;
      if (!axis && Math.abs(mx) + Math.abs(my) > 10) axis = Math.abs(mx) > Math.abs(my) ? "x" : "y";
      if (axis !== "x") return;
      dx = mx; c.classList.add("dragging");
      c.classList.toggle("dir-save", dx > 0); c.classList.toggle("dir-drop", dx < 0);
      inner.style.transform = `translateX(${dx}px) rotate(${dx / 50}deg)`;
    }, { passive: true });
    const end = () => {
      if (!on) return; on = false; c.classList.remove("dragging");
      if (Math.abs(dx) > 100) {
        inner.style.transform = `translateX(${dx > 0 ? 130 : -130}%)`; inner.style.opacity = "0";
        setTimeout(() => act(c.dataset.id, dx > 0 ? "save" : "drop"), 200);
      } else { inner.style.transform = ""; c.classList.remove("dir-save", "dir-drop"); }
    };
    c.addEventListener("touchend", end); c.addEventListener("touchcancel", end);
  }

  function toast(text, undo) {
    const r = document.getElementById("toast-root");
    clearTimeout(toast.t);
    r.innerHTML = `<div class="toast glass" role="status">${esc(text)}${undo ? '<button id="undo">Deshacer</button>' : ""}</div>`;
    if (undo) document.getElementById("undo").addEventListener("click", () => { r.innerHTML = ""; undo(); });
    toast.t = setTimeout(() => { r.innerHTML = ""; }, 3500);
  }

  /* ───────────── hojas ───────────── */
  function sheet(html, onClose) {
    const r = document.getElementById("sheet-root");
    r.innerHTML = `<div class="scrim" id="scrim"></div><div class="sheet glass" role="dialog" aria-modal="true"><div class="grabber"></div>${html}</div>`;
    document.body.style.overflow = "hidden";
    const close = () => { r.innerHTML = ""; document.body.style.overflow = ""; if (onClose) onClose(); };
    document.getElementById("scrim").addEventListener("click", close);
    r.querySelectorAll("[data-close]").forEach((b) => b.addEventListener("click", close));
    const sh = r.querySelector(".sheet");
    let y0 = null;
    sh.addEventListener("touchstart", (e) => { if (sh.scrollTop <= 0) y0 = e.touches[0].clientY; }, { passive: true });
    sh.addEventListener("touchmove", (e) => { if (y0 != null && e.touches[0].clientY - y0 > 110) { y0 = null; close(); } }, { passive: true });
    return { el: sh, close };
  }

  function openDetail(id) {
    const l = byId(id); if (!l) return;
    const p = l.score_parts, w = S.data.weights, ws = Object.values(w).reduce((a, b) => a + b, 0) || 1;
    const parts = [["value", "Precio/m²", `${nf.format(l.eur_m2)} frente a ${nf.format(l.eur_m2_ref)} €/m²`],
      ["size", "Superficie", `${nf1.format(l.surface)} m²`],
      ["commute", "Trayecto", l.km_to_work != null ? `${nf1.format(l.km_to_work)} km en línea recta hasta ${S.data.work.label}` : "sin ubicar"],
      ["extras", "Extras", l.extras_reasons.join(", ") || "ninguno detectado"]];
    const maps = l.lat != null ? `https://maps.apple.com/?ll=${l.lat},${l.lon}&q=${encodeURIComponent(l.zone || "Piso")}` : null;
    const srcCells = l.sources.map((s) => `<div class="cell"><span class="k">${esc(s.key === "trovit" && l.vias.length ? `Trovit (${l.vias.join(", ")})` : s.name)}</span>
      ${safeUrl(s.url) ? `<a class="v" href="${esc(s.url)}" target="_blank" rel="noopener">Abrir ↗</a>` : '<span class="v">—</span>'}</div>`).join("");
    const saved = !!S.saved[id];
    const { el } = sheet(`
      <div class="detail-media media">${gallery(l)}
        <div class="overlay-top"><div class="badges">${tags(l)}</div><span class="score-pill ${l.score >= 70 ? "hi" : ""}">${l.score}<small>/100</small></span></div>
        ${l.photos.length > 1 ? `<div class="overlay-bottom"><span></span><div class="dots">${l.photos.map((_, i) => `<i class="${i ? "" : "on"}"></i>`).join("")}</div></div>` : ""}</div>
      <div class="detail-price">${eur(l.price)}</div>
      <p class="detail-zone">${esc(l.kind || "Piso")} en ${esc(l.zone || "Luxemburgo")}${l.street ? ` · ${esc(l.street)}` : ""}</p>
      ${facts(l)}<div style="height:12px"></div>${m2Bar(l)}
      <div class="actions" style="margin:16px 0 4px">
        <button class="pill-btn wide ${saved ? "on" : ""}" data-dact="save">${saved ? I.heartFill + " Guardado" : I.heart + " Guardar"}</button>
        <button class="pill-btn wide" data-dact="drop">${I.x} Descartar</button>
      </div>
      <p class="group-label">Dónde está publicado</p><div class="group">${srcCells}
        ${l.agencies.length ? `<div class="cell"><span class="k">Agencia</span><span class="v">${esc(l.agencies.join(", "))}</span></div>` : ""}</div>
      <p class="group-label">Por qué ${l.score}</p>
      <div class="group"><div class="cell stack"><div class="parts">${parts.map(([k, label, det]) => `
        <div class="part"><span>${label} <small style="display:inline;color:var(--label-3)">${Math.round(100 * w[k] / ws)} %</small></span><span class="bar"><i style="width:${p[k]}%"></i></span><b>${p[k]}</b><small>${esc(det)}</small></div>`).join("")}</div></div></div>
      <p class="group-label">Historial</p>
      <div class="group">
        <div class="cell"><span class="k">Visto por primera vez</span><span class="v">${day(l.first_seen)} · ${l.days_listed} d</span></div>
        ${l.price_history.length > 1 ? l.price_history.map((h) => `<div class="cell"><span class="k">${day(h.date)}</span><span class="v">${eur(h.price)}</span></div>`).join("") : ""}
        ${maps ? `<div class="cell"><span class="k">Ubicación ${l.geo_precision === "exacta" ? "" : "aproximada"}</span><a class="v" href="${maps}" target="_blank" rel="noopener">Abrir en Mapas ↗</a></div>` : ""}
      </div>
      ${l.description ? `<p class="group-label">Descripción</p><div class="group"><div class="cell" style="color:var(--label-2);font-size:14.5px">${esc(l.description)}…</div></div>` : ""}
      <button class="pill-btn wide" data-close style="width:100%;margin-top:8px">Cerrar</button>`);
    bindGallery(el);
    el.querySelectorAll("[data-dact]").forEach((b) => b.addEventListener("click", () => {
      document.getElementById("sheet-root").innerHTML = ""; document.body.style.overflow = "";
      act(id, b.dataset.dact);
    }));
  }

  /* ───────────── escaneo bajo demanda (GitHub Actions) ───────────── */
  const GH = "https://api.github.com";
  const ghHeaders = () => ({ Authorization: `Bearer ${S.token}`, Accept: "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28" });

  function openScan() {
    if (!S.token || !repo()) {
      const { close } = sheet(`<div class="sheet-head"><h2>Escanear ahora</h2></div>
        <p class="note" style="margin:0 4px 14px">Para lanzar escaneos desde la app necesitas una clave de GitHub limitada a este repositorio. Solo se guarda en este dispositivo.</p>
        <button class="pill-btn primary wide" id="go-settings" style="width:100%;margin:0">Configurar en Ajustes</button>`);
      document.getElementById("go-settings").addEventListener("click", () => { close(); S.view = "ajustes"; render(); });
      return;
    }
    if (S.scan && !S.scan.done) { scanSheet(); return; }
    const { el, close } = sheet(`<div class="sheet-head"><h2>Escanear ahora</h2></div>
      <div class="group">
        <button class="cell" style="width:100%;border:0;background:none;text-align:left;cursor:pointer" data-mode="quick">
          <span><b>Rápido</b><br><span style="color:var(--label-2);font-size:14px">Lo más reciente de cada portal · ~1 min</span></span><span class="v">›</span></button>
        <button class="cell" style="width:100%;border:0;background:none;text-align:left;cursor:pointer" data-mode="full">
          <span><b>Completo</b><br><span style="color:var(--label-2);font-size:14px">Todo, bajadas y retirados · ~4 min</span></span><span class="v">›</span></button>
      </div>
      <p class="note">El escaneo completo ya se hace solo cada mañana.</p>`);
    el.querySelectorAll("[data-mode]").forEach((b) => b.addEventListener("click", () => { close(); startScan(b.dataset.mode); }));
  }

  const STEPS = [["dispatch", "Lanzando en GitHub"], ["queued", "En cola"], ["in_progress", "Leyendo portales"], ["publish", "Publicando resultados"]];
  function scanSheet() {
    const sc = S.scan; if (!sc) return;
    const idx = STEPS.findIndex((s) => s[0] === sc.phase);
    const secs = Math.round(((sc.done || Date.now()) - sc.started) / 1000);
    const body = `<div class="sheet-head"><h2>${sc.done ? (sc.error ? "No se pudo escanear" : "Escaneo terminado") : `Escaneo ${sc.mode === "full" ? "completo" : "rápido"}`}</h2><span class="status ${sc.error ? "err" : sc.done ? "ok" : ""}">${secs} s</span></div>
      <div class="group scan-steps">${STEPS.map(([id, label], i) => {
        const st = sc.done && !sc.error ? "done" : i < idx ? "done" : i === idx ? (sc.error ? "" : "now") : "";
        return `<div class="step ${st}"><i></i><span>${label}</span></div>`;
      }).join("")}</div>
      ${sc.error ? `<p class="note" style="color:var(--red)">${esc(sc.error)}</p>` : ""}
      ${sc.result ? `<p class="note" style="font-size:15px;color:var(--label)">${esc(sc.result)}</p>` : ""}
      ${sc.runUrl ? `<p class="note"><a href="${esc(sc.runUrl)}" target="_blank" rel="noopener">Ver ejecución en GitHub ↗</a></p>` : ""}
      <button class="pill-btn wide" data-close style="width:100%;margin-top:14px">${sc.done ? "Cerrar" : "Seguir en segundo plano"}</button>`;
    const open = document.querySelector("#sheet-root .sheet[data-scan]");
    if (open) { open.innerHTML = `<div class="grabber"></div>${body}`; open.querySelectorAll("[data-close]").forEach((b) => b.addEventListener("click", () => { document.getElementById("sheet-root").innerHTML = ""; document.body.style.overflow = ""; })); return; }
    const { el } = sheet(body); el.dataset.scan = "1";
  }

  async function startScan(mode) {
    const before = new Set(all().map((l) => l.id));
    S.scan = { mode, phase: "dispatch", started: Date.now() };
    renderTabs(); scanSheet();
    const fail = (msg) => { S.scan.error = msg; S.scan.done = Date.now(); renderTabs(); scanSheet(); };
    try {
      const r = await fetch(`${GH}/repos/${repo()}/actions/workflows/daily.yml/dispatches`, {
        method: "POST", headers: { ...ghHeaders(), "Content-Type": "application/json" },
        body: JSON.stringify({ ref: "main", inputs: { mode, notify: "false" } }),
      });
      if (r.status === 401) return fail("La clave de GitHub no es válida o ha caducado. Crea otra en Ajustes.");
      if (r.status === 403 || r.status === 404) return fail("La clave no tiene permiso de Actions (lectura y escritura) en este repositorio.");
      if (!r.ok) return fail(`GitHub respondió ${r.status}.`);
    } catch { return fail("Sin conexión con GitHub."); }
    S.scan.phase = "queued"; scanSheet();
    const since = S.scan.started - 20000;
    for (let i = 0; i < 160; i++) {  // ~13 min máximo
      await new Promise((res) => setTimeout(res, 5000));
      let run;
      try {
        const r = await fetch(`${GH}/repos/${repo()}/actions/workflows/daily.yml/runs?event=workflow_dispatch&per_page=5`, { headers: ghHeaders(), cache: "no-store" });
        const j = await r.json();
        run = (j.workflow_runs || []).find((x) => new Date(x.created_at).getTime() >= since);
      } catch { continue; }
      if (!run) continue;
      S.scan.runUrl = run.html_url;
      if (run.status === "completed") {
        if (run.conclusion !== "success") return fail(`La ejecución terminó con estado «${run.conclusion}».`);
        S.scan.phase = "publish"; scanSheet();
        await loadFresh();
        const fresh = all().filter((l) => !before.has(l.id) && l.active);
        S.scan.result = fresh.length ? `${fresh.length} piso${fresh.length > 1 ? "s" : ""} nuevo${fresh.length > 1 ? "s" : ""}. Los tienes en el filtro «Nuevos».` : "No hay pisos nuevos desde la última vez.";
        S.scan.done = Date.now(); render(); scanSheet();
        toast(S.scan.result);
        return;
      }
      S.scan.phase = run.status === "in_progress" ? "in_progress" : "queued";
      scanSheet();
    }
    fail("Está tardando más de lo normal. Mira la ejecución en GitHub.");
  }

  async function loadFresh() {
    // directo del repositorio: GitHub Pages tarda un par de minutos en publicar
    try {
      const r = await fetch(`${GH}/repos/${repo()}/contents/docs/listings.json?ref=main`, {
        headers: { ...ghHeaders(), Accept: "application/vnd.github.raw+json" }, cache: "no-store" });
      if (r.ok) { S.data = await r.json(); return; }
    } catch { /* cae a Pages */ }
    await load(true);
  }

  function renderToken() {
    const c = document.getElementById("token-cell"); if (!c) return;
    const r = repo();
    c.innerHTML = S.token
      ? `<span class="status ok">Clave guardada en este dispositivo</span>
         <p class="note" style="margin:0">Repositorio: ${esc(r || "?")}. Pulsa el botón ↻ de abajo para escanear.</p>
         <div class="actions"><button class="pill-btn" id="tok-test">Comprobar</button><button class="pill-btn" id="tok-del">Borrar clave</button></div>
         <p class="note" id="tok-msg" style="margin:0"></p>`
      : `<p class="note" style="margin:0;color:var(--label)">Crea una clave «fine-grained» en GitHub (Settings → Developer settings → Personal access tokens) con acceso solo a <b>${esc(r || "tu repositorio")}</b> y estos permisos: <b>Actions: Read and write</b> y <b>Contents: Read-only</b>. Pégala aquí:</p>
         <input class="input" id="tok-in" type="password" autocomplete="off" placeholder="github_pat_…" aria-label="Clave de GitHub">
         <div class="actions"><button class="pill-btn primary" id="tok-save" style="margin-left:0">Guardar</button></div>
         <p class="note" id="tok-msg" style="margin:0"></p>`;
    const msg = (t, bad) => { const m = document.getElementById("tok-msg"); m.textContent = t; m.style.color = bad ? "var(--red)" : "var(--green)"; };
    const test = async () => {
      try {
        const res = await fetch(`${GH}/repos/${r}/actions/workflows/daily.yml`, { headers: ghHeaders() });
        if (res.ok) { msg("Funciona: ya puedes escanear desde la app."); return true; }
        msg(res.status === 401 ? "Clave no válida." : `Sin acceso a Actions de ${r} (HTTP ${res.status}).`, true); return false;
      } catch { msg("Sin conexión con GitHub.", true); return false; }
    };
    document.getElementById("tok-save")?.addEventListener("click", async () => {
      const v = document.getElementById("tok-in").value.trim(); if (!v) return;
      S.token = v; persist(); renderToken(); await test();
    });
    document.getElementById("tok-test")?.addEventListener("click", test);
    document.getElementById("tok-del")?.addEventListener("click", () => { S.token = ""; persist(); renderToken(); });
  }

  /* ───────────── notificaciones ───────────── */
  const standalone = () => matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;
  const pushOk = () => "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
  const b64 = (s) => Uint8Array.from(atob((s + "=".repeat((4 - s.length % 4) % 4)).replace(/-/g, "+").replace(/_/g, "/")), (c) => c.charCodeAt(0));

  async function renderPush() {
    const c = document.getElementById("push-cell"); if (!c) return;
    const key = S.data?.vapid_public_key;
    if (!pushOk()) { c.innerHTML = '<span class="status">No disponible aquí</span><p class="note" style="margin:0">Abre la app desde el icono de la pantalla de inicio.</p>'; return; }
    if (!standalone() && /iPhone|iPad/.test(navigator.userAgent)) { c.innerHTML = '<span class="status">Instala la app primero</span><p class="note" style="margin:0">Safari → Compartir → Añadir a pantalla de inicio, y ábrela desde el icono.</p>'; return; }
    let sub = null;
    try { sub = await (await navigator.serviceWorker.ready).pushManager.getSubscription(); } catch { /* */ }
    if (sub) {
      c.innerHTML = `<span class="status ok">Avisos activados</span>
        <p class="note" style="margin:0">Si aún no lo has hecho, copia esto en el secreto <b>PUSH_SUBSCRIPTIONS</b> del repositorio:</p>
        <textarea class="input" id="sub-json" readonly>${esc(JSON.stringify(sub))}</textarea>
        <div class="actions"><button class="pill-btn" id="copy-sub">Copiar</button><button class="pill-btn" id="test-n">Probar aviso</button></div>`;
      document.getElementById("copy-sub").addEventListener("click", () => {
        const ta = document.getElementById("sub-json");
        navigator.clipboard.writeText(ta.value).then(() => toast("Copiado")).catch(() => { ta.select(); });
      });
      document.getElementById("test-n").addEventListener("click", async () => {
        (await navigator.serviceWorker.ready).showNotification("Pisos Lux", { body: "Así llegará el aviso de cada mañana.", icon: "icons/icon-192.png" });
      });
    } else {
      c.innerHTML = `<span class="status">Desactivados</span>
        <p class="note" style="margin:0">Cada mañana: cuántos pisos nuevos hay y cuál puntúa mejor.</p>
        <div class="actions"><button class="pill-btn primary" id="en-push" style="margin-left:0" ${key ? "" : "disabled"}>Activar avisos</button></div><p class="note" id="push-msg" style="margin:0"></p>`;
      document.getElementById("en-push").addEventListener("click", async () => {
        try {
          if (await Notification.requestPermission() !== "granted") { document.getElementById("push-msg").textContent = "Permiso denegado en Ajustes del iPhone."; return; }
          await (await navigator.serviceWorker.ready).pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64(key) });
          renderPush();
        } catch (e) { document.getElementById("push-msg").textContent = `No se pudo activar: ${e.message}`; }
      });
    }
  }

  /* ───────────── mapa (Leaflet + teselas CARTO) ───────────── */
  function loadLeaflet() {
    if (window.L) return Promise.resolve();
    return new Promise((res, rej) => {
      const css = document.createElement("link"); css.rel = "stylesheet";
      css.href = "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css"; document.head.appendChild(css);
      const s = document.createElement("script"); s.src = "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js";
      s.onload = res; s.onerror = rej; document.head.appendChild(s);
    });
  }

  async function drawMap() {
    try { await loadLeaflet(); } catch { document.getElementById("map").innerHTML = '<p class="note" style="padding:20px">No se pudo cargar el mapa.</p>'; return; }
    const el = document.getElementById("map"); if (!el) return;
    const dark = matchMedia("(prefers-color-scheme: dark)").matches;
    const map = L.map(el, { zoomControl: false, attributionControl: true }).setView([49.611, 6.12], 13);
    L.tileLayer(`https://{s}.basemaps.cartocdn.com/rastertiles/${dark ? "dark_all" : "voyager"}/{z}/{x}/{y}{r}.png`,
      { maxZoom: 19, attribution: "© OpenStreetMap · © CARTO" }).addTo(map);
    const color = (s) => (s >= 70 ? "var(--green)" : s >= 50 ? "var(--tint)" : "#8a8f99");
    const pts = [];
    pool().filter((l) => l.active && l.lat != null).sort((a, b) => a.score - b.score).forEach((l) => {
      const jitter = l.geo_precision === "exacta" ? 0 : (parseInt(l.id.replace(/\D/g, "").slice(-3) || "0", 10) % 40 - 20) / 9000;
      const ll = [l.lat + jitter, l.lon - jitter];
      pts.push(ll);
      L.marker(ll, { icon: L.divIcon({ className: "", html: `<div class="map-pin" style="background:${color(l.score)}">${kEur(l.price)}</div>`, iconSize: [0, 0] }) })
        .addTo(map).on("click", () => openDetail(l.id));
    });
    const w = S.data.work;
    L.marker([w.lat, w.lon], { icon: L.divIcon({ className: "", html: '<div class="map-work"></div>', iconSize: [0, 0] }) }).addTo(map).bindTooltip(w.label);
    if (pts.length) map.fitBounds(pts, { padding: [30, 30], maxZoom: 14 });
  }

  /* ───────────── carga ───────────── */
  async function load(silent) {
    try {
      const r = await fetch("listings.json", { cache: "no-store" });
      if (!r.ok) throw new Error(r.status);
      S.data = await r.json();
      S.loadedAt = Date.now();
    } catch { if (!S.data) S.data = null; }
    S.loading = false;
    if (!silent) render();
  }

  frame(); render(); load();
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => { /* vista previa */ });
  document.addEventListener("visibilitychange", async () => {
    // al volver a la app (p. ej. tras abrir un anuncio) solo recarga si los datos tienen más de 10 min
    if (document.visibilityState !== "visible" || (S.scan && !S.scan.done)) return;
    if (Date.now() - (S.loadedAt || 0) < 600000 || document.querySelector("#sheet-root .sheet")) return;
    const y = scrollY; await load(); scrollTo(0, y);
  });
})();
