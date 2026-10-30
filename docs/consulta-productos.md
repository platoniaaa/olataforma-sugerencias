# Consulta de productos (vista del vendedor)

Pantalla `Productos` del menu del vendedor de sucursal. Se pidio para que el vendedor
vea, sin pedirle nada a Abastecimiento: que hay, cuanto cuesta, donde hay stock, que viene
en camino, que reemplaza a que y cuanto se vende. Es la ficha del catalogo **sin costo**.

## Lo que ve y lo que NO ve

| Si | No |
|---|---|
| Codigo, descripcion, familia, procedencia, unidad | Costo, proveedor, margen |
| Precio de venta | Stock minimo, maximo, clasificacion de stock, parametros de compra |
| Stock por sucursal (todas) | El chat de la plataforma: sus herramientas devuelven costo |
| Unidades en transito por sucursal, con desde cuando se pidieron | De quien es cada orden de compra |
| Reemplazos del mix y lo que dice FORD | Los motivos internos del sugerido de compras |
| Un grafico de venta (12 meses) con filtro por sucursal | |

El dato no puede viajar al navegador (se veria en las herramientas del desarrollador),
asi que no basta con esconder la columna: las respuestas pasan por modelos que no la tienen
(`apps/api/src/schemas/consulta_productos.py`) y `tests/test_consulta_productos.py` busca los
campos prohibidos en el JSON. `/api/chat` exige `requiere_comprador` (como el resto de
Abastecimiento) y el `Shell` no monta el widget para el vendedor.

## Rutas

Todas bajo `/api/consulta/productos`, solo lectura, con sesion (`requiere_auth`). El orden
importa: las rutas con sufijo (`/sucursales`, `/ventas`, `/grupo-ventas`) van **antes** del
`{producto:path}` de cierre.

| Ruta | Para que |
|---|---|
| `GET ""` | Lista paginada (`q`, `familia`, `procedencia`, `categoria`, `con_stock`, `page`, `limit` hasta 200) |
| `GET /filtros` | Opciones de los desplegables |
| `GET /{producto}` | Detalle: datos, stock por sucursal, transito por sucursal, reemplazo FORD |
| `GET /{producto}/sucursales` | Opciones del filtro "Ver ventas de" |
| `GET /{producto}/ventas?sucursal_id=` | Venta mensual: total y, si se pide, de una sucursal |
| `GET /{producto}/grupo-ventas?sucursal_id=` | Historial de reemplazos: venta, stock y transito de cada codigo del grupo |

Web: `apps/web/app/consulta-productos/` (lista y `[producto]`), mas `grafico-stock-sucursal`,
`tabla-transito`, `grupo-reemplazos` y `grafico-ventas` en `components/`.

## Reglas de datos (no cambiarlas sin conversarlo)

- **El stock es el que el vendedor puede prometer.** Misma regla que la lista de precios
  (`precios_service._stock`, `bodega_cuenta`, `bodegas_excluidas`): sin bodegas no
  disponibles (danados, devolucion, scrap, sin bodega), sin el stock de Frontera y sin saldos
  en cero o negativos. Lo implementan `stock_service.filtro_vendible`,
  `stock_vendible_por_producto` y `productos_con_stock_vendible`. Depende de la tabla
  `bodega_tipo`: **si esta vacia no se excluye ninguna bodega** (ver `docs/precios.md`).
- **"Solo con stock" filtra con el stock vivo**, no con `producto_catalogo.stock_total`, que
  es una foto vieja del maestro.
- **El transito es solo el de Curifor** (`origen != FRONTERA`; sin origen cuenta como Curifor).
  Se muestra por sucursal de destino, y por codigo dentro del grupo de reemplazos.
- **La venta es la ventana de 12 meses** terminada en el ultimo mes cargado
  (`_ventana_12_meses`), igual que el historial de reemplazos. El grafico del comprador
  (`/api/catalogo/{p}/ventas`) conserva su comportamiento de siempre.
- **Un solo grafico de ventas.** Si el codigo tiene reemplazos se muestra el historial apilado;
  si no, la venta del codigo solo (`GrupoReemplazos` con la prop `alternativa`).
- Sucursales: "02 LINDEROS", "Linderos" y "linderos" son la misma. La clave se calcula con
  `sugerido_service.clave_sucursal` y las variantes escritas en la venta con
  `variantes_de_sucursal`.
- Los errores se muestran en palabras del vendedor (`mensajeLectura` en `lib/api-client.ts`):
  nunca la ruta de la API ni el codigo HTTP.

## Como probarla

```bash
cd apps/api && python -m pytest tests/test_consulta_productos.py -q
cd apps/web && npx vitest run && ../../node_modules/.bin/tsc --noEmit -p tsconfig.json
```

Con un vendedor real: entrar con una cuenta `es_vendedor`, abrir `Productos`, buscar un codigo,
abrirlo y revisar (1) que no aparezca la palabra costo en ninguna parte ni en la pestana Red de
las herramientas del navegador, (2) que el stock total no incluya danados, (3) que el filtro de
sucursal cambie la venta y la columna Stock del historial pero no las tarjetas de arriba.

## Pendientes y decisiones abiertas

