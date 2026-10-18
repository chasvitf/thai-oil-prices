// Prices come straight from the GitHub repo, which the scheduled workflow updates twice a day,
// so the page is always current without redeploying. jsDelivr and the copy deployed with the
// site are fallbacks.
const BASES = [
  "https://raw.githubusercontent.com/chasvitf/thai-oil-prices/main/data/",
  "https://cdn.jsdelivr.net/gh/chasvitf/thai-oil-prices@main/data/",
  "/data/",
];
const ORDER = ["diesel_b20", "diesel", "premium_diesel", "gasohol_e85", "gasohol_e20", "gasohol_91",
  "gasohol_95", "premium_gasohol_95", "benzine_95", "premium_98"];
const BRANDS = ["ptt", "bangchak"];
const CHART_DEFAULT = "diesel";

const $ = (id) => document.getElementById(id);
const thDate = new Intl.DateTimeFormat("th-TH", { day: "numeric", month: "short", year: "numeric" });
const thMonth = new Intl.DateTimeFormat("th-TH", { month: "short" });
const baht = (n) => n.toFixed(2);

async function get(file, as) {
  for (const base of BASES) {
    try {
      const res = await fetch(base + file, { cache: "no-cache" });
      if (res.ok) return as === "json" ? await res.json() : await res.text();
    } catch {
      // try the next mirror
    }
  }
  throw new Error(`โหลด ${file} ไม่ได้`);
}

const fmtDateTime = (iso) => {
  const d = new Date(iso + "+07:00");
  return `${thDate.format(d)} ${iso.slice(11, 16)} น.`;
};

// ---------- today ----------

function renderToday(latest) {
  $("updated").textContent = fmtDateTime(latest.updated);
  const byKey = {};
  for (const brand of BRANDS) {
    for (const p of latest.brands[brand]?.products ?? []) (byKey[p.product] ??= { label: p.label })[brand] = p;
  }
  const since = latest.brands.ptt?.products.find((p) => p.since)?.since;
  $("since").textContent = since ? `ราคามีผลตั้งแต่ ${fmtDateTime(since)}` : "";

  const keys = [...ORDER.filter((k) => byKey[k]), ...Object.keys(byKey).filter((k) => !ORDER.includes(k))];
  $("rows").innerHTML = keys.map((k) => {
    const row = byKey[k], a = row.ptt, b = row.bangchak;
    const cheaper = a && b && Math.abs(a.price - b.price) > 0.001 ? (a.price < b.price ? "ptt" : "bangchak") : null;
    const cell = (p, brand) => p
      ? `<td>${cheaper === brand ? '<span class="cheap">ถูกกว่า</span>' : ""}<span class="num">${baht(p.price)}</span>${tomorrowTag(p)}</td>`
      : '<td class="na">ไม่มีขาย</td>';
    const diff = a && b ? (Math.abs(a.price - b.price) < 0.001 ? "เท่ากัน" : baht(Math.abs(a.price - b.price))) : "–";
    return `<tr data-key="${k}"><td>${row.label}</td>${cell(a, "ptt")}${cell(b, "bangchak")}<td class="diff">${diff}</td></tr>`;
  }).join("");

  const coming = [];
  for (const brand of BRANDS) {
    for (const p of latest.brands[brand]?.products ?? []) {
      if (p.tomorrow != null) coming.push(`${latest.brands[brand].name} ${p.label} ${baht(p.price)} → ${baht(p.tomorrow)} (${signed(p.tomorrow - p.price)})`);
    }
  }
  $("tomorrow").hidden = !coming.length;
  $("tomorrow").innerHTML = coming.length
    ? `⛽ ประกาศราคาพรุ่งนี้ 05:00 น.<ul>${coming.map((c) => `<li>${c}</li>`).join("")}</ul>` : "";
  return keys.map((k) => ({ key: k, label: byKey[k].label }));
}

const signed = (n) => `${n > 0 ? "+" : ""}${n.toFixed(2)}`;

