"use strict";
/* Dashboard logic: routing between the sections, the pipeline tiles, and the data
   overview (folders, variable panel, chart). Data come from data/site.js and, per
   variable, data/series/<id>.js. Labels enter the page as text, never as HTML. */

const SITE = window.SITE;
const SECTIONS = ["hypothesis", "pipeline", "data", "tests", "results", "questions"];  // part 1, part 2 (the VARX), part 3
const PART_2 = ["pipeline", "data", "tests", "results"];
const ROLES = [["Endogenous", "endogenous"], ["Exogenous", "exogenous"], ["Input", "inputs"]];
const RANGES = [["Year", null], ["Quarter", 91], ["Month", 30], ["Week", 7]];
const HOUR_MS = 3600000;
const state = { section: null, variable: null, zones: new Set(), rangeDays: null };
const timeCache = {};

/* ---------- helpers ---------- */
const $ = (selector, root = document) => root.querySelector(selector);

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value);
  }
  for (const child of children) if (child != null) node.append(child);
  return node;
}

function token(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function fmt(x) {
  if (x == null) return "–";
  const a = Math.abs(x);
  return x.toLocaleString("en-GB", { maximumFractionDigits: a >= 100 ? 0 : a >= 1 ? 2 : 3 });
}

function stamp(ms) {  // "2025-01-01 00:00", read by the chart as a plain (UTC) time
  return new Date(ms).toISOString().slice(0, 16).replace("T", " ");
}

function zoneColor(zone) {
  return token(`--series-${SITE.zones.indexOf(zone) + 1}`);
}

function label(id) {  // the display name of a column
  const v = SITE.variables.find(x => x.id === id);
  return v ? v.label : id;
}

function axisStyle(title = "") {
  return { gridcolor: token("--grid"), linecolor: token("--axis"), zerolinecolor: token("--axis"),
    tickfont: { color: token("--text-muted"), size: 11 },
    title: { text: title, font: { size: 12, color: token("--text-muted") } } };
}

function baseLayout() {
  return {
    paper_bgcolor: token("--surface-1"), plot_bgcolor: token("--surface-1"),
    font: { family: token("--font"), size: 12, color: token("--text-secondary") },
    margin: { l: 64, r: 16, t: 10, b: 48 }, showlegend: false,
    hoverlabel: { bgcolor: token("--surface-1"), bordercolor: token("--axis"), font: { color: token("--text-primary"), size: 12 } },
  };
}

const PLOT_CONFIG = { responsive: true, displaylogo: false,
  modeBarButtonsToRemove: ["select2d", "lasso2d", "autoScale2d", "toggleSpikelines"] };

function legend(box, items) {  // [[label, color, kind]] kind: line | dot | star | bar | dashed
  box.replaceChildren(...items.map(([text, color, kind = "line"]) => el("span", { class: "legend-item" },
    el("span", { class: `key key-${kind}`, style: `--c:${color}` }), text)));
}

function table(headers, rows) {  // headers and rows: strings or nodes
  const cell = (tag, c) => el(tag, {}, typeof c === "string" ? document.createTextNode(c) : c);
  return el("table", { class: "stats" },
    el("thead", {}, el("tr", {}, ...headers.map(h => cell("th", h)))),
    el("tbody", {}, ...rows.map(r => el("tr", {}, ...r.map(c => cell("td", c))))));
}

function listText(items, word = "and") {  // ["a", "b", "c"] -> "a, b and c"
  return items.join(", ").replace(/, ([^,]*)$/, ` ${word} $1`);
}

/* ---------- theme: light or dark follows the computer's setting; the charts are redrawn when it changes ---------- */
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
  if (state.section === "hypothesis") renderHypothesis();
  if (state.section === "data") renderChart();
  if (state.section === "tests") renderTests();
  if (state.section === "results") renderResults();
});

/* ---------- header, footer, routing ---------- */
document.title = SITE.title;
$("#site-title").textContent = SITE.title;
$("#site-sub").textContent = `${SITE.dataframe} · ${SITE.zones.join(", ")} · ${SITE.facts.period}`;
$("#footer").textContent = `Built ${SITE.generated} from ${SITE.dataframe}.`;

function route() {
  const [section, sub] = (location.hash.slice(1) || "hypothesis").split("/");
  const current = SECTIONS.includes(section) ? section : "hypothesis";
  if (current !== state.section) {
    for (const s of SECTIONS) $("#" + s).hidden = s !== current;
    for (const a of document.querySelectorAll(".tabs a")) {  // a section tab, or the part it belongs to
      const on = a.dataset.section ? a.dataset.section === current : PART_2.includes(current);
      a.setAttribute("aria-current", on ? (a.dataset.section ? "page" : "true") : "false");
    }
    window.scrollTo(0, 0);
    state.section = current;
    if (current === "hypothesis") renderHypothesis();  // charts are drawn once their section is visible
    if (current === "tests") renderTests();
    if (current === "results") renderResults();
    if (current === "questions") renderQuestions();
  }
  if (current === "data") openVariable(decodeURIComponent(sub || "") || state.variable);
  if (["hypothesis", "tests", "results"].includes(current) && sub) {
    const target = document.getElementById(`${current}-${sub}`);
    const fold = target?.closest("details");
    if (fold) fold.open = true;  // a block folded under Details
    target?.scrollIntoView({ block: "start" });
  }
  if (FLAGS.length) placeFlags();
}
window.addEventListener("hashchange", route);

/* ---------- flags: the notes in flags.py as coloured numbered circles, the text on hover ---------- */
const FLAG_KINDS = { learning: "Learning", question: "Question", limitation: "Limitation" };
const POINTS = SITE.flags?.points || [];
const FLAGS = [  // learning and question n share a place; limitations are numbered on their own
  ...POINTS.flatMap((p, i) => [{ kind: "learning", n: i + 1, title: p.title, text: p.learning, at: p.at },
    { kind: "question", n: i + 1, title: p.title, text: p.question, at: p.at }]),
  ...(SITE.flags?.limitations || []).map((f, i) => ({ kind: "limitation", n: i + 1, ...f })),
];
const flagTip = el("div", { class: "flag-tip", role: "tooltip", hidden: "" });
document.body.append(flagTip);

function showFlag(button) {  // the note's text next to its circle, kept inside the window
  const f = FLAGS[Number(button.dataset.flag)];
  flagTip.className = `flag-tip flag-${f.kind}`;
  flagTip.replaceChildren(
    el("div", { class: "flag-tip-head" }, el("span", { class: "flag-kind", text: `${FLAG_KINDS[f.kind]} ${f.n}` }),
      el("b", { text: f.title })),
    el("p", { text: f.text }));
  flagTip.hidden = false;
  const r = button.getBoundingClientRect(), w = flagTip.offsetWidth, h = flagTip.offsetHeight;
  flagTip.style.left = `${Math.min(Math.max(8, r.right - w), innerWidth - w - 8)}px`;
  flagTip.style.top = `${r.bottom + 8 + h > innerHeight ? Math.max(8, r.top - h - 8) : r.bottom + 8}px`;
}

function hideFlag() {
  flagTip.hidden = true;
}

function flagTarget([selector, up]) {  // the element a note's circles go on
  const found = document.querySelector(selector);
  return found && (up ? found.closest(up) : found);
}

function placeFlags() {  // every note's circle on its elements (once), in the order of FLAGS
  FLAGS.forEach((f, i) => {
    for (const at of f.at) {
      const target = flagTarget(at);
      if (!target) continue;
      let row = target.querySelector(":scope > .flag-row");
      if (row?.querySelector(`.flag[data-flag="${i}"]`)) continue;
      if (!row) target.append(row = el("span", { class: "flag-row" }));
      target.classList.add("flagged");
      row.append(el("button", { class: `flag flag-${f.kind}`, type: "button", "data-flag": String(i), text: String(f.n),
        "aria-label": `${FLAG_KINDS[f.kind]} ${f.n}: ${f.title}`,
        onmouseenter: e => showFlag(e.currentTarget), onfocus: e => showFlag(e.currentTarget),
        onclick: e => showFlag(e.currentTarget), onmouseleave: hideFlag, onblur: hideFlag }));
    }
  });
}

function showOnPage(at) {  // go to the first place a note sits, and bring it into view
  const target = at.map(flagTarget).find(Boolean);
  if (!target) return;
  history.pushState(null, "", `#${target.closest(".section").id}`);
  route();
  target.scrollIntoView({ block: "center" });
}

if (FLAGS.length) {
  $("#flag-legend").hidden = false;
  $("#flag-legend").replaceChildren(...Object.entries(FLAG_KINDS).filter(([kind]) => FLAGS.some(f => f.kind === kind))
    .map(([kind, name]) => el("span", { class: "legend-item" }, el("span", { class: `flag-dot flag-${kind}` }), name)));
  document.body.classList.add("has-flags");
  addEventListener("scroll", hideFlag, { passive: true });
}

/* ---------- part 3: the open questions, each linked to where it applies ---------- */
function renderQuestions() {
  $("#question-list").replaceChildren(...POINTS.map((p, i) => el("li", { class: "card question-item" },
    el("div", { class: "question-head" }, el("span", { class: "flag-num flag-question", text: String(i + 1) }),
      el("h3", { text: p.title })),
    el("p", { class: "question-text", text: p.question }),
    el("p", { class: "question-context", text: p.learning }),
    el("button", { type: "button", class: "link-button", text: "Show on the page", onclick: () => showOnPage(p.at) }))));
}

/* ---------- overall pipeline ---------- */
function renderPipeline() {
  const f = SITE.facts;
  const calendar = SITE.variables.filter(v => v.calendar).length;
  const tiles = [
    ["Period", f.period.replace(" (UTC)", ""), "hourly, UTC"],
    ["Hours × zones", `${f.hours.toLocaleString("en-GB")} × ${f.zones.length}`, f.zones.join(" and ")],
    ["Model variables", String(f.counts.Endogenous + f.counts.Exogenous),
      `${f.counts.Endogenous} endogenous, ${f.counts.Exogenous - calendar} exogenous, ${calendar} dummy sets`],
    ["Inputs", String(f.counts.Input), "source columns used to build them"],
    ["Sources", f.sources.join(", "), "public data"],
  ];
  if (f.lag_orders) tiles.push(["Lag order", `${f.lag_orders.join(", ")} hours`, "AIC, all models"]);
  const box = $("#pipeline-tiles");
  box.replaceChildren(...tiles.map(([label, value, note]) => el("div", { class: "tile" },
    el("div", { class: "tile-label", text: label }),
    el("div", { class: value.length > 14 ? "tile-value long" : "tile-value", text: value }),
    el("div", { class: "tile-note", text: note }))));
  if (f.lag_orders) {
    $("#stage-tests-facts").replaceChildren("Lag order: ", el("b", { text: `${f.lag_orders.join(", ")} hours` }));
  }
  for (const img of document.querySelectorAll("#pipeline img[data-math]")) img.src = SITE.math[img.dataset.math] || "";
  renderRoles();  // what is a VARX: the endogenous and exogenous variables
  for (const stage of document.querySelectorAll(".stage")) {
    stage.addEventListener("click", event => {
      if (!event.target.closest("a")) location.hash = stage.dataset.link;
    });
  }
}

/* ---------- data overview: folders ---------- */
function buildTree() {
  const query = $("#tree-search").value.trim().toLowerCase();
  const tree = $("#tree");
  tree.replaceChildren();
  for (const theme of SITE.themes) {
    const vars = SITE.variables.filter(v => v.theme === theme
      && (!query || v.label.toLowerCase().includes(query) || v.id.includes(query)));
    if (!vars.length) continue;
    const folder = el("details", { class: "folder" },
      el("summary", {}, el("span", { text: theme }), el("span", { class: "folder-count", text: String(vars.length) })));
    folder.open = Boolean(query) || vars.some(v => v.id === state.variable);
    for (const [role, title] of ROLES) {
      const inRole = vars.filter(v => v.role === role);
      if (!inRole.length) continue;
      folder.append(el("div", { class: "role-group", text: title }));
      for (const v of inRole) {
        folder.append(el("button", {
          class: "var-btn", type: "button", title: v.id, "data-id": v.id,
          "aria-current": String(v.id === state.variable), text: v.label,
          onclick: () => { location.hash = "#data/" + encodeURIComponent(v.id); },
        }));
      }
    }
    tree.append(folder);
  }
}

/* ---------- data overview: one variable ---------- */
function loadSeries(id) {
  if (window.SITE_SERIES && window.SITE_SERIES[id]) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const script = el("script", { src: `data/series/${encodeURIComponent(id)}.js` });
    script.onload = resolve;
    script.onerror = () => reject(new Error(`could not load data/series/${id}.js`));
    document.head.append(script);
  });
}

function times(id) {
  if (!timeCache[id]) {
    const s = window.SITE_SERIES[id];
    const n = Object.values(s.values)[0].length;
    timeCache[id] = Array.from({ length: n }, (_, i) => stamp(s.t0_ms + i * s.step_ms));
  }
  return timeCache[id];
}

function currentVariable() {
  return SITE.variables.find(v => v.id === state.variable);
}

async function openVariable(id) {
  const v = SITE.variables.find(x => x.id === id) || SITE.variables.find(x => !x.calendar);
  const changed = v.id !== state.variable;
  state.variable = v.id;
  if (changed) state.zones = new Set(v.zones);
  buildTree();
  renderVariable(v);
  if (v.zones.length) {
    try {
      await loadSeries(v.id);
      if (state.variable === v.id) renderChart();
    } catch (error) {
      $("#chart").replaceChildren(el("p", { class: "note", text: error.message }));
    }
  }
}

function detailRows(v) {
  const rows = [["Meaning", v.meaning]];
  if (v.definition) rows.push(["Definition", el("code", { class: "formula", text: v.definition })]);
  rows.push(["Construction", v.transformation]);
  if (v.inputs.length) {
    rows.push(["Computed from", el("div", { class: "chips" }, ...v.inputs.map(input =>
      SITE.variables.some(x => x.id === input)
        ? el("a", { class: "chip", href: "#data/" + encodeURIComponent(input), text: input })
        : el("span", { class: "chip", text: input })))]);
  }
  rows.push([v.sources.length > 1 ? "Sources" : "Source", v.sources.length > 1
    ? el("ul", { class: "sources" }, ...v.sources.map(s => el("li", { text: s })))
    : v.sources[0]]);
  rows.push(["Unit", v.unit], ["Available", v.availability]);
  if (v.deviation) rows.push(["Deviation from the literature", v.deviation]);
  return rows.filter(([, value]) => value);
}

function longText(text, limit = 180) {  // long metadata: the start, the rest on click
  if (text.length <= limit) return document.createTextNode(text);
  const cut = text.lastIndexOf(" ", limit - 40);
  return el("details", { class: "more" }, el("summary", {}, `${text.slice(0, cut)}… `, el("span", { text: "more" })),
    el("span", { text: text }));
}

function renderVariable(v) {
  const panel = $("#variable");
  const head = el("header", { class: "var-head" },
    el("h2", { text: v.label }),
    el("div", { class: "meta-line" },
      el("span", { class: `badge ${v.role.toLowerCase()}`, text: v.role }),
      el("code", { text: v.id }),
      el("span", { text: `· ${v.theme}` }),
      v.unit ? el("span", { text: `· ${v.unit}` }) : null));
  const parts = [head];

  if (v.calendar) {
    parts.push(el("div", { class: "card note", text: "A category, not a measurement. The model uses one dummy per "
      + "category (one dropped), so there is nothing to plot." }));
  } else if (!v.zones.length) {
    parts.push(el("div", { class: "card note", text: "Constant in every zone, so there is nothing to plot." }));
  } else {
    const zoneButtons = v.zones.map(zone => el("button", {
      type: "button", "aria-pressed": String(state.zones.has(zone)),
      onclick: () => {
        if (state.zones.has(zone) && state.zones.size === 1) return;  // keep one zone on
        state.zones.has(zone) ? state.zones.delete(zone) : state.zones.add(zone);
        renderVariable(v); renderChart();
      },
    }, el("span", { class: "key", style: `background:${zoneColor(zone)}` }), zone));
    const rangeButtons = RANGES.map(([label, days]) => el("button", {
      type: "button", "aria-pressed": String(state.rangeDays === days), text: label,
      onclick: () => { state.rangeDays = days; renderVariable(v); renderChart(); },
    }));
    parts.push(el("div", { class: "controls" },
      el("div", { class: "seg", role: "group", "aria-label": "Zones" }, ...zoneButtons),
      el("div", { class: "seg", role: "group", "aria-label": "Time window" }, ...rangeButtons)));
    parts.push(el("div", { class: "card chart-card" }, el("div", { class: "chart", id: "chart" })));
  }

  const about = el("dl");
  for (const [label, value] of detailRows(v)) {
    about.append(el("dt", { text: label }), el("dd", {}, typeof value === "string" ? longText(value) : value));
  }
  const cards = [el("div", { class: "card" }, el("h3", { class: "card-title", text: "Details" }), about)];
  if (v.zones.length) {
    const table = el("table", { class: "stats" },
      el("thead", {}, el("tr", {}, ...["Zone", "Mean", "Std. dev.", "Min", "Max", "Missing"].map(h => el("th", { text: h })))),
      el("tbody", {}, ...v.zones.map(zone => {
        const s = v.stats[zone];
        return el("tr", {}, el("td", { text: zone }), el("td", { text: fmt(s.mean) }), el("td", { text: fmt(s.sd) }),
          el("td", { text: fmt(s.min) }), el("td", { text: fmt(s.max) }), el("td", { text: `${s.missing_pct}%` }));
      })));
    cards.push(el("div", { class: "card" }, el("h3", { class: "card-title", text: `Statistics (${v.unit || "value"})` }), table));
  }
  parts.push(el("div", { class: "details" }, ...cards));
  panel.replaceChildren(...parts);
}

