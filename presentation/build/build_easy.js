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
  pres.author = "C M Karthik";
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

  // ---- extra helpers for the easy deck
  const bullets = (items, o = {}) => items.map((t, i) => ({ text: t, options: { bullet: { indent: 18 }, breakLine: i < items.length - 1, ...o } }));
  const bigNum = (s, x, y, w, num, label, color = HEX.teal) => {
    T(s, num, { x, y, w, h: 0.62, fontSize: 32, bold: true, color });
    T(s, label, { x, y: y + 0.62, w, h: 0.5, fontSize: 13, color: HEX.muted });
  };
  const head = (s, kicker, title) => { s.addText(kicker, { placeholder: "kicker" }); s.addText(title, { placeholder: "title" }); };

  // 1 Title
  pres.addSection({ title: "Introduction" });
  let s = pres.addSlide({ masterName: "TITLE_DARK", sectionTitle: "Introduction" });
  s.addText("Demand-Driven E-Commerce Warehouse Location and Multi-Vehicle Delivery Route Optimization", { placeholder: "title" });
  s.addText("Using Hybrid Optimization Algorithms", { placeholder: "body" });
  T(s, [{ text: "C M Karthik", options: { bold: true, fontSize: 18, color: "FFFFFF", breakLine: true } },
    { text: "USN: SCA25MSD019 · M.Sc. Data Science", options: { breakLine: true } },
    { text: "Advanced Analytics and Optimisation (25MSD5303)", options: { breakLine: true } },
    { text: "Guide: Ms. Jithy Lijo · Dayananda Sagar University" }],
    { x: 0.6, y: 5.2, w: 6.6, h: 1.4, fontSize: 14, color: "D8D1C4", paraSpaceAfter: 2 });
  s.addNotes(`Good morning. My name is C M Karthik. My project is about helping an online store decide where to put its warehouses and how to deliver parcels to customers at the lowest cost.

I use real order data, predict future demand, and then use optimisation methods to choose warehouses and plan delivery routes.`);

  // 2 Problem
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Introduction" });
  head(s, "THE PROBLEM", "An online store must answer three questions");
  const q3 = [["chart", "1. How much will customers order?", "Demand changes by place and by time. We must predict it for the coming weeks."],
    ["wh", "2. Where should we open warehouses?", "Each warehouse costs rent and has a limited size. Far warehouses mean long, costly trips."],
    ["truck", "3. How should the vans deliver?", "Each van carries a limited number of parcels and can only drive a limited distance."]];
  q3.forEach(([ic, t, d], i) => {
    const x = 0.6 + i * 4.1;
    card(s, x, 1.75, 3.85, 3.9);
    iconDot(s, ic, x + 0.35, 2.05, 0.9);
    T(s, t, { x: x + 0.35, y: 3.15, w: 3.2, h: 0.9, fontSize: 19, bold: true });
    T(s, d, { x: x + 0.35, y: 4.1, w: 3.2, h: 1.4, fontSize: 15, color: HEX.muted });
  });
  takeaway(s, "Easy example: like a pizza chain: guess the orders, choose where to open kitchens, plan the bike routes, at the lowest total cost.");
  s.addNotes(`Every online store faces three simple questions.
First, how much will customers order next week, and where?
Second, where should we open warehouses? More warehouses means more rent, fewer warehouses means longer trips.
Third, how should our vans drive, so that no van is overloaded and no route is too long?

My project answers all three questions, one after the other.

An easy way to picture it: a pizza chain in a new city. It guesses how many pizzas each area will order, chooses where to open kitchens, and plans the delivery bike routes. Too many kitchens cost too much rent; too few make trips too long. I find the best balance.`);

  // 4 Objectives
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Introduction" });
  head(s, "OBJECTIVES", "What I set out to do");
  const ob = [["broom", "Clean the data", "and group customers into areas (zones)"], ["chart", "Predict demand", "for each zone, week by week"],
    ["wh", "Choose the best warehouses", "with an exact optimisation method"], ["dna", "Compare with a Genetic Algorithm", "and simple methods (K-Means, random)"],
    ["route", "Plan delivery routes", "for the vans from each warehouse"], ["flask", "Test the plan", "does forecasting help? what if costs change?"]];
  ob.forEach(([ic, a, b], i) => {
    const x = 0.6 + (i % 2) * 6.15, y = 1.7 + Math.floor(i / 2) * 1.45;
    card(s, x, y, 5.95, 1.25);
    iconDot(s, ic, x + 0.25, y + 0.3, 0.65);
    T(s, [{ text: a, options: { bold: true, fontSize: 18, breakLine: true } }, { text: b, options: { fontSize: 15, color: HEX.muted } }],
      { x: x + 1.1, y: y + 0.15, w: 4.7, h: 0.95, valign: "middle" });
  });
  s.addNotes(`I had six objectives.
One, clean the data and group nearby customers into zones.
Two, predict how much each zone will order every week.
Three, choose the best warehouses with an exact optimisation method.
Four, compare that with a Genetic Algorithm and with simple methods.
Five, plan delivery routes for the vans.
Six, test the plan: does forecasting really help, and what happens if costs or demand change?`);

  // Data + zones
  pres.addSection({ title: "Data" });
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Data" });
  head(s, "THE DATA", "Real order data, grouped into customer zones");
  const facts = [["180,519", "order lines, 2015 – 2018"], ["62,011", "clean orders used (from 65,752)"], ["312", "zones in the USA (max 50 km wide)"], ["25", "zones in Puerto Rico (max 10 km)"]];
  facts.forEach(([n, l], i) => { const x = 0.6 + (i % 2) * 2.7, y = 1.7 + Math.floor(i / 2) * 1.5; card(s, x, y, 2.5, 1.32); bigNum(s, x + 0.2, y + 0.1, 2.2, n, l); });
  T(s, [{ text: "What I did", options: { bold: true, color: HEX.teal, fontSize: 17, breakLine: true } },
    ...bullets(["Source: DataCo Smart Supply Chain dataset (Kaggle)", "Removed cancelled / fraud orders and wrong locations", "Removed personal details (names, streets)", "Grouped nearby customers into zones"])],
    { x: 0.6, y: 4.8, w: 5.3, h: 1.4, fontSize: 14, paraSpaceAfter: 2 });
  s.addImage({ ...(await fit(path.join(FIG, "zones_map.png"), 6.1, 1.6, 6.65, 4.45)), altText: "Map of demand zones" });
  takeaway(s, "Puerto Rico is an island with no road from the mainland, so it is planned as a separate network.", 6.28);
  s.addNotes(`I used a public dataset from Kaggle called DataCo Smart Supply Chain: 180,519 rows from 2015 to 2018.

I cleaned it: I removed cancelled and fraud orders, because they were never delivered, and orders with wrong locations. That leaves 62,011 orders. I also removed personal details like names and streets.

Thousands of addresses are too many to plan one by one, so I grouped nearby customers into zones: 312 in the USA and 25 in Puerto Rico. Each bubble on the map is a zone; bigger means more demand.

Puerto Rico is an island, so I plan it separately.`);

  // 7 Method
  pres.addSection({ title: "Method" });
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Method" });
  head(s, "MY APPROACH", "Three steps, one after the other");
  const st = [["chart", "Step 1", "Predict demand", "How much will each zone order per week?", "Random Forest, XGBoost, simple averages"],
    ["wh", "Step 2", "Choose warehouses", "Which places to open, and which zones each one serves?", "Exact optimiser (Pyomo + CBC) and Genetic Algorithm"],
    ["truck", "Step 3", "Plan routes", "Which van visits which zones, in which order?", "Google OR-Tools with Guided Local Search"]];
  st.forEach(([ic, a, b, c, d], i) => {
    const x = 0.6 + i * 4.2;
    card(s, x, 1.75, 3.75, 4.1);
    iconDot(s, ic, x + 0.3, 2.0, 0.85);
    T(s, a, { x: x + 1.35, y: 2.05, w: 2.2, h: 0.35, fontSize: 14, bold: true, color: HEX.coral });
    T(s, b, { x: x + 1.35, y: 2.38, w: 2.3, h: 0.5, fontSize: 21, bold: true });
    T(s, c, { x: x + 0.3, y: 3.15, w: 3.2, h: 1.2, fontSize: 16 });
    T(s, [{ text: "Tools: ", options: { bold: true, color: HEX.teal } }, { text: d }], { x: x + 0.3, y: 4.5, w: 3.2, h: 1.2, fontSize: 14, color: HEX.muted });
    if (i < 2) s.addShape(pres.shapes.RIGHT_ARROW, { x: x + 3.8, y: 3.55, w: 0.35, h: 0.45, fill: { color: HEX.teal }, line: { color: HEX.teal } });
  });
  takeaway(s, "\"Hybrid\" = machine learning + exact optimisation + smart search methods working together.");
  s.addNotes(`My method has three steps.
Step one: predict how much each zone will order each week.
Step two: use that prediction to choose which warehouses to open, and which zones each warehouse serves.
Step three: plan the delivery routes for the vans from each warehouse.

Each step gives its answer to the next step. That is why the title says "hybrid": I combine machine learning, an exact optimiser, and smart search methods like the Genetic Algorithm and Guided Local Search.`);

  // 8 Forecast
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Method" });
  head(s, "STEP 1 · PREDICTING DEMAND", "Customer behaviour suddenly changed in October 2017");
  const u = series.units;
  s.addChart(pres.charts.LINE, [
    { name: "Actual", labels: u.labels, values: u.actual },
    { name: "Old model (trained before the change)", labels: u.labels, values: u.naive_xgb },
    { name: "My model (updated with recent weeks)", labels: u.labels, values: u.selected }], {
    x: 0.45, y: 1.55, w: 7.5, h: 4.45, chartColors: [HEX.graph, HEX.coral, HEX.teal], lineSize: 2.5, lineDataSymbol: "none",
    showTitle: true, title: "Items ordered per week in the USA", showLegend: true, legendPos: "b",
    valAxisLabelFormatCode: "#,##0", catAxisLabelFrequency: 4, ...chartText, legendFontSize: 12, objectName: "Forecast chart" });
  T(s, [{ text: "What happened", options: { bold: true, color: HEX.teal, fontSize: 18, breakLine: true } },
    ...bullets(["Items per order dropped from about 6.5 to 1", "The old model kept predicting the old high level (orange)", "Fix: update the model with the newest weeks (green)"], { breakLine: true }),
    { text: " ", options: { fontSize: 8, breakLine: true } },
    { text: "Surprise", options: { bold: true, color: HEX.coral, fontSize: 18, breakLine: true } },
    { text: "A simple average was as good as XGBoost. A complex model is not always better." }],
    { x: 8.2, y: 1.65, w: 4.55, h: 4.3, fontSize: 15, paraSpaceAfter: 6 });
  takeaway(s, "A good forecast must notice when customer behaviour changes.", 6.2);
  s.addNotes(`For forecasting, I compared four methods: a simple historical average, a moving average, Random Forest and XGBoost.

The most important discovery is this chart. In October 2017, customer behaviour changed suddenly. Before, an order had about six and a half items. After, it had only about one.

The orange line is a model trained only on the old data. It keeps predicting the old high level, so it is very wrong. The green line is my model, updated with the newest weeks. It follows the real demand.

Another surprise: a simple average was just as accurate as XGBoost. So I did not choose XGBoost just because it is more advanced.

If asked "how did you measure accuracy?": I used MAE, RMSE and WAPE, which is the total error divided by the total demand. Lower is better.`);

  // 9 Warehouse step
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Method" });
  head(s, "STEP 2 · CHOOSING WAREHOUSES", "The computer finds the cheapest set of warehouses");
  s.addImage({ ...(await fit(path.join(FIG, "alloc_conus.png"), 0.45, 1.55, 7.4, 4.45)), altText: "Optimal USA warehouse allocation map" });
  T(s, [{ text: "How it works", options: { bold: true, color: HEX.teal, fontSize: 18, breakLine: true } },
    ...bullets(["37 possible places in the USA: more than 3 billion combinations", "Cost = warehouse rent + delivery travel", "Rules: each zone gets exactly one warehouse, and no warehouse is over-full", "The exact optimiser finds the cheapest plan and proves it is the best"])],
    { x: 8.1, y: 1.6, w: 4.65, h: 3.0, fontSize: 15, paraSpaceAfter: 6 });
  card(s, 8.1, 4.7, 2.25, 1.3); bigNum(s, 8.25, 4.75, 2.0, "6", "warehouses, USA ($18,497 / week)");
  card(s, 10.5, 4.7, 2.25, 1.3); bigNum(s, 10.65, 4.75, 2.0, "2", "warehouses, Puerto Rico ($2,510 / week)");
  takeaway(s, "Proven best answer, found in under one second.", 6.2);
  s.addNotes(`Now step two: choosing warehouses. In the USA there are 37 possible locations. If you try every combination, there are more than 3 billion. That is too many to check one by one.

So I used an exact optimisation model called the Capacitated Facility Location Problem. In simple words: the computer adds up warehouse rent plus travel cost, and finds the cheapest plan. It follows two rules: every zone is served by exactly one warehouse, and no warehouse can be over-full.

The answer is six warehouses in the USA, for about 18,500 dollars a week, and two in Puerto Rico. The solver proved this is the best possible plan, and it took less than one second.

On the map, each colour shows which warehouse serves which zones. The stars are the warehouses.

Note: costs like rent and travel cost per km are my assumptions, because the dataset does not have them.`);

  // 11 GA
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Method" });
  head(s, "GENETIC ALGORITHM", "A second method that learns like nature");
  const gs = [["1", "Start", "Make 60 random warehouse plans"], ["2", "Select", "Keep the cheaper plans, like \"survival of the fittest\""],
    ["3", "Mix", "Combine two good plans into a new one (crossover)"], ["4", "Change", "Make small random changes (mutation)"]];
  gs.forEach(([n, a, b], i) => {
    const y = 1.7 + i * 1.02;
    card(s, 0.6, y, 6.2, 0.88);
    s.addShape(pres.shapes.OVAL, { x: 0.8, y: y + 0.17, w: 0.54, h: 0.54, fill: { color: HEX.teal }, line: { color: HEX.teal } });
    T(s, n, { x: 0.8, y: y + 0.17, w: 0.54, h: 0.54, fontSize: 18, bold: true, color: "FFFFFF", align: "center", valign: "middle" });
    T(s, [{ text: a + "  ", options: { bold: true } }, { text: b }], { x: 1.55, y, w: 5.1, h: 0.88, fontSize: 16, valign: "middle" });
  });
  T(s, "Repeat for up to 80 generations, until the plans stop improving.", { x: 0.6, y: 5.8, w: 6.2, h: 0.35, fontSize: 14, italic: true, color: HEX.muted });
  s.addImage({ ...(await fit(path.join(FIG, "ga_convergence_conus.png"), 7.05, 1.6, 5.7, 3.6)), altText: "GA convergence chart" });
  T(s, "Each line is one run. Cost drops quickly, then flattens near the best answer (dashed line).", { x: 7.1, y: 5.25, w: 5.6, h: 0.6, fontSize: 13, color: HEX.muted });
  takeaway(s, "GA got within 0.58% of the best plan in the USA and found the best plan in Puerto Rico, but it cannot prove it is the best.", 6.2);
  s.addNotes(`I also used a Genetic Algorithm, which copies how nature evolves.
It starts with 60 random warehouse plans. It keeps the cheaper ones, like survival of the fittest. It mixes two good plans to make a new plan, which is called crossover. And it makes small random changes, which is called mutation. Then it repeats, generation after generation.

On the right, each line is one run. The cost drops fast and then flattens close to the best answer, which is the dashed line.

The result: in the USA the best GA run was only 0.58 percent more expensive than the exact answer. In Puerto Rico it found the exact best answer.

If asked "why use GA if the exact method is better?": because for very large problems an exact solver can become too slow. The GA still gives a good answer quickly. Here I could compare it with the proven best, so I know how good it is.`);

  // 12 Compare
  pres.addSection({ title: "Results" });
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Results" });
  head(s, "COMPARING METHODS", "Which method chose the cheapest warehouses?");
  s.addChart(pres.charts.BAR, [{ name: "USA weekly cost", labels: ["Exact optimiser", "Genetic Algorithm", "K-Means", "Random"], values: [18497.26, 18604.64, 18655.35, 30117.8] }], {
    x: 0.45, y: 1.55, w: 7.6, h: 4.5, barDir: "col", chartColors: [HEX.teal, HEX.sage, HEX.ochre, HEX.coral], showValue: true, dataLabelFormatCode: "$#,##0",
    valAxisHidden: true, valAxisMinVal: 0, showTitle: true, title: "USA total cost per week (same rules for every method)", ...chartText, catAxisLabelFontSize: 13, dataLabelFontSize: 13, objectName: "Method chart" });
  const cm = [["Exact optimiser", "the best (proven)", HEX.teal], ["Genetic Algorithm", "+0.58%", HEX.sage], ["K-Means", "+0.85%", HEX.ochre], ["Random places", "+62.8%", HEX.coral]];
  cm.forEach(([a, b, c], i) => { const y = 1.7 + i * 0.95; card(s, 8.35, y, 4.4, 0.8);
    s.addShape(pres.shapes.RECTANGLE, { x: 8.35, y, w: 0.12, h: 0.8, fill: { color: c }, line: { color: c } });
    T(s, [{ text: a, options: { bold: true, breakLine: true } }, { text: b, options: { color: HEX.muted } }], { x: 8.65, y: y + 0.05, w: 4.0, h: 0.7, fontSize: 15, valign: "middle" }); });
  T(s, "K-Means = simply put warehouses at the centres of customer groups.", { x: 8.35, y: 5.55, w: 4.4, h: 0.5, fontSize: 12, italic: true, color: HEX.muted });
  takeaway(s, "Smart optimisation is 38.6% cheaper than choosing warehouse places at random.", 6.2);
  s.addNotes(`Here I compare four ways of choosing six warehouses, all judged with exactly the same cost and rules.
The exact optimiser is the cheapest, and it is proven best.
The Genetic Algorithm is only 0.58 percent more.
K-Means, which just puts warehouses at the centre of customer groups, is 0.85 percent more.
Random places are almost 63 percent more expensive.

So good optimisation saves about 38.6 percent compared with choosing at random. In Puerto Rico, K-Means was 28 percent worse, because it only looks at where customers are, not at costs or warehouse size.`);

  // Routes combined
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Results" });
  head(s, "STEP 3 · DELIVERY ROUTES", "Planning the vans: Guided Local Search wins");
  T(s, [{ text: "The rules", options: { bold: true, color: HEX.teal, fontSize: 17, breakLine: true } },
    ...bullets(["Vans start and end at their warehouse", "Limited parcels per van, limited route length", "Every zone is visited"])],
    { x: 0.6, y: 1.6, w: 5.2, h: 1.45, fontSize: 15, paraSpaceAfter: 3 });
  const rr = [["Guided Local Search (best)", "16 vans · 31,610 km per week · all routes OK", HEX.teal], ["Standard local search", "16 vans · 31,647 km · all routes OK", HEX.sage], ["Nearest neighbour", "13 vans · 38,635 km · 5 routes too long, not allowed", HEX.coral]];
  rr.forEach(([a, b, c], i) => { const y = 3.15 + i * 0.98; card(s, 0.6, y, 5.2, 0.85);
    s.addShape(pres.shapes.RECTANGLE, { x: 0.6, y, w: 0.12, h: 0.85, fill: { color: c }, line: { color: c } });
    T(s, [{ text: a, options: { bold: true, breakLine: true } }, { text: b, options: { color: HEX.muted, fontSize: 13 } }], { x: 0.9, y: y + 0.03, w: 4.8, h: 0.8, fontSize: 15, valign: "middle" }); });
  s.addImage({ ...(await fit(path.join(FIG, "nn_vs_gls_dallas.png"), 6.05, 1.6, 6.7, 3.9)), altText: "Dallas: nearest neighbour vs GLS" });
  T(s, "Dallas example: nearest neighbour (left) uses 2 vans but one route is 6,607 km, too long. GLS (right) uses 4 vans and every route is within the limit. Puerto Rico: all methods give 7 vans, 174 km.",
    { x: 6.1, y: 5.5, w: 6.6, h: 0.65, fontSize: 12, color: HEX.muted });
  takeaway(s, "Fewer vans is not better if the routes break the rules. Solved with Google OR-Tools.", 6.28);
  s.addNotes(`Step three is delivery routes, which is the Capacitated Vehicle Routing Problem. For each warehouse I plan which van visits which zones and in which order. Each van carries limited parcels and cannot drive too far.

I compared three methods in Google OR-Tools.
Nearest neighbour: always drive to the closest next stop. It uses only 13 vans, but five routes are too long, so it is not a valid plan.
Standard local search: valid, 31,647 km.
Guided Local Search: the best valid plan, 16 vans and 31,610 km per week. When it gets stuck, it adds penalties to bad road links so it can try new routes.

The Dallas picture shows it: nearest neighbour has one route of over 6,600 km; GLS splits the work over four vans.

Distances are straight lines times 1.2, not real roads.`);

  // 15 Forecast helps?
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Results" });
  head(s, "DOES FORECASTING HELP?", "Plan from the forecast vs plan from old history");
  card(s, 0.6, 1.7, 5.95, 3.95, HEX.tealTint);
  iconDot(s, "check", 0.9, 1.95, 0.7);
  T(s, "USA: Yes", { x: 1.8, y: 2.0, w: 4.5, h: 0.6, fontSize: 24, bold: true, color: HEX.teal });
  bigNum(s, 0.95, 2.85, 5.3, "29.5% cheaper", "plan from the forecast vs plan from old history");
  T(s, bullets(["Old history still had the old high demand, so it opened 12 warehouses", "The forecast plan opened 6 and was only 0.4% above a perfect plan"]), { x: 0.95, y: 4.05, w: 5.4, h: 1.5, fontSize: 15, paraSpaceAfter: 5 });
  card(s, 6.8, 1.7, 5.95, 3.95, HEX.coralTint);
  iconDot(s, "warn", 7.1, 1.95, 0.7, HEX.coral);
  T(s, "Puerto Rico: No", { x: 8.0, y: 2.0, w: 4.5, h: 0.6, fontSize: 24, bold: true, color: HEX.coral });
  bigNum(s, 7.15, 2.85, 5.3, "21.6% more costly", "plan from the forecast vs plan from old history", HEX.coral);
  T(s, bullets(["The forecast of items was 20% too high", "So the plan opened a third warehouse that was not needed"]), { x: 7.15, y: 4.05, w: 5.4, h: 1.5, fontSize: 15, paraSpaceAfter: 5 });
  takeaway(s, "Forecasting helps when the forecast is accurate. I report both results honestly.", 6.0);
  s.addNotes(`This is my main experiment. I made warehouse plans in October 2017 using two inputs: my forecast, and old historical demand. Then I checked the real cost over the next 13 weeks.

In the USA, the forecast plan was 29.5 percent cheaper. The old history still had the high demand from before the change, so it opened 12 warehouses, which was too many. The forecast plan opened six, and was only 0.4 percent above a perfect plan made with full knowledge of the future.

In Puerto Rico, the result was the opposite. The forecast of items was about 20 percent too high, because the first week after the change still had large orders. So the plan opened an extra warehouse and cost 21.6 percent more.

I show both results honestly. The lesson: forecasting helps only when the forecast is accurate.`);

  // Conclusion + thanks
  pres.addSection({ title: "Conclusion" });
  s = pres.addSlide({ masterName: "CONTENT_DARK", sectionTitle: "Conclusion" });
  s.addText("CONCLUSION", { placeholder: "kicker" });
  s.addText("Four things to remember", { placeholder: "title" });
  const cc = [["chart", "Forecasting", "Demand changed suddenly in Oct 2017. Updated simple models worked as well as XGBoost."],
    ["wh", "Warehouses", "6 in the USA, 2 in Puerto Rico. Proven best plan, 38.6% cheaper than random places."],
    ["dna", "Genetic Algorithm", "Within 0.58% of the best plan: strong when exact solving is too slow."],
    ["route", "Routes", "GLS: 16 vans, 31,610 km per week, every route follows the rules."]];
  cc.forEach(([ic, a, b], i) => { const x = 0.6 + (i % 2) * 6.15, y = 1.6 + Math.floor(i / 2) * 1.72;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w: 5.95, h: 1.55, rectRadius: 0.08, fill: { color: "2C3438" }, line: { color: "2C3438" } });
    iconDot(s, ic, x + 0.3, y + 0.4, 0.75);
    T(s, [{ text: a, options: { bold: true, fontSize: 19, color: "6FC3B5", breakLine: true } }, { text: b, options: { color: "FFFFFF" } }], { x: x + 1.3, y: y + 0.1, w: 4.45, h: 1.35, fontSize: 15, valign: "middle" }); });
  takeaway(s, "Limits: costs are my assumptions and distances are straight-line × 1.2, so results compare methods, not real savings.", 5.15, true);
  T(s, "Thank you! Questions are welcome.", { x: 0.6, y: 5.9, w: 7.5, h: 0.6, fontSize: 26, bold: true, color: "FFFFFF", valign: "middle" });
  T(s, [{ text: "github.com/cmsoftx/Optimization", options: { hyperlink: { url: "https://github.com/cmsoftx/Optimization" }, color: "6FC3B5" } }], { x: 8.3, y: 5.9, w: 4.45, h: 0.6, fontSize: 15, align: "right", valign: "middle" });
  s.addNotes(`To conclude, four things to remember.
One: demand changed suddenly in October 2017, and simple updated models worked as well as XGBoost.
Two: the best plan is six warehouses in the USA and two in Puerto Rico. It is proven best and 38.6 percent cheaper than random places.
Three: the Genetic Algorithm came within 0.58 percent of the best, so it is a strong method when exact solving is too slow.
Four: Guided Local Search gave valid routes with 16 vans and about 31,600 km per week.

To be honest about limits: the costs and sizes are my assumptions, and distances are straight lines times 1.2. So the results compare methods fairly; they are not real company savings.

Thank you. I am happy to answer questions.

Easy answers to common questions:
Q: What is the CFLP? A: A model that chooses which warehouses to open and which zones each one serves, at the lowest cost, without any warehouse going over its size.
Q: Why not only the Genetic Algorithm? A: The exact method was fast here and gives a proven best answer. I used the GA to compare.
Q: What is Guided Local Search? A: It keeps improving routes, and when stuck it penalises bad road links to try new routes.
Q: Are the savings real? A: No, the costs are assumptions. The results compare methods fairly under the same rules.`);

  await pres.writeFile({ fileName: OUTFILE });
  await applyTheme(OUTFILE, THEME);
  console.log("written", OUTFILE);
})();
