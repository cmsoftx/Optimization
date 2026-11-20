const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, ImageRun, Table, TableRow, TableCell,
  AlignmentType, WidthType, BorderStyle, Footer, PageNumber, PageBreak,
  HeadingLevel, VerticalAlign, LevelFormat, ShadingType,
} = require("docx");

const FIG = path.join(__dirname, "figs");
const OUT = process.argv[2] || path.join(__dirname, "C_M_Karthik_Optimization_Case_Study_Report.docx");
const PAGES = process.argv[3] ? JSON.parse(fs.readFileSync(process.argv[3], "utf8")) : {};
const FONT = "Times New Roman";
const TW = 9026;

function runs(text, base = {}) {
  const out = [];
  const re = /\*\*(.+?)\*\*|\*(.+?)\*|_\{(.+?)\}|\^\{(.+?)\}/g;
  let last = 0, m;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) out.push(new TextRun({ text: text.slice(last, m.index), font: FONT, ...base }));
    if (m[1] !== undefined) out.push(...runs(m[1], { ...base, bold: true }));
    else if (m[2] !== undefined) out.push(...runs(m[2], { ...base, italics: true }));
    else if (m[3] !== undefined) out.push(new TextRun({ text: m[3], font: FONT, ...base, subScript: true }));
    else if (m[4] !== undefined) out.push(new TextRun({ text: m[4], font: FONT, ...base, superScript: true }));
    last = re.lastIndex;
  }
  if (last < text.length) out.push(new TextRun({ text: text.slice(last), font: FONT, ...base }));
  return out;
}

const P = (text, opt = {}) => new Paragraph({
  alignment: opt.align || AlignmentType.JUSTIFIED,
  spacing: { after: opt.after ?? 100, before: opt.before ?? 0, line: 259 },
  keepNext: opt.keepNext,
  children: runs(text, opt.run || {}),
});
const H1 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun({ text: t, font: FONT })] });
const H2 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun({ text: t, font: FONT })] });
const EQ = (text, after = 60) => new Paragraph({
  alignment: AlignmentType.CENTER, spacing: { after, line: 259 }, keepNext: true,
  children: runs(text, { italics: true }),
});
const BUL = (text, last) => new Paragraph({
  numbering: { reference: "bul", level: 0 }, alignment: AlignmentType.JUSTIFIED,
  spacing: { after: last ? 100 : 40, line: 259 }, children: runs(text),
});
const NUM = (ref, text, last) => new Paragraph({
  numbering: { reference: ref, level: 0 }, alignment: AlignmentType.JUSTIFIED,
  spacing: { after: last ? 100 : 40, line: 259 }, children: runs(text),
});

let tableNo = 0, figNo = 0;
const border = { style: BorderStyle.SINGLE, size: 4, color: "000000" };
const borders = { top: border, bottom: border, left: border, right: border, insideHorizontal: border, insideVertical: border };

function table(caption, widths, header, rows, note) {
  tableNo += 1;
  const scale = TW / widths.reduce((a, b) => a + b, 0);
  const w = widths.map((x) => Math.round(x * scale));
  w[w.length - 1] += TW - w.reduce((a, b) => a + b, 0);
  const cell = (t, i, head) => new TableCell({
    width: { size: w[i], type: WidthType.DXA }, verticalAlign: VerticalAlign.CENTER,
    margins: { top: 40, bottom: 40, left: 90, right: 90 },
    shading: head ? { fill: "E7E6E6", type: ShadingType.CLEAR, color: "auto" } : undefined,
    children: [new Paragraph({
      alignment: head || i > 0 ? AlignmentType.CENTER : AlignmentType.LEFT,
      spacing: { after: 0, line: 240 }, keepNext: true,
      children: runs(String(t), { size: 20, bold: head || undefined }),
    })],
  });
  const out = [
    new Paragraph({
      alignment: AlignmentType.CENTER, spacing: { before: 120, after: 80 }, keepNext: true,
      children: [new TextRun({ text: `Table ${tableNo}. `, bold: true, font: FONT }), ...runs(caption)],
    }),
    new Table({
      width: { size: TW, type: WidthType.DXA }, columnWidths: w, borders,
      rows: [
        new TableRow({ tableHeader: true, cantSplit: true, children: header.map((h, i) => cell(h, i, true)) }),
        ...rows.map((r) => new TableRow({ cantSplit: true, children: r.map((c, i) => cell(c, i, false)) })),
      ],
    }),
  ];
  out.push(note
    ? P(note, { run: { size: 19, italics: true }, before: 60, after: 140 })
    : new Paragraph({ spacing: { after: 80 }, children: [] }));
  return out;
}

function figure(file, widthIn, caption) {
  figNo += 1;
  const buf = fs.readFileSync(path.join(FIG, file));
  const { w, h } = pngSize(buf);
  const wpx = Math.round(widthIn * 96);
  return [
    new Paragraph({
      alignment: AlignmentType.CENTER, spacing: { before: 120, after: 60 }, keepNext: true,
      children: [new ImageRun({ type: "png", data: buf, transformation: { width: wpx, height: Math.round((wpx * h) / w) } })],
    }),
    new Paragraph({
      alignment: AlignmentType.CENTER, spacing: { after: 160 },
      children: [new TextRun({ text: `Figure ${figNo}. `, bold: true, italics: true, font: FONT, size: 22 }),
        ...runs(caption, { italics: true, size: 22 })],
    }),
  ];
}
function pngSize(buf) { return { w: buf.readUInt32BE(16), h: buf.readUInt32BE(20) }; }

const C = (text, size, opt = {}) => new Paragraph({
  alignment: AlignmentType.CENTER, spacing: { before: opt.before || 0, after: opt.after ?? 0 },
  children: [new TextRun({ text, font: FONT, size: size * 2, bold: opt.bold })],
});