function renderChart() {
  const v = currentVariable();
  const box = $("#chart");
  if (!v || !box || !v.zones.length || !window.SITE_SERIES || !window.SITE_SERIES[v.id]) return;
  const s = window.SITE_SERIES[v.id];
  const x = times(v.id);
  const unit = (v.unit || "").split(" (")[0];
  const traces = v.zones.filter(zone => state.zones.has(zone)).map(zone => ({
    type: "scatter", mode: "lines", name: zone, x, y: s.values[zone],
    line: { color: zoneColor(zone), width: 1.4 },
    hovertemplate: `%{y:,.3~f} ${unit.replace(/[<>]/g, "")}<extra>${zone}</extra>`,
  }));
  const last = s.t0_ms + (x.length - 1) * s.step_ms;
  const layout = {
    ...baseLayout(), margin: { l: 64, r: 16, t: 10, b: 10 }, hovermode: "x unified",
    xaxis: { ...axisStyle(), type: "date", hoverformat: "%a %d %b %Y, %H:%M UTC",
      showspikes: true, spikemode: "across", spikethickness: 1, spikecolor: token("--axis"), spikedash: "solid",
      rangeslider: { visible: true, thickness: 0.08, bgcolor: token("--surface-2"), bordercolor: token("--border") },
      ...(state.rangeDays ? { range: [stamp(last - state.rangeDays * 24 * HOUR_MS), stamp(last)] } : { autorange: true }) },
    yaxis: { ...axisStyle(v.unit), zeroline: true },
  };
  Plotly.react(box, traces, layout, { ...PLOT_CONFIG, toImageButtonOptions: { format: "png", scale: 2, filename: v.id } });
}

/* ---------- VARX tests ---------- */
const TESTS = SITE.tests;
const DECISIONS = {  // decision -> [status token, short code]
  "STATIONARY": ["good", "S"], "UNIT ROOT": ["critical", "U"], "CONFLICT": ["warning", "C"],
  "INCONCLUSIVE": ["neutral", "I"], "BANDWIDTH-SENSITIVE": ["serious", "B"],
};
const SYMBOLS = ["circle", "square", "diamond", "triangle-up", "x", "star", "hexagon"];
const GLYPHS = ["●", "■", "◆", "▲", "✕", "★", "⬢"];
const CRITERIA = [["aic", "AIC (used)", "--series-1"], ["hq", "HQ", "--series-3"], ["bic", "BIC", "--series-2"]];
const testState = { zone: SITE.zones[0], system: null, robust: "levels" };
const LAG_FLOOR = -0.05;  // lower end of the lag-selection y axis, so the points at 0 show in full

function decisionChip(decision, short = false) {
  const [status, code] = DECISIONS[decision] || ["neutral", "?"];
  return el("span", { class: `decision ${status}`, title: decision, text: short ? code : decision.toLowerCase() });
}

function models() {  // the (zone, system) of every model, from the lag-selection orders
  return (TESTS.orders || []).map(r => ({ zone: r.zone, system: r.variables.split(", ").at(-1), variables: r.variables, ...r }));
}

function missing(box, step) {
  box.replaceChildren(el("p", { class: "note", text: `No results yet: run the ${step} step of main.py.` }));
}

function renderRoles() {
  const group = (role, title) => el("div", { class: "role-box" }, el("h3", { class: "card-title", text: title }),
    el("div", { class: "chips" }, ...SITE.variables.filter(v => v.role === role).map(v =>
      el("a", { class: "chip chip-name", href: "#data/" + encodeURIComponent(v.id), text: v.label }))));
  $("#varx-roles").replaceChildren(group("Endogenous", "Endogenous"), group("Exogenous", "Exogenous"));
}

function ratios(r, stage) {  // each statistic over its 5 % critical value: above 1 = the test rejects
  return stage === "levels"
    ? { adf: r.adf_stat / r.adf_crit_5, kpss: r.kpss_stat / r.kpss_crit, adfCrit: r.adf_crit_5, kpssCrit: r.kpss_crit }
    : { adf: r.adf_stat / r.adf_crit_sim, kpss: r.kpss_stat / r.kpss_crit_sim, adfCrit: r.adf_crit_sim, kpssCrit: r.kpss_crit_sim };
}

function stationarityPoints(rows, stage) {
  const endo = SITE.variables.filter(v => v.role === "Endogenous").map(v => v.id);
  return SITE.zones.map(zone => {
    const zr = rows.filter(r => r.zone === zone);
    const q = zr.map(r => ratios(r, stage));
    return {
      type: "scatter", mode: "markers", name: zone, x: q.map(v => v.adf), y: q.map(v => v.kpss),
      text: zr.map(r => label(r.series)),
      customdata: zr.map((r, i) => [r.decision.toLowerCase(), r.adf_stat.toFixed(2), q[i].adfCrit.toFixed(2),
        r.kpss_stat.toFixed(3), q[i].kpssCrit.toFixed(3)]),
      marker: { color: zoneColor(zone), size: 12, symbol: zr.map(r => SYMBOLS[endo.indexOf(r.series) % SYMBOLS.length]),
        line: { color: token("--surface-1"), width: 2 } },
      hovertemplate: `<b>%{text}</b> · ${zone}<br>ADF %{customdata[1]} (5 % critical value %{customdata[2]})`
        + `<br>KPSS %{customdata[3]} (5 % critical value %{customdata[4]})<br>%{customdata[0]}<extra></extra>`,
    };
  });
}

function fmtP(p) {
  if (p == null) return "–";
  return p < 1e-4 ? "< 0.0001" : p.toLocaleString("en-GB", { maximumSignificantDigits: 2 });
}

