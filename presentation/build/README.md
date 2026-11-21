# Rebuilding the presentation

1. Redraw the deck graphics from the real outputs:

   ```bash
   python3 presentation/build/make_figs.py . presentation/build/figs
   ```

   The dashboard screenshots (`figs/dash_*.png`) were captured from the running app with Playwright.

2. Install the Node dependencies once, in `presentation/build`:

   ```bash
   npm install pptxgenjs react-icons react react-dom sharp playwright
   ```

3. Build the deck. `SKILL_DIR` must point to a folder containing `scripts/apply_theme.js`, the theme-writer helper that ships with the pptx authoring skill:

   ```bash
   SKILL_DIR=<pptx-skill-dir> REPO=$PWD OUTFILE=presentation/Ecommerce_Optimization_Final_Presentation.pptx node presentation/build/build.js
   ```

4. Render the cheat sheet to PDF:

   ```bash
   node presentation/build/pdf.js presentation/Presentation_Viva_Cheat_Sheet.pdf
   ```

`forecast_series.json` holds the weekly CONUS network totals extracted from `data/outputs/unit_demand_predictions.csv` and `order_demand_predictions.csv`, which are git-ignored.

## Easy version

`build_easy.js` builds `Ecommerce_Optimization_Easy_Presentation.pptx`: 12 slides in plain language, with no formulas and with simple speaker notes. It reuses the same figures and the same verified numbers. Build it the same way as step 3, with `build_easy.js` and a different `OUTFILE`.