const logo = fs.readFileSync(path.join(FIG, "dsu_logo.png"));
const cover = [
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 400, after: 300 },
    children: [new ImageRun({ type: "png", data: logo, transformation: { width: 118, height: 122 } })] }),
  C("DAYANANDA SAGAR UNIVERSITY", 15, { bold: true, after: 80 }),
  C("School of Computer Applications", 12, { after: 900 }),
  C("A Case Study On", 13, { bold: true, after: 300 }),
  C("DEMAND-DRIVEN E-COMMERCE WAREHOUSE", 17, { bold: true, after: 40 }),
  C("LOCATION AND MULTI-VEHICLE DELIVERY ROUTE", 17, { bold: true, after: 40 }),
  C("OPTIMIZATION USING HYBRID", 17, { bold: true, after: 40 }),
  C("OPTIMIZATION ALGORITHMS", 17, { bold: true, after: 900 }),
  C("Submitted by", 12, { after: 60 }),
  C("C M Karthik", 15, { bold: true, after: 60 }),
  C("USN: SCA25MSD019", 12, { after: 60 }),
  C("Programme: M.Sc. Data Science", 12, { after: 60 }),
  C("Course: Advanced Analytics and Optimisation (25MSD5303)", 12, { after: 700 }),
  C("Under the guidance of", 12, { after: 60 }),
  C("Ms. Jithy Lijo", 13, { bold: true, after: 900 }),
  C("Department of Computer Applications", 12, { bold: true, after: 40 }),
  C("Dayananda Sagar University", 12, { bold: true, after: 40 }),
  C("Kudlu Gate, Hosur Main Road, Bengaluru, Karnataka - 560068", 11, { after: 300 }),
  C("Academic Year 2026–2027", 12, { bold: true }),
  new Paragraph({ children: [new PageBreak()] }),
];

const abstract = [
  C("ABSTRACT", 16, { bold: true, after: 240 }),
  P("E-commerce fulfilment networks must decide where to open warehouses and how to deliver from them, and both decisions depend on demand that is uneven in space and unstable in time. This case study builds a reproducible, demand-driven planning pipeline on the public DataCo Smart Supply Chain dataset (180,519 order-item records, 2015–2018). After removing cancelled and suspected-fraud orders and records with invalid coordinates, 62,011 orders and 361,965 units were aggregated into 343 geographic demand zones by complete-linkage clustering; the continental United States (CONUS, 312 zones) and Puerto Rico (25 zones) are planned as separate networks."),
  P("Weekly zone demand was forecast for orders and units separately with historical-average, moving-average, Random Forest and XGBoost models under chronological, leakage-free evaluation. A structural break in October 2017 (units per order fell from 6.55 to 1.04) dominated model choice: tuned machine-learning models did not beat simple baselines before the break, and recalibrated or regime-reset models were selected after it (zone-total WAPE 0.24–0.46)."),
  P("Forecast demand drives a single-sourcing capacitated facility location problem (CFLP) solved by mixed-integer programming in Pyomo with CBC. Six CONUS and two Puerto Rico warehouses are optimal, at a modelled cost of $18,497 and $2,510 per week. A DEAP genetic algorithm reaches within 0.58% of the CONUS optimum and matches it in Puerto Rico, while K-Means and random siting cost 0.85% and 62.8% more in CONUS. Delivery from each selected warehouse is modelled as a capacitated vehicle routing problem solved with OR-Tools; Guided Local Search gives a feasible CONUS plan of 16 vehicles and 31,610 km per week, 0.12% shorter than a standard local search. In a held-out planning experiment the forecast-driven CONUS plan cost 29.5% less than a plan sized on historical demand, whereas the Puerto Rico forecast plan cost 21.6% more because units were over-forecast. Costs and capacities are assumed planning parameters and distances are great-circle approximations, so the results are relative comparisons rather than operational savings."),
  new Paragraph({ spacing: { before: 240, after: 80 }, children: [new TextRun({ text: "KEYWORDS", bold: true, font: FONT })] }),
  P("Capacitated Facility Location Problem; Mixed-Integer Programming; Genetic Algorithm; Vehicle Routing Problem; Guided Local Search; Demand Forecasting; XGBoost; Supply Chain Analytics; E-Commerce Logistics"),
  new Paragraph({ children: [new PageBreak()] }),
];

const indexRows = [
  ["1", "Introduction", "intro"], ["2", "Dataset Description and Preprocessing", "data"],
  ["3", "Exploratory Data Analysis", "eda"], ["4", "Demand Forecasting", "fc"],
  ["5", "Capacitated Facility Location Problem", "cflp"], ["6", "Genetic Algorithm", "ga"],
  ["7", "Vehicle Routing Optimization", "vrp"], ["8", "Experimental Results and Analysis", "exp"],
  ["9", "Conclusion and Future Scope", "concl"], ["10", "References", "refs"],
];
const iw = [1400, 6126, 1500];
const icell = (t, i, head) => new TableCell({
  width: { size: iw[i], type: WidthType.DXA }, verticalAlign: VerticalAlign.CENTER,
  margins: { top: 80, bottom: 80, left: 120, right: 120 },
  children: [new Paragraph({ alignment: i === 1 && !head ? AlignmentType.LEFT : AlignmentType.CENTER,
    children: [new TextRun({ text: t, font: FONT, bold: head })] })],
});
const index = [
  C("INDEX", 16, { bold: true, after: 240 }),
  new Table({
    width: { size: TW, type: WidthType.DXA }, columnWidths: iw, borders,
    rows: [
      new TableRow({ children: ["Sr. No.", "Content", "Page No."].map((t, i) => icell(t, i, true)) }),
      ...indexRows.map(([n, t, k]) => new TableRow({ children: [icell(n, 0), icell(t, 1), icell(PAGES[k] || "-", 2)] })),
    ],
  }),
  new Paragraph({ children: [new PageBreak()] }),
];

