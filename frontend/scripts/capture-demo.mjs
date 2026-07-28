#!/usr/bin/env node
/**
 * Capture synthetic-data screenshots for the public portfolio.
 *
 * Prerequisites:
 *   1. uv run ecom-demo          (build the demo DuckDB)
 *   2. uv run ecom-api            (start the API with ECOM_API_DATA_MODE=demo)
 *   3. npm --prefix frontend run dev  (start the Vite dev server)
 *
 * Usage:
 *   npm --prefix frontend run capture:demo
 *
 * Outputs:
 *   docs/assets/ui/overview.png         (desktop, 1440x900)
 *   docs/assets/ui/overview-mobile.png  (mobile, 390x844)
 *   docs/assets/ui/anomaly-detail.png   (desktop, 1440x900)
 */
import { chromium } from "playwright";
import { mkdirSync, existsSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(__dirname, "..", "..");
const outputDir = resolve(repoRoot, "docs", "assets", "ui");
const baseUrl = process.env.ECOM_FRONTEND_URL || "http://127.0.0.1:5173";
const apiUrl = process.env.ECOM_API_URL || "http://127.0.0.1:8000";

async function checkApiHealth() {
  try {
    const res = await fetch(`${apiUrl}/api/health`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    if (data.data_mode !== "demo") {
      console.error(`ERROR: API data_mode is "${data.data_mode}", expected "demo".`);
      console.error("Set ECOM_API_DATA_MODE=demo before running this script.");
      process.exit(1);
    }
    if (!data.database_exists) {
      console.error("ERROR: API reports database does not exist. Run `uv run ecom-demo` first.");
      process.exit(1);
    }
    console.log("API health OK: demo mode, database exists.");
  } catch (err) {
    console.error("ERROR: Cannot reach API at", apiUrl);
    console.error("Start the API with: ECOM_API_DATA_MODE=demo uv run ecom-api");
    process.exit(1);
  }
}

async function getFirstAnomalyId() {
  try {
    const res = await fetch(`${apiUrl}/api/anomalies?page=1&page_size=1`);
    const data = await res.json();
    if (data.items && data.items.length > 0) {
      return data.items[0].attribution_id;
    }
  } catch {
    // fall through
  }
  return null;
}

async function captureScreenshots() {
  mkdirSync(outputDir, { recursive: true });

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 2,
  });
  const page = await context.newPage();

  // --- Desktop overview ---
  console.log("Capturing desktop overview...");
  await page.goto(baseUrl, { waitUntil: "networkidle", timeout: 30000 });
  await page.waitForTimeout(2000);

  // Verify the Synthetic Demo badge is present
  const badge = await page.locator(".demo-badge").count();
  if (badge === 0) {
    console.error("ERROR: Synthetic Demo badge not found on overview page.");
    await browser.close();
    process.exit(1);
  }
  console.log("  Verified: Synthetic Demo badge is present.");

  await page.screenshot({
    path: resolve(outputDir, "overview.png"),
    fullPage: false,
  });
  console.log("  Saved: docs/assets/ui/overview.png");

  // --- Anomaly detail ---
  const anomalyId = await getFirstAnomalyId();
  if (anomalyId) {
    console.log(`Capturing anomaly detail (id=${anomalyId})...`);
    await page.goto(`${baseUrl}/anomalies/${anomalyId}`, {
      waitUntil: "networkidle",
      timeout: 30000,
    });
    await page.waitForTimeout(2000);
    await page.screenshot({
      path: resolve(outputDir, "anomaly-detail.png"),
      fullPage: false,
    });
    console.log("  Saved: docs/assets/ui/anomaly-detail.png");
  } else {
    console.warn("  WARNING: No anomaly events found; skipping anomaly-detail.png");
  }

  // --- Mobile overview ---
  console.log("Capturing mobile overview...");
  const mobileContext = await browser.newContext({
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 3,
    isMobile: true,
  });
  const mobilePage = await mobileContext.newPage();
  await mobilePage.goto(baseUrl, { waitUntil: "networkidle", timeout: 30000 });
  await mobilePage.waitForTimeout(2000);

  const mobileBadge = await mobilePage.locator(".demo-badge").count();
  if (mobileBadge === 0) {
    console.error("ERROR: Synthetic Demo badge not found on mobile overview.");
    await browser.close();
    process.exit(1);
  }

  await mobilePage.screenshot({
    path: resolve(outputDir, "overview-mobile.png"),
    fullPage: false,
  });
  console.log("  Saved: docs/assets/ui/overview-mobile.png");

  await browser.close();
  console.log("\nAll screenshots captured successfully.");
}

await checkApiHealth();
await captureScreenshots();
