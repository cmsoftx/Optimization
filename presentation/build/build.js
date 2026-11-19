// Final MSc presentation generator. Every number below was read from data/outputs of commit dc2e9ed.
const pptxgen = require("pptxgenjs");
const sharp = require("sharp");
const React = require("react");
const RDS = require("react-dom/server");
const fa = require("react-icons/fa6");
const fs = require("fs");
const path = require("path");
const { applyTheme } = require(process.env.SKILL_DIR + "/scripts/apply_theme.js");

const FIG = path.join(__dirname, "figs");
const REPO = process.env.REPO;
const OUTFILE = process.env.OUTFILE;
const series = JSON.parse(fs.readFileSync(path.join(__dirname, "forecast_series.json")));

const THEME = {
  name: "Logistics Network",
  headFontFace: "Calibri",
  bodyFontFace: "Calibri",
  colors: {
    dk1: "22272B", lt1: "FFFFFF", dk2: "1F2427", lt2: "F7F4EE",
    accent1: "0F7C74", accent2: "D9653B", accent3: "7FA37A", accent4: "A8A29A", accent5: "C99A2E", accent6: "5B6770",
    hlink: "0F7C74", folHlink: "5B6770",
  },
};
const HEX = { teal: "0F7C74", coral: "D9653B", sage: "7FA37A", grey: "A8A29A", ochre: "C99A2E", slate: "5B6770",
  graph: "22272B", ivory: "F7F4EE", char: "1F2427", line: "D8D1C4", tealTint: "E2EEEA", coralTint: "F6E3D9", card: "FFFFFF",
  muted: "6B655D" };

async function icon(Comp, color, size = 256) {
  const svg = RDS.renderToStaticMarkup(React.createElement(Comp, { color: "#" + color, size: String(size) }));
  const buf = await sharp(Buffer.from(svg)).resize(size, size).png().toBuffer();
  return "image/png;base64," + buf.toString("base64");
}
async function imgSize(file) { const m = await sharp(file).metadata(); return { w: m.width, h: m.height }; }
// fit an image inside a box, preserving aspect ratio; returns x,y,w,h
async function fit(file, x, y, w, h, align = "center") {
  const s = await imgSize(file); const r = Math.min(w / s.w, h / s.h);
  const iw = s.w * r, ih = s.h * r;
  const ix = align === "left" ? x : x + (w - iw) / 2;
  return { path: file, x: ix, y: y + (h - ih) / 2, w: iw, h: ih };
}
// equation markup: _{..} subscript, ^{..} superscript
function eq(str, opts = {}) {
  const runs = []; const re = /(_\{[^}]*\}|\^\{[^}]*\})/g; let last = 0, m;
  const base = { fontFace: "Cambria", color: opts.color || HEX.graph, fontSize: opts.size || 22, italic: false };
  while ((m = re.exec(str))) {
    if (m.index > last) runs.push({ text: str.slice(last, m.index), options: { ...base } });
    const t = m[0].slice(2, -1);
    runs.push({ text: t, options: { ...base, [m[0][0] === "_" ? "subscript" : "superscript"]: true } });
    last = re.lastIndex;
  }
  if (last < str.length) runs.push({ text: str.slice(last), options: { ...base } });
  if (opts.breakLine) runs[runs.length - 1].options.breakLine = true;
  return runs;
}

