# Entrega — rama `backlog-julio` (21-jul-2026)

Todo el backlog implementado **en una rama aparte**. `main` sigue exactamente como
estaba: producción no cambió y no cambia hasta que tú hagas el merge.

```powershell
git log --oneline main..backlog-julio     # los 6 commits nuevos
git checkout backlog-julio                # para probarlo local
```

**Verificación**: 129 tests de API en verde (eran 68), `tsc --noEmit` limpio,
`next build` completo con las 4 páginas nuevas.

---

## Qué hay en la rama

### 1. Margen FORD
Entre dos productos que el modelo sugiere por igual, ahora se ve cuál deja más plata.

- 5 columnas nuevas en el sugerido (ocultas por defecto) + en el Excel + tarjeta en la ficha.
- **Decisión que tomé sin consultarte** (dormías): el precio de venta es el **público**
  (sin IVA). El **flota** se calcula aparte y el **dealer** NO se usa como precio de venta
  —es lo que FORD le cobra al concesionario— sino como `Sobrecosto vs Dealer %`, para
  detectar compras por sobre la lista. Si prefieres otro precio como principal, es una
  línea en `apps/api/src/services/margen.py` (`PRECIO_VENTA_PRINCIPAL`).
- Si falta el precio o el costo, la columna queda vacía: no se inventan márgenes.
  El margen negativo **sí** se muestra.

### 2. Panel de salud del inventario (`/inventario`)
Dónde está la plata detenida y dónde falta.

- Inmovilizado (stock sin demanda), sobre-stock (umbral elegible 90/180/365 días),
  quiebres con demanda, bajo punto de pedido (contando tránsito), cobertura mediana.
- Valorizado en CLP, desglose por sucursal y top 25 de productos con más plata detenida.
- El stock **sin costo unitario** se reporta aparte en vez de contarse como cero.

### 3. Mesa de incidencias (`/incidencias`)
- Se reporta desde donde se vio la falla: el botón de la ficha del producto manda
  producto y sucursal con el reporte.
- Cada usuario ve lo suyo; tú ves todo y gestionas (en revisión / responder y cerrar /
  descartar). Al cerrar, le llega la respuesta al que reportó por la campanita.

### 4. Historia diaria + alertas
- Después de cada sync se guarda una foto del sugerido (solo filas con actividad,
  retención 60 días configurable). En la ficha del producto aparece un gráfico de
  evolución apenas hay dos días guardados.
- Notificación **por sucursal** con quiebres y bajo punto de pedido (agregada; una por
  producto serían miles al día).
- Todo el bloque corre **después** del commit de la carga y no propaga errores.

### 5. Motor propio en modo sombra ⭐
La pieza para dejar el Power BI, sin arriesgar nada.

- El motor corre en tu PC con los Excel de SharePoint y manda su resultado a
  `/api/admin/motor/comparar`, que **solo compara** contra lo vigente y guarda un reporte.
  **No escribe una sola fila en `sugerido`.**
- El panel con la paridad, las mayores divergencias y el historial sale en *Cargar datos*.
- El día del switch: el mismo CSV entra por el endpoint de carga (`--oficial` en el job).
  No hace falta código nuevo.

### 6. Cierre del loop y simulador
- **Ya Pedido**: registrar que una línea se pidió (con N° de OC). Columna en la grilla y
  bloque en la ficha. Informativo, no descuenta del sugerido. Caduca a los 45 días.
- **Simulador** (`/simulador`): mueve ciclo de orden, nivel de servicio por clase y lead
  time, y muestra el impacto en unidades y CLP antes de aplicarlo. Usa las constantes
  exactas del modelo; el test clave es que sin cambiar nada reproduce el sugerido vigente.

---

## Antes de mergear

1. Pruébalo local (`git checkout backlog-julio`, levantar API y web).
2. Al hacer merge y push, `create_all()` crea las 5 tablas nuevas solas
   (`enlace_documento`, `incidencia`, `sugerido_snapshot`, `comparacion_motor`,
   `linea_pedida`). Son todas aditivas: ninguna toca `sugerido`.
3. `apps/web/components/shell.tsx` e `indicador-sync.tsx` **no** están en ningún commit
   (no son míos).

## Lo que necesito de ti para seguir con el motor

1. El Excel del **seguimiento de compras nacional** (el de mayor volumen; hoy sale del SQL).
   El lector ya está escrito y probado con datos sintéticos, pero no contra el archivo real.
2. Los **respaldos de ventas 2025 y 2026**: los que hay (2024, 2020-2023) no cubren el
   período que usa el sugerido hoy (jul-2025 → jun-2026), así que la reconstrucción no se
   pudo comparar 1:1 contra el Power BI todavía.
3. Sincronizar la biblioteca de SharePoint a una carpeta local y apuntar ahí
   `MOTOR_CRUDOS_DIR` para correr el job en sombra.
