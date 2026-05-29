/** Verifica que el filtro por columna es modo CONTIENE (no snapshot exacto). */
import { chromium } from "@playwright/test";

const URL = process.env.VERCEL_URL ?? "https://olataforma-sugerencias-web.vercel.app";
const EMAIL = process.env.LOGIN_EMAIL ?? "fmora@curifor.com";
const PASS = process.env.LOGIN_PASSWORD ?? "123456";

async function main() {
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  page.on("pageerror", (e) => console.log("[page error]", e.message));

  try {
    console.log("1. Login");
    await page.goto(URL, { waitUntil: "networkidle", timeout: 60000 });
    await page.waitForTimeout(2000);
    if (page.url().includes("/login")) {
      await page.fill('input[type="email"]', EMAIL);
      await page.fill('input[type="password"]', PASS);
      await page.locator('button[type="submit"], button:has-text("Entrar")').first().click();
      await page.waitForURL((u) => !u.toString().includes("/login"), { timeout: 60000 });
    }
    await page.waitForSelector(".ag-row", { timeout: 90000 });
    await page.waitForTimeout(1500);

    // --- Test 1: codigo exacto ---
    const productos = await page.$$eval(
      ".ag-row .ag-cell[col-id='producto']",
      (cells) => cells.map((c) => c.textContent?.trim() ?? "").filter(Boolean)
    );
    const target = productos[0];
    console.log("\n=== Test 1: codigo exacto ===");
    console.log("   Busqueda:", target);

    let header = page.locator(".ag-header-cell[col-id='producto']").first();
    await header.locator(".ag-header-icon").first().click();
    await page.waitForSelector('input[placeholder*="Buscar en Producto"]', { timeout: 10000 });
    await page.fill('input[placeholder*="Buscar en Producto"]', target);
    await page.waitForTimeout(400);
    await page.click('button:has-text("ACEPTAR")');
    await page.waitForTimeout(1500);

    let unicos = [...new Set(await page.$$eval(
      ".ag-row .ag-cell[col-id='producto']",
      (cells) => cells.map((c) => c.textContent?.trim() ?? "")
    ))];
    console.log("   Productos visibles:", unicos);
    const test1OK = unicos.length === 1 && unicos[0] === target;
    console.log(test1OK ? "   OK" : "   FALLA");

    // Limpiar filtro
    await header.locator(".ag-header-icon").first().click();
    await page.waitForSelector('button:has-text("Borrar filtro")', { timeout: 10000 });
    await page.click('button:has-text("Borrar filtro")');
    await page.waitForTimeout(1500);

    // --- Test 2: texto parcial (contiene) ---
    console.log("\n=== Test 2: texto PARCIAL (modo contiene) ===");
    // Busqueda parcial que deberia matchear varios productos
    const parcial = target.split(" ")[0]; // ej. "70" del "70 2723982"
    console.log("   Busqueda parcial:", JSON.stringify(parcial));

    header = page.locator(".ag-header-cell[col-id='producto']").first();
    await header.locator(".ag-header-icon").first().click();
    await page.waitForSelector('input[placeholder*="Buscar en Producto"]', { timeout: 10000 });
    await page.fill('input[placeholder*="Buscar en Producto"]', parcial);
    await page.waitForTimeout(400);
    await page.click('button:has-text("ACEPTAR")');
    await page.waitForTimeout(1500);

    unicos = [...new Set(await page.$$eval(
      ".ag-row .ag-cell[col-id='producto']",
      (cells) => cells.map((c) => c.textContent?.trim() ?? "")
    ))];
    console.log("   Productos UNICOS visibles:", unicos.slice(0, 10), unicos.length > 10 ? `... y ${unicos.length-10} mas` : "");

    // TODOS los productos visibles deben contener el texto parcial
    const todosContienen = unicos.every((p) => p.toLowerCase().includes(parcial.toLowerCase()));
    const masDeUno = unicos.length >= 1;  // al menos uno coincide
    const test2OK = todosContienen && masDeUno;
    console.log(test2OK ? "   OK (todos contienen y hay matches)" : "   FALLA");

    console.log("\n=== RESULTADO FINAL ===");
    if (test1OK && test2OK) {
      console.log("FILTRO CONTIENE OK");
      process.exit(0);
    } else {
      console.log("FILTRO CONTIENE FALLA");
      process.exit(2);
    }
  } catch (e) {
    console.error("ERROR:", e.message);
    process.exit(1);
  } finally {
    await browser.close();
  }
}

main();
