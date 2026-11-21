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
  takeaway(s, "Goal: serve every customer at the lowest total cost, without overloading any warehouse or van.");
  s.addNotes(`Every online store faces three simple questions.
First, how much will customers order next week, and where?
Second, where should we open warehouses? More warehouses means more rent, fewer warehouses means longer trips.
Third, how should our vans drive, so that no van is overloaded and no route is too long?

My project answers all three questions, one after the other.`);

  // 3 Analogy
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Introduction" });
  head(s, "AN EASY EXAMPLE", "Think of a pizza chain opening in a new city");
  const pz = [["chart", "Guess how many pizzas each area will order", "Demand forecasting"],
    ["wh", "Decide where to open kitchens", "Warehouse location"],
    ["truck", "Plan the routes of the delivery bikes", "Vehicle routing"]];
  pz.forEach(([ic, a, b], i) => {
    const y = 1.75 + i * 1.2;
    card(s, 0.6, y, 7.4, 1.0);
    iconDot(s, ic, 0.8, y + 0.2, 0.6);
    T(s, a, { x: 1.6, y, w: 4.2, h: 1.0, fontSize: 17, valign: "middle" });
    T(s, "→  " + b, { x: 5.6, y, w: 2.3, h: 1.0, fontSize: 16, bold: true, color: HEX.teal, valign: "middle" });
  });
  card(s, 8.4, 1.75, 4.33, 3.4, HEX.coralTint);
  T(s, [{ text: "The balance we look for", options: { bold: true, fontSize: 19, color: HEX.coral, breakLine: true } },
    { text: " ", options: { fontSize: 8, breakLine: true } },
    ...bullets(["Too many kitchens → too much rent", "Too few kitchens → very long trips", "We find the number and places that make the total cost smallest"])],
    { x: 8.7, y: 1.95, w: 3.85, h: 3.1, fontSize: 16, paraSpaceAfter: 6 });
  takeaway(s, "My project does the same for an online store, using real order data instead of pizzas.", 5.6);
  s.addNotes(`To make this easy, think of a pizza chain coming to a new city.
First they guess how many pizzas each area will order. That is forecasting.
Then they choose where to open kitchens. That is warehouse location.
Then they plan the routes of the delivery bikes. That is vehicle routing.

The key idea is balance: too many kitchens cost too much rent, too few make trips too long. My project finds the best balance, using real data.`);

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

  // 5 Data
  pres.addSection({ title: "Data" });
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Data" });
  head(s, "THE DATA", "Real order data from an online store");
  const facts = [["180,519", "order lines (rows)"], ["65,752", "orders from 20,652 customers"], ["2015 – 2018", "three years of orders"], ["Kaggle", "DataCo Smart Supply Chain dataset"]];
  facts.forEach(([n, l], i) => { const x = 0.6 + (i % 2) * 2.95, y = 1.75 + Math.floor(i / 2) * 1.55; card(s, x, y, 2.75, 1.35); bigNum(s, x + 0.2, y + 0.12, 2.4, n, l); });
  s.addChart(pres.charts.BAR, [{ name: "Orders", labels: ["All orders", "After removing cancelled / fraud", "After removing wrong locations"], values: [65752, 62897, 62011] }], {
    x: 6.6, y: 1.65, w: 6.1, h: 3.4, barDir: "bar", chartColors: [HEX.teal], showValue: true, dataLabelFormatCode: "#,##0", valAxisHidden: true,
    showTitle: true, title: "Cleaning the data (orders kept)", ...chartText, catAxisLabelFontSize: 12, dataLabelFontSize: 12, objectName: "Cleaning chart" });
  T(s, bullets(["Personal details (names, streets) were removed", "94% of all units were kept"]), { x: 6.7, y: 5.1, w: 6, h: 0.8, fontSize: 14, paraSpaceAfter: 3 });
  takeaway(s, "Clean, checked data: 62,011 real orders are used in every later step.");
  s.addNotes(`I used a public dataset from Kaggle called DataCo Smart Supply Chain. It has 180,519 rows, about 65,000 orders, from 2015 to 2018.

I cleaned it in two steps. First I removed cancelled and fraud orders, because they were never delivered. Then I removed orders with wrong or missing locations. That leaves 62,011 orders, and I kept 94 percent of all items.

I also removed personal details like customer names and street addresses, to protect privacy.

If asked "why remove cancelled orders?": because they never needed a delivery, so they should not affect warehouse or route planning.`);

  // 6 Zones
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Data" });
  head(s, "DEMAND ZONES", "Nearby customers are grouped into zones");
  s.addImage({ ...(await fit(path.join(FIG, "zones_map.png"), 0.45, 1.55, 7.6, 4.5)), altText: "Map of demand zones" });
  T(s, [{ text: "Why zones?", options: { bold: true, color: HEX.teal, fontSize: 18, breakLine: true } },
    ...bullets(["Thousands of addresses are too many to plan one by one", "Customers close together are put in one zone", "USA: 312 zones, each at most 50 km wide", "Puerto Rico: 25 zones, each at most 10 km wide", "Puerto Rico is planned separately: no road from the mainland"])],
    { x: 8.3, y: 1.65, w: 4.45, h: 4.3, fontSize: 16, paraSpaceAfter: 8 });
  takeaway(s, "Zones turn thousands of customer locations into a map we can optimise.");
  s.addNotes(`There are thousands of customer locations, which is too many to plan directly. So I grouped customers who live close to each other into zones.

In the USA there are 312 zones, and no zone is wider than 50 kilometres. In Puerto Rico there are 25 smaller zones.

Puerto Rico is an island, so trucks cannot drive there from the mainland. That is why I plan it as a separate network.

Each bubble on the map is one zone. Bigger bubbles mean more demand. You can see demand is high around New York, California, Texas, Chicago and Florida.`);

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

  // 10 Utilisation
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Method" });
  head(s, "THE CHOSEN WAREHOUSES", "Where they are and how full they are");
  s.addChart(pres.charts.BAR, [{ name: "How full", labels: ["Brooklyn, NY", "Long Beach, CA", "Chicago, IL", "Dallas, TX", "Livermore, CA", "Hialeah, FL", "Caguas, PR (1)", "Caguas, PR (2)"],
    values: [91.1, 85.6, 69.4, 50.6, 44.0, 31.5, 94.2, 81.2] }], {
    x: 0.45, y: 1.55, w: 8.0, h: 4.5, barDir: "bar", chartColors: [HEX.teal, HEX.teal, HEX.teal, HEX.teal, HEX.teal, HEX.teal, HEX.coral, HEX.coral],
    showValue: true, dataLabelFormatCode: "0.0\"%\"", valAxisHidden: true, valAxisMaxVal: 100, catAxisOrientation: "maxMin",
    showTitle: true, title: "How full each warehouse is (% of capacity)", ...chartText, catAxisLabelFontSize: 13, dataLabelFontSize: 12, objectName: "Utilisation chart" });
  T(s, [{ text: "Easy to read", options: { bold: true, color: HEX.teal, fontSize: 18, breakLine: true } },
    ...bullets(["Big cities (New York, Los Angeles) get busy warehouses", "California needs two warehouses: one is not big enough", "No warehouse is over 100%: the capacity rule holds", "Teal = USA, orange = Puerto Rico"])],
    { x: 8.75, y: 1.65, w: 4.0, h: 4.3, fontSize: 15, paraSpaceAfter: 8 });
  takeaway(s, "Warehouses sit near the biggest customer areas, and none is overloaded.", 6.2);
  s.addNotes(`This chart shows the eight chosen warehouses and how full each one is.
Brooklyn near New York is 91 percent full, Long Beach near Los Angeles is 86 percent. These are the busiest areas.
California needs two warehouses, because one warehouse is not big enough for all its demand.
Most importantly, no warehouse goes over 100 percent, so the capacity rule is respected.`);

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

  // 13 Routing step
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Results" });
  head(s, "STEP 3 · DELIVERY ROUTES", "Planning the vans from each warehouse");
  T(s, [{ text: "The rules", options: { bold: true, color: HEX.teal, fontSize: 18, breakLine: true } },
    ...bullets(["Every van starts and ends at its warehouse", "A van can carry only a limited number of parcels", "A route cannot be longer than the daily limit", "Every customer zone is visited"], { breakLine: true }),
    { text: " ", options: { fontSize: 8, breakLine: true } },
    { text: "Three methods compared", options: { bold: true, color: HEX.teal, fontSize: 18, breakLine: true } },
    ...bullets(["Nearest neighbour: always drive to the closest next stop", "Standard: build a route, then improve it step by step", "Guided Local Search (GLS): keeps improving and avoids getting stuck"])],
    { x: 0.6, y: 1.6, w: 5.6, h: 4.5, fontSize: 15, paraSpaceAfter: 5 });
  s.addImage({ ...(await fit(path.join(FIG, "gls_routes_conus.png"), 6.4, 1.55, 6.35, 4.5)), altText: "GLS routes in the USA" });
  takeaway(s, "This is the Capacitated Vehicle Routing Problem, solved with Google OR-Tools.", 6.2);
  s.addNotes(`Step three is delivery routes. For each warehouse, I plan which van visits which zones and in which order.
The rules are simple: every van starts and ends at the warehouse, it can carry only so many parcels, a route cannot be too long, and every zone must be visited.

I compared three methods. Nearest neighbour is the simplest: always go to the closest next stop. The standard method builds routes and then improves them. Guided Local Search keeps improving, and when it gets stuck it adds a penalty to bad road links so it can escape and find better routes.

The map shows the final GLS routes in the USA. Lines are straight, because I used straight-line distances, not real roads.`);

  // 14 Routing result
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Results" });
  head(s, "ROUTING RESULTS", "Fewer vans is not better if the routes break the rules");
  s.addImage({ ...(await fit(path.join(FIG, "nn_vs_gls_dallas.png"), 0.45, 1.55, 7.6, 4.2)), altText: "Dallas: nearest neighbour vs GLS" });
  T(s, "Dallas example: nearest neighbour (left) uses 2 vans but one route is 6,607 km, far too long. GLS (right) uses 4 vans and every route is within the limit.",
    { x: 0.6, y: 5.6, w: 7.4, h: 0.6, fontSize: 12, color: HEX.muted });
  const rr = [["GLS (best)", "16 vans · 31,610 km per week · all routes OK", HEX.teal], ["Standard", "16 vans · 31,647 km · all routes OK", HEX.sage], ["Nearest neighbour", "13 vans · 38,635 km · 5 routes too long ✗", HEX.coral]];
  rr.forEach(([a, b, c], i) => { const y = 1.7 + i * 1.15; card(s, 8.35, y, 4.4, 1.0);
    s.addShape(pres.shapes.RECTANGLE, { x: 8.35, y, w: 0.12, h: 1.0, fill: { color: c }, line: { color: c } });
    T(s, [{ text: a, options: { bold: true, breakLine: true } }, { text: b, options: { color: HEX.muted, fontSize: 14 } }], { x: 8.65, y: y + 0.05, w: 4.0, h: 0.9, fontSize: 16, valign: "middle" }); });
  T(s, "Puerto Rico: all methods give the same plan, 7 vans and 174 km per week.", { x: 8.35, y: 5.2, w: 4.4, h: 0.7, fontSize: 13, color: HEX.muted });
  takeaway(s, "GLS gives the shortest plan that follows every rule in the USA.", 6.2);
  s.addNotes(`Here are the routing results for the USA.
GLS uses 16 vans and about 31,600 km per week, and every route follows the rules.
The standard method is almost the same, only 0.12 percent longer.
Nearest neighbour looks cheaper because it uses only 13 vans. But five of its routes are longer than allowed. So it is not a valid plan.

The Dallas picture shows this clearly. Nearest neighbour on the left uses two vans, but one route is over 6,600 km. GLS on the right uses four vans, and every route is within the limit.

In Puerto Rico distances are very short, so all three methods give the same plan.`);

  // 15 Forecast helps?
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Results" });
  head(s, "DOES FORECASTING HELP?", "I planned with the forecast and with old history, then compared");
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

  // 16 What if
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Results" });
  head(s, "WHAT IF?", "How the plan reacts when things change");
  s.addChart(pres.charts.LINE, [{ name: "Total cost", labels: ["4*", "5", "6", "7", "8", "10", "12"], values: [21859.63, 19531.54, 18497.26, 19047.52, 19682.55, 21439.31, 23355.08] }], {
    x: 0.45, y: 1.55, w: 7.4, h: 4.2, chartColors: [HEX.teal], lineSize: 3, lineDataSymbol: "circle", lineDataSymbolSize: 9, showValue: true, dataLabelFormatCode: "$#,##0", dataLabelPosition: "t",
    showTitle: true, title: "USA weekly cost if we force a number of warehouses", catAxisTitle: "number of warehouses", showCatAxisTitle: true, catAxisTitleFontSize: 12,
    valAxisLabelFormatCode: "$#,##0", valAxisMinVal: 16000, ...chartText, catAxisLabelFontSize: 13, objectName: "Forced count chart" });
  T(s, "* with 4 warehouses the solver stopped at its time limit (best plan found, not proven best: gap 5.75%). 2 or 3 warehouses are not enough to hold the demand.", { x: 0.6, y: 5.72, w: 7.3, h: 0.45, fontSize: 11, color: HEX.muted });
  T(s, [{ text: "What I learned", options: { bold: true, color: HEX.teal, fontSize: 18, breakLine: true } },
    ...bullets(["6 warehouses is the sweet spot: fewer or more costs more", "The plan stays at 6 warehouses from 10% less to 20% more demand", "Higher rent → fewer warehouses; higher travel cost → more warehouses", "Bigger vans (15 → 60 parcels): 24 → 15 vans needed"])],
    { x: 8.1, y: 1.65, w: 4.65, h: 4.4, fontSize: 15, paraSpaceAfter: 8 });
  takeaway(s, "The plan is stable: small changes in demand do not change the best answer.", 6.2);
  s.addNotes(`Here I test "what if" questions. The chart shows the weekly cost if I force the number of warehouses. It is a U shape. With too few warehouses, trips are long. With too many, rent is high. The lowest point is six, exactly what the optimiser chose.

I also changed demand, rent, travel cost and van size. The plan stays at six warehouses from 10 percent less to 20 percent more demand, so it is stable. Higher rent means fewer warehouses, and higher travel cost means more warehouses, which makes sense. And bigger vans need fewer vans: from 24 down to 15.

Note: for four warehouses the solver hit its time limit, so I show its best plan and say it is not proven best.`);

  // 17 Dashboard
  pres.addSection({ title: "Conclusion" });
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Conclusion" });
  head(s, "DASHBOARD", "An interactive app to explore the results");
  s.addImage({ ...(await fit(path.join(FIG, "dash_whatif.png"), 0.45, 1.5, 7.2, 4.5)), altText: "Dashboard what-if page" });
  T(s, [{ text: "8 pages, built with Streamlit", options: { bold: true, color: HEX.teal, fontSize: 18, breakLine: true } },
    ...bullets(["See the data, forecasts, warehouses and routes", "What-if page: change capacity, costs, vans or demand", "Press Run: the app solves the problem again live", "Download reports and tables"])],
    { x: 7.95, y: 1.6, w: 4.8, h: 4.4, fontSize: 16, paraSpaceAfter: 8 });
  takeaway(s, "A manager can try new ideas without writing any code.", 6.2);
  s.addNotes(`I also built a dashboard with Streamlit. It has eight pages: data, forecasts, warehouses, routes, comparisons, what-if, and reports.

The what-if page is the most useful. You can change the warehouse size, the costs, the number of vans or the demand growth, press Run, and the app solves the whole problem again live and shows the new plan.

So a manager can test ideas without writing any code.`);

  // 18 Limitations
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Conclusion" });
  head(s, "LIMITATIONS AND FUTURE WORK", "What to keep in mind, and what comes next");
  card(s, 0.6, 1.7, 5.95, 4.2);
  T(s, [{ text: "Limitations", options: { bold: true, color: HEX.coral, fontSize: 20, breakLine: true } },
    ...bullets(["Costs, warehouse sizes and vans are my assumptions, not company data", "Distances are straight lines × 1.2, not real roads", "Warehouses and routes are planned one after the other, not together", "Only a few weeks of data after the October 2017 change"])],
    { x: 0.9, y: 1.9, w: 5.4, h: 3.9, fontSize: 16, paraSpaceAfter: 8 });
  card(s, 6.8, 1.7, 5.95, 4.2);
  T(s, [{ text: "Future work", options: { bold: true, color: HEX.teal, fontSize: 20, breakLine: true } },
    ...bullets(["Use real road distances and travel times", "Add delivery time windows", "Plan warehouses and routes together", "Plan for several possible futures (uncertain demand)", "Retrain the forecast as new data arrives"])],
    { x: 7.1, y: 1.9, w: 5.4, h: 3.9, fontSize: 16, paraSpaceAfter: 8 });
  takeaway(s, "So the money values are for comparing methods, not real savings.", 6.2);
  s.addNotes(`I want to be honest about the limits.
The costs, warehouse sizes and number of vans are my assumptions, because the dataset does not include them. So the dollar values are for comparing methods, not real company savings.
Distances are straight-line distances times 1.2, not real road distances.
I plan warehouses first and routes second, not both together.
And there were only a few weeks of data after the October 2017 change.

In the future, I would use real road distances, add delivery time windows, plan warehouses and routes together, and handle uncertain demand.`);

  // 19 Conclusion
  s = pres.addSlide({ masterName: "CONTENT_DARK", sectionTitle: "Conclusion" });
  s.addText("CONCLUSION", { placeholder: "kicker" });
  s.addText("Four things to remember", { placeholder: "title" });
  const cc = [["chart", "Forecasting", "Demand changed suddenly in Oct 2017. Updated simple models worked as well as XGBoost."],
    ["wh", "Warehouses", "6 in the USA and 2 in Puerto Rico. Proven best plan, 38.6% cheaper than random."],
    ["dna", "Genetic Algorithm", "Within 0.58% of the best plan: a strong method when exact solving is too slow."],
    ["route", "Routes", "GLS: 16 vans, 31,610 km per week, every route follows the rules."]];
  cc.forEach(([ic, a, b], i) => { const x = 0.6 + (i % 2) * 6.15, y = 1.75 + Math.floor(i / 2) * 2.1;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w: 5.95, h: 1.85, rectRadius: 0.08, fill: { color: "2C3438" }, line: { color: "2C3438" } });
    iconDot(s, ic, x + 0.3, y + 0.35, 0.75);
    T(s, [{ text: a, options: { bold: true, fontSize: 20, color: "6FC3B5", breakLine: true } }, { text: b, options: { color: "FFFFFF" } }], { x: x + 1.3, y: y + 0.2, w: 4.45, h: 1.5, fontSize: 15, valign: "middle" }); });
  takeaway(s, "Predict → choose warehouses → plan routes: a full, tested pipeline from raw data to delivery plan.", 6.15, true);
  s.addNotes(`To conclude, four things to remember.
One: demand changed suddenly in October 2017, and simple updated models worked as well as XGBoost.
Two: the best plan is six warehouses in the USA and two in Puerto Rico, proven best, and 38.6 percent cheaper than random.
Three: the Genetic Algorithm came within 0.58 percent of the best, so it is a strong method when exact solving is too slow.
Four: Guided Local Search gave valid routes with 16 vans and about 31,600 km per week.

Overall, I built a complete pipeline from raw data to a delivery plan, with 69 automated tests.`);

  // 20 Thank you
  s = pres.addSlide({ masterName: "CLOSING_DARK", sectionTitle: "Conclusion" });
  s.addText("Thank you", { placeholder: "title" });
  s.addText("Questions are welcome", { placeholder: "body" });
  T(s, [{ text: "C M Karthik · SCA25MSD019", options: { breakLine: true, bold: true, color: "FFFFFF" } }, { text: "Guide: Ms. Jithy Lijo" }], { x: 0.6, y: 4.6, w: 6.4, h: 0.8, fontSize: 15, color: "D8D1C4" });
  s.addImage({ data: ICON.git.white, x: 0.6, y: 5.6, w: 0.35, h: 0.35 });
  T(s, [{ text: "github.com/cmsoftx/Optimization", options: { hyperlink: { url: "https://github.com/cmsoftx/Optimization" }, color: "6FC3B5" } }], { x: 1.1, y: 5.6, w: 6, h: 0.4, fontSize: 15 });
  s.addNotes(`Thank you for listening. I am happy to answer your questions.

Easy answers to common questions:
Q: What is the CFLP? A: A model that chooses which warehouses to open and which customers each one serves, at the lowest cost, without going over any warehouse's size.
Q: Why not use only the Genetic Algorithm? A: The exact method was fast enough here and gives a proven best answer. I used the GA to compare and to show it works well.
Q: What is Guided Local Search? A: A method that keeps improving routes, and when it gets stuck it adds penalties to bad road links so it can try something new.
Q: Are the savings real? A: No, the costs are assumptions. The results compare methods fairly, under the same rules.`);

  await pres.writeFile({ fileName: OUTFILE });
  await applyTheme(OUTFILE, THEME);
  console.log("written", OUTFILE);
})();