function rgba(hex, alpha) {  // "#rrggbb" + opacity -> a colour Plotly understands
  const n = parseInt(hex.replace("#", ""), 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
}

function quadrantLayout(points) {
  // log axes shared by both charts; the lines at 1 are the 5 % critical values
  const span = values => {
    const lo = Math.min(1, ...values), hi = Math.max(1, ...values);
    return [Math.log10(lo) - 0.25, Math.log10(hi) + 0.25];
  };
  const [x0, x1] = span(points.map(p => p.adf)), [y0, y1] = span(points.map(p => p.kpss));
  const X0 = 10 ** x0, X1 = 10 ** x1, Y0 = 10 ** y0, Y1 = 10 ** y1;
  const ticks = (lo, hi) => [0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50, 100].filter(t => t >= lo && t <= hi);
  const tint = (name, alpha) => rgba(token(name), alpha / 100);
  const box = (a, b, c, d, color) => ({ type: "rect", xref: "x", yref: "y", x0: a, x1: b, y0: c, y1: d, fillcolor: color,
    line: { width: 0 }, layer: "below" });
  const note = (x, y, text, xanchor, yanchor) => ({ x, y, xref: "x", yref: "y", text, showarrow: false, xanchor, yanchor,
    font: { size: 11, color: token("--text-secondary") } });
  return {
    ...baseLayout(), margin: { l: 64, r: 16, t: 10, b: 52 }, hovermode: "closest",
    xaxis: { ...axisStyle("ADF: statistic ÷ 5 % critical value (> 1 rejects a unit root)"), type: "log", range: [x0, x1],
      zeroline: false, tickvals: ticks(X0, X1) },
    yaxis: { ...axisStyle("KPSS: statistic ÷ 5 % critical value (> 1 rejects stationarity)"), type: "log",
      range: [y0, y1], zeroline: false, tickvals: ticks(Y0, Y1) },
    shapes: [
      box(1, X1, Y0, 1, tint("--good", 12)), box(X0, 1, 1, Y1, tint("--critical", 10)),
      box(1, X1, 1, Y1, tint("--warning", 14)), box(X0, 1, Y0, 1, tint("--text-muted", 8)),
      { type: "line", x0: 1, x1: 1, y0: Y0, y1: Y1, line: { color: token("--axis"), width: 1 } },
      { type: "line", x0: X0, x1: X1, y0: 1, y1: 1, line: { color: token("--axis"), width: 1 } },
    ],
    annotations: [
      note(x1, y0, "STATIONARY", "right", "bottom"), note(x0, y1, "UNIT ROOT", "left", "top"),
      note(x1, y1, "CONFLICT", "right", "top"), note(x0, y0, "INCONCLUSIVE", "left", "bottom"),
    ].map(a => ({ ...a, xshift: a.xanchor === "left" ? 6 : -6, yshift: a.yanchor === "bottom" ? 6 : -6 })),
  };
}

function robustnessChecks(rows) {  // the baseline column, the checks next to it, and the rows whose decision holds under all
  const [base, ...others] = Object.keys(rows[0]).filter(k => !["zone", "series"].includes(k));
  return { base, others, stable: rows.filter(r => others.every(c => r[c] === r[base])) };
}

function checkName(c) {  // a robustness column as a heading: "KPSS bw 48" -> "KPSS bandwidth 48 h"
  return ["Levels", "After dummies"].includes(c) ? "Baseline" : c.startsWith("KPSS bw ") ? `KPSS bandwidth ${c.slice(8)} h`
    : c.startsWith("alpha ") ? `α = ${c.slice(6).replace("%", " %")}` : c.startsWith("Window ") ? `From ${c.slice(7)}` : c;
}

const DECISION_VERBS = {  // a decision in a sentence: [one series, several]
  "STATIONARY": ["is stationary", "are stationary"], "CONFLICT": ["gives a conflict", "give a conflict"],
  "UNIT ROOT": ["has a unit root", "have a unit root"], "INCONCLUSIVE": ["is inconclusive", "are inconclusive"],
  "BANDWIDTH-SENSITIVE": ["is bandwidth-sensitive", "are bandwidth-sensitive"],
};

function robustnessSummary(rows, intro) {  // which decisions hold under every check, and where the others change
  const { base, others, stable } = robustnessChecks(rows);
  const verb = (d, many = false) => (DECISION_VERBS[d] || [d.toLowerCase(), d.toLowerCase()])[many ? 1 : 0];
  const named = list => listText(unique(list.map(r => r.series)).map(s => {  // the zone is named when not every zone agrees
    const zs = list.filter(r => r.series === s).map(r => r.zone);
    return lowerFirst(label(s)) + (zs.length === SITE.zones.length ? "" : ` (${listText(zs)})`);
  }));
  const parts = [stable.length === rows.length ? `${intro}, no decision changes in any of the ${others.length} checks.`
    : `${intro}, ${stable.length} of ${rows.length} decisions hold in all ${others.length} checks.`];
  for (const d of unique(stable.map(r => r[base]))) {
    const same = stable.filter(r => r[base] === d);
    parts.push(` The ${named(same)} ${verb(d, unique(same.map(r => r.series)).length > 1)} in every check.`);
  }
  const changes = rows.filter(r => !stable.includes(r)).flatMap(r => others.filter(c => r[c] !== r[base]).map(c =>
    `the ${lowerFirst(label(r.series))} (${r.zone}) ${verb(r[c])} at ${checkName(c)}`));
  if (changes.length) {
    parts.push(` Otherwise ${listText(changes)}.`);
    const n = rows.filter(r => r[base] === "STATIONARY").length;
    if (n === rows.length) parts.push(` With the settings of the tests themselves, all ${n} are stationary.`);
  }
  return parts.join("");
}

function renderStationarityRobustness(levels, robustness, robustnessAfter) {  // the decision under each check, before or after the dummies
  const views = [["levels", "Before dummies", robustness], ["after", "After dummies", robustnessAfter]].filter(v => v[2]);
  if (!views.some(v => v[0] === testState.robust)) testState.robust = views[0][0];
  const rows = views.find(v => v[0] === testState.robust)[2];
  $("#robust-view").replaceChildren(seg(views.map(([key, text]) => [key, text]), testState.robust,
    v => { testState.robust = v; renderStationarityRobustness(levels, robustness, robustnessAfter); }, "Tests shown"));
  const checks = Object.keys(rows[0]).filter(k => !["zone", "series"].includes(k));
  $("#stat-robust").replaceChildren(table(["Zone", "Series", ...checks.map(checkName)],
    rows.map(r => [r.zone, label(r.series), ...checks.map(c => decisionChip(r[c]))])));
  const lags = levels.map(r => r.kpss_lags);
  const levelChecks = Object.keys(robustness[0]);
  $("#robust-auto").textContent = `here ${Math.min(...lags) === Math.max(...lags) ? Math.min(...lags)
    : `${Math.min(...lags)}–${Math.max(...lags)}`} hours`;
  $("#robust-bws").textContent = listText(levelChecks.filter(c => c.startsWith("KPSS bw ")).map(c => c.slice(8)));
  $("#robust-alphas").textContent = listText(levelChecks.filter(c => c.startsWith("alpha ")).map(c => c.slice(6).replace("%", " %")));
  $("#stat-robust-summary").replaceChildren(el("b", { text: "Summary. " }), [robustnessSummary(robustness, "As they are"),
    robustnessAfter && robustnessSummary(robustnessAfter, "After the hour and month dummies, as in the model")]
    .filter(Boolean).join(" "));
}

function renderStationarity() {
  const { levels, after, robustness } = TESTS;
  if (!levels) { missing($("#stat-levels"), "stationarity"); return; }
  const endo = SITE.variables.filter(v => v.role === "Endogenous");
  legend($("#stat-legend"), [...SITE.zones.map(z => [z, zoneColor(z), "dot"]),
    ...endo.map((v, i) => [`${GLYPHS[i % GLYPHS.length]} ${v.label}`, "transparent", "none"])]);
  const points = [...levels.map(r => ratios(r, "levels")), ...(after || []).map(r => ratios(r, "after"))];
  Plotly.react($("#stat-levels"), stationarityPoints(levels, "levels"), quadrantLayout(points), PLOT_CONFIG);
  if (after) Plotly.react($("#stat-after"), stationarityPoints(after, "after"), quadrantLayout(points), PLOT_CONFIG);
  else missing($("#stat-after"), "stationarity");

  if (robustness) renderStationarityRobustness(levels, robustness, TESTS.robustness_after);
  else missing($("#stat-robust"), "stationarity");

  const count = (rows, d) => rows.filter(r => r.decision === d).length;
  const conflicts = unique(levels.filter(r => r.decision === "CONFLICT").map(r => lowerFirst(label(r.series))));
  const parts = [`${count(levels, "STATIONARY")} of ${levels.length} series are stationary as they are.`];
  if (conflicts.length) parts.push(` The ${listText(conflicts)} `
    + `${conflicts.length > 1 ? "give" : "gives"} a conflict.`);
  if (after) parts.push(count(after, "STATIONARY") === after.length
    ? ` After the hour and month dummies all ${after.length} are stationary, so every series enters the model in levels.`
    : ` After the hour and month dummies ${count(after, "STATIONARY")} of ${after.length} are stationary.`);
  $("#stat-summary").replaceChildren(el("b", { text: "Summary. " }), parts.join(""));
}

function renderFilters() {  // every section that shows one model has its own model choice (one shared state)
  const all = models();
  if (!all.length) return;
  testState.system = testState.system || all[0].system;
  const pick = (key, value) => { testState[key] = value; renderFilters(); renderLags(); renderResiduals(); };
  for (const box of document.querySelectorAll("#tests .model-choice")) {
    box.replaceChildren(
      el("span", { class: "filters-label", text: "Model" }),
      seg(SITE.zones.map(z => [z, z]), testState.zone, v => pick("zone", v), "Zone"),
      seg(unique(all.map(m => m.system)).map(s => [s, label(s)]), testState.system, v => pick("system", v), "Spread in the model"),
      el("span", { class: "note", text: "Each model contains the wind error, the demand error and this spread." }));
  }
}

function renderLags() {
  const { criteria } = TESTS;
  const order = models().find(m => m.zone === testState.zone && m.system === testState.system);
  if (!criteria || !order) { missing($("#lag-chart"), "lag_selection"); return; }
  const rows = criteria.filter(r => r.zone === testState.zone && r.system === testState.system);
  const contiguous = rows.filter(r => r.order !== "literature");
  const literature = rows.find(r => r.order === "literature");
  const traces = [];
  for (const [key, name, color] of CRITERIA) {
    const low = Math.min(...contiguous.map(r => r[key]));
    const best = contiguous.find(r => r[key] === low);
    traces.push({ type: "scatter", mode: "lines", name, x: contiguous.map(r => r.n_lag_matrices),
      y: contiguous.map(r => r[key] - low), line: { color: token(color), width: 2 },
      hovertemplate: `${name}: %{y:.4f}<extra></extra>` });
    traces.push({ type: "scatter", mode: "markers", name: `${name} choice`, x: [best.n_lag_matrices], y: [0],
      marker: { color: token(color), size: 10, line: { color: token("--surface-1"), width: 2 } },
      hovertemplate: `${name}: minimum at p = ${best.n_lag_matrices}<extra></extra>` });
    if (literature) traces.push({ type: "scatter", mode: "markers", name: `${name}, literature`,
      x: [literature.n_lag_matrices], y: [literature[key] - low],
      marker: { color: token(color), size: 13, symbol: "star", line: { color: token("--surface-1"), width: 1 } },
      hovertemplate: `${name}, lags 1–24 and 48: %{y:.4f}<extra></extra>` });
  }
  const top = Math.max(...traces.flatMap(t => t.y));
  const layout = { ...baseLayout(), hovermode: "x unified",
    xaxis: { ...axisStyle("Lag order p (hours)"), dtick: 6, zeroline: false },
    yaxis: { ...axisStyle("Criterion − minimum"), range: [LAG_FLOOR, top + 0.05 * (top - LAG_FLOOR)] },
    shapes: [{ type: "line", x0: order.p, x1: order.p, yref: "paper", y0: 0, y1: 1,
      line: { color: token("--text-muted"), width: 1, dash: "dash" } }],
    annotations: [{ x: order.p, yref: "paper", y: 1, text: `p = ${order.p}`, showarrow: false, xanchor: "left",
      yanchor: "top", xshift: 4, font: { size: 11, color: token("--text-secondary") } }] };
  legend($("#lag-legend"), [...CRITERIA.map(([, name, color]) => [name, token(color)]),
    ["minimum", token("--text-muted"), "dot"], ["lags 1–24 and 48 (literature)", token("--text-muted"), "star"]]);
  Plotly.react($("#lag-chart"), traces, layout, PLOT_CONFIG);

  const all = models();
  const tbl = table(["Zone", "Spread", "BIC", "HQ", "AIC (used)"],
    all.map(m => [m.zone, label(m.system), String(m.BIC), String(m.HQ), String(m.p)]));
  tbl.querySelectorAll("tbody tr").forEach((tr, i) => {
    if (all[i].zone === testState.zone && all[i].system === testState.system) tr.classList.add("current");
  });
  $("#lag-table").replaceChildren(tbl);
  $("#lag-summary").replaceChildren(el("b", { text: "Summary. " }),
    `AIC picks ${orderRange("p")} lags in ${all.length === 1 ? "the model" : `all ${all.length} models`}, BIC `
    + `${orderRange("BIC")} and HQ ${orderRange("HQ")}. The BIC and HQ orders and the literature structure are used `
    + "as robustness checks in the results.");
}

function orderRange(key) {  // the lag orders one criterion chooses across the models: "25" or "2–3"
  const v = unique(models().map(m => m[key])).sort((a, b) => a - b);
  return v.length === 1 ? String(v[0]) : `${v[0]}–${v.at(-1)}`;
}

function residualFacts(checks) {  // the numbers both residual summaries report
  const week = checks.reduce((a, r) => Math.abs(r.week_r) > Math.abs(a.week_r) ? r : a);
  return {
    maxDay: Math.max(...checks.map(r => Math.abs(r.day_r))),
    rejects: checks.filter(r => r.robust_p < 0.05).length,
    modulus: Math.max(...checks.map(r => r.modulus)),
    week: `${Math.abs(week.week_r).toFixed(2)} (${lowerFirst(label(week.week_pair.split(" on ")[0]))}, ${week.zone}, `
      + `${week.week_lag / 168 === 1 ? "one week" : `${week.week_lag / 168} weeks`})`,
  };
}

function chiSquareDensity(df, xMax, n = 600) {  // χ²(df) on (0, xMax], scaled to area 1 on the grid (no gamma function)
  const xs = Array.from({ length: n }, (_, i) => xMax * (i + 1) / n);
  const logs = xs.map(x => (df / 2 - 1) * Math.log(x) - x / 2);
  const top = Math.max(...logs);
  const ys = logs.map(l => Math.exp(l - top));
  const area = ys.reduce((a, y) => a + y, 0) * xMax / n;
  return { xs, ys: ys.map(y => y / area) };
}

function renderResiduals() {
  const { checks, acf, weekly, quarters, variance } = TESTS;
  if (!checks || !acf) { missing($("#acf-chart"), "residual_checks"); return; }
  const z = testState.zone, s = testState.system;
  const check = checks.find(r => r.zone === z && r.system === s);
  const series = acf.filter(r => r.zone === z && r.system === s);
  if (!check || !series.length) return;
  const colors = ["--series-1", "--series-2", "--series-3"];
  const n = series[0].r.length;
  const lags = Array.from({ length: n }, (_, i) => i + 1);
  legend($("#acf-legend"), [...series.map((r, i) => [label(r.equation), token(colors[i % 3])]),
    [`white-noise band ±${check.band.toFixed(3)}`, token("--grid"), "bar"]]);
  Plotly.react($("#acf-chart"), series.map((r, i) => ({ type: "scatter", mode: "lines", name: label(r.equation),
    x: lags, y: r.r, line: { color: token(colors[i % 3]), width: 1.3 },
    hovertemplate: `${label(r.equation)}: %{y:.3f}<extra></extra>` })), {
    ...baseLayout(), hovermode: "x unified",
    xaxis: { ...axisStyle("Lag h (hours)"), dtick: 24, zeroline: false, range: [0, n + 6] },
    yaxis: { ...axisStyle("Residual autocorrelation") },
    shapes: [{ type: "rect", xref: "paper", x0: 0, x1: 1, y0: -check.band, y1: check.band, fillcolor: token("--surface-2"),
      line: { width: 0 }, layer: "below" },
      ...[168, 336].filter(w => w <= n).map(w => ({ type: "line", x0: w, x1: w, yref: "paper", y0: 0, y1: 1,
        line: { color: token("--text-muted"), width: 1, dash: "dot" } }))],
  }, PLOT_CONFIG);

  const names = checks.map(r => `${r.zone} · ${label(r.system)}`);
  const df = checks[0].lm_df, crit = checks[0].lm_crit_5, sd = Math.sqrt(2 * df);
  const xMax = Math.max(...checks.map(r => r.standard_lm)) * 1.08;
  const curve = chiSquareDensity(df, xMax);
  const peak = Math.max(...curve.ys);
  const tail = curve.xs.map((x, i) => [x, curve.ys[i]]).filter(([x]) => x >= crit);
  const ticks = (key, color, text) => ({ type: "scatter", mode: "markers", x: checks.map(r => r[key]),
    y: checks.map(() => peak * 0.06), customdata: names, cliponaxis: false,
    marker: { symbol: "line-ns-open", size: 26, color, line: { width: 2.5 } },
    hovertemplate: `%{customdata}: ${text} %{x:.0f}<extra></extra>` });
  legend($("#lm-legend"), [[`χ² with ${df} degrees of freedom`, token("--text-secondary")],
    ["5 % of the area", rgba(token("--text-muted"), 0.35), "bar"], ["5 % critical value", token("--text-secondary"), "dashed"],
    ["robust LM (used)", token("--series-1"), "bar"], ["standard LM", token("--text-muted"), "bar"]]);
  Plotly.react($("#lm-chart"), [
    { type: "scatter", mode: "lines", x: curve.xs, y: curve.ys, line: { color: token("--text-secondary"), width: 2 },
      hoverinfo: "skip" },
    { type: "scatter", mode: "lines", x: tail.map(p => p[0]), y: tail.map(p => p[1]), fill: "tozeroy",
      fillcolor: rgba(token("--text-muted"), 0.35), line: { width: 0 }, hoverinfo: "skip" },
    ticks("robust_lm", token("--series-1"), "robust LM"), ticks("standard_lm", token("--text-muted"), "standard LM")], {
    ...baseLayout(), hovermode: "closest",
    xaxis: { ...axisStyle("LM statistic"), range: [Math.max(0, df - 5 * sd), xMax], zeroline: false },
    yaxis: { ...axisStyle("Density"), rangemode: "tozero", showticklabels: false },
    shapes: [{ type: "line", x0: crit, x1: crit, yref: "paper", y0: 0, y1: 1,
      line: { color: token("--text-secondary"), width: 1.5, dash: "dash" } }],
    annotations: [{ x: crit, y: 1, yref: "paper", text: `5 % limit ${crit.toFixed(0)}`, showarrow: false,
      xanchor: "left", xshift: 6, yanchor: "top", font: { size: 11, color: token("--text-secondary") } }],
  }, PLOT_CONFIG);
  const f = residualFacts(checks);
  const span = values => `${Math.min(...values).toFixed(0)}–${Math.max(...values).toFixed(0)}`;
  const archRejects = (variance || []).filter(r => r.arch_p < 0.05).length;
  Object.entries({
    T: checks[0].T.toLocaleString("en-GB"), df: String(df), sd: sd.toFixed(0), crit: crit.toFixed(0),
    "crit-sd": ((crit - df) / sd).toFixed(1), robust: span(checks.map(r => r.robust_lm)),
    "robust-sd": span(checks.map(r => (r.robust_lm - df) / sd)), standard: span(checks.map(r => r.standard_lm)),
    "robust-p": (p => p < 1e-4 ? "< 0.0001" : `≤ ${fmtP(p)}`)(Math.max(...checks.map(r => r.robust_p))),
    ratio: `${Math.min(...checks.map(r => r.standard_lm / r.robust_lm)).toFixed(1)} to `
      + `${Math.max(...checks.map(r => r.standard_lm / r.robust_lm)).toFixed(1)}`,
    "per-df": `${Math.min(...checks.map(r => r.robust_lm / df)).toFixed(1)} to ${Math.max(...checks.map(r => r.robust_lm / df)).toFixed(1)}`,
    arch: `${archRejects} of ${(variance || []).length}`,
    kurtosis: `${Math.min(...(variance || []).map(r => r.kurtosis)).toFixed(0)} to ${Math.max(...(variance || []).map(r => r.kurtosis)).toFixed(0)}`,
    band: `±${checks[0].band.toFixed(3)}`, "max-day": f.maxDay.toFixed(3),
  }).forEach(([key, text]) => document.querySelectorAll(`[data-fact="${key}"]`).forEach(s => { s.textContent = text; }));

  const wrows = (weekly || []).filter(r => r.zone === z && r.system === s);
  if (wrows.length) {
    const weeks = Object.keys(wrows[0]).filter(k => k.endsWith(", baseline")).map(k => k.split(",")[0]);
    const variants = [["baseline", "chosen model", "--series-1"], ["weekly lags", "+ lags around 1 and 2 weeks", "--series-2"],
      ["weekly dummies", "hour-of-week dummies", "--series-3"]];
    const cats = wrows.flatMap(r => weeks.map(w => `${label(r.equation)} · ${w === "168 h" ? "1 week" : w === "336 h" ? "2 weeks" : w}`));
    legend($("#weekly-legend"), [...variants.map(([, text, c]) => [text, token(c), "bar"]),
      [`white-noise band ±${check.band.toFixed(3)}`, token("--grid"), "bar"]]);
    Plotly.react($("#weekly-chart"), variants.map(([key, text, c]) => ({ type: "bar", name: text, x: cats,
      y: wrows.flatMap(r => weeks.map(w => r[`${w}, ${key}`])), marker: { color: token(c) },
      hovertemplate: `${text}: %{y:.3f}<extra></extra>` })), {
      ...baseLayout(), barmode: "group", bargap: 0.3, bargroupgap: 0.08, hovermode: "x unified",
      xaxis: { ...axisStyle() }, yaxis: { ...axisStyle("Residual autocorrelation") },
      shapes: [{ type: "rect", xref: "paper", x0: 0, x1: 1, y0: -check.band, y1: check.band, fillcolor: token("--surface-2"),
        line: { width: 0 }, layer: "below" }],
    }, PLOT_CONFIG);
  }
  const qrows = (quarters || []).filter(r => r.zone === z && r.system === s);
  if (qrows.length) {
    const qs = Object.keys(qrows[0]).filter(k => /^Q\d$/.test(k));
    $("#quarter-table").replaceChildren(table(["Equation", "Lag", ...qs],
      qrows.map(r => [label(r.equation), r.lag === "168 h" ? "1 week" : r.lag === "336 h" ? "2 weeks" : r.lag,
        ...qs.map(q => r[q].toFixed(3))])));
  }
  const vrows = (variance || []).filter(r => r.zone === z && r.system === s);
  $("#variance-table").replaceChildren(table(["Equation", "ARCH-LM", "p", "Kurtosis"],
    vrows.map(r => [label(r.equation), r.arch_lm.toFixed(0), fmtP(r.arch_p), r.kurtosis.toFixed(1)])));
  $("#stability-tiles").replaceChildren(...checks.map(r => el("div", { class: "tile" },
    el("div", { class: "tile-label", text: `${r.zone} · ${label(r.system)}` }),
    el("div", { class: "tile-value", text: r.modulus.toFixed(3) }),
    el("div", { class: "tile-note", text: r.modulus < 1 ? "stable" : "not stable" }))));

  const lm = checks.map(r => r.robust_lm);
  const day = `largest ${f.maxDay.toFixed(3)}, band ±${checks[0].band.toFixed(3)}`;
  $("#res-summary").replaceChildren(el("b", { text: "Summary. " }),
    `The robust LM test rejects in ${f.rejects} of ${checks.length} models (${Math.min(...lm).toFixed(0)}–`
    + `${Math.max(...lm).toFixed(0)}, critical value ${checks[0].lm_crit_5.toFixed(0)}). `
    + (f.maxDay < checks[0].band ? `Within a day no single residual correlation leaves the white-noise band (${day}). `
      : `Within a day the residual correlations reach the white-noise band (${day}). `)
    + `The largest correlation left is weekly, ${f.week}. `
    + (f.modulus < 1 ? `All models are stable (largest modulus ${f.modulus.toFixed(3)}).` : "Some models are not stable."));
}

function renderTestOverview() {  // the summary at the top: every test with its result, each a link to its section
  const { levels, after, robustness, checks, variance } = TESTS;
  const stationary = rows => `${rows.filter(r => r.decision === "STATIONARY").length} of ${rows.length}`;
  const f = checks && residualFacts(checks);
  const groups = [
    ["Stationarity", [
      ["stationarity", "ADF and KPSS", levels && `${stationary(levels)} stationary as they are`
        + (after ? `, ${stationary(after)} after the dummies` : "")],
      ["robustness", "Robustness", robustness && [[robustness, "as they are"], [TESTS.robustness_after, "after the dummies"]]
        .filter(([rows]) => rows).map(([rows, when]) => {
          const { stable, others } = robustnessChecks(rows);
          return stable.length === rows.length ? `same decisions in all ${others.length} checks ${when}`
            : `${stable.length} of ${rows.length} hold in all checks ${when}`;
        }).join("; ").replace(/^./, c => c.toUpperCase())]]],
    ["Lag selection", [
      ["lags", "Lag order", models().length
        && `AIC: ${orderRange("p")} lags (BIC ${orderRange("BIC")}, HQ ${orderRange("HQ")})`]]],
    ["Residual checks", [
      ["residuals", "Autocorrelation", f && `LM rejects in ${f.rejects} of ${checks.length} models; within a day at most `
        + `${f.maxDay.toFixed(3)} (band ±${checks[0].band.toFixed(3)})`],
      ["weekly", "Weekly pattern", f && `Up to ${f.week}`],
      ["variance", "Variance and kurtosis", variance && `Variance changes in `
        + `${variance.filter(r => r.arch_p < 0.05).length} of ${variance.length} equations; kurtosis up to `
        + Math.max(...variance.map(r => r.kurtosis)).toFixed(1)],
      ["stability", "Stability", f && (f.modulus < 1 ? `All ${checks.length} models stable (largest modulus `
        + `${f.modulus.toFixed(3)})` : "Some models not stable")]]],
  ];
  $("#test-overview").replaceChildren(...groups.map(([title, tests], i) => el("div", { class: "card" },
    el("div", { class: "overview-head" }, el("span", { class: "stage-num", text: String(i + 1) }), el("h3", { text: title })),
    el("ul", { class: "steps" }, ...tests.map(([id, name, result]) => el("li", {}, el("a", { href: `#tests/${id}` },
      el("span", { class: "check-name", text: name }),
      el("span", { class: "check-result", text: result || "No results yet" }))))))));
}

function renderTests() {
  for (const img of document.querySelectorAll("img[data-math]")) img.src = SITE.math[img.dataset.math] || "";
  renderTestOverview();
  renderStationarity();
  renderFilters();
  renderLags();
  renderResiduals();
}

/* ---------- VARX results ---------- */
const RESULTS = SITE.results;
const DASHES = ["dot", "dashdot", "longdash", "dash"];  // robustness lines, in the order of the structures
const FOREST_HOURS = [0, 1, 3, 6, 12, 24];
const SVG_NS = "http://www.w3.org/2000/svg";
const resultState = { structure: "chosen", model: 0, robust: false, hour: 0, shock: 0, shared: true, view: "0" };

function structures() {  // lag structures in the order of robustness_structures.csv: "chosen", then the robustness ones
  return RESULTS.structures ? Object.keys(RESULTS.structures[0]).filter(k => !["zone", "system"].includes(k)) : ["chosen"];
}

function otherOrders() {  // the other Cholesky orders of the varx step (main.py's other_orders), each with its own band
  return Object.keys(RESULTS.irf?.[0]?.orders || {});
}

function structureName(s) {
  return s === "chosen" ? "Chosen model" : s[0].toUpperCase() + s.slice(1);
}

function outside(r, h) {  // the band of an impulse response excludes zero at hour h
  return r.lower[h] > 0 || r.upper[h] < 0;
}

function resultModels() {  // [{zone, system, p, T, regressors, number, name, eqs: [equation rows in Cholesky order]}]
  return (RESULTS.models || []).map((m, i) => ({ ...m, number: i + 1, name: `${m.zone} · ${label(m.system)}`,
    eqs: (RESULTS.equations || []).filter(e => e.zone === m.zone && e.system === m.system).sort((a, b) => a.position - b.position) }));
}

function modelOf(ms, row) {  // the model a result row belongs to
  return ms.find(m => m.zone === row.zone && m.system === row.system);
}

function irfOf(m, response, shock) {
  return (RESULTS.irf || []).find(r => r.zone === m.zone && r.system === m.system && r.response === response && r.shock === shock);
}

function grangerOf(m) {
  return (RESULTS.granger || []).filter(r => r.zone === m.zone && r.system === m.system);
}

function modelTag(m) {  // a model's number in its zone colour, then its name: the same mark everywhere on the page
  return el("span", { class: "model-tag", style: `--c:${zoneColor(m.zone)}` },
    el("span", { class: "model-num", text: String(m.number) }), m.name);
}

function roleName(id, system) {  // "Spread" for the model's own spread, else the variable's name
  return id === system ? "Spread" : label(id);
}

function positionName(ms, j) {  // the variable in Cholesky position j: its name if every model has it, else "Spread"
  return ms.every(m => m.eqs[j].variable === ms[0].eqs[j].variable) ? label(ms[0].eqs[j].variable) : "Spread";
}

function lowerFirst(text) {  // "Wind forecast error" -> "wind forecast error"; "ID-BAL spread" stays
  return /^[A-Z][a-z]/.test(text) ? text[0].toLowerCase() + text.slice(1) : text;
}

function size(v) {
  return Math.abs(v) >= 100 ? v.toFixed(0) : v.toFixed(1);
}

function signed(x, digits = 2) {
  return `${x > 0 ? "+" : x < 0 ? "−" : ""}${Math.abs(x).toFixed(digits)}`;
}

function bandText(r, h) {
  return `${signed(r.lower[h])} to ${signed(r.upper[h])}`;
}

function laterHours(r) {  // the hours after the shock where the band excludes zero
  return r.estimate.map((_, h) => h).filter(h => h > 0 && outside(r, h));
}

function halfLife(r) {  // the first hour where the response is below half of its first value (-1: never)
  return r.estimate.findIndex(v => Math.abs(v) < 0.5 * Math.abs(r.estimate[0]));
}

function horizon() {
  return RESULTS.irf ? RESULTS.irf[0].estimate.length - 1 : 0;
}

function bullet(lead, text) {
  return el("li", {}, el("b", { text: `${lead} ` }), text);
}

function seg(items, current, onPick, aria) {
  return el("div", { class: "seg", role: "group", "aria-label": aria }, ...items.map(([value, text]) =>
    el("button", { type: "button", "aria-pressed": String(value === current), text, onclick: () => onPick(value) })));
}

function rangeText(values, digits = 2) {
  const lo = Math.min(...values), hi = Math.max(...values);
  return lo.toFixed(digits) === hi.toFixed(digits) ? lo.toFixed(digits) : `${lo.toFixed(digits)}–${hi.toFixed(digits)}`;
}

function renderFit(ms) {
  $("#models-table").replaceChildren(table(["Model", "Lags", ...ms[0].eqs.map((_, j) => positionName(ms, j))],
    ms.map(m => [modelTag(m), String(m.p), ...m.eqs.map(e => e.r2.toFixed(2))])));
  const pairs = RESULTS.correlations || [];
  const pairKey = (c, m) => `${roleName(c.a, m.system)} / ${roleName(c.b, m.system)}`;
  const keys = [...new Set(ms.flatMap(m => pairs.filter(c => c.zone === m.zone && c.system === m.system).map(c => pairKey(c, m))))];
  $("#corr-table").replaceChildren(table(["Model", ...keys], ms.map(m => [modelTag(m),
    ...keys.map(k => { const c = pairs.find(x => x.zone === m.zone && x.system === m.system && pairKey(x, m) === k);
      return c ? signed(c.corr) : "–"; })])));
}

function pBand(p) {  // ordinal shading of a p-value
  return p < 0.01 ? 0.5 : p < 0.05 ? 0.3 : p < 0.10 ? 0.12 : 0;
}

function renderGranger(ms) {
  const rows = RESULTS.granger;
  if (!rows) { missing($("#granger-table"), "varx"); return; }
  const s = resultState.structure;
  const pOf = r => s === "chosen" ? r.p : r[`p_${s}`];
  $("#granger-filters").replaceChildren(el("span", { class: "filters-label", text: "Lag structure" }),
    seg(structures().map(x => [x, structureName(x)]), s, v => { resultState.structure = v; renderGranger(ms); }, "Lag structure"));
  const key = r => `${roleName(r.cause, r.system)} → ${roleName(r.effect, r.system)}`;
  const keys = [...new Set(rows.map(key))];
  const blue = token("--series-1");
  const tbl = table(["Cause → effect", ...ms.map(modelTag)], keys.map(k => [k, ...ms.map(m => {
    const r = rows.find(x => x.zone === m.zone && x.system === m.system && key(x) === k);
    if (!r) return "–";
    const p = pOf(r);
    const differs = s !== "chosen" && (p < 0.05) !== (r.p < 0.05);
    const cell = el("span", { class: `pcell${p < 0.05 ? " sig" : ""}${differs ? " differs" : ""}`,
      style: `background:${rgba(blue, pBand(p))}`, title: `W = ${r.W.toFixed(1)}, df ${r.df}; chosen model p = ${r.p.toFixed(3)}`,
      text: `${p.toFixed(3)}${differs ? " ◆" : ""}` });
    return cell;
  })]));
  tbl.classList.add("heat");
  $("#granger-table").replaceChildren(tbl);
  legend($("#granger-legend"), [["p < 0.01", rgba(blue, 0.5), "bar"], ["p < 0.05 (bold)", rgba(blue, 0.3), "bar"],
    ["p < 0.10", rgba(blue, 0.12), "bar"], ["◆ differs from the chosen model", "transparent", "none"]]);
}

function irfChart(box, r, unit, { range = null, robust = false, order = null } = {}) {  // one response and its band;
  const hours = r.estimate.map((_, h) => h);  // optionally the other lag structures (grey) and another Cholesky order (green)
  const color = zoneColor(r.zone);
  const traces = [
    { type: "scatter", mode: "lines", x: hours, y: r.upper, line: { width: 0 }, hoverinfo: "skip" },
    { type: "scatter", mode: "lines", x: hours, y: r.lower, line: { width: 0 }, fill: "tonexty",
      fillcolor: rgba(color, 0.18), hoverinfo: "skip" },
  ];
  if (robust) {
    for (const [i, name] of structures().slice(1).entries()) {
      if (!r.robust[name]) continue;
      traces.push({ type: "scatter", mode: "lines", x: hours, y: r.robust[name],
        line: { color: token("--text-secondary"), width: 1, dash: DASHES[i % DASHES.length] },
        hovertemplate: `${name}: %{y:.2f}<extra></extra>` });
    }
  }
  if (order && r.orders?.[order]) {
    traces.push({ type: "scatter", mode: "lines", x: hours, y: r.orders[order].estimate,
      line: { color: token("--series-3"), width: 1.5 }, hovertemplate: `${order}: %{y:.2f}<extra></extra>` });
  }
  traces.push({ type: "scatter", mode: "lines", x: hours, y: r.estimate, line: { color, width: 2 },
    customdata: hours.map(h => [r.lower[h], r.upper[h]]),
    hovertemplate: `%{y:.2f} ${unit} [%{customdata[0]:.2f}, %{customdata[1]:.2f}]<extra></extra>` });
  Plotly.react(box, traces, {
    ...baseLayout(), margin: { l: 48, r: 10, t: 6, b: 34 }, hovermode: "x unified",
    xaxis: { ...axisStyle("Hours after the shock"), dtick: 12, zeroline: false, range: [0, hours.at(-1)],
      title: { text: "Hours after the shock", font: { size: 11, color: token("--text-muted") } } },
    yaxis: { ...axisStyle(unit), zeroline: true, zerolinecolor: token("--text-muted"), ...(range ? { range } : {}) },
  }, { ...PLOT_CONFIG, displayModeBar: false });
}

/* Granger map: the model's variables as boxes, one arrow per Granger test, drawn by its p-value */
function svg(tag, attrs = {}, ...children) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === "text") node.textContent = value;
    else node.setAttribute(key, value);
  }
  for (const child of children) if (child != null) node.append(child);
  return node;
}