(async () => {
  const pres = new pptxgen();
  pres.layout = "LAYOUT_WIDE"; // 13.333 x 7.5
  pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
  pres.title = "Demand-Driven E-Commerce Warehouse Location and Multi-Vehicle Delivery Route Optimization";
  pres.author = "[Student name]";
  pres.subject = "MSc Data Science, Advanced Analytics and Optimization";
  const C = pres.SchemeColor;

  // faint map-grid background for light slides (generated, decorative only)
  const gridSvg = `<svg xmlns="http://www.w3.org/2000/svg" width="2666" height="1500"><rect width="2666" height="1500" fill="#F7F4EE"/>` +
    Array.from({ length: 27 }, (_, i) => Array.from({ length: 15 }, (_, j) => `<circle cx="${50 + i * 100}" cy="${50 + j * 100}" r="2.2" fill="#E3DCCF"/>`).join("")).join("") + `</svg>`;
  const gridPng = "image/png;base64," + (await sharp(Buffer.from(gridSvg)).png().toBuffer()).toString("base64");

  const footer = (dark) => [
    { text: { text: "MSc Data Science · Advanced Analytics and Optimization", options: { x: 0.6, y: 7.0, w: 7, h: 0.3, fontSize: 10, color: dark ? "A8A29A" : HEX.muted, margin: 0 } } },
  ];
  pres.defineSlideMaster({
    title: "TITLE_DARK", background: { color: HEX.char },
    objects: [{ image: { path: path.join(FIG, "title_network.png"), x: 0, y: 0, w: 13.333, h: 7.5 } },
      { placeholder: { options: { name: "title", type: "title", x: 0.6, y: 2.05, w: 6.3, h: 2.3, fontSize: 34, bold: true, color: "FFFFFF", valign: "top", align: "left", margin: 0 }, text: "" } },
      { placeholder: { options: { name: "body", type: "body", x: 0.6, y: 4.55, w: 6.4, h: 0.9, fontSize: 16, color: "D8D1C4", valign: "top", margin: 0 }, text: "" } }],
  });
  pres.defineSlideMaster({
    title: "CONTENT", background: { data: gridPng },
    objects: [
      { placeholder: { options: { name: "kicker", type: "body", x: 0.6, y: 0.38, w: 9, h: 0.3, fontSize: 12, bold: true, color: C.accent1, charSpacing: 1.5, margin: 0 }, text: "" } },
      { placeholder: { options: { name: "title", type: "title", x: 0.6, y: 0.68, w: 12.1, h: 0.75, fontSize: 30, bold: true, color: C.text1, valign: "top", align: "left", margin: 0 }, text: "" } },
      ...footer(false)],
    slideNumber: { x: 12.2, y: 7.0, w: 0.55, h: 0.3, fontSize: 10, color: HEX.muted, align: "right" },
  });
  pres.defineSlideMaster({
    title: "CONTENT_DARK", background: { color: HEX.char },
    objects: [
      { placeholder: { options: { name: "kicker", type: "body", x: 0.6, y: 0.38, w: 9, h: 0.3, fontSize: 12, bold: true, color: "6FC3B5", charSpacing: 1.5, margin: 0 }, text: "" } },
      { placeholder: { options: { name: "title", type: "title", x: 0.6, y: 0.68, w: 12.1, h: 0.75, fontSize: 30, bold: true, color: "FFFFFF", valign: "top", align: "left", margin: 0 }, text: "" } },
      ...footer(true)],
    slideNumber: { x: 12.2, y: 7.0, w: 0.55, h: 0.3, fontSize: 10, color: "A8A29A", align: "right" },
  });
  pres.defineSlideMaster({
    title: "CLOSING_DARK", background: { color: HEX.char },
    objects: [{ image: { path: path.join(FIG, "title_network.png"), x: 0, y: 0, w: 13.333, h: 7.5 } },
      { placeholder: { options: { name: "title", type: "title", x: 0.6, y: 2.3, w: 6.6, h: 1.4, fontSize: 48, bold: true, color: "FFFFFF", align: "left", margin: 0 }, text: "" } },
      { placeholder: { options: { name: "body", type: "body", x: 0.6, y: 3.9, w: 6.6, h: 1.6, fontSize: 16, color: "D8D1C4", valign: "top", margin: 0 }, text: "" } }],
  });

  // ---- helpers for composed elements
  const T = (s, text, o) => s.addText(text, { isTextBox: true, margin: 0, fontSize: 14, color: HEX.graph, valign: "top", ...o });
  const card = (s, x, y, w, h, fill = HEX.card, name) => s.addShape(pres.shapes.ROUNDED_RECTANGLE,
    { x, y, w, h, rectRadius: 0.08, fill: { color: fill }, line: { color: HEX.line, width: 0.75 }, objectName: name });
  const takeaway = (s, text, y = 6.28, dark = false) => {
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 0.6, y, w: 12.13, h: 0.56, rectRadius: 0.08,
      fill: { color: dark ? "2C3438" : HEX.tealTint }, line: { color: dark ? "2C3438" : HEX.tealTint }, objectName: "Takeaway box" });
    s.addShape(pres.shapes.OVAL, { x: 0.82, y: y + 0.2, w: 0.16, h: 0.16, fill: { color: HEX.teal }, line: { color: HEX.teal }, objectName: "Takeaway node" });
    T(s, [{ text: "Takeaway  ", options: { bold: true, color: dark ? "6FC3B5" : HEX.teal } }, { text, options: { color: dark ? "FFFFFF" : HEX.graph } }],
      { x: 1.12, y, w: 11.45, h: 0.56, fontSize: 14, valign: "middle", objectName: "Takeaway text" });
  };
  const ICON = {};
  for (const [k, comp] of Object.entries({ wh: fa.FaWarehouse, truck: fa.FaTruckFast, pin: fa.FaLocationDot, chart: fa.FaChartLine, route: fa.FaRoute,
    dna: fa.FaDna, scale: fa.FaScaleBalanced, gauge: fa.FaGaugeHigh, slider: fa.FaSliders, db: fa.FaDatabase, broom: fa.FaBroom,
    layers: fa.FaLayerGroup, calc: fa.FaCalculator, shield: fa.FaShieldHalved, map: fa.FaMapLocationDot, flask: fa.FaFlask,
    desk: fa.FaDesktop, clock: fa.FaClock, warn: fa.FaTriangleExclamation, check: fa.FaCircleCheck, boxes: fa.FaBoxesStacked, git: fa.FaGithub })) {
    ICON[k] = { white: await icon(comp, "FFFFFF"), teal: await icon(comp, HEX.teal), coral: await icon(comp, HEX.coral) };
  }
  const iconDot = (s, key, x, y, d = 0.5, fill = HEX.teal) => {
    s.addShape(pres.shapes.OVAL, { x, y, w: d, h: d, fill: { color: fill }, line: { color: fill }, objectName: `Icon circle ${key}` });
    s.addImage({ data: ICON[key].white, x: x + d * 0.24, y: y + d * 0.24, w: d * 0.52, h: d * 0.52, altText: key });
  };
  const chartText = { catAxisLabelFontFace: "+mn-lt", valAxisLabelFontFace: "+mn-lt", dataLabelFontFace: "+mn-lt", legendFontFace: "+mn-lt",
    titleFontFace: "+mn-lt", catAxisLabelColor: "5F5A53", valAxisLabelColor: "5F5A53", catAxisLabelFontSize: 11, valAxisLabelFontSize: 10,
    dataLabelFontSize: 10, legendFontSize: 11, titleFontSize: 13, titleColor: HEX.graph, valGridLine: { color: "E6E0D6", size: 0.5 },
    catGridLine: { style: "none" }, catAxisLineShow: true, valAxisLineShow: false };

  // ================= Section: Introduction
  pres.addSection({ title: "Introduction" });
  let s = pres.addSlide({ masterName: "TITLE_DARK", sectionTitle: "Introduction" });
  s.addText("Demand-Driven E-Commerce Warehouse Location and Multi-Vehicle Delivery Route Optimization", { placeholder: "title" });
  s.addText("Using Hybrid Optimization Algorithms: forecasting → exact facility location (CFLP) → evolutionary benchmark (GA) → capacitated routing with Guided Local Search", { placeholder: "body" });
  T(s, "MSC DATA SCIENCE · ADVANCED ANALYTICS AND OPTIMIZATION", { x: 0.6, y: 1.55, w: 7, h: 0.3, fontSize: 12, bold: true, color: "6FC3B5", charSpacing: 1.5 });
  T(s, [{ text: "[Student name]  ·  [University]  ·  [Department]", options: { breakLine: true } }, { text: "Supervisor: [Supervisor name]" }],
    { x: 0.6, y: 5.75, w: 6.4, h: 0.65, fontSize: 14, color: "FFFFFF" });
  T(s, "Background: the project's actual weekly delivery routes from the 6 optimised US depots (Guided Local Search output).",
    { x: 7.6, y: 6.95, w: 5.2, h: 0.35, fontSize: 10, color: "A8A29A", align: "right" });
  s.addNotes(`Hi everyone. My project is about two decisions every online retailer has to make. First, where should the warehouses be? And second, once you have them, how do the delivery vans actually run?

What you can see behind the title is real output from the project. These are the weekly delivery routes the system built from six warehouse locations it chose itself.

The short version of the pipeline: I took the DataCo supply-chain data and turned the orders into demand per location. I forecast that demand, then chose warehouses with an exact optimisation model called a CFLP. I checked that model against a genetic algorithm, and finally planned the vehicle routes with Google OR-Tools.

Let me start with why this problem matters.

Source: reports/figures generated from data/outputs/all_method_route_stops.csv (GLS routes).`);

  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Introduction" });
  s.addText("THE REAL-WORLD PROBLEM", { placeholder: "kicker" });
  s.addText("Warehouse location and delivery routing are linked decisions", { placeholder: "title" });
  const probs = [["pin", "Location sets the cost base", "A warehouse far from demand makes every single delivery more expensive."],
    ["boxes", "Capacity limits who can be served", "A full warehouse pushes customers to a farther one, so the nearest site isn't always possible."],
    ["route", "Routes drive daily operating cost", "Poor stop sequences add kilometres and driver hours every week."],
    ["chart", "Demand moves over time", "This data has a structural break in Oct 2017. Planning on stale demand opens the wrong network."]];
  probs.forEach(([ic, h, b], i) => {
    const y = 1.7 + i * 1.08;
    iconDot(s, ic, 0.6, y + 0.05, 0.55, i < 3 ? HEX.teal : HEX.coral);
    T(s, h, { x: 1.35, y, w: 5.4, h: 0.35, fontSize: 17, bold: true });
    T(s, b, { x: 1.35, y: y + 0.38, w: 5.4, h: 0.6, fontSize: 14, color: HEX.muted });
  });
  card(s, 7.25, 1.7, 5.48, 4.3, HEX.card, "Coupled decisions card");
  T(s, "How the decisions feed each other in this project", { x: 7.55, y: 1.88, w: 5, h: 0.35, fontSize: 15, bold: true });
  const chain = [["Demand forecast", "orders + units per zone per week", HEX.slate], ["Warehouse location", "which sites open, who they serve", HEX.teal], ["Vehicle routing", "which van visits which stops, in what order", HEX.coral]];
  chain.forEach(([h, b, col], i) => {
    const y = 2.45 + i * 1.12;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 7.6, y, w: 4.8, h: 0.78, rectRadius: 0.06, fill: { color: HEX.ivory }, line: { color: col, width: 1.5 }, objectName: `Chain ${h}` });
    T(s, [{ text: h, options: { bold: true, breakLine: true, color: col } }, { text: b, options: { fontSize: 13, color: HEX.muted } }], { x: 7.8, y: y + 0.08, w: 4.5, h: 0.65, fontSize: 15 });
    if (i < 2) s.addShape(pres.shapes.DOWN_ARROW, { x: 9.85, y: y + 0.82, w: 0.3, h: 0.27, fill: { color: HEX.grey }, line: { color: HEX.grey }, objectName: "Chain arrow" });
  });
  T(s, "Solved in sequence: each stage's output is the next stage's input.", { x: 7.6, y: 5.6, w: 4.9, h: 0.3, fontSize: 12, italic: true, color: HEX.muted });
  takeaway(s, "Bad demand inputs lead to the wrong warehouses, and the wrong warehouses make routing expensive.");
  s.addNotes(`So why does this matter?

If a warehouse sits far from where customers actually are, every order costs more to deliver, and no clever routing fully fixes that later. Capacity matters as well. If the nearest warehouse is full, some customers have to be served from somewhere farther away. Then there's routing, which is the cost you pay every single week. And underneath all of it is demand, which changes. In this dataset it changed quite sharply in October 2017, and we'll come back to that.

One honest point up front: I solve these decisions in sequence, not as one giant joint model. The forecast feeds the warehouse model, and the warehouse model feeds routing.

Possible professor questions
Q: Why not solve location and routing jointly?
A: A joint location-routing problem is much harder to solve exactly. Sequencing them is standard practice, and it keeps each stage verifiable. I list joint optimisation as future work.`);

  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Introduction" });
  s.addText("RESEARCH OBJECTIVES AND CONTRIBUTION", { placeholder: "kicker" });
  s.addText("Eight objectives, each checked against a baseline", { placeholder: "title" });
  const objs = [["chart", "Forecast demand", "Orders and units per zone, 4 methods compared"],
    ["wh", "Locate warehouses", "Exact CFLP with Pyomo + CBC"],
    ["dna", "Benchmark a GA", "DEAP genetic algorithm vs the exact optimum"],
    ["boxes", "Allocate within capacity", "Every zone served, no warehouse overloaded"],
    ["truck", "Route vehicles", "CVRP per depot: capacity, route length, fleet"],
    ["route", "Improve with GLS", "Guided Local Search vs standard search and Nearest Neighbor"],
    ["flask", "Test & stress", "Forecast impact, sensitivity, robustness"],
    ["desk", "Support decisions", "Streamlit dashboard with a live what-if page"]];
  objs.forEach(([ic, h, b], i) => {
    const col = i % 4, row = Math.floor(i / 4), x = 0.6 + col * 3.07, y = 1.7 + row * 2.0;
    card(s, x, y, 2.85, 1.78, HEX.card, `Objective ${i + 1}`);
    iconDot(s, ic, x + 0.22, y + 0.22, 0.52);
    T(s, String(i + 1).padStart(2, "0"), { x: x + 2.1, y: y + 0.25, w: 0.55, h: 0.4, fontSize: 18, bold: true, color: HEX.grey, align: "right" });
    T(s, h, { x: x + 0.22, y: y + 0.88, w: 2.5, h: 0.34, fontSize: 16, bold: true });
    T(s, b, { x: x + 0.22, y: y + 1.2, w: 2.5, h: 0.52, fontSize: 12, color: HEX.muted });
  });
  takeaway(s, "Contribution: one reproducible pipeline where every optimiser is measured against simpler methods on identical inputs.", 5.85);
  s.addNotes(`These are the eight things the project set out to do.

The important word is "measured". Every method here has a comparison. The forecasts are compared with simple averages. The exact warehouse model is compared with a genetic algorithm, K-Means and random choices. And Guided Local Search is compared with Nearest Neighbor and standard OR-Tools.

All of them get exactly the same demand, the same candidate sites, the same distances and the same costs. That's what makes the comparisons fair.

The contribution isn't a brand-new algorithm. It's the integration, plus honest benchmarking on real order data, including a couple of results where the fancier method didn't win.

Possible professor questions
Q: What exactly is novel here?
A: The end-to-end chain on real data, with exact-versus-heuristic benchmarking on identical inputs. Plus a measured test of whether forecasting actually improves the warehouse plan, rather than just assuming it does.`);

  // ================= Section: Data
  pres.addSection({ title: "Data" });
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Data" });
  s.addText("DATASET AND DATA CLEANING", { placeholder: "kicker" });
  s.addText("From 180,519 order items to 62,011 deliveries we can locate", { placeholder: "title" });
  s.addChart(pres.charts.BAR, [{ name: "Orders", labels: ["Raw orders", "Remove cancelled / fraud", "Remove invalid coordinates"], values: [65752, 62897, 62011] }], {
    x: 0.5, y: 1.6, w: 5.6, h: 3.9, barDir: "col", chartColors: [HEX.teal], showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: "#,##0",
    showTitle: true, title: "Orders remaining after each step", showLegend: false, valAxisMinVal: 55000, valAxisMaxVal: 67000, valAxisLabelFormatCode: "#,##0",
    valAxisTitle: "orders", showValAxisTitle: true, valAxisTitleFontSize: 11, valAxisTitleColor: "5F5A53", ...chartText, objectName: "Cleaning funnel chart" });
  T(s, "Axis starts at 55,000 so the 1.4% coordinate step stays visible.", { x: 0.6, y: 5.5, w: 5.4, h: 0.3, fontSize: 10, italic: true, color: HEX.muted });
  const rows = [["Step", "Effect", "Why"],
    ["Item rows → orders", "180,519 → 65,752", "One order = one delivery; items of an order share address, date and mode"],
    ["Cancelled & suspected fraud", "−2,855 orders", "All have status 'Shipping canceled': no physical delivery"],
    ["Invalid coordinates", "−886 orders", "Sign flips, cut-off longitudes, placeholder point, >1,000 km from state"],
    ["Personal data", "5 columns dropped", "Names / street never written to any output"],
    ["Reconciliation", "37 / 37 checks pass", "Units, orders and sales conserved item → order → zone-day"]];
  s.addTable(rows.map((r, i) => r.map((c) => ({ text: c, options: { bold: i === 0, color: i === 0 ? "FFFFFF" : HEX.graph, fill: { color: i === 0 ? HEX.graph : (i % 2 ? HEX.card : HEX.ivory) } } }))), {
    x: 6.4, y: 1.65, w: 6.33, colW: [1.75, 1.45, 3.13], fontSize: 12, fontFace: "Calibri", border: { type: "solid", color: HEX.line, pt: 0.5 }, valign: "middle", rowH: 0.62, objectName: "Cleaning steps table" });
  takeaway(s, "94.2% of units retained (361,965 of 384,079). Rows are flagged, not deleted, so every exclusion can be audited.", 6.0);
  s.addNotes(`The data is the DataCo Smart Supply Chain dataset from Kaggle: 180,519 rows, 53 columns, covering January 2015 to January 2018.

First thing I noticed: each row is one item, not one order. An order with three products appears three times, and if you treat every row as a delivery you triple-count trips. So I grouped items into 65,752 orders. I checked that everything order-level, like the address and shipping mode, really is identical inside each order.

Then two removals. Cancelled and suspected-fraud orders never ship, so they aren't demand. And some coordinates were simply broken: flipped signs, a truncated longitude that puts Oregon in the Atlantic, and one placeholder point near the centre of the US.

I also dropped the customer names and street columns. 37 reconciliation checks confirm nothing gets lost when we aggregate.

Possible professor questions
Q: Why not repair the bad coordinates instead of removing them?
A: We can't recover the true location. Imputing a city average would invent locations. It's only 1.4% of orders, and it's logged.
Q: Why remove cancelled orders?
A: They never generate a truck movement, so keeping them would overstate demand.

Source: data/outputs/data_quality_report.csv, reports/phase2_preprocessing_eda.md §1.`);

  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Data" });
  s.addText("GEOGRAPHIC DEMAND ZONES AND DATA LIMITATIONS", { placeholder: "kicker" });
  s.addText("Customers grouped into zones of guaranteed size", { placeholder: "title" });
  s.addImage({ ...(await fit(path.join(FIG, "zones_map.png"), 0.45, 1.5, 7.6, 4.3)), altText: "Demand zone map: 312 CONUS, 25 Puerto Rico and 6 Hawaii zones" });
  T(s, [{ text: "How", options: { bold: true, fontSize: 16, color: HEX.teal, breakLine: true } },
    { text: "Complete-linkage clustering of the customer coordinates, cut at a maximum diameter: every pair of customers in a zone is within the limit.", options: { breakLine: true } },
    { text: "CONUS: 4,107 points → 312 zones (≤ 50 km)", options: { bullet: true, breakLine: true } },
    { text: "Puerto Rico: 7,381 → 25 zones (≤ 10 km)", options: { bullet: true, breakLine: true } },
    { text: "Hawaii: 28 → 6 zones, analysis only", options: { bullet: true } }],
    { x: 8.35, y: 1.55, w: 4.4, h: 2.35, fontSize: 13, paraSpaceAfter: 4 });
  card(s, 8.35, 4.0, 4.4, 1.85, HEX.coralTint, "Limitation card");
  s.addImage({ data: ICON.warn.coral, x: 8.55, y: 4.15, w: 0.32, h: 0.32 });
  T(s, [{ text: "Not real delivery addresses", options: { bold: true, breakLine: true } },
    { text: "Destination fields cover 164 countries with no coordinates, and they're independent of the customer's location (Cramér's V ≤ 0.04). Customer coordinates act as simulated demand points in a hypothetical domestic network." }],
    { x: 8.98, y: 4.12, w: 3.65, h: 1.68, fontSize: 12 });
  takeaway(s, "Zones turn about 62,000 orders into 337 demand points the models can use. Puerto Rico is a separate network (no trucks across the sea).", 6.0);
  s.addNotes(`The warehouse model can't work with sixty thousand individual orders. It needs demand at a manageable set of locations, so I grouped nearby customers into zones.

I used complete-linkage hierarchical clustering, which guarantees that no two customers in the same zone are more than 50 km apart on the mainland, or 10 km on the islands. It's deterministic: no random seed, so you get the same zones every time.

That gives 312 zones on the mainland and 25 in Puerto Rico. Hawaii's 6 zones are only analysed, never routed.

The coral box matters. These are customer locations, not verified delivery addresses. The destination fields in this dataset look synthetic: a US customer can have an order going to Indonesia. So this is a hypothetical domestic network built on real customer geography. It isn't a replay of historical shipments.

Possible professor questions
Q: Why complete linkage rather than k-means?
A: K-means can't guarantee a maximum zone size. Complete linkage bounds the diameter by construction, which I verified exactly.
Q: Why is Puerto Rico separate?
A: There's no road connection, so the models are solved separately and a mainland-to-island assignment is impossible.

Source: data/outputs/demand_zones.csv, phase2_coordinate_validation.csv, eda_destination_independence.csv.`);

  s = pres.addSlide({ masterName: "CONTENT_DARK", sectionTitle: "Data" });
  s.addText("SYSTEM ARCHITECTURE", { placeholder: "kicker" });
  s.addText("One pipeline: each stage's output feeds the next", { placeholder: "title" });
  const stages = [["db", "Raw data", "DataCo CSV"], ["broom", "Cleaning", "flag & log"], ["map", "Demand zones", "337 zones"], ["chart", "Forecasting", "orders + units"],
    ["pin", "Candidates", "37 CONUS · 25 PR"], ["calc", "CFLP", "Pyomo + CBC"], ["dna", "GA benchmark", "DEAP, 5 seeds"], ["boxes", "Allocation", "capacity-feasible"],
    ["truck", "CVRP", "per depot"], ["route", "Guided LS", "OR-Tools"], ["flask", "Evaluation", "Exp. A–E"], ["desk", "Dashboard", "8 pages"]];
  T(s, "STRATEGIC: where to build and how many", { x: 0.6, y: 1.65, w: 6, h: 0.3, fontSize: 12, bold: true, color: "6FC3B5" });
  T(s, "OPERATIONAL: how to deliver each week", { x: 1.55, y: 3.98, w: 6, h: 0.3, fontSize: 12, bold: true, color: "F0A07E" });
  stages.forEach(([ic, h, b], i) => {
    const row = i < 8 ? 0 : 1; const col = row === 0 ? i : i - 8;
    const x = 0.6 + col * 1.54, y = row === 0 ? 2.05 : 4.5;
    const fill = row === 0 ? (i < 4 ? "33403F" : "1F4E4A") : "4A3027";
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w: 1.36, h: 1.45, rectRadius: 0.08, fill: { color: fill }, line: { color: fill }, objectName: `Stage ${h}` });
    s.addImage({ data: row === 0 ? ICON[ic].white : ICON[ic].white, x: x + 0.47, y: y + 0.15, w: 0.42, h: 0.42 });
    T(s, h, { x: x + 0.05, y: y + 0.65, w: 1.26, h: 0.35, fontSize: 13, bold: true, color: "FFFFFF", align: "center" });
    T(s, b, { x: x + 0.05, y: y + 0.98, w: 1.26, h: 0.4, fontSize: 10, color: "D8D1C4", align: "center" });
    if ((row === 0 && col < 7) || (row === 1 && col < 3)) s.addShape(pres.shapes.RIGHT_ARROW, { x: x + 1.37, y: y + 0.62, w: 0.16, h: 0.2, fill: { color: "A8A29A" }, line: { color: "A8A29A" }, objectName: "Flow arrow" });
  });
  s.addShape(pres.shapes.LINE, { x: 11.15, y: 3.55, w: 0, h: 0.27, line: { color: "A8A29A", width: 1.5, endArrowType: "triangle" }, objectName: "Down link" });
  s.addShape(pres.shapes.LINE, { x: 1.28, y: 3.82, w: 9.87, h: 0, line: { color: "A8A29A", width: 1.5 }, objectName: "Return link" });
  s.addShape(pres.shapes.LINE, { x: 1.28, y: 3.82, w: 0, h: 0.68, line: { color: "A8A29A", width: 1.5, endArrowType: "triangle" }, objectName: "Down link 2" });
  card(s, 6.85, 4.5, 5.88, 1.45, "2C3438", "Handoff card");
  T(s, [{ text: "Hand-offs (actual files)", options: { bold: true, color: "6FC3B5", breakLine: true } },
    { text: "cflp_zone_demand_forecast.csv → CFLP → selected_allocation.csv → CVRP → vehicle_assignments.csv → experiments & dashboard. Run end to end with python main.py all.", options: { color: "FFFFFF" } }],
    { x: 7.05, y: 4.62, w: 5.5, h: 1.25, fontSize: 13 });
  takeaway(s, "Strategic stages run once per plan. Routing runs weekly on the chosen warehouses. The objectives are optimised in sequence, not jointly.", 6.2, true);
  s.addNotes(`Here's the whole system on one slide.

The top row is the strategic part: deciding where warehouses go. It starts with cleaning and zones, then forecasting, then candidate sites, the exact CFLP model, and the genetic algorithm as a comparison. After that, every zone gets a warehouse within capacity.

The bottom row is operational. For each chosen warehouse I build vehicle routes, improve them with Guided Local Search, and then evaluate everything.

The stages are connected by actual files, not copy-pasting. The forecast file goes into the warehouse model, its allocation file goes into routing, and so on. One command, python main.py all, reruns the whole chain. My full verified run took about 54 minutes and all 69 automated tests pass.

Possible professor questions
Q: Is the final answer a global optimum of the whole system?
A: No. Each stage is optimised given the previous one. The CFLP is globally optimal for its own model, but routing cost isn't part of that objective.

Source: src/pipeline.py, main.py, README.md.`);

  // ================= Section: Forecasting
  pres.addSection({ title: "Forecasting" });
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Forecasting" });
  s.addText("DEMAND FORECASTING: HOW AND WHY", { placeholder: "kicker" });
  s.addText("Simple, break-aware models beat XGBoost", { placeholder: "title" });
  const u = series.units;
  s.addChart(pres.charts.LINE, [
    { name: "Actual units", labels: u.labels, values: u.actual },
    { name: "XGBoost trained before the break (no post-break data)", labels: u.labels, values: u.naive_xgb },
    { name: "Selected: Random Forest, recalibrated after 4 weeks", labels: u.labels, values: u.selected }], {
    x: 0.45, y: 1.55, w: 7.4, h: 4.3, chartColors: [HEX.graph, HEX.coral, HEX.teal], lineSize: 2, lineDataSymbol: "none",
    showTitle: true, title: "CONUS weekly units (network total), Jun 2017 – Jan 2018", showLegend: true, legendPos: "b",
    valAxisTitle: "units / week", showValAxisTitle: true, valAxisTitleFontSize: 11, valAxisTitleColor: "5F5A53", valAxisLabelFormatCode: "#,##0",
    catAxisLabelFrequency: 4, ...chartText, catAxisLabelFontSize: 10, objectName: "Forecast break chart" });
  T(s, [{ text: "How", options: { bold: true, color: HEX.teal, breakLine: true } },
    { text: "Weekly zone series; orders and units forecast separately", options: { bullet: true, breakLine: true } },
    { text: "Historical avg · moving avg · Random Forest · XGBoost", options: { bullet: true, breakLine: true } },
    { text: "29 lag/rolling features built only from past weeks (leakage test)", options: { bullet: true, breakLine: true } },
    { text: "Chronological splits; selection on 13 held-out post-break weeks", options: { bullet: true } }],
    { x: 8.15, y: 1.55, w: 4.6, h: 1.95, fontSize: 13, paraSpaceAfter: 3 });
  const fr = [["Selected (zone-total WAPE)", "Orders", "Units"], ["CONUS", "Share × recent level 0.24", "RF recalibrated 0.30"], ["Puerto Rico", "Post-break avg 0.25", "Post-break avg 0.46"]];
  s.addTable(fr.map((r, i) => r.map((c) => ({ text: c, options: { bold: i === 0, color: i === 0 ? "FFFFFF" : HEX.graph, fill: { color: i === 0 ? HEX.teal : HEX.card } } }))),
    { x: 8.15, y: 3.62, w: 4.58, colW: [1.42, 1.62, 1.54], fontSize: 11, fontFace: "Calibri", border: { type: "solid", color: HEX.line, pt: 0.5 }, rowH: 0.42, objectName: "Selected models table" });
  T(s, "Before the break, zone-week WAPE: historical average 0.726 vs XGBoost 0.743 (noise floor 0.684). Demand is near-stationary count noise, so boosting has little to learn.",
    { x: 8.15, y: 5.0, w: 4.58, h: 0.9, fontSize: 12, color: HEX.muted });
  takeaway(s, "From Oct 2017 units/order fell from 6.5 to 1.0. Pre-break-trained models overshoot about 5×, so handling the break mattered more than model choice.", 6.05);
  s.addNotes(`For forecasting I used weekly demand per zone, and I forecast orders and units separately. Orders are deliveries, so they drive transport cost. Units are items, so they drive warehouse capacity.

I compared four methods: a historical average, a moving average, Random Forest and XGBoost. The machine-learning models use 29 features built only from past weeks, and a unit test checks that changing the future never changes those features.

The chart shows the big discovery. In October 2017 units per order dropped from about 6.5 to 1. The coral line is XGBoost trained before the break: it keeps predicting the old level, around 1,400 units a week, while reality is about 280. The teal line is the selected model after seeing four post-break weeks.

XGBoost wasn't selected anywhere. Before the break, a plain historical average was slightly better, and both sit close to the noise floor.

Possible professor questions
Q: Why didn't XGBoost win?
A: Zone-week demand is mostly zeros and ones around a stable level, so there's little nonlinear structure to learn. After the break, the problem is a level shift that no model trained on pre-break data can learn.
Q: Why select on zone totals, not zone-week error?
A: Zone-week absolute error rewards under-forecasting when most weeks are zero. The CFLP needs unbiased weekly rates.

Source: data/outputs/unit_demand_predictions.csv, selected_forecast_model.csv, forecast_evaluation.csv; reports/phase3_forecasting_report.md.`);

  // ================= Section: Warehouse location
  pres.addSection({ title: "Warehouse location" });
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Warehouse location" });
  s.addText("CFLP: MATHEMATICAL FORMULATION", { placeholder: "kicker" });
  s.addText("Capacitated Facility Location Problem (single sourcing)", { placeholder: "title" });
  card(s, 0.6, 1.6, 3.7, 4.25, HEX.card, "Symbols card");
  T(s, [{ text: "Symbols", options: { bold: true, color: HEX.teal, breakLine: true } },
    ...eq("i ∈ I: demand zones; j ∈ J: candidate sites", { size: 13, breakLine: true }),
    ...eq("Y_{j} = 1 if site j opens", { size: 13, breakLine: true }),
    ...eq("X_{ij} = 1 if zone i is served by j", { size: 13, breakLine: true }),
    ...eq("o_{i}: forecast orders / week", { size: 13, breakLine: true }),
    ...eq("u_{i}: forecast units / week", { size: 13, breakLine: true }),
    ...eq("d_{ij}: approx. road km (1.2 × great-circle)", { size: 13, breakLine: true }),
    ...eq("F_{j}: fixed cost $1,500/wk (PR $1,200)", { size: 13, breakLine: true }),
    ...eq("Q_{j}: capacity 80 units/wk (PR 100)", { size: 13, breakLine: true }),
    ...eq("c: $0.10 per order-km", { size: 13 })],
    { x: 0.8, y: 1.75, w: 3.4, h: 4.0, paraSpaceAfter: 5 });
  T(s, [...eq("min  Z = Σ_{j} F_{j} Y_{j} + Σ_{i} Σ_{j} c · d_{ij} · o_{i} · X_{ij}", { size: 24 })], { x: 4.6, y: 1.65, w: 8.1, h: 0.6, align: "left" });
  T(s, "opening cost  +  demand-weighted transport cost (orders drive delivery cost)", { x: 4.6, y: 2.22, w: 8.1, h: 0.3, fontSize: 12, italic: true, color: HEX.muted });
  const cons = [["Σ_{j} X_{ij} = 1   ∀ i", "every zone is served by exactly one warehouse"],
    ["Σ_{i} u_{i} X_{ij} ≤ Q_{j} Y_{j}   ∀ j", "assigned units fit the capacity; closed sites have none"],
    ["X_{ij} ≤ Y_{j}   ∀ i, j", "only open warehouses serve (tightens the LP relaxation)"],
    ["p_{min} ≤ Σ_{j} Y_{j} ≤ p_{max}", "warehouse count between 1 and 12 (PR: 1–4)"],
    ["X_{ij}, Y_{j} ∈ {0, 1}", "binary decisions: open or not, serve or not"]];
  cons.forEach(([e, txt], i) => {
    const y = 2.72 + i * 0.6;
    T(s, eq(e, { size: 18 }), { x: 4.6, y, w: 4.0, h: 0.5, valign: "middle" });
    T(s, txt, { x: 8.7, y, w: 4.05, h: 0.5, fontSize: 13, color: HEX.graph, valign: "middle" });
  });
  card(s, 4.6, 5.78 - 0.02, 8.13, 0.0, HEX.line, "Separator");
  takeaway(s, "Orders set the transport cost; units use the capacity. Mixing them would be wrong, because before the break one order was about 6.5 units.", 6.0);
  s.addNotes(`This is the model that chooses the warehouses.

There are two kinds of yes-or-no decision. Y j is whether we open candidate site j. X i j is whether zone i is served by warehouse j.

The objective has two parts. The first sum is the fixed weekly cost of the warehouses we open. The second is transport: cost per order-kilometre, times distance, times forecast orders. The solver looks for the cheapest combination that respects all the rules on the right.

The rules in plain English: every zone gets exactly one warehouse. A warehouse can't take more units than its capacity, and a closed one takes none. The middle constraint looks redundant, but it makes the solver much faster. Then the warehouse count stays within limits.

A uniform handling cost of 50 cents per unit is added only for reporting. It doesn't change the optimum, and that's why you'll see $18,348 for the objective and $18,497 for total cost: same solution.

Possible professor questions
Q: What is a binary decision variable?
A: A variable that can only be 0 or 1, here meaning open or closed, assigned or not.
Q: What if capacity is exceeded?
A: The model forbids it. In experiments I allow penalised unserved demand, at $10,000 per unit, so infeasibility is reported explicitly instead of the solver just failing.

Source: src/warehouse_cflp.py (solve_cflp), config.yaml optimization.networks.`);

  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Warehouse location" });
  s.addText("CFLP IMPLEMENTATION AND SOLVER", { placeholder: "kicker" });
  s.addText("Pyomo + CBC proves the CONUS optimum in under a second", { placeholder: "title" });
  s.addImage({ ...(await fit(path.join(FIG, "alloc_conus.png"), 5.2, 1.5, 7.6, 4.4)), altText: "CFLP allocation map, CONUS" });
  const steps = [["pin", "Candidate sites", "37 = demand-weighted k-means coverage sites (27) + top-demand zones (7) + both (3)"],
    ["calc", "MILP in Pyomo", "11,893 variables (11,581 binary) · 11,895 constraints (CONUS)"],
    ["gauge", "CBC branch-and-cut", "Status optimal · gap 0 · 0.96 s (PR 0.07 s)"],
    ["check", "Independent check", "Costs recomputed from the allocation, outside the solver"]];
  steps.forEach(([ic, h, b], i) => {
    const y = 1.62 + i * 0.98;
    iconDot(s, ic, 0.6, y, 0.5);
    T(s, h, { x: 1.28, y: y - 0.02, w: 3.7, h: 0.32, fontSize: 15, bold: true });
    T(s, b, { x: 1.28, y: y + 0.3, w: 3.7, h: 0.6, fontSize: 12, color: HEX.muted });
  });
  card(s, 0.6, 5.55, 4.4, 0.0, HEX.line, "Spacer");
  takeaway(s, "\"Proven optimal\" = CBC's lower bound equals the solution cost (gap 0). No other configuration of these 37 sites is cheaper under these costs.", 6.0);
  T(s, "Squares = opened warehouses (% = capacity used) · open circles = unused candidates · lines = zone allocation", { x: 5.3, y: 5.75, w: 7.4, h: 0.25, fontSize: 10, color: HEX.muted, italic: true });
  s.addNotes(`So how was it actually solved?

First, candidate sites. Picking only the biggest-demand zones would bunch all the candidates in New York and LA. So I combined demand-weighted k-means coverage sites with the top-demand zones, which gives 37 candidates. They're only options; the model decides which ones open.

The model is written in Pyomo and solved with CBC, an open-source mixed-integer solver. CBC uses branch-and-cut. It solves relaxed versions of the problem to get a lower bound, and branches on variables to find feasible solutions. When the best feasible cost equals the bound, the solution is proven optimal. For the mainland that took under a second, with a gap of zero.

I also recompute every cost from the final allocation outside the solver, as an independent check.

Possible professor questions
Q: Why not just use K-Means to place warehouses?
A: K-Means only minimises geographic distance. It ignores fixed costs, capacity and the number of warehouses. You'll see it's 0.85% worse on the mainland and 28% worse in Puerto Rico.
Q: How does CBC prove optimality?
A: It keeps a lower bound from LP relaxations and cuts. Once the best solution found meets that bound, nothing cheaper can exist.

Source: data/outputs/cflp_solver_report.csv, candidate_warehouses.csv, selected_allocation.csv.`);

  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Warehouse location" });
  s.addText("GENETIC ALGORITHM: HOW IT WORKS", { placeholder: "kicker" });
  s.addText("A GA searches the same 2³⁷ configuration space", { placeholder: "title" });
  // chromosome illustration (first 12 of 37 genes)
  const genesA = [1, 0, 1, 0, 1, 0, 0, 0, 0, 0, 0, 0], genesB = [0, 0, 1, 1, 0, 0, 1, 0, 0, 1, 0, 0];
  const drawGenes = (gs, y, label, colA, cut = null) => {
    T(s, label, { x: 0.6, y: y + 0.05, w: 1.35, h: 0.32, fontSize: 12, bold: true });
    gs.forEach((g, k) => {
      const inCut = cut && k >= cut[0] && k < cut[1];
      const fill = g ? (inCut ? HEX.coral : colA) : "FFFFFF";
      s.addShape(pres.shapes.RECTANGLE, { x: 1.95 + k * 0.33, y, w: 0.3, h: 0.38, fill: { color: fill }, line: { color: HEX.line, width: 0.75 }, objectName: `gene ${label} ${k}` });
      T(s, String(g), { x: 1.95 + k * 0.33, y, w: 0.3, h: 0.38, fontSize: 11, align: "center", valign: "middle", color: g ? "FFFFFF" : HEX.muted });
    });
  };
  drawGenes(genesA, 1.65, "Parent A", HEX.teal, [4, 8]);
  drawGenes(genesB, 2.13, "Parent B", HEX.slate, [4, 8]);
  const child = genesA.slice(0, 4).concat(genesB.slice(4, 8), genesA.slice(8)); child[10] = 1;
  drawGenes(child, 2.75, "Child", HEX.teal, [4, 8]);
  T(s, "two-point crossover swaps genes 5–8 · bit-flip mutation on gene 11 · repair keeps 4–12 sites open · first 12 of 37 genes shown",
    { x: 1.95, y: 3.18, w: 4.6, h: 0.5, fontSize: 10, italic: true, color: HEX.muted });
  T(s, [{ text: "Fitness (minimise), same data and costs as the CFLP", options: { bold: true, breakLine: true, color: HEX.teal } },
    ...eq("f(y) = Σ_{j} F_{j} y_{j} + transport(A(y)) + M · unserved(y)", { size: 15, breakLine: true }),
    { text: "A(y): capacity-feasible regret allocation (never overloads a site). The best chromosome is re-allocated exactly with CBC.", options: { fontSize: 12, color: HEX.muted } }],
    { x: 0.6, y: 3.75, w: 6.0, h: 1.3 });
  T(s, "Population 60 · ≤ 80 generations · tournament k = 3 · crossover 0.8 · mutation 0.3 (1/37 per gene) · elitism 2 · stop after 25 stale gens · seeds 11–55",
    { x: 0.6, y: 5.1, w: 6.0, h: 0.6, fontSize: 12 });
  s.addImage({ ...(await fit(path.join(FIG, "ga_convergence_conus.png"), 6.85, 1.5, 5.9, 3.7)), altText: "GA convergence, CONUS" });
  T(s, "Best seed: +0.58% · 5-seed mean: +1.71% above the optimum · 1 of 5 seeds within 1%", { x: 6.95, y: 5.25, w: 5.8, h: 0.45, fontSize: 12, bold: true, color: HEX.coral });
  takeaway(s, "Convergence shows the search stopped improving, not that it is optimal. Only the exact CFLP can certify optimality.", 6.0);
  s.addNotes(`The genetic algorithm attacks the same problem a different way.

Each solution is a chromosome: 37 bits, one per candidate site, where 1 means "open". The fitness is opening cost plus transport plus a big penalty for any unserved demand. The data and costs are the same as the CFLP.

To score a chromosome, zones are allocated with a regret heuristic that never overloads a warehouse. If a zone fits nowhere, it counts as unserved and gets penalised.

Each generation picks parents by tournament. Two-point crossover swaps a block of genes, like genes five to eight here, and mutation occasionally flips a bit. A repair step keeps the number of open sites sensible, and the two best solutions always survive. I ran five seeds.

On the right is convergence for the mainland. The best seed got within 0.58% of the proven optimum, but the average seed was 1.7% above, and the curves plateau without proving anything.

Possible professor questions
Q: Why use a GA if the CFLP is exact?
A: As a benchmark. On larger or nonlinear versions the MILP may become intractable, and a GA still works. Here I could measure exactly how far off it is.
Q: Why can a GA be worse?
A: It samples the search space stochastically and has no bound, so it can converge to a local optimum.

Source: src/genetic_algorithm.py; data/outputs/genetic_algorithm_results.csv, ga_convergence.csv; config.yaml genetic_algorithm.`);

  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Warehouse location" });
  s.addText("WAREHOUSE OPTIMIZATION RESULTS", { placeholder: "kicker" });
  s.addText("Exact CFLP is the benchmark: no method beat it", { placeholder: "title" });
  const meth = ["CFLP (exact)", "GA (best of 5)", "K-Means", "Random (mean of 30)"];
  s.addChart(pres.charts.BAR, [{ name: "CONUS", labels: meth, values: [18497.26, 18604.64, 18655.35, 30117.8] }], {
    x: 0.45, y: 1.5, w: 6.2, h: 3.3, barDir: "bar", chartColors: [HEX.teal, HEX.slate, HEX.ochre, HEX.coral], showValue: true, dataLabelPosition: "outEnd",
    dataLabelFormatCode: "$#,##0", showTitle: true, title: "Contiguous US, total cost (simulated USD / week)", showLegend: false, valAxisMinVal: 0, valAxisMaxVal: 35000,
    valAxisLabelFormatCode: "$#,##0", catAxisOrientation: "maxMin", ...chartText, objectName: "CONUS method chart" });
  s.addChart(pres.charts.BAR, [{ name: "Puerto Rico", labels: meth, values: [2509.51, 2509.51, 3206.39, 3394.69] }], {
    x: 6.75, y: 1.5, w: 6.0, h: 3.3, barDir: "bar", chartColors: [HEX.teal, HEX.slate, HEX.ochre, HEX.coral], showValue: true, dataLabelPosition: "outEnd",
    dataLabelFormatCode: "$#,##0", showTitle: true, title: "Puerto Rico, total cost (simulated USD / week)", showLegend: false, valAxisMinVal: 0, valAxisMaxVal: 4000,
    valAxisLabelFormatCode: "$#,##0", catAxisOrientation: "maxMin", ...chartText, objectName: "PR method chart" });
  const res = [["vs CFLP", "GA", "K-Means", "Random"], ["CONUS gap", "+0.58%", "+0.85%", "+62.8%"], ["Puerto Rico gap", "0.00%", "+27.8%", "+35.3%"], ["CONUS runtime", "72 s (5 runs)", "0.5 s", "25 s (30 draws)"]];
  s.addTable(res.map((r, i) => r.map((c, k) => ({ text: c, options: { bold: i === 0 || k === 0, color: i === 0 ? "FFFFFF" : HEX.graph, fill: { color: i === 0 ? HEX.graph : HEX.card } } }))),
    { x: 0.6, y: 4.88, w: 7.6, colW: [1.9, 1.9, 1.9, 1.9], fontSize: 11, fontFace: "Calibri", border: { type: "solid", color: HEX.line, pt: 0.5 }, rowH: 0.3, objectName: "Gap table" });
  T(s, "Same number of warehouses (6 / 2), same 37 / 25 candidates, same costs. All configurations feasible. CFLP runtime 0.8 s.", { x: 8.45, y: 4.9, w: 4.3, h: 0.9, fontSize: 12, color: HEX.muted });
  takeaway(s, "Placing warehouses with optimisation saves 38.6% versus random sites on the mainland. Geography-only K-Means is close in CONUS but 27.8% worse in Puerto Rico.", 6.2);
  s.addNotes(`Here are the four approaches side by side, all on exactly the same inputs.

On the mainland the exact CFLP costs $18,497 a week. The genetic algorithm's best run is 0.58% more, and K-Means is 0.85% more. Random warehouse locations are the real warning: 62.8% more expensive, or put the other way, the optimised plan saves 38.6%.

Puerto Rico is interesting. The GA found the exact optimum, since the search space is small. K-Means is 28% worse, because it places sites in the geographic middle of the zones. But two zones hold almost all the demand and have to sit next to a warehouse.

These are simulated costs from my assumptions. What's valid is the comparison, because every method shares the same assumptions.

Possible professor questions
Q: Are these actual warehouse costs?
A: No. They're documented assumptions in config.yaml. The dataset has no cost data, so absolute dollars are illustrative and relative differences are the result.
Q: Why compare with the same number of warehouses?
A: To isolate where the sites go, rather than how many open.

Source: data/outputs/warehouse_algorithm_comparison.csv, experiment_warehouse_comparison.csv.`);

  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Warehouse location" });
  s.addText("SELECTED WAREHOUSES AND CAPACITY UTILIZATION", { placeholder: "kicker" });
  s.addText("Six mainland sites, two in Puerto Rico, all within capacity", { placeholder: "title" });
  s.addChart(pres.charts.BAR, [{ name: "Utilisation", labels: ["Brooklyn, NY", "Long Beach, CA", "Chicago, IL", "Dallas, TX", "Livermore, CA", "Hialeah, FL", "Caguas, PR (03)", "Caguas, PR (05)"],
    values: [91.1, 85.6, 69.4, 50.6, 44.0, 31.5, 94.2, 81.2] }], {
    x: 0.45, y: 1.55, w: 5.6, h: 4.35, barDir: "bar", chartColors: [HEX.teal, HEX.teal, HEX.teal, HEX.teal, HEX.teal, HEX.teal, HEX.coral, HEX.coral],
    showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: "0.0\"%\"", showTitle: true, title: "Capacity used (% of 80 / 100 units per week)", showLegend: false,
    valAxisMinVal: 0, valAxisMaxVal: 100, catAxisOrientation: "maxMin", ...chartText, objectName: "Utilisation chart" });
  s.addImage({ ...(await fit(path.join(FIG, "alloc_pr.png"), 6.4, 1.6, 6.3, 2.5)), altText: "Puerto Rico allocation" });
  T(s, [{ text: "Why these sites", options: { bold: true, color: HEX.teal, breakLine: true } },
    { text: "Each extra warehouse costs $1,500/week and saves transport. The optimum stops at 6, where the next site saves less than it costs (forcing 5 or 7 costs more).", options: { bullet: true, breakLine: true } },
    { text: "Brooklyn and Long Beach run near capacity, so nearby demand overflows to Chicago and Livermore.", options: { bullet: true, breakLine: true } },
    { text: "Puerto Rico needs 2 sites only because of capacity: transport there is just $22/week.", options: { bullet: true } }],
    { x: 6.45, y: 4.15, w: 6.3, h: 1.85, fontSize: 13, paraSpaceAfter: 4 });
  takeaway(s, "These are optimised candidate locations under simulated costs. They are not existing company warehouses.", 6.15);
  s.addNotes(`Here are the chosen sites and how full they are.

On the mainland: Brooklyn at 91.1% of capacity, Long Beach 85.6%, Chicago 69.4%, Dallas 50.6%, Livermore 44.0% and Hialeah near Miami 31.5%. In Puerto Rico, two sites near Caguas at 94.2% and 81.2%.

Why six? Each warehouse costs $1,500 a week, and every extra one cuts transport cost. Six is where adding one more saves less than it costs. I confirmed it in the sensitivity runs: forcing five or seven warehouses is more expensive.

Capacity shapes the map too. Brooklyn and Long Beach are almost full, which is why some East Coast demand goes to Chicago, and some California demand to Livermore.

In Puerto Rico transport costs just $22 a week, so a single warehouse would be ideal. But demand exceeds one site's capacity, so it has to be two.

Possible professor questions
Q: Why does Hialeah run at only 31.5%?
A: It exists to cut long transport to Florida. Serving Florida from Dallas or Brooklyn would cost more than its fixed cost.
Q: Are these real warehouses?
A: No, they're demand-zone locations chosen by the model under simulated costs.

Source: data/outputs/optimal_warehouse_locations.csv, sensitivity_analysis.csv (fixed_warehouse_count).`);

  // ================= Section: Routing
  pres.addSection({ title: "Vehicle routing" });
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Vehicle routing" });
  s.addText("CVRP: VEHICLE ROUTING MODEL", { placeholder: "kicker" });
  s.addText("Each warehouse becomes a depot with its own fleet", { placeholder: "title" });
  s.addImage({ ...(await fit(path.join(FIG, "depot_example.png"), 0.45, 1.5, 4.6, 4.0)), altText: "Real example: Hialeah depot, 2 vehicles" });
  T(s, [{ text: "Real example, Hialeah depot (GLS): ", options: { bold: true } }, { text: "vehicle 1 (teal) 13 packages · vehicle 2 (coral) 10 packages" }],
    { x: 0.6, y: 5.55, w: 4.4, h: 0.5, fontSize: 11, color: HEX.muted });
  T(s, [...eq("min  Σ_{k} Σ_{i} Σ_{j} d_{ij} x_{ijk}", { size: 22 })], { x: 5.3, y: 1.6, w: 7.4, h: 0.55 });
  T(s, eq("minimise total route distance;  x_{ijk} = 1 if vehicle k drives directly from stop i to stop j", { size: 13, color: HEX.muted }), { x: 5.3, y: 2.12, w: 7.4, h: 0.35 });
  const vr = [["each stop visited exactly once", "or dropped at a large penalty and reported as unserved"],
    ["start and end at the depot", "a vehicle returns to its own warehouse"],
    ["load ≤ 30 packages per vehicle", "1 package = 1 forecast order (no weights in the data)"],
    ["route ≤ 3,000 km (PR 400 km)", "at most 8 vehicles per depot"]];
  vr.forEach(([h, b], i) => {
    const y = 2.6 + i * 0.66;
    s.addShape(pres.shapes.OVAL, { x: 5.32, y: y + 0.1, w: 0.17, h: 0.17, fill: { color: HEX.teal }, line: { color: HEX.teal }, objectName: "node" });
    T(s, [{ text: h, options: { bold: true, breakLine: true } }, { text: b, options: { fontSize: 12, color: HEX.muted } }], { x: 5.65, y, w: 7.0, h: 0.62, fontSize: 14 });
  });
  card(s, 5.3, 5.3, 7.43, 0.62, HEX.coralTint, "Capacity distinction");
  T(s, [{ text: "Two different capacities: ", options: { bold: true } }, { text: "warehouse 80 units/week (CFLP) vs vehicle 30 packages/route (CVRP)." }],
    { x: 5.5, y: 5.3, w: 7.1, h: 0.62, fontSize: 13, valign: "middle" });
  takeaway(s, "One week of consolidated deliveries per depot. Stops are the zones allocated by the CFLP, so no route can cross networks.", 6.15);
  s.addNotes(`Once the warehouses are fixed, each one becomes a depot, and I solve a capacitated vehicle routing problem for it.

The objective is simple: minimise total kilometres driven. x i j k is one if vehicle k drives directly from stop i to stop j.

The rules: every stop gets visited once. Each vehicle starts and ends at its own depot. A van carries at most 30 packages. A route can't exceed 3,000 km, and there are at most 8 vans per depot.

Two modelling choices to be upfront about. The data has no package weights, so one order equals one package. And I plan one consolidated week of deliveries, where each zone centre is a drop point. The picture is a real example: the Hialeah depot with its two vans.

Don't mix up the two capacities: the warehouse handles 80 units a week, while a van carries 30 packages per route.

Possible professor questions
Q: What's the difference between CVRP and TSP?
A: TSP is one vehicle visiting every city once. CVRP adds capacity, so you need several vehicles and must also decide which stops go on which vehicle.
Q: Why must vehicles return to the depot?
A: To reload for the next run. Mathematically it makes each route a closed tour.

Source: src/vehicle_routing.py; config.yaml routing.`);

  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Vehicle routing" });
  s.addText("GUIDED LOCAL SEARCH", { placeholder: "kicker" });
  s.addText("Penalising long arcs lets the search escape local minima", { placeholder: "title" });
  s.addImage({ ...(await fit(path.join(FIG, "nn_vs_gls_dallas.png"), 0.45, 1.5, 7.9, 3.55)), altText: "Dallas depot: Nearest Neighbor vs GLS routes" });
  T(s, "Real Dallas depot (WH-US-14). Left: greedy routes break the 3,000 km limit. Right: GLS splits the work into 4 feasible routes, 2.2% shorter in total.",
    { x: 0.6, y: 5.1, w: 7.7, h: 0.6, fontSize: 12, color: HEX.muted });
  const gls = [["1", "Start", "PATH_CHEAPEST_ARC: extend routes with the cheapest feasible arc"],
    ["2", "Improve", "Local moves (relocate, exchange, 2-opt, Or-opt, cross) while cost falls"],
    ["3", "Stuck?", "At a local minimum, penalise the arcs with highest  cₐ / (1 + pₐ)"],
    ["4", "Continue", "Search on  g(s) = cost(s) + λ Σ pₐ Iₐ(s), so long arcs look expensive"],
    ["5", "Stop", "10 s time limit per depot; return the best true-cost solution"]];
  gls.forEach(([n, h, b], i) => {
    const y = 1.6 + i * 0.85;
    s.addShape(pres.shapes.OVAL, { x: 8.6, y, w: 0.42, h: 0.42, fill: { color: i === 2 ? HEX.coral : HEX.teal }, line: { color: i === 2 ? HEX.coral : HEX.teal }, objectName: `GLS step ${n}` });
    T(s, n, { x: 8.6, y, w: 0.42, h: 0.42, fontSize: 13, bold: true, color: "FFFFFF", align: "center", valign: "middle" });
    T(s, [{ text: h, options: { bold: true, breakLine: true } }, { text: b, options: { fontSize: 12, color: HEX.muted } }], { x: 9.15, y: y - 0.04, w: 3.6, h: 0.8, fontSize: 14 });
  });
  takeaway(s, "Compared against Nearest Neighbor (no improvement) and OR-Tools greedy descent (stops at the first local minimum).", 6.1);
  s.addNotes(`Guided Local Search is how OR-Tools improves the routes.

It starts with a quick initial solution, adding the cheapest arc it can. Then local search keeps making small moves: shift a stop to another van, swap two stops, reverse a piece of a route. It keeps doing that while the distance goes down.

The problem is that eventually no small move helps. That's a local minimum, and plain greedy descent, my "standard" baseline, stops there. GLS doesn't stop. It adds a penalty to the arcs that are long and keep appearing, using the utility formula in step 3. The search then works on cost plus penalties, so those arcs suddenly look expensive, and it's pushed into routes it would never have tried.

The Dallas example is real data. Nearest Neighbor builds two huge routes that break the 3,000 km limit. GLS builds four valid routes.

Possible professor questions
Q: How exactly does GLS escape local minima?
A: By changing the landscape. Penalties make the current minimum's frequent long arcs costlier, so neighbouring solutions become relatively better and the search moves on. The true cost is still used to pick the final answer.
Q: Why compare with Nearest Neighbor?
A: It's the classic constructive baseline. It shows what you get without any optimisation.

Source: src/vehicle_routing.py (ortools_solve), data/outputs/all_method_route_stops.csv, route_distance_report.csv.`);

  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Vehicle routing" });
  s.addText("VEHICLE ROUTING RESULTS", { placeholder: "kicker" });
  s.addText("16 vehicles, 31,610 km a week, every constraint met", { placeholder: "title" });
  s.addImage({ ...(await fit(path.join(FIG, "gls_routes_conus.png"), 0.45, 1.5, 6.9, 3.9)), altText: "GLS routes CONUS" });
  T(s, "GLS routes per depot (approximate road km; drawn as straight segments)", { x: 0.6, y: 5.4, w: 6.7, h: 0.3, fontSize: 10, italic: true, color: HEX.muted });
  const rr2 = [["CONUS, per week", "Vehicles", "km", "Hours", "Feasible"],
    ["Guided Local Search", "16", "31,610", "510", "Yes"], ["OR-Tools standard", "16", "31,647", "510", "Yes"], ["Nearest Neighbor", "13", "38,635", "618", "No: 5 routes > 3,000 km"]];
  s.addTable(rr2.map((r, i) => r.map((c, k) => ({ text: c, options: { bold: i === 0 || k === 0, color: i === 0 ? "FFFFFF" : (i === 3 && k === 4 ? HEX.coral : HEX.graph), fill: { color: i === 0 ? HEX.graph : HEX.card } } }))),
    { x: 7.55, y: 1.6, w: 5.18, colW: [1.6, 0.8, 0.8, 0.68, 1.3], fontSize: 11, fontFace: "Calibri", border: { type: "solid", color: HEX.line, pt: 0.5 }, rowH: 0.42, objectName: "Routing table" });
  card(s, 7.55, 3.5, 2.5, 1.85, HEX.tealTint, "Fair comparison card");
  T(s, [{ text: "−0.12%", options: { fontSize: 30, bold: true, color: HEX.teal, breakLine: true } }, { text: "GLS vs standard OR-Tools. Both feasible: the fair, like-for-like gain." }],
    { x: 7.7, y: 3.6, w: 2.25, h: 1.7, fontSize: 12 });
  card(s, 10.23, 3.5, 2.5, 1.85, HEX.coralTint, "Unfair comparison card");
  T(s, [{ text: "−18.2%", options: { fontSize: 30, bold: true, color: HEX.coral, breakLine: true } }, { text: "vs Nearest Neighbor, which is infeasible, so this isn't like-for-like." }],
    { x: 10.38, y: 3.6, w: 2.25, h: 1.7, fontSize: 12 });
  T(s, "Puerto Rico: all three methods give the same 7 vehicles and 174 km (most volume sits at the depots' own zones).", { x: 7.55, y: 5.45, w: 5.18, h: 0.5, fontSize: 12, color: HEX.muted });
  takeaway(s, "GLS gains little here: few stops per depot and a binding route-length limit leave little room. That's what we measured, not a shortcoming we hid.", 6.1);
  s.addNotes(`Here's the routing outcome on the mainland.

GLS uses 16 vehicles and 31,610 km a week. Standard OR-Tools gets 31,647, so GLS is only 0.12% shorter. That's the fair comparison, because both solutions satisfy every constraint.

Nearest Neighbor looks like it uses fewer vans, 13. But five of its routes are longer than the 3,000 km limit, so it's not a valid plan. The 18% distance difference against it is real, but I wouldn't call it a like-for-like improvement.

Why is the GLS gain so small? Each depot has only 12 to 36 stops, and the route-length limit already forces fairly direct out-and-back routes. Greedy descent gets very close to the best answer. Even so, small percentages compound: 0.12% of a weekly routing bill, every week, every year.

Puerto Rico is trivial: all three methods give identical routes.

Possible professor questions
Q: Why was the GLS improvement only 0.12%?
A: Small instances per depot with a binding length limit; the standard search was already near-optimal. With more stops or time windows, the gap usually grows.
Q: Are these actual road routes?
A: No. Distances are great-circle times 1.2, and the lines are straight segments between stops.

Source: data/outputs/route_comparison.csv, experiment_routing_comparison.csv, route_feasibility_report.csv.`);

  // ================= Section: Experiments
  pres.addSection({ title: "Experiments" });
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Experiments" });
  s.addText("FORECAST-DRIVEN OPTIMIZATION EXPERIMENT", { placeholder: "kicker" });
  s.addText("Forecasting helped on the mainland and hurt in Puerto Rico", { placeholder: "title" });
  const plans = ["Historical-avg plan", "Forecast plan", "Perfect-info benchmark"];
  s.addChart(pres.charts.BAR, [{ name: "Opening", labels: plans, values: [18000, 9000, 9000] }, { name: "Transport", labels: plans, values: [8237.95, 9455.27, 9380.5] }], {
    x: 0.45, y: 1.55, w: 4.3, h: 3.9, barDir: "col", barGrouping: "stacked", chartColors: [HEX.slate, HEX.teal], showValue: true, dataLabelPosition: "ctr",
    dataLabelFormatCode: "$#,##0", dataLabelColor: "FFFFFF", showTitle: true, title: "CONUS realised cost (USD / week)", showLegend: true, legendPos: "b", valAxisLabelFormatCode: "$#,##0",
    ...chartText, catAxisLabelFontSize: 10, objectName: "CONUS forecast impact" });
  s.addChart(pres.charts.BAR, [{ name: "Opening", labels: plans, values: [2400, 3600, 2400] }, { name: "Transport", labels: plans, values: [556.99, 14.89, 19.34] }], {
    x: 4.85, y: 1.55, w: 4.3, h: 3.9, barDir: "col", barGrouping: "stacked", chartColors: [HEX.slate, HEX.coral], showValue: false,
    showTitle: true, title: "Puerto Rico realised cost (USD / week)", showLegend: true, legendPos: "b", valAxisLabelFormatCode: "$#,##0",
    ...chartText, catAxisLabelFontSize: 10, objectName: "PR forecast impact" });
  T(s, [{ text: "Setup", options: { bold: true, color: HEX.teal, breakLine: true } },
    { text: "Both planners stand at 28 Oct 2017 with the same information", options: { bullet: true, breakLine: true } },
    { text: "Each plan is scored on the 13 real weeks that followed", options: { bullet: true, breakLine: true } },
    { text: "Zones re-allocated optimally to each plan's warehouses", options: { bullet: true, breakLine: true } },
    { text: "Benchmark = plan built on realised demand (not deployable)", options: { bullet: true } }],
    { x: 9.35, y: 1.6, w: 3.4, h: 2.2, fontSize: 12, paraSpaceAfter: 3 });
  card(s, 9.35, 3.85, 3.4, 0.82, HEX.tealTint, "CONUS result");
  T(s, [{ text: "CONUS: −29.5% ", options: { bold: true, color: HEX.teal } }, { text: "vs historical plan; only 0.4% above the benchmark" }], { x: 9.5, y: 3.88, w: 3.15, h: 0.76, fontSize: 12, valign: "middle" });
  card(s, 9.35, 4.75, 3.4, 1.0, HEX.coralTint, "PR result");
  T(s, [{ text: "Puerto Rico: +21.6% worse. ", options: { bold: true, color: HEX.coral } }, { text: "Units over-forecast by 20.4% (a transitional week at 1.96 units/order) → a 3rd warehouse" }],
    { x: 9.5, y: 4.78, w: 3.15, h: 0.95, fontSize: 12, valign: "middle" });
  T(s, "Historical CONUS plan hit the 120 s limit (incumbent, gap 0.57%); all other plans proven optimal.", { x: 0.6, y: 5.5, w: 8.5, h: 0.3, fontSize: 10, italic: true, color: HEX.muted });
  takeaway(s, "Forecasting pays off when it's unbiased. In Puerto Rico a biased unit forecast drove a capacity decision, so bias matters more than accuracy.", 6.0);
  s.addNotes(`This is the experiment I find most interesting: does forecasting actually lead to a better warehouse plan?

Two planners stand at the same date, 28 October 2017. One plans with plain historical averages, the other with my selected forecasts. Then we check both plans against what really happened over the next 13 weeks.

On the mainland the forecast plan wins clearly: 29.5% cheaper. The historical averages still contain the old 6.5-units-per-order world, so that planner opened 12 warehouses. The forecast plan is only 0.4% above the perfect-information benchmark. That benchmark is just a yardstick; nobody can actually plan with next quarter's real demand.

Puerto Rico went the other way, and I'm not hiding it. The units forecast was 20% too high. The cause is one transitional week at the start of October, still at 1.96 units per order, which was inside the calibration window. That pushed the plan to a third warehouse.

Possible professor questions
Q: Why did forecasting help CONUS but hurt Puerto Rico?
A: The CONUS forecast was nearly unbiased. Puerto Rico's was 20% high, and in a capacity-driven network that buys a whole extra warehouse, while transport there is almost free.
Q: What's a perfect-information benchmark?
A: The plan you'd make if you knew the future. It's the lower bound for regret, not a method.

Source: data/outputs/forecast_impact_comparison.csv; reports/final_project_report.md §16b.`);

  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Experiments" });
  s.addText("SENSITIVITY AND ROBUSTNESS", { placeholder: "kicker" });
  s.addText("The solution responds to costs the way theory predicts", { placeholder: "title" });
  s.addChart(pres.charts.LINE, [{ name: "Total cost", labels: ["4*", "5", "6", "7", "8", "10", "12"], values: [21859.63, 19531.54, 18497.26, 19047.52, 19682.55, 21439.31, 23355.08] }], {
    x: 0.45, y: 1.55, w: 4.2, h: 3.7, chartColors: [HEX.teal], lineSize: 2.5, lineDataSymbol: "circle", lineDataSymbolSize: 8, showValue: false,
    showTitle: true, title: "CONUS cost vs forced warehouse count", showLegend: false, valAxisLabelFormatCode: "$#,##0", valAxisMinVal: 17000, valAxisMaxVal: 24000,
    catAxisTitle: "warehouses opened (forced)", showCatAxisTitle: true, catAxisTitleFontSize: 11, catAxisTitleColor: "5F5A53", ...chartText, objectName: "Forced count chart" });
  T(s, "* p = 4: time-limited, incumbent with 5.8% gap. p = 2–3 infeasible (capacity).", { x: 0.6, y: 5.25, w: 4.1, h: 0.45, fontSize: 10, italic: true, color: HEX.muted });
  s.addChart(pres.charts.BAR, [{ name: "Fixed cost × base", labels: ["×0.25", "×0.5", "×1", "×2", "×4"], values: [12, 8, 6, 5, 4] },
    { name: "Cost per km × base", labels: ["×0.25", "×0.5", "×1", "×2", "×4"], values: [5, 5, 6, 8, 12] }], {
    x: 4.8, y: 1.55, w: 4.2, h: 3.7, barDir: "col", chartColors: [HEX.slate, HEX.teal], showValue: true, dataLabelPosition: "outEnd",
    showTitle: true, title: "Warehouses opened (CONUS)", showLegend: true, legendPos: "b", valAxisMinVal: 0, valAxisMaxVal: 14, ...chartText, objectName: "Cost multiplier chart" });
  T(s, "Time-limited points (gap): fixed ×4 (4.0%), km ×0.25 (10.3%).", { x: 4.9, y: 5.25, w: 4.1, h: 0.45, fontSize: 10, italic: true, color: HEX.muted });
  T(s, [{ text: "Robustness: demand ±10% / ±20%", options: { bold: true, color: HEX.teal, breakLine: true } },
    { text: "CONUS: feasible from −20% to +20% after re-allocating zones (max use 100%). Keeping the old allocation overloads by 9.7 units at +20%.", options: { bullet: true, breakLine: true } },
    { text: "Puerto Rico: infeasible from +10%. One zone (≈102 units) exceeds a single 100-unit warehouse, and single sourcing can't split it.", options: { bullet: true, breakLine: true } },
    { text: "Routing: bigger vans → fewer vehicles (15 → 60 packages: 24 → 15 vans). Under 4 vans per depot leaves stops unserved.", options: { bullet: true } }],
    { x: 9.2, y: 1.6, w: 3.55, h: 4.1, fontSize: 12, paraSpaceAfter: 5 });
  takeaway(s, "Cost is U-shaped in warehouse count, with its minimum at 6. 6 of 34 CONUS sensitivity solves hit the 120 s limit and are reported as incumbents with gaps.", 6.0);
  s.addNotes(`Next I stress-tested the solution.

Left chart: I forced the model to open a fixed number of warehouses. Cost is U-shaped and bottoms out at six, which is exactly what the free model chose. Two or three warehouses can't hold the demand at all.

Middle chart: the classic trade-off. Make warehouses cheaper and the model opens more, up to 12. Make transport cheaper and it opens fewer. Both directions are what facility-location theory predicts, which is a good sanity check on the model.

On the right, robustness. With demand up 20%, the mainland plan still works if we re-allocate some zones. Puerto Rico breaks at plus 10%, because one zone alone becomes bigger than a warehouse.

One honesty point: a few of these runs hit my two-minute limit. Those are labelled as incumbents with their gaps, not as optimal.

Possible professor questions
Q: What does a time-limited result mean?
A: CBC returns its best feasible solution plus a proven lower bound. For example at four warehouses the true optimum is at most 5.8% below what I report.
Q: How would you fix Puerto Rico's fragility?
A: Allow split sourcing for very large zones, or add a capacity buffer.

Source: data/outputs/sensitivity_analysis.csv, robustness_analysis.csv; reports/final_project_report.md §15, §16c.`);

  // ================= Section: Dashboard & conclusion
  pres.addSection({ title: "Dashboard and conclusion" });
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Dashboard and conclusion" });
  s.addText("INTERACTIVE STREAMLIT DASHBOARD", { placeholder: "kicker" });
  s.addText("A what-if page that re-solves the models live", { placeholder: "title" });
  s.addImage({ ...(await fit(path.join(FIG, "dash_whatif.png"), 0.45, 1.5, 6.6, 4.15)), altText: "Dashboard what-if page after a live Puerto Rico run" });
  s.addImage({ ...(await fit(path.join(FIG, "dash_warehouse.png"), 7.3, 1.5, 3.0, 1.95)), altText: "Dashboard warehouse page" });
  s.addImage({ ...(await fit(path.join(FIG, "dash_overview.png"), 10.0, 1.5, 3.0, 1.95)), altText: "Dashboard overview page" });
  T(s, [{ text: "8 pages", options: { bold: true, color: HEX.teal, breakLine: true } },
    { text: "Overview · Data analytics · Forecasting · Warehouse optimisation · Delivery routing · Algorithm performance · What-if · Reports & downloads", options: { breakLine: true } },
    { text: "What-if: ", options: { bold: true } }, { text: "change warehouse count, capacity, costs, fleet or demand growth. Each run re-solves the CFLP with CBC and re-routes with OR-Tools, then reports feasibility." }],
    { x: 7.3, y: 3.6, w: 5.45, h: 1.9, fontSize: 12, paraSpaceAfter: 4 });
  T(s, "streamlit run dashboard/app.py", { x: 7.3, y: 5.5, w: 5.4, h: 0.3, fontSize: 12, fontFace: "Courier New", color: HEX.graph });
  T(s, "Screenshots from the running app. Map tiles were blocked in the build environment, so maps show markers without a basemap.", { x: 0.6, y: 5.68, w: 6.5, h: 0.3, fontSize: 10, italic: true, color: HEX.muted });
  takeaway(s, "Shown: a live Puerto Rico run reproducing the baseline (2 warehouses, $2,510/week, 94.2% max use). Tested by 9 automated page tests.", 6.15);
  s.addNotes(`To make this usable, I built a Streamlit dashboard with eight pages, from data analytics through to downloadable reports.

The page I'd highlight is What-if, on the left. You can change things like warehouse capacity, opening cost, number of vans or demand growth, and press Run optimization. That isn't just a lookup: it actually re-solves the CFLP with CBC, re-allocates the zones and re-routes the vehicles with OR-Tools. Then it tells you whether the new setup is feasible.

In this screenshot I ran Puerto Rico with the default settings, and it reproduces the baseline exactly: two warehouses, $2,510 a week. That's a nice consistency check.

The maps have no background here only because my build environment couldn't download map tiles. On a normal machine they show OpenStreetMap.

Possible professor questions
Q: Does the what-if page recompute, or just display stored values?
A: It recomputes. It calls the same solve_cflp and routing functions as the pipeline, with results cached per parameter set. An automated test clicks the button and checks the output.
Q: How do you launch it?
A: From the project root: streamlit run dashboard/app.py.

Source: dashboard/app.py, tests/test_dashboard.py.`);

  s = pres.addSlide({ masterName: "CONTENT_DARK", sectionTitle: "Dashboard and conclusion" });
  s.addText("CONCLUSION, CONTRIBUTION AND LIMITATIONS", { placeholder: "kicker" });
  s.addText("What the results show, and what they don't", { placeholder: "title" });
  card(s, 0.6, 1.6, 6.0, 4.35, "2C3438", "Findings card");
  T(s, [{ text: "Contribution and findings", options: { bold: true, color: "6FC3B5", fontSize: 16, breakLine: true } },
    { text: "Integrated forecasting → CFLP → CVRP pipeline, one command, 69 passing tests", options: { bullet: true, breakLine: true } },
    { text: "Exact CFLP optimal in < 1 s; beat GA (+0.58%), K-Means (+0.85%) and random (+62.8%)", options: { bullet: true, breakLine: true } },
    { text: "GLS feasible routes: 0.12% shorter than standard search", options: { bullet: true, breakLine: true } },
    { text: "Forecast-aware planning: −29.5% CONUS, but +21.6% Puerto Rico due to bias", options: { bullet: true, breakLine: true } },
    { text: "Sensitivity behaves as theory predicts; Puerto Rico fragile above +10% demand", options: { bullet: true, breakLine: true } },
    { text: "Dashboard with live re-optimisation", options: { bullet: true } }],
    { x: 0.85, y: 1.75, w: 5.55, h: 4.1, fontSize: 15, color: "FFFFFF", paraSpaceAfter: 8 });
  card(s, 6.85, 1.6, 5.88, 4.35, "3A2A24", "Limitations card");
  T(s, [{ text: "Limitations", options: { bold: true, color: "F0A07E", fontSize: 16, breakLine: true } },
    { text: "Simulated costs, capacities and fleet: compare methods, don't read absolute $", options: { bullet: true, breakLine: true } },
    { text: "Customer coordinates are not verified delivery destinations", options: { bullet: true, breakLine: true } },
    { text: "Distances = great-circle × 1.2, not a live road network", options: { bullet: true, breakLine: true } },
    { text: "Structural break leaves only 17 post-break weeks", options: { bullet: true, breakLine: true } },
    { text: "Sequential, not joint, optimisation; some experiment solves time-limited", options: { bullet: true, breakLine: true } },
    { text: "For real deployment: actual costs and capacities, road-network times (e.g. OSRM), time windows, stochastic demand", options: { bullet: true } }],
    { x: 7.1, y: 1.75, w: 5.45, h: 4.1, fontSize: 15, color: "FFFFFF", paraSpaceAfter: 8 });
  takeaway(s, "Exact optimisation dominated at this scale, and forecasting helped only where it was unbiased. Both are measured, not assumed.", 6.2, true);
  s.addNotes(`To wrap up.

What I built is one reproducible pipeline: forecasting, then exact warehouse location, then vehicle routing. Every step is measured against baselines. The main results: the exact CFLP was proven optimal in under a second and nothing beat it. GLS produced valid routes, slightly shorter than standard search. And forecasting cut the mainland planning cost by almost 30%, but made Puerto Rico worse, because of a biased forecast.

The limitations matter just as much. The costs are simulated, the locations are customer coordinates rather than verified destinations, and distances are straight-line times 1.2, not roads. To use this for real, a company would plug in its actual costs and capacities, real road travel times, delivery time windows, and probably plan against several demand scenarios rather than one forecast.

Possible professor questions
Q: Could a real company use this?
A: The method, yes. The numbers, no. The code is configuration-driven, so real costs, capacities and road distances can be swapped in. The current outputs are a proof of method.
Q: What would you do next?
A: Real road distances, a stochastic CFLP over demand scenarios, joint location-routing, and bias-corrected unit forecasts.

Source: reports/final_project_report.md §16–§19.`);

  s = pres.addSlide({ masterName: "CLOSING_DARK", sectionTitle: "Dashboard and conclusion" });
  s.addText("Thank you", { placeholder: "title" });
  s.addText("Questions welcome", { placeholder: "body" });
  T(s, "Demand-Driven E-Commerce Warehouse Location and Multi-Vehicle Delivery Route Optimization Using Hybrid Optimization Algorithms",
    { x: 0.6, y: 4.5, w: 6.4, h: 0.85, fontSize: 14, color: "D8D1C4" });
  s.addImage({ data: ICON.git.white, x: 0.6, y: 5.6, w: 0.35, h: 0.35 });
  T(s, [{ text: "github.com/cmsoftx/Optimization", options: { hyperlink: { url: "https://github.com/cmsoftx/Optimization" }, color: "6FC3B5", breakLine: true } },
    { text: "branch claude/gifted-bohr-s602fx", options: { color: "A8A29A", fontSize: 12 } }], { x: 1.1, y: 5.55, w: 6, h: 0.7, fontSize: 15 });
  s.addNotes(`Thank you for listening. I'm happy to take any questions.

If it helps, everything I showed can be reproduced from the repository on this branch. The full pipeline is one command, and the dashboard runs locally with streamlit run dashboard/app.py.

Possible professor questions (quick recap)
Q: What's the single most important result?
A: The exact CFLP gave a provably optimal network, 38.6% cheaper than random sites. And forecasting improved the mainland plan by 29.5%, while also showing that forecast bias can backfire.
Q: What surprised you?
A: That XGBoost didn't win, and that the Puerto Rico demand literally moved about 35 km at the October 2017 break.`);

  await pres.writeFile({ fileName: OUTFILE });
  await applyTheme(OUTFILE, THEME);
  console.log("written", OUTFILE);
})();