const body = [
  H1("1. INTRODUCTION"),
  H2("1.1 Background"),
  P("Online retail has moved fulfilment closer to the customer: delivery promises are measured in days, and transport and warehousing are the largest controllable logistics costs. Two decisions shape these costs. The strategic decision chooses which warehouses to open and which customers each one serves; the operational decision builds the vehicle routes that deliver from each warehouse. Both rest on demand that varies strongly across regions and over time, so a plan sized on past demand can be badly wrong when buying behaviour changes."),
  H2("1.2 Problem Statement"),
  P("Given historical order records with customer coordinates, the study asks: (i) how much demand will each geographic zone generate in the coming planning horizon; (ii) which candidate warehouses should be opened, and how zones should be assigned to them, to minimise fixed and transport cost without exceeding capacity; and (iii) how a fleet of capacitated vehicles should deliver the resulting weekly demand from each warehouse. The decisions are solved in sequence, so each stage hands a validated file to the next."),
  H2("1.3 Objectives"),
  NUM("obj", "**Data foundation:** clean the order-item data, aggregate it to orders and units, and build geographic demand zones."),
  NUM("obj", "**Forecasting:** forecast weekly zone demand for orders and units with leakage-free, chronological evaluation."),
  NUM("obj", "**Exact location:** formulate and solve the CFLP as a mixed-integer program and report optimality gaps honestly."),
  NUM("obj", "**Metaheuristic comparison:** implement a genetic algorithm and compare it with the exact solution and simple baselines under the same objective."),
  NUM("obj", "**Routing:** solve a capacitated vehicle routing problem per warehouse and compare Guided Local Search with simpler methods."),
  NUM("obj", "**Evaluation:** test whether forecast-driven planning beats history-driven planning and how sensitive the plan is to its assumptions.", true),
  H2("1.4 Scope"),
  P("The CONUS network is the primary case and Puerto Rico is planned as an independent network because it cannot be served by road from the mainland. Hawaii is kept for analysis only, and international destinations are excluded. Unit costs, warehouse capacities and the fleet are stated planning assumptions, not dataset values; distances are great-circle distances multiplied by a circuity factor of 1.2 [14], not road distances."),

  H1("2. DATASET DESCRIPTION AND PREPROCESSING"),
  H2("2.1 Source"),
  P("The study uses the DataCo Smart Supply Chain for Big Data Analysis dataset, published on Kaggle (https://www.kaggle.com/datasets/shashwatwork/dataco-smart-supply-chain-for-big-data-analysis) [1]. The raw file is licensed third-party data that includes customer names and street addresses, so it is downloaded locally and never committed to version control."),
  H2("2.2 Structure"),
  P("The file has 180,519 rows and 53 columns. Each row is an *order item* (one product line of an order), with 65,752 distinct orders from 20,652 customers between 1 January 2015 and 31 January 2018. Columns describe the order, product, shipping and customer location. Because one order usually contains several items, order items were aggregated to orders, and both *orders* (delivery stops, which drive transport cost) and *units* (item quantity, which consumes warehouse capacity) were kept as separate demand measures."),
  H2("2.3 Data Quality and Cleaning"),
  P("Cleaning used explicit flags and a decision log rather than silent deletion (Table 1). Five personally identifying columns were dropped before any analysis, and 37 of 37 reconciliation checks between record, order and zone totals passed.", { keepNext: true }),
  ...table("Data cleaning steps and their effect",
    [3400, 1500, 1300, 1300, 1500],
    ["Step", "Records removed", "Orders removed", "Units removed", "Orders remaining"],
    [
      ["Raw order-item file", "–", "–", "–", "65,752"],
      ["Exclude CANCELED and SUSPECTED_FRAUD orders", "7,754", "2,855", "16,488", "62,897"],
      ["Exclude invalid or missing coordinates", "2,608", "886", "5,626", "62,011"],
      ["Final analytical set (170,157 records)", "–", "–", "–", "62,011 (361,965 units, 94.2%)"],
    ]),
  H2("2.4 Geographic Demand Zones"),
  P("The destination fields in the dataset are not geographically consistent with customer locations (Cramér's V between order and customer region was 0.010 by network and 0.039 by state), so demand was placed at customer coordinates. Unique coordinates were grouped by complete-linkage clustering on chord distance with a maximum zone diameter of 50 km in CONUS and 10 km in Puerto Rico and Hawaii (Table 2). Complete linkage guarantees the diameter limit, so every customer in a zone is close to its demand-weighted centroid; the largest CONUS zone radius is 46.5 km. Figure 1 shows the resulting zones."),
  ...table("Demand zones by network",
    [1800, 1700, 1100, 1500, 1400, 1500],
    ["Network", "Coordinate points", "Zones", "Max diameter", "Orders", "Units"],
    [
      ["CONUS", "4,107", "312", "50 km", "37,617", "219,308"],
      ["Puerto Rico", "7,381", "25", "10 km", "23,975", "140,273"],
      ["Hawaii (analysis only)", "28", "6", "10 km", "419", "2,384"],
    ]),
  ...figure("zones_map.png", 4.4, "CONUS demand zones, sized by units. Demand concentrates in the north-east, California, Texas, Illinois and Florida."),

  H1("3. EXPLORATORY DATA ANALYSIS"),
  P("**Spatial concentration.** Demand is highly concentrated: 95 of the 312 CONUS zones carry 80% of units (Gini coefficient 0.657), and the largest zone (Brooklyn, New York) alone holds 6.4%. Puerto Rico is more extreme, with two zones holding 86.9% of units (Gini 0.886). Concentration of this kind favours a small number of warehouses near the dense metropolitan clusters."),
  P("**Orders versus units.** Order counts and unit volumes behave differently, which is why both are modelled. Sparsity is severe at fine resolution: 91.1% of CONUS zone-days have no demand, falling to 64.8% of zone-weeks and 34.4% of zone-months. The week was therefore chosen as the planning period, balancing sparsity against operational relevance."),
  P("**Structural break in October 2017.** Figure 2 shows an abrupt change at the start of October 2017. Daily orders rose (CONUS 32.6 → 39.8, Puerto Rico 20.8 → 24.8), but units per order fell from 6.55 to 1.04 and items per order from 3.00 to 1.02. Only 0.9% of post-break customers had ordered before, and the top category changed from cleats to video games. The data therefore contain two different regimes, and any model trained only on the old regime will overstate unit demand."),
  ...figure("monthly_demand.png", 5.8, "Monthly orders and units by network. Units collapse after October 2017 while orders rise, indicating a change in order composition rather than a fall in customers."),
  P("**Spatial shift in Puerto Rico.** In CONUS the zone ranking survived the break (Spearman ρ = 0.93), but Puerto Rico demand relocated: the total variation distance between pre- and post-break zone shares was 0.897, the two leading pre-break zones fell from 88.8% to 2.5% of demand, and two zones about 35 km east now hold 95.0% (ρ = 0.71). This shift is the main source of forecast error in Puerto Rico and is carried through to the results rather than hidden."),

  H1("4. DEMAND FORECASTING"),
  H2("4.1 Objective"),
  P("The forecast must supply, for every zone, the expected orders and units per week over a 13-week planning horizon. These two quantities become the transport weights and capacity loads of the CFLP."),
  H2("4.2 Methodology"),
  P("A weekly Sunday–Saturday panel of 160 complete weeks (4 January 2015 to 27 January 2018) was built for 337 zones. Four approaches were compared: historical average, moving average, Random Forest [13] and XGBoost [12]. The tree models use 29 features (lags, rolling means, zone history and calendar terms) computed with prefix sums so that a week's features use only earlier weeks; this property is unit-tested. XGBoost minimises a regularised objective"),
  EQ("L = Σ_{i} l(y_{i}, ŷ_{i}) + Σ_{k} [ γT_{k} + ½λ‖w_{k}‖^{2} ]", 100),
  P("where *l* is squared error, *T_{k}* the number of leaves of tree *k*, *w_{k}* its leaf weights, and γ and λ penalise complexity [12]. Splits are chronological, with one-step and recursive multi-step modes. After the break, models were re-fitted on a short adapted window (4 observed post-break weeks, 13 forecast weeks), with recalibrated and regime-reset variants; an oracle that knows the realised zone means gives the noise floor."),
  H2("4.3 Model Evaluation"),
  P("Accuracy is measured by MAE = (1/*n*)Σ|*y_{i}* − *ŷ_{i}*|, RMSE = √[(1/*n*)Σ(*y_{i}* − *ŷ_{i}*)^{2}] and WAPE = Σ|*y_{i}* − *ŷ_{i}*| / Σ*y_{i}*. MAPE was not used because most zone-weeks are zero. Zone-week WAPE is minimised by the median, which is often zero and rewards under-forecasting, so final selection used *zone-total* WAPE, the error on each zone's 13-week total, which is what sizes a warehouse. Table 3 gives the pre-break test results."),
  ...table("Pre-break test accuracy, CONUS zone-week, one-step ahead",
    [2600, 1300, 1300, 1300, 1300, 1300, 1300],
    ["Model", "Orders MAE", "Orders RMSE", "Orders WAPE", "Units MAE", "Units RMSE", "Units WAPE"],
    [
      ["Historical average", "0.519", "0.830", "0.726", "3.656", "6.107", "0.830"],
      ["Moving average", "0.525", "0.858", "0.736", "3.694", "6.357", "0.838"],
      ["Random Forest", "0.534", "0.838", "0.748", "3.754", "6.184", "0.852"],
      ["XGBoost", "0.531", "0.839", "0.743", "3.726", "6.205", "0.846"],
      ["Oracle (noise floor)", "0.489", "0.800", "0.684", "3.398", "5.888", "0.771"],
    ],
    "The historical average is best on every metric; the gap to the oracle shows how little predictable signal remains at zone-week level."),
  H2("4.4 Results"),
  P("Before the break the tuned tree models did not beat the historical average (Table 3), so XGBoost was not selected merely because it is more complex. After the break, a model trained on the old regime over-forecast units badly (Figure 3), while short-window recalibration tracked the new level. Table 4 lists the selected models on the 13 held-out post-break weeks."),
  ...figure("forecast_units.png", 5.8, "CONUS weekly units: actual demand, an XGBoost forecast trained before the break, and the selected recalibrated Random Forest."),
  ...table("Selected forecast models, zone-total accuracy over 13 held-out weeks",
    [2200, 3000, 1100, 1100, 1100, 1100],
    ["Target / network", "Selected model", "MAE", "RMSE", "WAPE", "Bias"],
    [
      ["Orders, CONUS", "Zone share × recent level (regime reset)", "2.806", "4.259", "0.242", "+0.4%"],
      ["Orders, Puerto Rico", "Post-break average", "23.21", "54.70", "0.254", "−3.0%"],
      ["Units, CONUS", "Random Forest, recalibrated", "3.520", "6.203", "0.304", "+18.8%"],
      ["Units, Puerto Rico", "Post-break average", "42.19", "111.36", "0.462", "+20.4%"],
    ],
    "Near ties: the recalibrated historical average scored 0.243 (orders) and 0.305 (units) in CONUS. In Puerto Rico the best XGBoost variant scored about 1.0, far worse than the post-break average."),
  P("The Puerto Rico units over-forecast (+20.4%) arises because the first post-break week (1–7 October 2017) still averaged 1.96 units per order and fell inside the 4-week calibration window. The forward forecast for 28 January to 28 April 2018 is calibrated on January 2018 and gives 279.5 orders and 297.81 units per week in CONUS and 175.5 orders and units in Puerto Rico. A coherence step enforces units ≥ orders in every zone; it raised units in 125 zones (+4.3%)."),

  H1("5. CAPACITATED FACILITY LOCATION PROBLEM"),
  H2("5.1 Need for Optimisation"),
  P("With 37 CONUS candidate sites and between 1 and 12 open warehouses there are 3,231,939,122 possible open sets, each with its own optimal assignment, so enumeration is impossible. The CFLP [2], [3] captures the trade-off: each additional warehouse adds fixed cost but shortens delivery distances, while capacity limits force some zones to be served from farther away."),
  H2("5.2 Mathematical Formulation"),
  P("Let *I* be the demand zones and *J* the candidate warehouses. Zone *i* has forecast orders *o_{i}* and units *u_{i}* per week; *d_{ij}* is the distance (km), *F_{j}* the weekly fixed cost, *Q_{j}* the weekly capacity in units and *c* the transport cost per order-km. *Y_{j}* = 1 if warehouse *j* opens and *X_{ij}* = 1 if zone *i* is served by *j* (single sourcing). The model is:", { keepNext: true }),
  EQ("Minimize  Z = Σ_{j∈J} F_{j}Y_{j} + Σ_{i∈I} Σ_{j∈J} c d_{ij} o_{i} X_{ij}"),
  EQ("subject to  Σ_{j∈J} X_{ij} = 1   for every zone i"),
  EQ("Σ_{i∈I} u_{i} X_{ij} ≤ Q_{j}Y_{j}   for every warehouse j"),
  EQ("X_{ij} ≤ Y_{j}   for every i, j;     p_{min} ≤ Σ_{j} Y_{j} ≤ p_{max}"),
  EQ("X_{ij}, Y_{j} ∈ {0, 1}", 100),
  P("Orders drive transport cost because each order is a delivery stop, while units consume capacity. A handling cost of $0.50 per unit is added to the reported total; it is constant across solutions and does not change the optimum. In the experiments an unserved-demand slack with a penalty of $10,000 per unit keeps stress tests solvable while still showing infeasibility."),
  H2("5.3 Implementation"),
  P("Candidates were 27 coverage-driven sites, 7 demand-driven sites and 3 chosen by both rules (37 in CONUS); all 25 zone centroids were candidates in Puerto Rico. Assumed parameters are *c* = $0.10 per order-km, *F_{j}* = $1,500 per week ($1,200 in Puerto Rico), *Q_{j}* = 80 units per week (100 in Puerto Rico) and 1 ≤ Σ*Y_{j}* ≤ 12 (at most 4 in Puerto Rico). The model was written in Pyomo [9] and solved with CBC 2.10.11 [10] using a 120 s limit and a 10^{−4} relative gap. The CONUS model has 11,893 variables (11,581 binary) and 11,895 constraints; Puerto Rico has 675 variables and 677 constraints. Infeasible terminations raise an error rather than returning a partial solution."),
  H2("5.4 Results"),
  P("Both networks were solved to proven optimality: CONUS in 0.96 s with zero gap and Puerto Rico in 0.07 s. The CONUS optimum opens six warehouses at a total cost of $18,497.26 per week ($18,348.36 fixed plus transport and $148.90 handling); Puerto Rico opens two for $2,509.51. The average order-weighted distance is 334.5 km in CONUS and 1.24 km in Puerto Rico. Table 5 and Figure 4 show the selected sites."),
  ...table("Optimal warehouses and their allocated weekly demand",
    [1500, 2100, 1000, 1400, 1400, 1500],
    ["Warehouse", "Location", "Zones", "Orders/week", "Units/week", "Utilisation"],
    [
      ["WH-US-01", "Brooklyn, NY", "64", "70.8", "72.9", "91.1%"],
      ["WH-US-05", "Long Beach, CA", "39", "65.4", "68.5", "85.6%"],
      ["WH-US-03", "Chicago, IL", "81", "51.2", "55.5", "69.4%"],
      ["WH-US-14", "Dallas, TX", "49", "37.4", "40.5", "50.6%"],
      ["WH-US-31", "Livermore, CA", "48", "31.2", "35.2", "44.0%"],
      ["WH-US-37", "Hialeah, FL", "31", "23.4", "25.2", "31.5%"],
      ["WH-PR-03", "Caguas, PR", "17", "94.2", "94.2", "94.2%"],
      ["WH-PR-05", "Caguas, PR", "8", "81.2", "81.2", "81.2%"],
    ]),
  ...figure("alloc_conus.png", 4.4, "Optimal CONUS allocation. Each zone is coloured by its assigned warehouse (stars); California needs two sites to serve its demand within capacity."),

  H1("6. GENETIC ALGORITHM"),
  H2("6.1 Why a Genetic Algorithm"),
  P("The MIP is exact but its run time can grow quickly with more candidates or tighter capacity, as the time-limited sensitivity runs in Section 8.4 show. A genetic algorithm [4] searches the open-set space directly and scales predictably, so it was implemented with DEAP [5] and compared with the proven optimum under the identical objective and constraints."),
  H2("6.2 Procedure"),
  NUM("ga", "**Encoding:** a binary chromosome of 37 genes, where gene *j* = 1 opens warehouse *j*."),
  NUM("ga", "**Decoding:** a regret-based heuristic assigns each zone to an open warehouse with spare capacity; fitness is the total cost *Z*, with a penalty for unserved units."),
  NUM("ga", "**Operators:** tournament selection (*k* = 3), two-point crossover (probability 0.8) and bit-flip mutation (probability 0.3 per individual, 1/*n* per gene); a repair step keeps the open count within [*p_{min}*, 12]."),
  NUM("ga", "**Control:** population 60, elitism of 2, at most 80 generations, stopping after 25 generations without improvement; five seeds (11–55)."),
  NUM("ga", "**Polishing:** the best chromosome's assignment is re-solved exactly by CBC, so the reported cost is the true cost of that open set.", true),
  H2("6.3 Results and Comparison"),
  P("The best GA run in CONUS cost $18,604.64, 0.58% above the CFLP optimum; across the five seeds the cost ranged from $18,604.64 to $18,942.04 (mean $18,813.07, +1.71%). In Puerto Rico four of five seeds found the optimum. The GA is therefore a strong heuristic but not a proof of optimality. Figure 5 shows its convergence, and Table 6 compares all siting methods under the same cost function."),
  ...figure("ga_convergence_conus.png", 3.4, "GA convergence in CONUS for five seeds; the dashed line is the proven CFLP optimum ($18,348 before the constant handling cost)."),
  ...table("Warehouse siting methods compared under the same objective",
    [1500, 2300, 1900, 1500, 1800],
    ["Network", "Method", "Total cost/week", "Gap vs CFLP", "Run time"],
    [
      ["CONUS", "CFLP (Pyomo + CBC)", "$18,497.26", "0.00%", "0.83 s"],
      ["CONUS", "GA (best of 5 seeds)", "$18,604.64", "+0.58%", "72 s (5 runs)"],
      ["CONUS", "K-Means (k = 6, snapped)", "$18,655.35", "+0.85%", "0.48 s"],
      ["CONUS", "Random (k = 6, mean of 30)", "$30,117.80", "+62.8%", "24.6 s"],
      ["Puerto Rico", "CFLP", "$2,509.51", "0.00%", "0.05 s"],
      ["Puerto Rico", "GA (best of 5 seeds)", "$2,509.51", "0.00%", "1.6 s (5 runs)"],
      ["Puerto Rico", "K-Means (k = 2)", "$3,206.39", "+27.8%", "0.07 s"],
      ["Puerto Rico", "Random (k = 2, mean of 30)", "$3,394.69", "+35.3%", "1.5 s"],
    ],
    "K-Means and Random open the same number of sites as the CFLP. The CFLP saves 38.6% against random siting in CONUS; its average order-weighted distance is 334.5 km against 750.2 km for random sites."),

  H1("7. VEHICLE ROUTING OPTIMIZATION"),
  H2("7.1 CVRP versus TSP"),
  P("A travelling salesman tour visits every stop with one vehicle and ignores load. Delivery vans have a limited capacity and a maximum route length, so the problem from each warehouse is a capacitated vehicle routing problem (CVRP) [6], [7]: several routes start and end at the depot, and each respects load and length limits."),
  H2("7.2 Formulation"),
  P("For each selected warehouse, the weekly forecast orders of its zones form one consolidated delivery plan, with one package per order. Fractional forecasts are rounded by the largest-remainder method so the depot total is preserved, and stops larger than a van are split. With *x_{ijk}* = 1 if vehicle *k* travels from stop *i* to stop *j*, the model minimises Σ_{k}Σ_{i}Σ_{j} *d_{ij}x_{ijk}* subject to every stop being visited once, each route starting and ending at the depot, Σ *q_{i}* ≤ *Q* on each route and route length ≤ *L*. OR-Tools [11] implements load and length as capacity and distance dimensions, and a drop penalty (disjunction) makes any unserved stop visible instead of making the model infeasible."),
  H2("7.3 Guided Local Search"),
  P("Three methods were compared: a nearest-neighbour (NN) construction, the OR-Tools path-cheapest-arc start improved by greedy descent (“standard”), and Guided Local Search (GLS) [8]. GLS escapes local optima by adding penalties to features of the current solution, here the arcs, chosen by their utility *d_{ij}* / (1 + *p_{ij}*); local search then continues on the augmented cost *d_{ij}* + λ*p_{ij}*. GLS was given 10 s per depot."),
  H2("7.4 Results"),
  P("The CONUS depots have 12 to 36 stops and 278 packages in total. Table 7 summarises the results. GLS gives a feasible plan of 16 vehicles and 31,610 km per week, 0.12% shorter than the standard method. NN uses fewer vehicles and appears cheaper in vehicle count, but five of its routes break the route-length limit, so the 18.2% distance difference is not a like-for-like saving. Figure 6 illustrates this at the Dallas depot."),
  ...table("Routing methods compared (weekly plan)",
    [1500, 2300, 1300, 1700, 1300, 1800],
    ["Network", "Method", "Vehicles", "Distance (km)", "Hours", "Feasible"],
    [
      ["CONUS", "Guided Local Search", "16", "31,610.44", "509.65", "Yes"],
      ["CONUS", "Standard (PCA + descent)", "16", "31,647.27", "510.21", "Yes"],
      ["CONUS", "Nearest neighbour", "13", "38,635.49", "617.73", "No (5 length violations)"],
      ["Puerto Rico", "All three methods", "7", "173.58", "6.17", "Yes"],
    ],
    "GLS fleet utilisation in CONUS is 57.9%. The modelled routing cost is $53,500.54 per week in CONUS and $2,815.65 in Puerto Rico under the assumed rates."),
  ...figure("nn_vs_gls_dallas.png", 5.2, "Dallas depot: nearest neighbour (2 vehicles, 10,186 km, routes of 6,607 and 3,579 km) versus GLS (4 vehicles, 9,962 km, all routes within limits). Straight lines stand for great-circle legs."),

  H1("8. EXPERIMENTAL RESULTS AND ANALYSIS"),
  H2("8.1 Warehouse Comparison"),
  P("At this problem size the exact CFLP is both the cheapest and among the fastest methods (Table 6). K-Means is close in CONUS (+0.85%) because demand is clustered, but it places sites by demand geometry alone, without regard to capacity, and performs much worse in Puerto Rico (+27.8%), where its sites sit an average 40.9 km from customers instead of 1.2 km. The GA is a reliable second-best that does not depend on an exact solver."),
  H2("8.2 Routing Comparison"),
  P("GLS improves the standard method by only 0.12% because the per-depot instances are small (Table 7); the fair comparison is between feasible plans, which excludes NN. In Puerto Rico all methods reach the same plan."),
  H2("8.3 Forecast-Assisted Planning"),
  P("To test the value of forecasting, plans were built at a forecast origin of 28 October 2017 using three demand inputs and evaluated on the realised demand of the next 13 weeks (Table 8). Regret is the realised cost above the plan built with perfect information, which is a benchmark and not a deployable plan."),
  ...table("Realised cost of plans built on different demand inputs",
    [1500, 2100, 1800, 1400, 2000, 1300],
    ["Network", "Demand input", "Planned units/week", "Warehouses", "Realised cost/week", "Regret"],
    [
      ["CONUS", "Historical average", "1,461.6", "12", "$26,377.06", "42.4%"],
      ["CONUS", "Forecast", "330.6", "6", "$18,594.38", "0.40%"],
      ["CONUS", "Perfect information", "278.2", "6", "$18,519.62", "–"],
      ["Puerto Rico", "Historical average", "935.6", "2", "$3,044.72", "21.4%"],
      ["Puerto Rico", "Forecast", "211.25", "3", "$3,702.62", "47.7%"],
      ["Puerto Rico", "Perfect information", "175.5", "2", "$2,507.07", "–"],
    ],
    "The CONUS historical plan stopped at the 120 s limit with a 0.57% gap and is reported as an incumbent."),
  P("In CONUS the forecast plan cost 29.5% less than the historical plan, because the historical plan sized twelve warehouses for pre-break unit volumes. In Puerto Rico the result is negative: the forecast plan cost 21.6% *more*, because units were over-forecast by 20.4% and a third warehouse was opened. Forecast-driven planning helps only when the forecast tracks the new regime."),
  H2("8.4 Sensitivity and Robustness"),
  P("Each CONUS parameter was varied one at a time and the CFLP re-solved (Table 9). Six of the 34 CONUS solves reached the time limit and are reported with their gaps, not as optima."),
  ...table("CFLP sensitivity in CONUS (one parameter varied at a time)",
    [2200, 2800, 4000],
    ["Parameter", "Range tested", "Effect on plan and cost/week"],
    [
      ["Warehouse capacity", "×0.6 to ×3", "8 sites, $20,479 at ×0.6 (time limit, gap 3.9%); 5 sites, $18,449 from ×1.5"],
      ["Forced warehouse count", "2 to 12", "2–3 infeasible; 4: $21,860 (gap 5.75%); minimum at 6: $18,497; 12: $23,355"],
      ["Fixed cost", "×0.25 to ×4", "12 sites, $9,855 at ×0.25; 4 sites, $39,840 at ×4 (gap 4.0%)"],
      ["Transport cost per km", "×0.25 to ×4", "5 sites, $10,778 at ×0.25 (gap 10.3%); 12 sites, $38,974 at ×4"],
      ["Demand level", "−20% to +40%", "5 sites, $16,372 at −20%; 6 sites up to +20%; 7 sites, $23,151 at +40%"],
      ["Zone diameter", "25, 50, 100 km", "6 sites in all cases; $18,543, $18,579, $18,490 (post-break-average demand)"],
    ]),
  P("The plan is stable: six warehouses remain optimal from −10% to +20% demand and for all zone diameters, and the forced-count curve is U-shaped with its minimum at the selected six. For routing, raising van capacity from 15 to 60 packages reduces the CONUS fleet from 24 to 15 vehicles and distance from 33,642.5 to 31,447.5 km, while limiting each depot to 2 or 3 vans leaves 38 or 4 packages unserved. In robustness tests the CONUS network stays feasible up to +20% demand if zones are re-allocated (keeping the old allocation overloads by 9.7 units), but Puerto Rico becomes infeasible from +10% because one zone alone exceeds a warehouse's 100-unit capacity (102.0 units unserved)."),

  H1("9. CONCLUSION AND FUTURE SCOPE"),
  H2("9.1 Achievements"),
  P("The project delivers an end-to-end, reproducible pipeline from raw order items to warehouse locations and weekly routes, with 69 automated tests, 15 of 15 consistency checks and an eight-page Streamlit dashboard that re-solves the CFLP and routing for what-if scenarios. Table 10 summarises the key results."),
  ...table("Summary of key results",
    [3600, 5400],
    ["Item", "Result"],
    [
      ["Analytical data", "62,011 orders, 361,965 units, 343 zones; 37/37 reconciliation checks"],
      ["Forecast (zone-total WAPE)", "CONUS orders 0.242, units 0.304; Puerto Rico 0.254 and 0.462"],
      ["CFLP optimum", "CONUS 6 sites, $18,497.26/week; Puerto Rico 2 sites, $2,509.51/week; gap 0"],
      ["Genetic algorithm", "+0.58% (best seed) and +1.71% (mean) in CONUS; optimum in Puerto Rico"],
      ["Routing (GLS)", "CONUS 16 vehicles, 31,610 km/week, feasible; Puerto Rico 7 vehicles, 174 km"],
      ["Forecast-assisted planning", "CONUS −29.5% vs historical plan; Puerto Rico +21.6% (negative result)"],
    ]),
  H2("9.2 Limitations"),
  BUL("Costs, capacities and fleet size are assumptions, so costs are relative comparisons, not real savings."),
  BUL("Distances are great-circle × 1.2, not road-network distances; routes are drawn as straight lines."),
  BUL("Location and routing are optimised in sequence, not jointly, and the routing plan is a weekly consolidation."),
  BUL("Only four post-break weeks were available for recalibration, which caused the Puerto Rico unit bias.", true),
  H2("9.3 Future Scope"),
  P("Future work could use road-network distances from a self-hosted routing engine, add delivery time windows and multiple shifts, solve location and routing jointly as a location-routing problem, use stochastic or robust optimisation over forecast scenarios, and re-estimate the forecast as more post-break data arrive."),

  H1("REFERENCES"),
  ...[
    "[1] Shashwat (n.d.). DataCo Smart Supply Chain for Big Data Analysis [Dataset]. Kaggle. https://www.kaggle.com/datasets/shashwatwork/dataco-smart-supply-chain-for-big-data-analysis (originally published by Constante, F., Silva, F. & Pereira, A. (2019), Mendeley Data).",
    "[2] Sridharan, R. (1995). The capacitated plant location problem. *European Journal of Operational Research*, 87(2), 203–213.",
    "[3] Cornuéjols, G., Nemhauser, G. L. & Wolsey, L. A. (1990). The uncapacitated facility location problem. In P. B. Mirchandani & R. L. Francis (Eds.), *Discrete Location Theory* (pp. 119–171). Wiley.",
    "[4] Holland, J. H. (1975). *Adaptation in Natural and Artificial Systems*. University of Michigan Press.",
    "[5] Fortin, F.-A., De Rainville, F.-M., Gardner, M.-A., Parizeau, M. & Gagné, C. (2012). DEAP: Evolutionary algorithms made easy. *Journal of Machine Learning Research*, 13, 2171–2175.",
    "[6] Dantzig, G. B. & Ramser, J. H. (1959). The truck dispatching problem. *Management Science*, 6(1), 80–91.",
    "[7] Toth, P. & Vigo, D. (Eds.) (2014). *Vehicle Routing: Problems, Methods, and Applications* (2nd ed.). SIAM.",
    "[8] Voudouris, C. & Tsang, E. (1999). Guided local search and its application to the traveling salesman problem. *European Journal of Operational Research*, 113(2), 469–499.",
    "[9] Hart, W. E., Watson, J.-P. & Woodruff, D. L. (2011). Pyomo: Modeling and solving mathematical programs in Python. *Mathematical Programming Computation*, 3(3), 219–260.",
    "[10] Forrest, J. et al. COIN-OR Branch and Cut (CBC), version 2.10.11 [Software]. https://github.com/coin-or/Cbc",
    "[11] Perron, L. & Furnon, V. OR-Tools [Software]. Google. https://developers.google.com/optimization",
    "[12] Chen, T. & Guestrin, C. (2016). XGBoost: A scalable tree boosting system. *Proceedings of the 22nd ACM SIGKDD International Conference on Knowledge Discovery and Data Mining*, 785–794.",
    "[13] Breiman, L. (2001). Random forests. *Machine Learning*, 45(1), 5–32.",
    "[14] Ballou, R. H., Rahardja, H. & Sakai, N. (2002). Selected country circuity factors for road travel distance estimation. *Transportation Research Part A*, 36(9), 843–848.",
    "[15] Pedregosa, F. et al. (2011). Scikit-learn: Machine learning in Python. *Journal of Machine Learning Research*, 12, 2825–2830.",
    "[16] Karthik, C. M. (2026). Optimization: project source code and outputs [Repository]. GitHub. https://github.com/cmsoftx/Optimization (branch claude/gifted-bohr-s602fx)",
  ].map((r) => new Paragraph({ alignment: AlignmentType.LEFT, spacing: { after: 80, line: 250 }, indent: { left: 440, hanging: 440 }, children: runs(r, { size: 22 }) })),
];