function pLevel(p) {
  return p < 0.05 ? "sig" : p < 0.10 ? "weak" : "none";
}

function mapLegend(box) {
  legend(box, [["p < 0.05", token("--text-primary")], ["p < 0.10", token("--text-secondary"), "dashed"],
    ["not significant", token("--text-muted"), "dashed"], ["numbers: bootstrap p-values", "transparent", "none"]]);
  return box;
}

function grangerMap(m, uid) {
  const W = 420, H = 226, hw = 76, hh = 17, K = m.eqs.length;
  const pos = Object.fromEntries(m.eqs.map((e, j) => {  // on an ellipse: the forecast errors on top, the spread below
    const a = (210 + j * 360 / K) * Math.PI / 180;
    return [e.variable, [W / 2 + 113 * Math.cos(a), 104 + 96 * Math.sin(a)]];
  }));
  const defs = svg("defs", {}, ...["sig", "weak", "none"].map(k => svg("marker", { id: `${uid}-${k}`, viewBox: "0 0 10 10",
    refX: "9", refY: "5", markerWidth: "9", markerHeight: "9", markerUnits: "userSpaceOnUse", orient: "auto" },
    svg("path", { d: "M0,0 L10,5 L0,10 z", class: `gm-head ${k}` }))));
  const edges = grangerOf(m).filter(r => pos[r.cause] && pos[r.effect]).map(r => {
    const [ax, ay] = pos[r.cause], [bx, by] = pos[r.effect];
    const len = Math.hypot(bx - ax, by - ay), ux = (bx - ax) / len, uy = (by - ay) / len, nx = -uy, ny = ux;
    const cut = Math.min(Math.abs(ux) > 1e-9 ? hw / Math.abs(ux) : Infinity, Math.abs(uy) > 1e-9 ? hh / Math.abs(uy) : Infinity) + 5;
    const [x1, y1, x2, y2] = [ax + ux * cut + nx * 7, ay + uy * cut + ny * 7, bx - ux * cut + nx * 7, by - uy * cut + ny * 7];
    const k = pLevel(r.p);
    return svg("g", {},
      svg("title", { text: `${roleName(r.cause, m.system)} → ${roleName(r.effect, m.system)}: p = ${r.p.toFixed(3)} (W = ${r.W.toFixed(1)}, ${r.df} df)` }),
      svg("line", { x1, y1, x2, y2, class: `gm-edge ${k}`, "marker-end": `url(#${uid}-${k})` }),
      svg("line", { x1, y1, x2, y2, class: "gm-hit" }),
      svg("text", { x: (x1 + x2) / 2 + nx * 17, y: (y1 + y2) / 2 + ny * 17, class: `gm-p ${k}`, text: r.p.toFixed(3) }));
  });
  const nodes = m.eqs.map(e => {
    const [x, y] = pos[e.variable];
    return svg("g", { class: `gm-node${e.variable === m.system ? " own" : ""}` },
      svg("rect", { x: x - hw, y: y - hh, width: 2 * hw, height: 2 * hh, rx: 8 }),
      svg("text", { x, y, text: label(e.variable) }));
  });
  return svg("svg", { viewBox: `0 0 ${W} ${H}`, class: "gmap", role: "img", "aria-label": `Granger map of ${m.name}`,
    style: `--c:${zoneColor(m.zone)}` }, defs, ...edges, ...nodes);
}

/* Model by model */
function renderPicker(ms) {
  $("#model-picker").replaceChildren(...ms.map((m, i) => {
    const spread = m.eqs.find(e => e.variable === m.system);
    const tests = grangerOf(m);
    const row = (name, value, quiet = false) => el("span", { class: "mc-row" }, el("span", { text: name }),
      el("b", { class: quiet ? "quiet" : "", text: value }));
    return el("button", { type: "button", class: "model-card", style: `--c:${zoneColor(m.zone)}`,
      "aria-pressed": String(i === resultState.model),
      onclick: () => { resultState.model = i; renderPicker(ms); renderPanel(ms); } },
      el("span", { class: "mc-head" }, modelTag(m)),
      row("Significant Granger tests (5 %)", `${tests.filter(r => r.p < 0.05).length} of ${tests.length}`),
      ...m.eqs.filter(e => e !== spread).map(e => {
        const r = irfOf(m, m.system, e.variable);
        return r ? row(`${label(e.variable)} shock → spread`, `${signed(r.estimate[0], 1)} ${spread.unit}`, !outside(r, 0)) : null;
      }),
      row("R², spread equation", spread.r2.toFixed(2)));
  }));
}