function tomorrowTag(p) {
  if (p.tomorrow == null) return "";
  const up = p.tomorrow > p.price;
  return `<span class="tm ${up ? "up" : "down"}">พรุ่งนี้ ${baht(p.tomorrow)} (${signed(p.tomorrow - p.price)})</span>`;
}

// ---------- history chart ----------

function parseDaily(csv) {
  const series = {};
  for (const line of csv.trim().split("\n").slice(1)) {
    const [date, brand, product, , price] = line.split(",");
    ((series[product] ??= {})[brand] ??= []).push({ t: Date.parse(date + "T00:00:00+07:00"), date, v: Number(price) });
  }
  for (const byBrand of Object.values(series)) for (const pts of Object.values(byBrand)) pts.sort((a, b) => a.t - b.t);
  return series;
}

const chart = { series: {}, product: CHART_DEFAULT, days: 366, labels: {} };

function renderChips(products) {
  const withHistory = products.filter((p) => chart.series[p.key]);
  if (!withHistory.some((p) => p.key === chart.product)) chart.product = withHistory[0]?.key;
  // index.html already has a chip per known fuel (so nothing moves while loading); only
  // rebuild when the brands sell something new.
  const have = [...$("products").querySelectorAll("button")].map((b) => b.dataset.key).join();
  if (have !== withHistory.map((p) => p.key).join()) {
    $("products").innerHTML = withHistory.map((p) => `<button data-key="${p.key}">${p.label}</button>`).join("");
  }
  $("products").querySelectorAll("button").forEach((b) => b.classList.toggle("on", b.dataset.key === chart.product));
}

