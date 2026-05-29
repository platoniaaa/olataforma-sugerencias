/** Verifica que escribir en el buscador + ACEPTAR filtra (sin desmarcar nada). */
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

    // Tomar un producto real de la tabla
    const productos = await page.$$eval(
      ".ag-row .ag-cell[col-id='producto']",
      (cells) => cells.map((c) => c.textContent?.trim() ?? "").filter(Boolean)
    );
    const target = productos[0];
    console.log("   Buscare:", target);

    console.log("2. Abrir filtro de Producto");
    const headerProducto = page.locator(".ag-header-cell[col-id='producto']").first();
    await headerProducto.locator(".ag-header-icon").first().click();
    await page.waitForSelector('input[placeholder*="Buscar en Producto"]', { timeout: 10000 });

    console.log("3. Escribir el codigo en el buscador (SIN desmarcar nada)");
    await page.fill('input[placeholder*="Buscar en Producto"]', target);
    await page.waitForTimeout(500);

    // Verificar que (Seleccionar todo) sigue marcado (estado inicial)
    const todoMarcado = await page.locator('label:has-text("(Seleccionar todo)") input[type="checkbox"]').isChecked();
    console.log("   (Seleccionar todo) marcado?", todoMarcado);

    console.log("4. ACEPTAR (sin tocar checkboxes)");
    await page.click('button:has-text("ACEPTAR")');
    await page.waitForTimeout(1500);

    const popupVisible = await page.isVisible('input[placeholder*="Buscar en Producto"]');
    console.log("   Popup cerrado?", !popupVisible);

    const productosFiltrados = await page.$$eval(
      ".ag-row .ag-cell[col-id='producto']",
      (cells) => cells.map((c) => c.textContent?.trim() ?? "")
    );
    const unicos = [...new Set(productosFiltrados)];
    console.log("5. Productos UNICOS visibles tras filtrar:", unicos);

    console.log("\n=== RESULTADO ===");
    if (!popupVisible && unicos.length === 1 && unicos[0] === target) {
      console.log("FILTRO POR BUSQUEDA OK (sin desmarcar)");
      process.exit(0);
    } else {
      console.log("FILTRO POR BUSQUEDA FALLA");
      console.log("Esperado: solo", target, "| obtuvo:", unicos);
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