function modelAnalysis(m) {  // facts computed from the model's results
  const H = horizon();
  const spread = m.eqs.find(e => e.variable === m.system);
  const errors = m.eqs.filter(e => e !== spread);
  const items = [bullet("Fit.", `R² is ${spread.r2.toFixed(2)} for the spread, `
    + errors.map(e => `${e.r2.toFixed(2)} for the ${lowerFirst(label(e.variable))}`).join(" and ") + ".")];

  const robust = structures().slice(1);
  const tests = grangerOf(m);
  const name = r => `${roleName(r.cause, m.system)} → ${roleName(r.effect, m.system)}`;
  const sig = tests.filter(r => r.p < 0.05), weak = tests.filter(r => r.p >= 0.05 && r.p < 0.10);
  const holds = r => robust.filter(l => r[`p_${l}`] < 0.05).length;
  const only = tests.filter(r => r.p >= 0.05 && robust.some(l => r[`p_${l}`] < 0.05));
  items.push(bullet("Granger causality.", (sig.length ? `Significant at 5 %: ${sig.map(r => `${name(r)} (p = ${r.p.toFixed(3)}, `
      + `also in ${holds(r)} of ${robust.length} other lag structures)`).join("; ")}. ` : "Nothing is significant at 5 %. ")
    + (weak.length ? `Only at 10 %: ${weak.map(r => `${name(r)} (p = ${r.p.toFixed(3)})`).join("; ")}. ` : "")
    + `Not significant: ${tests.length - sig.length - weak.length} of ${tests.length}.`
    + (only.length ? ` Significant only with other lags: ${only.map(r => `${name(r)} `
      + `(${robust.filter(l => r[`p_${l}`] < 0.05).join(", ")})`).join("; ")}.` : "")));

  for (const e of errors) {
    const r = irfOf(m, m.system, e.variable);
    if (!r) continue;
    const later = laterHours(r);
    items.push(bullet(`${label(e.variable)} shock (1 s.d. = ${size(e.shock_sd)} ${e.unit}).`,
      `Same hour: ${signed(r.estimate[0])} ${spread.unit} (band ${bandText(r, 0)}${outside(r, 0) ? "" : ", includes zero"}), `
      + `or ${signed(100 * r.estimate[0] / e.shock_sd)} per 100 ${e.unit}. `
      + (later.length ? `Later, the band excludes zero in ${later.length} of ${H} hours, last at hour ${Math.max(...later)}.`
        : "Later, the band includes zero in every hour.")));
  }

  const own = irfOf(m, m.system, m.system);
  if (own) {
    const half = halfLife(own), later = laterHours(own);
    items.push(bullet(`Spread shock (1 s.d. = ${size(spread.shock_sd)} ${spread.unit}).`,
      (half < 0 ? `Stays above half its first response for all ${H} hours. ` : `Falls below half its first response after ${half} h. `)
      + (later.length ? `The band last excludes zero at hour ${Math.max(...later)}.` : "The band includes zero from hour 1 on.")));
  }

  const [a, b] = errors;
  const cross = a && b && irfOf(m, b.variable, a.variable);
  if (cross) {
    const peak = cross.estimate.reduce((best, v, h) => Math.abs(v) > Math.abs(cross.estimate[best]) ? h : best, 0);
    items.push(bullet("Between the forecast errors.", `A ${lowerFirst(label(a.variable))} shock moves the `
      + `${lowerFirst(label(b.variable))} by ${signed(cross.estimate[0])} ${b.unit} in the same hour (band ${bandText(cross, 0)}), `
      + `and by at most ${signed(cross.estimate[peak])} ${b.unit} (hour ${peak}${outside(cross, peak) ? "" : ", band includes zero"}).`));
  }

  const inside = (RESULTS.irf_robustness || []).filter(r => r.zone === m.zone && r.system === m.system
    && r.response === m.system && r.shock !== m.system);
  if (inside.length) {
    const worst = inside.reduce((x, y) => y.hours_inside < x.hours_inside ? y : x);
    items.push(bullet("Other lag structures.", `The spread's responses to the forecast-error shocks stay inside this `
      + `model's band in at least ${worst.hours_inside} of ${worst.hours} hours (lowest: ${worst.structure}, `
      + `${lowerFirst(label(worst.shock))} shock).`));
  }
  return items;
}

function renderPanel(ms) {
  const m = ms[resultState.model];
  const spread = m.eqs.find(e => e.variable === m.system);
  const panel = $("#model-panel");
  panel.style.setProperty("--c", zoneColor(m.zone));
  const pairs = (RESULTS.correlations || []).filter(c => c.zone === m.zone && c.system === m.system);
  const charts = [];
  const grid = el("div", { class: "irf-grid" });
  for (const resp of [spread, ...m.eqs.filter(e => e !== spread)]) {  // the spread's responses first
    grid.append(el("div", { class: "grid-row-head", text: `Response of the ${lowerFirst(label(resp.variable))} (${resp.unit})` }));
    for (const e of m.eqs) {
      const r = irfOf(m, resp.variable, e.variable);
      const box = el("div", { class: "chart chart-irf" });
      grid.append(el("div", { class: `card irf-card${resp === spread ? " focus" : ""}` },
        el("div", { class: "irf-title", text: `${label(e.variable)} shock` }),
        el("div", { class: "irf-sub", text: `1 s.d. = ${size(e.shock_sd)} ${e.unit}` }), box));
      if (r) charts.push([box, r, resp.unit]);
    }
  }
  const irfLegend = el("div", { class: "legend-row" });
  const order = otherOrders()[0];
  legend(irfLegend, [["response", zoneColor(m.zone)], ["95 % bootstrap band", rgba(zoneColor(m.zone), 0.25), "bar"],
    ...(order ? [[order, token("--series-3")]] : []),
    ...(resultState.robust ? structures().slice(1).map(n => [n, token("--text-secondary"), "dashed"]) : [])]);
  panel.replaceChildren(
    el("div", { class: "panel-head" },
      el("h3", { class: "panel-title" }, modelTag(m)),
      el("div", { class: "panel-meta", text: `Model ${m.number} of ${ms.length} · ${m.p} lags · `
        + `${m.T.toLocaleString("en-GB")} hours · ${m.regressors} regressors per equation` })),
    el("div", { class: "panel-top" },
      el("div", { class: "panel-col" },
        el("h4", { class: "card-title", text: "Granger map" }), grangerMap(m, `panel-${m.number}`),
        mapLegend(el("div", { class: "legend-row" })),
        el("h4", { class: "card-title", text: "Equations" }),
        table(["Equation", "R²", "Shock (1 s.d.)"], m.eqs.map(e => [label(e.variable), e.r2.toFixed(2), `${size(e.shock_sd)} ${e.unit}`])),
        table(["Same-hour residual correlation", ""], pairs.map(c => [`${label(c.a)} / ${label(c.b)}`, signed(c.corr)]))),
      el("div", { class: "panel-col" },
        el("h4", { class: "card-title", text: "Main results" }), el("ul", { class: "analysis" }, ...modelAnalysis(m)))),
    el("div", { class: "panel-irf-head" },
      el("h4", { class: "card-title", text: "Impulse responses" }),
      seg([[false, "Chosen lags"], [true, "+ other lag structures"]], resultState.robust,
        v => { resultState.robust = v; renderPanel(ms); }, "Lines shown")),
    irfLegend, grid);
  for (const [box, r, unit] of charts) irfChart(box, r, unit, { robust: resultState.robust, order });
}

/* Compare the models */
function renderForest(ms) {  // the spread's response at one hour, model by model, one chart per shock
  const h = resultState.hour;
  const unit = ms[0].eqs.find(e => e.variable === ms[0].system).unit;
  $("#forest-filters").replaceChildren(el("span", { class: "filters-label", text: "Hour after the shock" }),
    seg(FOREST_HOURS.filter(x => x <= horizon()).map(x => [x, String(x)]), h, v => { resultState.hour = v; renderForest(ms); },
      "Hour after the shock"));
  legend($("#forest-legend"), [...SITE.zones.map(z => [z, zoneColor(z), "dot"]),
    ["filled: band excludes zero", token("--text-secondary"), "dot"], ["hollow: band includes zero", token("--text-secondary"), "ring"]]);
  const cells = ms[0].eqs.map((_, j) => {
    const box = el("div", { class: "chart chart-forest" });
    return [el("div", { class: "card irf-card" }, el("div", { class: "irf-title", text: `${positionName(ms, j)} shock` }),
      el("div", { class: "irf-sub", text: `Spread at hour ${h} (${unit}), 95 % band` }), box), box, j];
  });
  $("#forest").replaceChildren(...cells.map(c => c[0]));
  for (const [, box, j] of cells) {
    const traces = SITE.zones.map(z => {
      const rows = ms.filter(m => m.zone === z).map(m => [m, irfOf(m, m.system, m.eqs[j].variable)]).filter(x => x[1]);
      const color = zoneColor(z);
      return { type: "scatter", mode: "markers", y: rows.map(([m]) => m.name), x: rows.map(([, r]) => r.estimate[h]),
        error_x: { type: "data", symmetric: false, array: rows.map(([, r]) => r.upper[h] - r.estimate[h]),
          arrayminus: rows.map(([, r]) => r.estimate[h] - r.lower[h]), color, thickness: 2, width: 0 },
        marker: { size: 11, color: rows.map(([, r]) => outside(r, h) ? color : token("--surface-1")), line: { color, width: 2 } },
        customdata: rows.map(([m, r]) => [r.lower[h], r.upper[h], `${size(m.eqs[j].shock_sd)} ${m.eqs[j].unit}`]),
        hovertemplate: `%{y}<br>%{x:.2f} ${unit} [%{customdata[0]:.2f}, %{customdata[1]:.2f}]<br>1 s.d. shock: %{customdata[2]}<extra></extra>` };
    });
    Plotly.react(box, traces, { ...baseLayout(), margin: { l: 10, r: 16, t: 6, b: 40 }, hovermode: "closest",
      xaxis: { ...axisStyle(unit), zeroline: true, zerolinecolor: token("--text-muted") },
      yaxis: { ...axisStyle(), automargin: true, categoryorder: "array", categoryarray: ms.map(m => m.name).reverse() },
    }, { ...PLOT_CONFIG, displayModeBar: false });
  }
}

function renderWhole(ms) {  // the spread's whole response to one shock, model by model, also under the other order
  const j = resultState.shock;
  const unit = ms[0].eqs.find(e => e.variable === ms[0].system).unit;
  const order = otherOrders()[0];
  $("#compare-filters").replaceChildren(el("span", { class: "filters-label", text: "Shock" }),
    seg(ms[0].eqs.map((_, i) => [i, `${positionName(ms, i)} shock`]), j, v => { resultState.shock = v; renderWhole(ms); }, "Shock"),
    seg([[true, "Same scale"], [false, "Own scale"]], resultState.shared, v => { resultState.shared = v; renderWhole(ms); }, "Scale"));
  legend($("#compare-legend"), [...SITE.zones.map(z => [`response, ${z}`, zoneColor(z)]),
    ["95 % bootstrap band", rgba(token("--text-muted"), 0.3), "bar"], ...(order ? [[order, token("--series-3")]] : [])]);
  const rows = ms.map(m => [m, irfOf(m, m.system, m.eqs[j].variable)]);
  const values = (r, k) => [...r[k], ...(order && r.orders?.[order] ? r.orders[order].estimate : [])];
  const lo = Math.min(...rows.flatMap(([, r]) => r ? values(r, "lower") : []));
  const hi = Math.max(...rows.flatMap(([, r]) => r ? values(r, "upper") : []));
  const range = resultState.shared ? [lo - 0.05 * (hi - lo), hi + 0.05 * (hi - lo)] : null;
  const cells = rows.map(([m, r]) => {
    const box = el("div", { class: "chart chart-irf" });
    const e = m.eqs[j];
    return [el("div", { class: "card irf-card zone-card", style: `--c:${zoneColor(m.zone)}` },
      el("div", { class: "irf-title" }, modelTag(m)),
      el("div", { class: "irf-sub", text: `${label(e.variable)} shock, 1 s.d. = ${size(e.shock_sd)} ${e.unit}` }), box), box, r];
  });
  $("#compare-grid").replaceChildren(...cells.map(c => c[0]));
  for (const [, box, r] of cells) if (r) irfChart(box, r, unit, { range, order });
}

function renderCompareSummary(ms) {  // facts computed across the models
  const H = horizon();
  const unit = ms[0].eqs.find(e => e.variable === ms[0].system).unit;
  const rows = RESULTS.granger || [];
  const key = r => `${roleName(r.cause, r.system)} → ${roleName(r.effect, r.system)}`;
  const counts = [...new Set(rows.map(key))].map(k => [k, rows.filter(r => key(r) === k && r.p < 0.05).map(r => modelOf(ms, r).number),
    rows.filter(r => key(r) === k).length]);
  const all = counts.filter(([, s, t]) => s.length === t).map(([k]) => k);
  const some = counts.filter(([, s, t]) => s.length && s.length < t).map(([k, s]) => `${k} (models ${s.join(", ")})`);
  const none = counts.filter(([, s]) => !s.length).map(([k]) => k);
  const items = [bullet("Granger causality at 5 %.", [all.length ? `In every model: ${all.join("; ")}.` : "",
    some.length ? `In some: ${some.join("; ")}.` : "", none.length ? `In none: ${none.join("; ")}.` : ""].filter(Boolean).join(" "))];

  for (const j of ms[0].eqs.keys()) {
    if (positionName(ms, j) === "Spread") continue;
    const rs = ms.map(m => [m, m.eqs[j], irfOf(m, m.system, m.eqs[j].variable)]).filter(x => x[2]);
    if (!rs.length) continue;
    const impact = x => x[2].estimate[0], per100 = x => 100 * x[2].estimate[0] / x[1].shock_sd;
    const pick = (f, larger) => rs.reduce((a, b) => (Math.abs(f(b)) > Math.abs(f(a))) === larger ? b : a);
    const span = (f, u) => `from ${signed(f(pick(f, false)))}${u} (${pick(f, false)[0].name}) to ${signed(f(pick(f, true)))}${u} (${pick(f, true)[0].name})`;
    items.push(bullet(`${positionName(ms, j)} shock, same hour.`, `The band excludes zero in ${rs.filter(x => outside(x[2], 0)).length} `
      + `of ${rs.length} models. The spread moves ${span(impact, ` ${unit}`)}; per 100 ${rs[0][1].unit}, ${span(per100, "")}.`));
  }

  const fe = ms.flatMap(m => m.eqs.filter(e => e.variable !== m.system).map(e => irfOf(m, m.system, e.variable))).filter(Boolean);
  const later = fe.flatMap(laterHours);
  if (fe.length) items.push(bullet("Later hours.", later.length
    ? `The bands exclude zero in ${later.length} of ${fe.length * H} response-hours `
      + `(${(100 * later.length / (fe.length * H)).toFixed(1)} %; about 5 % is expected by chance), never after hour ${Math.max(...later)}.`
    : "The bands include zero in every later hour."));

  const halves = ms.map(m => { const r = irfOf(m, m.system, m.system); return r ? [m, halfLife(r)] : null; }).filter(Boolean);
  if (halves.length) items.push(bullet("Spread shocks.", "Hours until the response halves: "
    + halves.map(([m, h]) => `${m.name} ${h < 0 ? `more than ${H}` : h}`).join(", ") + "."));
  items.push(bullet("Fit (R²).", ms[0].eqs.map((_, j) => `${positionName(ms, j)} ${rangeText(ms.map(m => m.eqs[j].r2))}`).join(", ") + "."));
  $("#compare-summary").replaceChildren(el("b", { text: "Summary" }), el("ul", { class: "analysis" }, ...items));
}

function renderCompare(ms) {
  $("#granger-maps").replaceChildren(...ms.map(m => el("div", { class: "card map-card zone-card", style: `--c:${zoneColor(m.zone)}` },
    el("div", { class: "irf-title" }, modelTag(m)), grangerMap(m, `compare-${m.number}`))));
  mapLegend($("#map-legend"));
  renderFit(ms);
  renderCompareSummary(ms);
}

function renderRobustness(ms) {
  const { irf_robustness: inside, granger } = RESULTS;
  if (!RESULTS.structures) { missing($("#structures-table"), "varx"); return; }
  const labels = structures();
  $("#structures-table").replaceChildren(table(["Model", ...labels.map(structureName)],
    RESULTS.structures.map(r => [modelTag(modelOf(ms, r)), ...labels.map(l => r[l])])));
  const robust = labels.slice(1);
  if (inside) {
    const keys = [...new Set(inside.map(r => `${r.zone}|${r.system}|${r.shock}`))];
    $("#irf-robust-table").replaceChildren(table(["Model", "Shock", ...robust.map(structureName)], keys.map(k => {
      const [zone, system, shock] = k.split("|");
      return [modelTag(modelOf(ms, { zone, system })), roleName(shock, system), ...robust.map(l => {
        const r = inside.find(x => x.zone === zone && x.system === system && x.shock === shock && x.structure === l);
        return r ? el("span", { class: r.hours_inside === r.hours ? "full" : "", text: `${r.hours_inside} of ${r.hours}` }) : "–";
      })];
    })));
  }
  const changed = (granger || []).filter(r => robust.some(l => (r[`p_${l}`] < 0.05) !== (r.p < 0.05)));
  $("#granger-changes").replaceChildren(changed.length ? table(["Model", "Cause → effect", ...labels.map(structureName)],
    changed.map(r => [modelTag(modelOf(ms, r)), `${roleName(r.cause, r.system)} → ${roleName(r.effect, r.system)}`,
      ...[r.p, ...robust.map(l => r[`p_${l}`])].map(p => el("span", { class: p < 0.05 ? "sig" : "", text: p.toFixed(3) }))]))
    : el("p", { class: "note", text: "No Granger decision changes with the lag structure." }));
  const fe = (inside || []).filter(r => r.shock !== r.system);
  const minBy = l => Math.min(...fe.filter(r => r.structure === l).map(r => r.hours_inside));
  $("#robust-summary").replaceChildren(el("b", { text: "Summary. " }),
    `${(granger || []).length - changed.length} of ${(granger || []).length} Granger decisions are the same under every lag `
    + "structure. " + (fe.length ? "The spread responses to forecast-error shocks stay inside the chosen model's band in at least "
      + robust.map(l => `${minBy(l)} (${l})`).join(", ") + ` of ${fe[0].hours} hours.` : ""));
}