const numbered = (ref) => ({ reference: ref, levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT,
  style: { paragraph: { indent: { left: 500, hanging: 320 } } } }] });

const doc = new Document({
  creator: "C M Karthik",
  title: "Demand-Driven E-Commerce Warehouse Location and Multi-Vehicle Delivery Route Optimization",
  styles: {
    default: { document: { run: { font: FONT, size: 24 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { font: FONT, size: 28, bold: true, color: "000000" },
        paragraph: { spacing: { before: 280, after: 120 }, keepNext: true, keepLines: true, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { font: FONT, size: 24, bold: true, color: "000000" },
        paragraph: { spacing: { before: 160, after: 80 }, keepNext: true, keepLines: true, outlineLevel: 1 } },
    ],
  },
  numbering: { config: [
    { reference: "bul", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
      style: { paragraph: { indent: { left: 500, hanging: 320 } } } }] },
    numbered("obj"), numbered("ga"),
  ] },
  sections: [{
    properties: { page: { size: { width: 11906, height: 16838 },
      margin: { top: 1440, right: 1440, bottom: 1300, left: 1440, footer: 600 } } },
    footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER,
      children: [new TextRun({ children: [PageNumber.CURRENT], font: FONT, size: 22 })] })] }) },
    children: [...cover, ...abstract, ...index, ...body],
  }],
});

Packer.toBuffer(doc).then((b) => { fs.writeFileSync(OUT, b); console.log("wrote", OUT, tableNo, "tables", figNo, "figures"); });