- **Pagina de inicio del vendedor.** Sigue siendo `Mis requerimientos` (login, logo y
  redireccion de `/`). Si consultar stock es lo que hace todo el dia, conviene mandarlo a
  `Productos`: es una decision de producto, no un defecto.
- **Procedencia.** Se muestra en la lista y el detalle. Si algun valor identifica a un proveedor
  o canal de compra, hay que quitarlo del modelo y de la pantalla.
- **Precio de venta.** La etiqueta no dice si es neto o con IVA; confirmarlo y rotularlo.
- **Busqueda.** `ILIKE '%q%'` sobre ~400 mil filas sin indice; lo usa mucha mas gente que
  antes. Si se nota lenta: indice `pg_trgm` en `producto` y `glosa`, y minimo de 3 letras.
- **Filtro de sucursal.** Las opciones salen de la venta de todo el grupo de reemplazos; una
  sucursal que solo vendio un codigo hermano muestra el grafico del codigo en cero (el
  historial de reemplazos de la misma pantalla si trae su venta).
- **Datos que viajan sin usarse:** `stock_por_sucursal[].origen`, `reemplazo_ford.aviso` y
  `extraido_en`. No son costo, pero convendria modelos propios.
- **Tabla de reemplazos en el celular** (6 columnas, scroll horizontal) y **texto equivalente
  de los graficos de venta** (hoy solo el de stock lo tiene).
- **Revision final del 30-10-2026** (4 revisores independientes + 2 escepticos por hallazgo, sobre
  `05076cc..b1fc6af`). Ninguna fuga de costo en las rutas nuevas. Quedaron sin corregir, por decision
  de tiempo, y conviene verlos en este orden:
  1. **Inventario ciclico (media, heredado).** Un `es_vendedor` al que se le asigna un rol en `ic_rol`
     recibe `costo_unitario`, `diferencia_valor` y los montos de sobrante/faltante en
     `/api/inventario-ciclico/items` y `/resumen`. Decidir con el dueño: o se quitan esos campos cuando
     el usuario es vendedor, o `guardar_rol` rechaza vendedores. **Mientras tanto: no asignar roles de
     inventario ciclico a los 24 vendedores nuevos.**
  2. **"Nuevo requerimiento" del vendedor (media, heredado).** `/api/requerimientos/buscar`, `/pegar` y
     `/producto/{p}` siguen sumando todas las bodegas (danados, Frontera, saldos negativos) y todo el
     transito: el mismo producto da 13 ahi y 5 en `Productos`. Arreglo: usar
     `stock_service.stock_vendible_por_producto`, `filtro_vendible` y `transito solo_curifor=True` en
     `requerimiento_service`. Es un cambio visible para el vendedor: consultarlo antes.
  3. **Modelos de respuesta propios** para `grupo-ventas`, `sucursales` y `filtros` (hoy son diccionarios
     con un `pop` manual) y para FORD y stock (viajan `aviso`, `extraido_en`, `origen`, `agrupado`).
  4. **Stock con error silencioso:** si falla la lectura de `stock_unificado`, la lista responde 200 con
     "Sin stock" en vez de un error.
  5. **Combinacion admin + vendedor:** el formulario de Usuarios la permite y conserva el acceso admin.
  6. `GET /api/actualizacion/estado` esta abierto a cualquier sesion y devuelve al vendedor el nombre
     del PC del motor y quien pidio el recalculo (heredado).
  7. Web: al elegir una sucursal desde "todas", la tabla del historial no avisa que esta actualizando;
     al volver del detalle no se restauran las paginas de "Ver mas" ni el scroll; objetivos tactiles
     de 19 px en los enlaces de codigo; el menu no resalta `Productos` dentro de un detalle; la tabla de
     reemplazos en celular (ver arriba).
  8. **Rendimiento de la lista:** cada pedido arma la subconsulta de "solo con stock" aunque no se
     pida (9 consultas, 2 lecturas de `bodega_tipo` y 2 `DISTINCT bodega`). Arreglo de una linea:
     pasar `con_stock_de` solo si `con_stock`, y calcular `bodegas_excluidas` una vez por pedido.
  9. **Bordes del stock y el transito** (bajos): saldos negativos de transito se suman en la API pero la
     tabla solo cuenta los mayores a cero; filas de stock sin `sucursal_id` se dibujan con el nombre de la
     bodega en el grafico y se descartan al filtrar por sucursal; `clave_sucursal` no es idempotente
     (una sucursal llamada "02 3 NORTE" daria "3 NORTE" y luego "NORTE"); si `bodega_tipo` esta vacia o
     falla su lectura no se excluye nada y se cuentan los danados.
  10. Orden: `/api/catalogo/{p}/grupo-ventas` (comprador) ahora trae ademas la clave `sucursal: null`;
     el comentario de `main.py` sobre el chat quedo viejo.
  11. **Rama remota `respaldo-salida-vista-vendedor-productos`:** su commit `c7bfad8` contiene la capa
     temporal de vista previa (`apps/web/app/consulta-productos/layout.tsx`), que REEMPLAZA los datos de la
     vista por datos inventados. No fusionarla ni hacer cherry-pick a `main`; borrarla cuando ya no sirva.
- Estan sin tocar a proposito (heredados): botones de menos de 44 px en `Button`, el cajon del
  menu cerrado sigue en el orden de tabulacion, inputs de 13 px (zoom en iOS).
