/** Verifica el filtro pegando codigos TRUNCADOS de productos que SI estan en la vista.
 *  Estrategia: lee un producto real de la tabla, le saca el ultimo caracter, y lo pega.
 *  La expansion por prefijo deberia volverlo a encontrar.
 */
import { chromium } from "@playwright/test";

const URL = process.env.VERCEL_URL ?? "https://olataforma-sugerencias-web.vercel.app";
const EMAIL = process.env.LOGIN_EMAIL ?? "fmora@curifor.com";
const PASS = process.env.LOGIN_PASSWORD ?? "123456";

async function main() {
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();

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

    // Tomar 3 productos DISTINTOS reales de la tabla
    const todos = await page.$$eval(
      ".ag-row .ag-cell[col-id='producto']",
      (cells) => cells.map((c) => c.textContent?.trim() ?? "")
    );
    const productos = [];
    const seen = new Set();
    for (const p of todos) {
      if (p && !seen.has(p) && p.length > 2) {
        seen.add(p); productos.push(p);
      }
      if (productos.length === 3) break;
    }
    console.log("   Productos reales en la vista:", productos);

    // Truncar el ultimo caracter de cada uno (simulando que el BI los muestra cortados)
    const truncados = productos.map((p) => p.slice(0, -1));
    const PEGADO = truncados.join("\n");
    console.log("   Truncados a pegar:", truncados);

    console.log("2. Abrir filtro de Producto");
    const headerProducto = page.locator(".ag-header-cell[col-id='producto']").first();
    await headerProducto.locator(".ag-header-icon").first().click();
    await page.waitForSelector('input[placeholder*="Buscar en Producto"]', { timeout: 10000 });

    console.log("3. Pegar codigos truncados");
    await page.evaluate(async (text) => {
      const input = document.querySelector('input[placeholder*="Buscar en Producto"]');
      input.focus();
      const dt = new DataTransfer();
      dt.setData("text/plain", text);
      input.dispatchEvent(new ClipboardEvent("paste", { clipboardData: dt, bubbles: true }));
    }, PEGADO);

    await page.waitForSelector("text=Lista pegada", { timeout: 5000 });

    // Leer el feedback
    const feedback = await page.locator("p:has-text('pegado')").first().textContent().catch(() => "");
    console.log("   Feedback:", feedback);

    const matchedValues = await page.$$eval(
      ".ag-popup label .truncate, body label .truncate",
      (els) => els.map((e) => e.textContent?.trim() ?? "").filter(Boolean)
    );
    console.log("   Valores en la lista pegada:", matchedValues);

    console.log("4. ACEPTAR");
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

    const setProductos = new Set(productos);
    const indeseados = unicos.filter((p) => !setProductos.has(p));
    const faltantes = productos.filter((p) => !unicos.includes(p));

    console.log("\n=== RESULTADO ===");
    console.log("Indeseados:", indeseados);
    console.log("Faltantes:", faltantes);
    console.log("Popup cerrado:", !popupVisible);

    if (indeseados.length === 0 && faltantes.length === 0 && !popupVisible) {
      console.log("\nFILTRO PREFIJO OK");
      process.exit(0);
    } else {
      console.log("\nFILTRO PREFIJO FALLA");
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