function drawChart() {
  const box = $("chart");
  const byBrand = chart.series[chart.product];
  if (!byBrand) {
    box.innerHTML = '<p class="muted">ยังไม่มีข้อมูลย้อนหลัง</p>';
    return;
  }
  const end = Math.max(...Object.values(byBrand).map((p) => p.at(-1).t));
  const start = end - chart.days * 864e5;
  const lines = {};
  for (const [brand, pts] of Object.entries(byBrand)) {
    const inRange = pts.filter((p) => p.t >= start);
    if (inRange.length) lines[brand] = inRange;
  }
  const all = Object.values(lines).flat();
  if (!all.length) {
    box.innerHTML = '<p class="muted">ไม่มีข้อมูลในช่วงนี้</p>';
    return;
  }
  const W = box.clientWidth, H = box.clientHeight, L = 46, R = 10, T = 10, B = 26;
  let lo = Math.min(...all.map((p) => p.v)), hi = Math.max(...all.map((p) => p.v));
  if (hi - lo < 1) { lo -= 0.5; hi += 0.5; }
  const pad = (hi - lo) * 0.08;
  lo -= pad; hi += pad;
  const x0 = Math.min(...all.map((p) => p.t));
  const x = (t) => L + ((t - x0) / Math.max(1, end - x0)) * (W - L - R);
  const y = (v) => T + (1 - (v - lo) / (hi - lo)) * (H - T - B);

  const step = niceStep((hi - lo) / 4);
  let grid = "";
  for (let v = Math.ceil(lo / step) * step; v <= hi; v += step) {
    grid += `<line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}"/><text x="${L - 6}" y="${y(v) + 4}" text-anchor="end">${v.toFixed(step < 1 ? 1 : 0)}</text>`;
  }
  let months = "";
  const d = new Date(x0);
  d.setDate(1);
  d.setMonth(d.getMonth() + 1);
  const every = chart.days > 200 ? 2 : 1;
  for (let i = 0; d.getTime() <= end; d.setMonth(d.getMonth() + 1), i++) {
    if (i % every) continue;
    months += `<text x="${x(d.getTime())}" y="${H - 6}" text-anchor="middle">${thMonth.format(d)}</text>`;
  }
  // Prices hold until the next change, so draw steps rather than slopes.
  const path = (pts) => pts.map((p, i) => (i ? `H${x(p.t).toFixed(1)}V${y(p.v).toFixed(1)}` : `M${x(p.t).toFixed(1)},${y(p.v).toFixed(1)}`)).join("") + `H${x(end).toFixed(1)}`;
  box.innerHTML = `<svg role="img" aria-label="กราฟราคา ${chart.labels[chart.product] ?? ""} ย้อนหลัง">
    <g class="grid axis">${grid}</g><g class="axis">${months}</g>
    ${lines.ptt ? `<path class="s-ptt" d="${path(lines.ptt)}"/>` : ""}
    ${lines.bangchak ? `<path class="s-bcp" d="${path(lines.bangchak)}"/>` : ""}
    <line class="cursor" y1="${T}" y2="${H - B}" visibility="hidden"/></svg><div class="tip" hidden></div>`;

  const svg = box.querySelector("svg"), cursor = svg.querySelector(".cursor"), tip = box.querySelector(".tip");
  const valueAt = (pts, t) => { let v = null; for (const p of pts ?? []) { if (p.t <= t) v = p.v; else break; } return v; };
  svg.addEventListener("pointermove", (e) => {
    const r = svg.getBoundingClientRect();
    const t = x0 + ((e.clientX - r.left - L) / (W - L - R)) * (end - x0);
    if (t < x0 || t > end) return;
    const day = Math.round(t / 864e5) * 864e5;
    const a = valueAt(lines.ptt, day), b = valueAt(lines.bangchak, day);
    cursor.setAttribute("x1", x(day)); cursor.setAttribute("x2", x(day)); cursor.setAttribute("visibility", "visible");
    tip.hidden = false;
    tip.style.left = `${Math.min(Math.max(x(day), 90), W - 90)}px`;
    tip.style.top = `${y(a ?? b ?? lo)}px`;
    tip.textContent = `${thDate.format(new Date(day))} · ${a != null ? `ปตท. ${baht(a)}` : ""}${a != null && b != null ? " · " : ""}${b != null ? `บางจาก ${baht(b)}` : ""}`;
  });
  svg.addEventListener("pointerleave", () => { cursor.setAttribute("visibility", "hidden"); tip.hidden = true; });

  const firstBcp = byBrand.bangchak?.[0]?.date;
  $("chartNote").textContent = firstBcp ? `· บางจากเริ่มเก็บ ${thDate.format(new Date(firstBcp + "T00:00:00+07:00"))}` : "";
}

function niceStep(raw) {
  const p = 10 ** Math.floor(Math.log10(raw));
  return [1, 2, 2.5, 5, 10].map((m) => m * p).find((s) => s >= raw) ?? 10 * p;
}

// ---------- start ----------

$("xlsx").href = BASES[0] + "thai-oil-prices.xlsx";
$("csv").href = BASES[0] + "daily.csv";
$("products").addEventListener("click", (e) => {
  const b = e.target.closest("button");
  if (!b) return;
  chart.product = b.dataset.key;
  document.querySelectorAll("#products button").forEach((x) => x.classList.toggle("on", x === b));
  drawChart();
});
$("range").addEventListener("click", (e) => {
  const b = e.target.closest("button");
  if (!b) return;
  chart.days = Number(b.dataset.days);
  document.querySelectorAll("#range button").forEach((x) => x.classList.toggle("on", x === b));
  drawChart();
});
new ResizeObserver(() => chart.series[chart.product] && drawChart()).observe($("chart"));

try {
  const [latest, daily] = await Promise.all([get("latest.json", "json"), get("daily.csv", "text")]);
  const products = renderToday(latest);
  for (const p of products) chart.labels[p.key] = p.label;
  chart.series = parseDaily(daily);
  renderChips(products);
  drawChart();
} catch (err) {
  console.error(err);
  $("rows").innerHTML = `<tr><td colspan="4" class="muted">${err.message} ลองโหลดหน้าใหม่อีกครั้ง</td></tr>`;
}