/* The simple view at the top: how to read the numbers, what we expect, what came out */
function pShade(p) {  // the opacity of a p-value's shading: link (< 0.05), weak (< 0.10), no evidence
  return p < 0.05 ? 0.3 : p < 0.10 ? 0.12 : 0;
}

function ticks(values) {  // labels under a scale: [[text, % from the left]]
  return el("div", { class: "scale-ticks" }, ...values.map(([text, at]) => el("span", { style: `left:${at}%`, text })));
}

function pScale() {  // what a p-value means, along a log scale from 0.001 to 1
  const x = p => 100 * (Math.log10(p) + 3) / 3;
  const blue = token("--series-1");
  const zones = [[0.001, 0.05, "significant"], [0.05, 0.10, "weak"], [0.10, 1, "not significant"]];
  const at = (a, b) => `left:${x(a)}%;width:${x(b) - x(a)}%`;
  return el("div", { class: "scale" },
    el("div", { class: "scale-names" }, ...zones.map(([a, b, name]) => el("span", { style: at(a, b), text: name }))),
    el("div", { class: "scale-track" }, ...zones.map(([a, b]) => el("span", {
      style: `${at(a, b)};background:${pShade(a) ? rgba(blue, pShade(a)) : token("--surface-2")}` }))),
    ticks([0.001, 0.01, 0.05, 0.1, 1].map(t => [String(t), x(t)])));
}

function bandSketch() {  // a response with its band, one clear of zero and one across it (a sketch, not data)
  const x = v => 50 + 45 * v;
  const rows = [["significant", -0.6, -0.85, -0.35], ["not significant", 0.1, -0.3, 0.5]];
  return el("div", { class: "sketch" }, ...rows.map(([name, est, lo, hi]) => el("div", { class: "sketch-row" },
    el("span", { class: "sketch-name", text: name }),
    el("span", { class: "sketch-track" }, el("span", { class: "sketch-band", style: `left:${x(lo)}%;width:${x(hi) - x(lo)}%` }),
      el("span", { class: "sketch-dot", style: `left:${x(est)}%` })))),
    el("div", { class: "sketch-row axis" }, el("span"), ticks([["spread falls", 0], ["0", 50], ["spread rises", 100]])));
}

function r2Strip(ms) {  // every equation's R²: one row per variable, one dot per model
  const vars = unique(ms.flatMap(m => m.eqs.map(e => e.variable)));
  const box = el("div", { class: "strip" }, ...vars.map(v => el("div", { class: "strip-row" },
    el("span", { class: "strip-name", text: label(v) }),
    el("span", { class: "strip-track" }, ...ms.flatMap(m => m.eqs.filter(e => e.variable === v).map(e => el("span", {
      class: "strip-dot", title: `${m.name}: R² ${e.r2.toFixed(2)}`, style: `left:${100 * e.r2}%;--c:${zoneColor(m.zone)}` })))))),
    el("div", { class: "strip-row axis" }, el("span"), ticks([["0", 0], ["0.5", 50], ["1", 100]])));
  const keys = el("div", { class: "legend-row" });
  legend(keys, SITE.zones.map(z => [z, zoneColor(z), "dot"]));
  return el("div", {}, box, keys);
}

function renderReading(ms) {
  $("#read-p").replaceChildren(pScale());
  $("#read-irf").replaceChildren(bandSketch());
  $("#read-r2").replaceChildren(r2Strip(ms));
}

function renderExpected(ms) {  // the hypothesis: the sign of each spread's response to a positive forecast error
  const exp = SITE.expected || {};
  const errors = Object.keys(exp);
  if (!errors.length) {
    $("#expect-table").replaceChildren(el("p", { class: "note", text: "No expected signs: set EXPECTED_SIGNS in main.py." }));
    return;
  }
  const spreads = unique(ms.map(m => m.system));
  const arrow = s => s < 0 ? "↓ falls" : s > 0 ? "↑ rises" : "–";
  $("#expect-table").replaceChildren(table(["Forecast error", "Positive error", "System", "ID and BAL prices",
    ...spreads.map(label)], errors.map(error => {
    const signs = spreads.map(s => exp[error][s]);
    const short = signs.every(s => s < 0), long = signs.every(s => s > 0);  // all spreads down: the later prices go up
    return [label(error), `less ${lowerFirst(label(error)).replace(/ forecast error$/, "")} than forecast`,
      short ? "short" : long ? "long" : "–", short ? "up" : long ? "down" : "–", ...signs.map(arrow)];
  })));
}

function answerViews() {  // [key, button, in a sentence]: hour 0 and 1 of our order, hour 1 of each other order
  return [["0", "Hour 0", "same hour"], ["1", "Hour 1", "one hour later"],
    ...otherOrders().map(o => [o, `Hour 1, ${o}`, `one hour later with the ${o}`])];
}

function responseAt(r, view) {  // [estimate, lower, upper] of a response in one view, or null
  const src = view === "0" || view === "1" ? r : r.orders?.[view];
  const h = view === "0" ? 0 : 1;
  return src ? [src.estimate[h], src.lower[h], src.upper[h]] : null;
}

function renderAnswer(ms) {  // every link from a forecast error to a spread: its Granger p-value and its response
  const exp = SITE.expected || {};
  const blue = token("--series-1");
  const spreads = unique(ms.map(m => m.system));
  const errors = unique(ms.flatMap(m => m.eqs.map(e => e.variable).filter(v => v !== m.system)));
  const views = answerViews();
  if (!views.some(([key]) => key === resultState.view)) resultState.view = "0";
  const fitOf = (v, want) => !v || !(v[1] > 0 || v[2] < 0) ? "none" : want == null ? "clear" : Math.sign(v[0]) === want ? "match" : "opposite";
  const links = SITE.zones.flatMap(zone => errors.flatMap(error => spreads.map(spread => {
    const m = ms.find(x => x.zone === zone && x.system === spread);
    if (!m) return null;
    const r = irfOf(m, spread, error), want = (exp[error] || {})[spread];
    const at = Object.fromEntries(views.map(([key]) => { const v = r && responseAt(r, key); return [key, { v, fit: fitOf(v, want) }]; }));
    return { zone, error, spread, r, at, test: grangerOf(m).find(t => t.cause === error && t.effect === spread),
      eq: m.eqs.find(e => e.variable === error) };
  }))).filter(Boolean);

  const grid = (cell, sub) => table(["", ...spreads.map(label)], SITE.zones.flatMap(zone => errors.map(error => {
    const ls = links.filter(l => l.zone === zone && l.error === error);
    return [el("span", {}, el("b", { text: zone }), ` ${lowerFirst(label(error))}`, sub && ls[0] ? sub(ls[0]) : null),
      ...spreads.map(s => { const l = ls.find(x => x.spread === s); return l ? cell(l) : "–"; })];
  })));
  $("#answer-granger").replaceChildren(grid(l => l.test ? el("span", { class: `pcell${l.test.p < 0.05 ? " sig" : ""}`,
    style: `background:${rgba(blue, pShade(l.test.p))}`, title: `W = ${l.test.W.toFixed(1)}, ${l.test.df} lags`,
    text: l.test.p.toFixed(3) }) : "–"));
  const MARKS = { match: ["good", "✓"], opposite: ["critical", "✗"], none: ["neutral", ""], clear: ["neutral", ""] };
  $("#answer-hour").replaceChildren(seg(views.map(([key, text]) => [key, text]), resultState.view,
    v => { resultState.view = v; renderAnswer(ms); }, "Hour shown"));
  $("#answer-irf").replaceChildren(grid(l => {
    const { v, fit } = l.at[resultState.view];
    if (!v) return "–";
    const [status, mark] = MARKS[fit];
    return el("span", { class: `decision ${status}`, title: `95 % band ${signed(v[1])} to ${signed(v[2])}`,
      text: `${signed(v[0], Math.abs(v[0]) < 1 ? 2 : 1)} ${mark}`.trim() });
  }, l => el("span", { class: "row-sub", text: `1 s.d. = ${size(l.eq.shock_sd)} ${l.eq.unit}` })));
  legend($("#answer-granger-legend"), [["p < 0.05", rgba(blue, 0.3), "bar"], ["0.05 ≤ p < 0.10", rgba(blue, 0.12), "bar"],
    ["p ≥ 0.10", token("--surface-2"), "bar"]]);
  legend($("#answer-irf-legend"), [["✓ expected sign", token("--good"), "dot"], ["✗ opposite sign", token("--critical"), "dot"],
    ["grey: not significant", token("--text-muted"), "dot"]]);

  const name = l => `${l.zone} ${lowerFirst(label(l.error))} → ${label(l.spread)}`;
  const tested = links.filter(l => l.test), n = tested.length;
  const sig = tested.filter(l => l.test.p < 0.05), weak = tested.filter(l => l.test.p >= 0.05 && l.test.p < 0.10);
  const kept = tested.filter(l => l.test.p * n < 0.05), minP = Math.min(...tested.map(l => l.test.p));
  const items = [bullet("Granger causality.", `${sig.length} of ${n} links are significant at 5 %`
    + (sig.length ? `: ${listText(sig.map(name))}` : "") + "." + (weak.length ? ` ${weak.length} more at 10 %.` : "")
    + (!sig.length ? "" : kept.length ? ` With a Bonferroni correction for the ${n} tests, ${listText(kept.map(name))} stay significant.`
      : ` None survives a Bonferroni correction for the ${n} tests (smallest p × ${n} = ${(minP * n).toFixed(2)}).`))];

  for (const error of errors) {  // per forecast error: how many responses are significant, and with which sign, in each view
    const ls = links.filter(l => l.error === error);
    const part = ([key, , words]) => {
      const c = ls.filter(l => l.at[key].fit !== "none"), match = c.filter(l => l.at[key].fit === "match").length;
      const opposite = c.length - match;
      return `${words}, ${c.length} of ${ls.length} significant` + (!c.length ? "" : !opposite ? ", all with the expected sign"
        : !match ? ", all with the opposite sign" : `, ${match} with the expected sign and ${opposite} with the opposite`);
    };
    items.push(bullet(`${label(error)}.`, `${views.map(part).join("; ")}.`.replace(/^./, c => c.toUpperCase())));
  }

  const order = otherOrders()[0];
  const paired = links.filter(l => l.r?.orders?.[order]);
  if (paired.length) {  // the other order against the band of ours, from the hour after the shock on
    const H = horizon();
    const inside = paired.reduce((s, l) => s + l.r.orders[order].estimate.slice(1, H + 1)
      .filter((v, i) => v >= l.r.lower[i + 1] && v <= l.r.upper[i + 1]).length, 0);
    items.push(bullet("Ordering.", `With the ${order}, the response in the hour of the shock is zero by construction. From the `
      + `next hour on, it stays inside the band of our ordering in ${inside} of ${paired.length * H} cases.`));
  }
  $("#answer-summary").replaceChildren(el("b", { text: "Summary" }), el("ul", { class: "analysis" }, ...items));
}

function renderResults() {
  for (const img of document.querySelectorAll("#results img[data-math]")) img.src = SITE.math[img.dataset.math] || "";
  const ms = resultModels();
  if (!ms.length) {
    for (const id of ["#answer-granger", "#model-panel", "#granger-maps", "#structures-table"]) missing($(id), "varx");
    return;
  }
  renderExpected(ms);
  renderAnswer(ms);
  renderWhole(ms);
  renderRobustness(ms);
  renderReading(ms);  // the rest is folded under Details
  resultState.model = Math.min(resultState.model, ms.length - 1);
  renderPicker(ms);
  renderCompare(ms);
  renderGranger(ms);
  if ($("#results-detail").open) renderDetails(ms);
}

function renderDetails(ms) {  // the charts under Details, drawn once the fold is open (a hidden chart has no width)
  renderPanel(ms);
  renderForest(ms);
}

$("#results-detail").addEventListener("toggle", e => {
  if (e.target.open && state.section === "results" && resultModels().length) renderDetails(resultModels());
});

/* ---------- part 1: hypothesis ---------- */
const ERR = SITE.errors || {};
const SIGNS = [[1, "over-forecast", "--over"], [-1, "under-forecast", "--under"]];  // sign, name, colour token
const PERIODS = [["year", "Year"], ["quarter", "Quarter"], ["month", "Month"], ["week", "Week"]];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const RUN_BINS = [[1, 1, "1 h"], [2, 3, "2–3 h"], [4, 6, "4–6 h"], [7, 12, "7–12 h"], [13, 24, "13–24 h"],
  [25, 48, "1–2 days"], [49, Infinity, "over 2 days"]];  // run lengths (hours): from, to, name
const DAY_MS = 24 * HOUR_MS;
const ZONE_NAMES = { DK1: "West Denmark (Jutland and Funen)", DK2: "East Denmark (Zealand, Lolland-Falster and Bornholm)" };
// period: the window over time; at: a time inside the chosen period; view: what the hour-by-month map shows;
// units: the zone comparison in MW or as a % of the average hour
const hypState = { zone: null, error: null, period: "year", at: null, view: "mean", units: "pct" };

const unique = values => [...new Set(values)];
const mw = v => `${Math.round(v).toLocaleString("en-GB")} MW`;
const signedMw = v => `${Math.round(v) > 0 ? "+" : Math.round(v) < 0 ? "−" : ""}${mw(Math.abs(v))}`;
const pct = v => `${Math.round(100 * v)} %`;
const pct1 = v => `${(100 * v).toFixed(1)} %`;
const variable = id => SITE.variables.find(v => v.id === id);

function signName(sign) {
  return SIGNS.find(s => s[0] === sign)[1];
}

function signColor(sign) {
  return token(SIGNS.find(s => s[0] === sign)[2]);
}

function ofError(rows) {  // the rows of the error and zone shown
  return (rows || []).filter(r => r.zone === hypState.zone && r.error === hypState.error);
}

function isoWeek(monday) {  // [ISO year, ISO week number] of the week starting on this Monday (UTC ms)
  const thursday = new Date(monday + 3 * DAY_MS);
  const year = thursday.getUTCFullYear();
  return [year, Math.floor((thursday - Date.UTC(year, 0, 1)) / (7 * DAY_MS)) + 1];
}

function calendarPeriods(kind, first, last) {  // the quarters, months or ISO weeks (Monday-Sunday) from first to last, UTC
  const d = new Date(first);
  let from = kind === "week" ? Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate() - (d.getUTCDay() + 6) % 7)
    : Date.UTC(d.getUTCFullYear(), d.getUTCMonth() - (kind === "quarter" ? d.getUTCMonth() % 3 : 0), 1);
  const day = ms => new Date(ms).toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" });
  const out = [];
  while (from <= last) {
    const s = new Date(from);
    const to = kind === "week" ? from + 7 * DAY_MS
      : Date.UTC(s.getUTCFullYear(), s.getUTCMonth() + (kind === "quarter" ? 3 : 1), 1);
    const [isoYear, week] = isoWeek(from);
    out.push({ from, to, label: kind === "quarter" ? `Q${s.getUTCMonth() / 3 + 1} ${s.getUTCFullYear()}`
      : kind === "month" ? s.toLocaleDateString("en-GB", { month: "long", year: "numeric", timeZone: "UTC" })
      : `Week ${week}, ${isoYear} · ${day(from)} – ${day(to - DAY_MS)}` });
    from = to;
  }
  return out;
}

function renderErrorFilters() {  // every section that shows one zone has its own zone and error choice (one shared state)
  const rows = ERR.summary;
  const pick = (key, value) => { hypState[key] = value; renderStep1(); };
  for (const box of document.querySelectorAll("#hypothesis .zone-choice")) {
    box.replaceChildren(
      el("span", { class: "filters-label", text: "Zone" }),
      seg(unique(rows.map(r => r.zone)).map(z => [z, z]), hypState.zone, v => pick("zone", v), "Zone"),
      el("span", { class: "filters-label", text: "Forecast error" }),
      seg(unique(rows.map(r => r.error)).map(e => [e, label(e)]), hypState.error, v => pick("error", v), "Forecast error"));
  }
}

function largeShare(s) {  // the share of hours with a large error
  return ofError(ERR.large).reduce((sum, r) => sum + r.hours, 0) / s.hours;
}

function renderErrorSources() {  // the forecast, the actual, their source and timing, per error; the zones and the period
  const errors = unique(ERR.summary.map(r => r.error));
  const zones = unique(ERR.summary.map(r => r.zone));
  const lists = errors.map(id => {
    const v = variable(id), [forecast, actual] = v.inputs.map(variable);
    const rows = [["Forecast", forecast?.meaning], ["Actual", actual?.meaning], ["Source", v.sources.join("; ")],
      ["Timing", forecast?.availability], ["Compared with the literature", v.deviation]].filter(([, text]) => text);
    return el("div", {}, el("h4", { class: "q-title", text: label(id) }),
      el("dl", {}, ...rows.flatMap(([name, text]) => [el("dt", { text: name }), el("dd", {}, longText(text))])),
      el("a", { href: `#data/${encodeURIComponent(id)}`, text: "More in the Data overview →" }));
  });
  $("#error-sources").replaceChildren(el("div", { class: "details" }, ...lists),
    el("p", { class: "note" }, `${zones.map(z => `${z}: ${ZONE_NAMES[z] || "bidding zone"}`).join(". ")}. `
      + "Hourly values; chart times in UTC, hours of the day in Copenhagen time."));
}

function sourceText(...ids) {  // "Source: Nord Pool": the organisations behind the variables shown
  const orgs = unique(ids.flatMap(id => variable(id)?.sources || []).map(s =>
    ["Nord Pool", "ENTSO-E", "Energinet"].find(org => s.includes(org)) || s.split(/ [—(:]/)[0]));
  return `Source: ${listText(orgs)}`;
}

function renderSourceLines() {  // under every chart of one zone and error
  for (const p of document.querySelectorAll("#hypothesis .q-source:not([id])")) p.textContent = sourceText(hypState.error);
}

function renderZoneCompare() {  // the same key numbers for every zone, per error; sizes in MW or as a % of the average hour
  const share = hypState.units === "pct";
  const zones = unique(ERR.summary.map(r => r.zone));
  $("#compare-units").replaceChildren(el("span", { class: "filters-label", text: "Unit" }),
    seg([["pct", "% of the average hour"], ["mw", "MW"]], hypState.units, v => { hypState.units = v; renderZoneCompare(); }, "Units"));
  const size = (r, v) => share ? 100 * v / r.actual_mean : v;
  const sizeText = (r, v, sign) => share ? `${sign && v > 0 ? "+" : ""}${size(r, v).toFixed(1).replace("-", "−")} %`
    : sign ? signedMw(v) : mw(v);
  const metrics = [  // name, value, text, bar colour (null: neutral)
    ["Yearly total", r => r.actual_total_twh, r => `${r.actual_total_twh.toFixed(1)} TWh`],
    ["Average hour", r => r.actual_mean, r => mw(r.actual_mean)],
    ["Median absolute error", r => size(r, r.median_abs), r => sizeText(r, r.median_abs)],
    ["Large-error threshold", r => size(r, r.large_threshold), r => sizeText(r, r.large_threshold)],
    ["Mean error", r => size(r, r.mean), r => sizeText(r, r.mean, true), r => signColor(Math.sign(r.mean) || 1)],
    ["Over-forecast hours", r => r.over_share, r => pct(r.over_share)],
    ["Same sign as the previous hour", r => r.same_sign_share, r => pct(r.same_sign_share)],
    ["Median run length", r => r.median_run_of_hour, r => `${r.median_run_of_hour} h`],
    ["Longest run", r => r.longest_run, r => `${r.longest_run} h`],
  ];
  const cards = unique(ERR.summary.map(r => r.error)).map(error => {
    const rows = zones.map(z => ERR.summary.find(r => r.zone === z && r.error === error));
    const tbl = table(["", ...zones], metrics.map(([name, value, text, color]) => {
      const top = Math.max(...rows.map(r => Math.abs(value(r))));
      return [name, ...rows.map(r => el("span", { class: "cmp" },
        el("span", { class: "cmp-track" }, el("span", { class: "cmp-bar", style: `width:${top ? 100 * Math.abs(value(r)) / top : 0}%;`
          + `background:${color ? color(r) : token("--axis")}` })), el("span", { class: "cmp-value", text: text(r) })))];
    }));
    tbl.classList.add("compare");
    return el("div", { class: "card q-card" }, el("h3", { class: "q-title", text: label(error) }), tbl);
  });
  $("#zone-compare").replaceChildren(...cards);
}

function renderErrorTiles(s) {
  const tiles = [
    ["Median absolute error", mw(s.median_abs), `${pct1(s.median_abs / s.actual_mean)} of the average hour`],
    ["Large-error threshold", `±${mw(s.large_threshold)}`, `top ${pct(largeShare(s))} of hours`],
    ["Over-forecast hours", pct(s.over_share), `mean error ${signedMw(s.mean)}`],
    ["Same sign as the previous hour", pct(s.same_sign_share), `median run ${s.median_run_of_hour} h`],
    ["Longest run", `${s.longest_run} h`, `${signName(s.longest_run_sign)}, from ${s.longest_run_start}`],
  ];
  $("#error-tiles").replaceChildren(...tiles.map(([name, value, note]) => el("div", { class: "tile" },
    el("div", { class: "tile-label", text: name }), el("div", { class: "tile-value", text: value }),
    el("div", { class: "tile-note", text: note }))));
}

/* the two time charts share the time window: the whole period, or a chosen quarter, month or week */
function timeWindow(series) {  // the periods of the chosen kind, the chosen one, the x range and an hour's position
  const n = Object.values(series.values)[0].length;
  const first = series.t0_ms, last = series.t0_ms + (n - 1) * series.step_ms;
  const periods = hypState.period === "year" ? [] : calendarPeriods(hypState.period, first, last);
  const index = Math.max(0, periods.findIndex(p => (hypState.at ?? first) >= p.from && (hypState.at ?? first) < p.to));
  return { periods, index, first, last, position: ms => Math.round((ms - first) / series.step_ms),
    range: periods.length ? [stamp(periods[index].from), stamp(periods[index].to - HOUR_MS)] : [stamp(first), stamp(last)] };
}

function periodControls(box, series, note = null, lead = []) {  // [lead], Show: year | quarter | month | week, which one
  const { periods, index } = timeWindow(series);
  const show = (period, time = hypState.at) => { Object.assign(hypState, { period, at: time }); renderTimeCharts(); };
  const step = (offset, text, name) => el("button", { type: "button", class: "step", text, "aria-label": name,
    ...(periods[index + offset] ? {} : { disabled: "" }), onclick: () => show(hypState.period, periods[index + offset].from) });
  box.replaceChildren(...lead, el("span", { class: "filters-label", text: "Period" }),
    seg(PERIODS, hypState.period, v => show(v), "Time window"),
    ...(periods.length ? [el("span", { class: "period-picker" }, step(-1, "‹", "Previous"),
      el("select", { class: "select", "aria-label": "Period", onchange: event => show(hypState.period, Number(event.target.value)) },
        ...periods.map((p, i) => el("option", { value: String(p.from), ...(i === index ? { selected: "" } : {}),
          text: note ? `${p.label} · ${note(p)}` : p.label }))),
      step(1, "›", "Next"))] : []));
}

function signFill(x, values, sign, yaxis = "y") {  // the area between zero and the error, in the colour of its sign
  return { type: "scatter", mode: "lines", x, yaxis, y: values.map(v => v == null ? null : sign * v > 0 ? v : 0),
    line: { width: 0 }, fill: "tozeroy", fillcolor: rgba(signColor(sign), 0.55), hoverinfo: "skip" };
}

function span(lists, i0, i1, extra = []) {  // a padded [min, max] of the values between two positions
  const v = [...lists.flatMap(values => values.slice(Math.max(0, i0), Math.max(0, i1) + 1)).filter(y => y != null), ...extra];
  const [lo, hi] = [Math.min(...v), Math.max(...v)];
  return [lo - 0.06 * (hi - lo), hi + 0.06 * (hi - lo)];
}

function zoomFit(box, w, fit) {  // a zoom by hand: fit the y axes to the hours in view
  const at = t => w.position(Date.parse(String(t).replace(" ", "T") + "Z"));
  box.removeAllListeners("plotly_relayout");
  box.on("plotly_relayout", event => {
    const r = event["xaxis.range[0]"] !== undefined ? [event["xaxis.range[0]"], event["xaxis.range[1]"]] : event["xaxis.range"];
    if (event["xaxis.autorange"]) Plotly.relayout(box, fit(0, w.position(w.last)));
    else if (r) Plotly.relayout(box, fit(...r.map(at)));
  });
}

function renderOverTime(s) {  // the hourly error of one zone, over-forecasts and under-forecasts in their colours
  const series = window.SITE_SERIES[hypState.error];
  const values = series.values[hypState.zone];
  const x = times(hypState.error);
  const w = timeWindow(series);
  const large = p => values.slice(Math.max(0, w.position(p.from)), Math.max(0, w.position(p.to)))
    .filter(v => v != null && Math.abs(v) > s.large_threshold).length;
  periodControls($("#over-time-controls"), series, p => `${large(p)} large-error hours`);
  const fit = (i0, i1) => ({ "yaxis.range": span([values], i0, i1, [s.large_threshold, -s.large_threshold]) });
  const box = $("#over-time");
  Plotly.react(box, [signFill(x, values, 1), signFill(x, values, -1), { type: "scatter", mode: "lines", x, y: values,
    line: { color: token("--text-secondary"), width: 0.8 }, hovertemplate: "%{y:+,.0f} MW<extra></extra>" }], {
    ...baseLayout(), margin: { l: 64, r: 16, t: 8, b: 36 }, hovermode: "x unified",
    shapes: [1, -1].map(sign => ({ type: "line", xref: "paper", x0: 0, x1: 1, y0: sign * s.large_threshold,
      y1: sign * s.large_threshold, line: { color: token("--text-muted"), width: 1, dash: "dot" } })),
    xaxis: { ...axisStyle(), type: "date", hoverformat: "%a %d %b %Y, %H:%M UTC", range: w.range },
    yaxis: { ...axisStyle("MW"), zeroline: true, zerolinecolor: token("--text-muted"),
      range: fit(...w.range.map(t => w.position(Date.parse(t.replace(" ", "T") + "Z"))))["yaxis.range"] },
  }, { ...PLOT_CONFIG, toImageButtonOptions: { format: "png", scale: 2, filename: `${hypState.zone}_${hypState.error}` } });
  zoomFit(box, w, fit);
  legend($("#over-time-legend"), [["over-forecast (error > 0)", signColor(1), "bar"], ["under-forecast (error < 0)", signColor(-1), "bar"],
    [`large error (±${mw(s.large_threshold)})`, token("--text-muted"), "dotted"]]);
}

function renderZonesOverTime() {  // every zone's hourly error as a % of its average hour, one panel each, on one scale
  const series = window.SITE_SERIES[hypState.error];
  const rows = ERR.summary.filter(r => r.error === hypState.error && series.values[r.zone]);
  const x = times(hypState.error);
  const w = timeWindow(series);
  const shares = rows.map(r => series.values[r.zone].map(v => v == null ? null : 100 * v / r.actual_mean));
  const errors = unique(ERR.summary.map(r => r.error));  // the error shown, chosen here too (the same choice as above)
  periodControls($("#zones-time-controls"), series, null, [el("span", { class: "filters-label", text: "Forecast error" }),
    seg(errors.map(e => [e, label(e)]), hypState.error, v => { hypState.error = v; renderStep1(); }, "Forecast error")]);
  const axis = i => (i ? `y${i + 1}` : "y"), name = i => (i ? `yaxis${i + 1}` : "yaxis");
  const gap = 0.1, height = (1 - gap * (rows.length - 1)) / rows.length;
  const top = i => 1 - i * (height + gap);
  const fit = (i0, i1) => { const r = span(shares, i0, i1); return Object.fromEntries(rows.map((_, i) => [`${name(i)}.range`, r])); };
  const ranges = fit(...w.range.map(t => w.position(Date.parse(t.replace(" ", "T") + "Z"))));
  const box = $("#zones-time");
  Plotly.react(box, rows.flatMap((r, i) => [signFill(x, shares[i], 1, axis(i)), signFill(x, shares[i], -1, axis(i)),
    { type: "scatter", mode: "lines", x, y: shares[i], yaxis: axis(i), line: { color: token("--text-secondary"), width: 0.8 },
      hovertemplate: `${r.zone}: %{y:+.1f} %<extra></extra>` }]), {
    ...baseLayout(), margin: { l: 64, r: 16, t: 26, b: 36 }, hovermode: "x unified", hoversubplots: "axis",
    annotations: rows.map((r, i) => ({ xref: "paper", yref: "paper", x: 0, y: top(i), xanchor: "left", yanchor: "bottom",
      showarrow: false, text: `${r.zone} · average hour ${mw(r.actual_mean)}`, font: { size: 13, color: token("--text-primary") } })),
    xaxis: { ...axisStyle(), type: "date", anchor: axis(rows.length - 1), hoverformat: "%a %d %b %Y, %H:%M UTC", range: w.range },
    ...Object.fromEntries(rows.map((_, i) => [name(i), { ...axisStyle("% of the average hour"), domain: [top(i) - height, top(i)],
      zeroline: true, zerolinecolor: token("--text-muted"), ticksuffix: " %", range: ranges[`${name(i)}.range`] }])),
  }, { ...PLOT_CONFIG, toImageButtonOptions: { format: "png", scale: 2, filename: `zones_${hypState.error}` } });
  zoomFit(box, w, fit);
  legend($("#zones-time-legend"), [["over-forecast (error > 0)", signColor(1), "bar"], ["under-forecast (error < 0)", signColor(-1), "bar"]]);
  $("#zones-time-source").textContent = sourceText(hypState.error);
}

/* step 2: what the forecast errors do to the price spreads: an error and a spread on one time axis, the large
   errors shaded by sign, and the spread's mean in them against its mean in all hours */
const SPREADS = SITE.spreads || {};

async function renderLink() {
  const spreads = unique((SPREADS.means || []).map(r => r.spread));
  const box = $("#link-chart");
  if (!spreads.length) { missing(box, "error_spreads"); return; }
  hypState.spread ||= spreads[0];
  const { zone, error, spread } = hypState;
  try {
    await Promise.all([loadSeries(error), loadSeries(spread)]);
  } catch (failure) {
    box.replaceChildren(el("p", { class: "note", text: failure.message }));
    return;
  }
  if (state.section !== "hypothesis" || hypState.zone !== zone || hypState.error !== error || hypState.spread !== spread) return;
  const es = window.SITE_SERIES[error], e = es.values[zone], p = window.SITE_SERIES[spread].values[zone];
  const s = ERR.summary.find(r => r.zone === zone && r.error === error);
  const mean = group => SPREADS.means.find(r => r.zone === zone && r.error === error && r.spread === spread && r.group === group);
  const [over, under, all] = [mean("over"), mean("under"), mean("all")];
  const x = times(error);
  const w = timeWindow(es);
  const sign = i => (e[i] == null || Math.abs(e[i]) <= s.large_threshold ? 0 : Math.sign(e[i]));  // 0: not large
  const inside = (from, to) => { const n = { 1: 0, [-1]: 0 };
    for (let i = Math.max(0, w.position(from)); i < Math.min(e.length, w.position(to)); i++) if (sign(i)) n[sign(i)]++;
    return n; };
  periodControls($("#link-controls"), es, period => { const n = inside(period.from, period.to);
    return `large: ${n[1]} over, ${n[-1]} under`; },
  [el("span", { class: "filters-label", text: "Spread" }),
    seg(spreads.map(c => [c, label(c)]), spread, v => { hypState.spread = v; renderLink(); renderSpreadLags(); }, "Spread")]);

  const runs = [];  // consecutive large-error hours of one sign, shaded through both panels
  for (let i = 0; i < e.length; i++) {
    const k = sign(i);
    if (!k) continue;
    if (runs.length && runs.at(-1)[1] === i - 1 && runs.at(-1)[2] === k) runs.at(-1)[1] = i;
    else runs.push([i, i, k]);
  }
  const unit = (variable(spread)?.unit || "EUR/MWh").split(" (")[0];
  const fit = (i0, i1) => ({ "yaxis.range": span([e], i0, i1, [s.large_threshold, -s.large_threshold]),
    "yaxis2.range": span([p], i0, i1) });
  const ranges = fit(...w.range.map(t => w.position(Date.parse(t.replace(" ", "T") + "Z"))));
  const title = (text, y) => ({ xref: "paper", yref: "paper", x: 0, y, xanchor: "left", yanchor: "bottom", showarrow: false,
    text, font: { size: 13, color: token("--text-primary") } });
  const level = (yref, y, color, dash) => ({ type: "line", xref: "paper", x0: 0, x1: 1, yref, y0: y, y1: y,
    line: { color, width: 1.4, dash } });
  Plotly.react(box, [
    signFill(x, e, 1), signFill(x, e, -1),
    { type: "scatter", mode: "lines", x, y: e, line: { color: token("--text-secondary"), width: 0.8 },
      hovertemplate: `${label(error)}: %{y:+,.0f} MW<extra></extra>` },
    { type: "scatter", mode: "lines", x, y: p, yaxis: "y2", line: { color: token("--text-secondary"), width: 1 },
      hovertemplate: `${label(spread)}: %{y:+,.1f} ${unit}<extra></extra>` },
  ], {
    ...baseLayout(), margin: { l: 70, r: 16, t: 26, b: 36 }, hovermode: "x unified", hoversubplots: "axis",
    shapes: [...runs.map(([a, b, k]) => ({ type: "rect", xref: "x", yref: "paper", layer: "below", y0: 0, y1: 1,
      x0: x[a], x1: stamp(es.t0_ms + (b + 1) * es.step_ms), fillcolor: rgba(signColor(k), 0.18), line: { width: 0 } })),
      level("y", s.large_threshold, token("--text-muted"), "dot"), level("y", -s.large_threshold, token("--text-muted"), "dot")],
    annotations: [title(`${zone} · ${label(error)}`, 1), title(`${zone} · ${label(spread)}`, 0.44)],
    xaxis: { ...axisStyle(), type: "date", anchor: "y2", hoverformat: "%a %d %b %Y, %H:%M UTC", range: w.range },
    yaxis: { ...axisStyle("MW"), domain: [0.56, 1], zeroline: true, zerolinecolor: token("--text-muted"), range: ranges["yaxis.range"] },
    yaxis2: { ...axisStyle(unit), domain: [0, 0.44], zeroline: true, zerolinecolor: token("--axis"), range: ranges["yaxis2.range"] },
  }, { ...PLOT_CONFIG, toImageButtonOptions: { format: "png", scale: 2, filename: `${zone}_${error}_${spread}` } });
  zoomFit(box, w, fit);
  const groups = [[over, "Large<br>over-forecast", signColor(1)], [under, "Large<br>under-forecast", signColor(-1)],
    [all, "All<br>hours", token("--axis")]];
  Plotly.react($("#link-bars"), [{ type: "bar", x: groups.map(g => g[1]), y: groups.map(([r]) => r.mean),
    marker: { color: groups.map(g => g[2]) }, text: groups.map(([r]) => (r.mean == null ? "" : signed(r.mean, 1))),
    textposition: "outside", cliponaxis: false, textfont: { color: token("--text-primary"), size: 12 },
    customdata: groups.map(([r]) => r.hours), hovertemplate: `%{y:+.1f} ${unit} (%{customdata} hours)<extra></extra>` }], {
    ...baseLayout(), margin: { l: 52, r: 8, t: 24, b: 64 }, bargap: 0.35,
    xaxis: { ...axisStyle(), tickangle: 0, automargin: true, tickfont: { color: token("--text-muted"), size: 10 } },
    yaxis: { ...axisStyle(`${label(spread)} (${unit})`), zeroline: true, zerolinecolor: token("--text-muted"), zerolinewidth: 1.5 },
  }, { ...PLOT_CONFIG, displayModeBar: false });

  legend($("#link-legend"), [["over-forecast (error > 0)", signColor(1), "bar"], ["under-forecast (error < 0)", signColor(-1), "bar"],
    [`large error (±${mw(s.large_threshold)})`, token("--text-muted"), "dotted"]]);
  $("#link-q").textContent = pct(1 - largeShare(s));
  $("#link-top").textContent = pct(largeShare(s));
  $("#link-source").textContent = sourceText(error, spread);
}

/* step 2, lags: around a large error, correlation by lag, the tenths (whole year, from the error_spreads step) */
function renderSpreadLags() {
  if (!SPREADS.around) {
    for (const id of ["#around-chart", "#corr-chart", "#tenths-chart"]) missing($(id), "error_spreads");
    return;
  }
  const spreads = unique(SPREADS.means.map(r => r.spread));
  hypState.spread ||= spreads[0];
  const { zone, error, spread } = hypState;
  const mine = rows => rows.filter(r => r.zone === zone && r.error === error && r.spread === spread);
  const unit = (variable(spread)?.unit || "EUR/MWh").split(" (")[0];
  const all = mine(SPREADS.means).find(r => r.group === "all").mean;
  $("#lag-spread").replaceChildren(el("span", { class: "filters-label", text: "Spread" }),
    seg(spreads.map(c => [c, label(c)]), spread, v => { hypState.spread = v; renderLink(); renderSpreadLags(); }, "Spread"));
  const allLine = { type: "line", xref: "paper", x0: 0, x1: 1, y0: all, y1: all, line: { color: token("--text-muted"), width: 1.2, dash: "dash" } };

  // around a large error
  const around = mine(SPREADS.around);
  Plotly.react($("#around-chart"), around.flatMap(r => {
    const color = signColor(r.sign);
    return [
      { type: "scatter", mode: "lines", x: r.h, y: r.upper, line: { width: 0 }, hoverinfo: "skip" },
      { type: "scatter", mode: "lines", x: r.h, y: r.lower, line: { width: 0 }, fill: "tonexty", fillcolor: rgba(color, 0.16), hoverinfo: "skip" },
      { type: "scatter", mode: "lines+markers", x: r.h, y: r.mean, line: { color, width: 2 }, marker: { color, size: 4 },
        customdata: r.h.map((_, i) => r.lower[i] == null ? "no interval: too few blocks"
          : `[${signed(r.lower[i], 1)}, ${signed(r.upper[i], 1)}]`),
        hovertemplate: `large ${signName(r.sign)} runs: %{y:+.1f} ${unit} %{customdata}<extra></extra>` },
    ];
  }), {
    ...baseLayout(), margin: { l: 64, r: 12, t: 8, b: 44 }, hovermode: "x unified",
    shapes: [allLine, { type: "line", xref: "x", yref: "paper", x0: 0, x1: 0, y0: 0, y1: 1, line: { color: token("--text-muted"), width: 1, dash: "dot" } }],
    xaxis: { ...axisStyle("Hours from the start of the run"), dtick: 6, zeroline: false },
    yaxis: { ...axisStyle(unit), zeroline: true, zerolinecolor: token("--axis") },
  }, { ...PLOT_CONFIG, displayModeBar: false });
  legend($("#around-legend"), [...around.map(r => [`large ${signName(r.sign)}s (${r.runs} runs`
    + `${r.lower.every(v => v == null) ? ", too few for a band" : ""})`, signColor(r.sign)]),
    ["95 % band", rgba(token("--text-muted"), 0.3), "bar"], ["mean over all hours", token("--text-muted"), "dashed"]]);

  // correlation by lag
  const corr = mine(SPREADS.correlation);
  Plotly.react($("#corr-chart"), [{ type: "bar", x: corr.map(r => r.lag), y: corr.map(r => r.corr),
    marker: { color: corr.map(r => (r.lag === 0 ? token("--text-primary") : token("--axis"))) },
    hovertemplate: "k = %{x} h: r = %{y:+.3f}<extra></extra>" }], {
    ...baseLayout(), margin: { l: 56, r: 12, t: 8, b: 44 }, bargap: 0.15,
    xaxis: { ...axisStyle("Lag k (hours)"), dtick: 12, zeroline: false },
    yaxis: { ...axisStyle("r"), zeroline: true, zerolinecolor: token("--text-muted") },
  }, { ...PLOT_CONFIG, displayModeBar: false });

  // the tenths
  const lags = unique(SPREADS.tenths.map(t => t.lag));
  if (!lags.includes(hypState.tenthLag)) hypState.tenthLag = lags[0];
  $("#tenths-controls").replaceChildren(el("span", { class: "filters-label", text: "Spread at" }),
    seg(lags.map(k => [k, k === 0 ? "same hour" : `${k} h later`]), hypState.tenthLag, v => { hypState.tenthLag = v; renderSpreadLags(); }, "Lag"));
  const groups = mine(SPREADS.tenths).filter(t => t.lag === hypState.tenthLag).sort((a, b) => a.tenth - b.tenth);
  Plotly.react($("#tenths-chart"), [
    { type: "scatter", mode: "lines", x: groups.map(g => g.error_mean), y: groups.map(g => g.mean), line: { color: token("--axis"), width: 1.5 },
      hoverinfo: "skip" },
    { type: "scatter", mode: "markers", x: groups.map(g => g.error_mean), y: groups.map(g => g.mean),
      error_y: { type: "data", symmetric: false, array: groups.map(g => g.upper - g.mean), arrayminus: groups.map(g => g.mean - g.lower),
        color: token("--text-muted"), thickness: 1.5, width: 4 },
      marker: { size: 10, color: groups.map(g => signColor(Math.sign(g.error_mean) || 1)), line: { color: token("--surface-1"), width: 1 } },
      customdata: groups.map(g => [g.tenth, g.lower, g.upper, g.hours]),
      hovertemplate: `decile %{customdata[0]}: mean error %{x:+,.0f} MW<br>spread %{y:+.1f} ${unit} [%{customdata[1]:+.1f}, %{customdata[2]:+.1f}], %{customdata[3]} hours<extra></extra>` },
  ], {
    ...baseLayout(), margin: { l: 64, r: 12, t: 8, b: 44 }, hovermode: "closest", shapes: [allLine],
    xaxis: { ...axisStyle("Mean forecast error of the decile (MW)"), zeroline: true, zerolinecolor: token("--axis") },
    yaxis: { ...axisStyle(unit), zeroline: true, zerolinecolor: token("--axis") },
  }, { ...PLOT_CONFIG, displayModeBar: false });

  $("#lag-source").textContent = sourceText(error, spread);
}

async function renderTimeCharts() {  // the charts that need the hourly values
  const s = (ERR.summary || []).find(r => r.zone === hypState.zone && r.error === hypState.error);
  try {
    await loadSeries(hypState.error);
  } catch (failure) {
    $("#over-time").replaceChildren(el("p", { class: "note", text: failure.message }));
    return;
  }
  if (state.section !== "hypothesis" || s !== (ERR.summary || []).find(r => r.zone === hypState.zone && r.error === hypState.error)) return;
  renderOverTime(s);
  renderZonesOverTime();
  renderHistogram();
  await renderLink();
}

function renderHistogram() {
  const values = window.SITE_SERIES[hypState.error].values[hypState.zone].filter(v => v != null);
  const raw = (Math.max(...values) - Math.min(...values)) / 60;  // about 60 bins, of a round width
  const size = [1, 2, 5, 10].map(m => m * 10 ** Math.floor(Math.log10(raw))).find(w => w >= raw) || raw;
  const bins = { start: Math.floor(Math.min(...values) / size) * size, end: Math.ceil(Math.max(...values) / size) * size, size };
  const traces = SIGNS.map(([sign, name]) => ({ type: "histogram", name, x: values.filter(v => sign * v > 0), xbins: bins,
    marker: { color: signColor(sign) }, hovertemplate: `%{x} MW: %{y} hours<extra>${name}</extra>` }));
  Plotly.react($("#err-hist"), traces, {
    ...baseLayout(), margin: { l: 56, r: 12, t: 8, b: 44 }, barmode: "overlay", bargap: 0.04,
    xaxis: { ...axisStyle("Forecast error (MW)"), zeroline: false }, yaxis: { ...axisStyle("Hours") },
  }, { ...PLOT_CONFIG, displayModeBar: false });
}

function renderRuns() {
  const rows = ofError(ERR.runs);
  const total = rows.reduce((sum, r) => sum + r.runs * r.length, 0);
  const share = (sign, [from, to]) => rows.filter(r => r.sign === sign && r.length >= from && r.length <= to)
    .reduce((sum, r) => sum + r.runs * r.length, 0) / total;
  const traces = SIGNS.map(([sign, name]) => ({ type: "bar", name, x: RUN_BINS.map(b => b[2]), y: RUN_BINS.map(b => 100 * share(sign, b)),
    marker: { color: signColor(sign) }, hovertemplate: `runs of %{x}: %{y:.0f} % of the hours<extra>${name}</extra>` }));
  Plotly.react($("#err-runs"), traces, {
    ...baseLayout(), margin: { l: 56, r: 12, t: 8, b: 44 }, barmode: "stack", bargap: 0.25,
    xaxis: { ...axisStyle("Run length (consecutive hours with one sign)"), type: "category" },
    yaxis: { ...axisStyle("% of hours"), ticksuffix: " %" },
  }, { ...PLOT_CONFIG, displayModeBar: false });
}

function renderHourMonth() {
  const rows = ofError(ERR.hour_month);
  const months = unique(rows.map(r => r.month)).sort((a, b) => a - b);
  const hours = Array.from({ length: 24 }, (_, h) => h);
  const cell = (m, h) => rows.find(r => r.month === m && r.hour === h);
  const share = hypState.view === "share";
  const z = months.map(m => hours.map(h => cell(m, h)?.[share ? "over_share" : "mean"] ?? null));
  const reach = Math.max(...z.flat().filter(v => v != null).map(v => Math.abs(share ? v - 0.5 : v)));
  $("#hour-month-controls").replaceChildren(seg([["mean", "Mean error"], ["share", "Share of over-forecast hours"]], hypState.view,
    v => { hypState.view = v; renderHourMonth(); }, "Map"));
  Plotly.react($("#err-hour-month"), [{
    type: "heatmap", x: hours.map(h => `${String(h).padStart(2, "0")}:00`), y: months.map(m => MONTHS[m - 1]), z,
    colorscale: [[0, token("--under")], [0.5, token("--mid")], [1, token("--over")]],
    zmid: share ? 0.5 : 0, zmin: share ? 0.5 - reach : -reach, zmax: share ? 0.5 + reach : reach, xgap: 1, ygap: 1,
    colorbar: { thickness: 10, outlinewidth: 0, tickfont: { color: token("--text-muted"), size: 10 },
      ticksuffix: share ? "" : " MW", tickformat: share ? ".0%" : "+,.0f" },
    hovertemplate: share ? "%{y}, %{x}: %{z:.0%} of the hours over-forecast<extra></extra>"
      : "%{y}, %{x}: mean error %{z:+,.0f} MW<extra></extra>",
  }], {
    ...baseLayout(), margin: { l: 44, r: 8, t: 8, b: 44 },
    xaxis: { ...axisStyle("Hour of the day (Copenhagen)"), dtick: 3 }, yaxis: { ...axisStyle(), autorange: "reversed" },
  }, { ...PLOT_CONFIG, displayModeBar: false });
}

function renderLarge(s) {
  const rows = ofError(ERR.large);
  const months = unique(ofError(ERR.hour_month).map(r => r.month)).sort((a, b) => a - b);
  const count = (m, sign) => rows.find(r => r.month === m && r.sign === sign)?.hours ?? 0;
  Plotly.react($("#err-large"), SIGNS.map(([sign, name]) => ({ type: "bar", name, x: months.map(m => MONTHS[m - 1]),
    y: months.map(m => count(m, sign)), marker: { color: signColor(sign) }, hovertemplate: `%{x}: %{y} hours<extra>${name}</extra>` })), {
    ...baseLayout(), margin: { l: 56, r: 12, t: 8, b: 44 }, barmode: "stack", bargap: 0.25,
    xaxis: { ...axisStyle(), type: "category" }, yaxis: { ...axisStyle(`Hours with |error| > ${mw(s.large_threshold)}`) },
  }, { ...PLOT_CONFIG, displayModeBar: false });
}

async function renderStep1() {  // the charts of one zone and error
  const s = (ERR.summary || []).find(r => r.zone === hypState.zone && r.error === hypState.error);
  renderErrorFilters();
  renderErrorTiles(s);
  renderSourceLines();
  renderRuns();
  renderHourMonth();
  renderLarge(s);
  renderSpreadLags();
  await renderTimeCharts();
}

function renderHypothesis() {
  for (const img of document.querySelectorAll("#hypothesis img[data-math]")) img.src = SITE.math[img.dataset.math] || "";
  if (!ERR.summary) {
    for (const id of ["#error-sources", "#zone-compare", "#error-tiles", "#over-time"]) missing($(id), "forecast_errors");
    return;
  }
  hypState.zone ||= ERR.summary[0].zone;
  hypState.error ||= ERR.summary[0].error;
  renderErrorSources();
  renderZoneCompare();
  renderStep1();
}

/* ---------- start ---------- */
$("#tree-search").addEventListener("input", buildTree);
renderPipeline();
route();
