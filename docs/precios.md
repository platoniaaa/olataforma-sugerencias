# Lista de precios

La lista que se sube al ERP, viva en la plataforma. Reemplaza al Excel
`LISTA DE PRECIOS.xlsx` y al `.exe` que corria en el PC de Hugo: la regla es la
misma, pero corre donde estan los datos (stock, costo, compras y ventas que la
plataforma ya recibe del motor) y las decisiones de las personas quedan en una
tabla que ningun job toca.

Pantallas: `/precios` (la lista) y `/precios/politicas` (factores y rubros).

## Como se decide el precio

En este orden; gana el primero que aplica (`services/precios_service.calcular`):

1. **Precio fijo** (decision humana): ese es el precio, pase lo que pase.
2. **Congelado** (decision humana): el precio que tenia al congelar, aunque el
   costo cambie despues.
3. **Stock 0 y nada en transito**: precio 0 (el ERP no lo ofrece).
4. **No es producto** (servicios, mano de obra): sin precio.
5. **Margen fijo** (decision humana, % sobre la venta): `ROUND(costo x 1/(1 - margen))`.
   Sigue al costo y sin stock cae a 0 como la regla. No convive con el precio fijo.
6. **Tipo Sugerido**: la lista del proveedor (Gildemeister).
7. **El resto**: `ROUND(costo x factor)`, redondeando como Excel (la mitad hacia
   arriba).

El **factor** sale de la politica por (tipo, procedencia).

El **tipo** se decide: escrito a mano > la glosa empieza con `NEU` (neumatico) >
el tipo del rubro (`politica_rubro`).

**Un factor propio para un rubro (14-10-2026).** El factor es por tipo, asi que
un rubro que comparte tipo con otros no puede moverse solo. En
`/precios/politicas` se crea un tipo nuevo ("Agregar tipo": nombre, factor
nacional e importado, descuento) y se le asigna al rubro en la tabla de Rubros.
Antes de guardar, `POST /api/precios/politica/vista-previa` corre la misma regla
con la politica propuesta y dice cuantos precios cambian, cuantos productos del
rubro tienen el tipo escrito a mano (esos no siguen al rubro) y da ejemplos.
`PUT /api/precios/politica` guarda factores, rubros y `seguir_al_rubro` juntos
(si algo no valida, no se guarda nada) y recalcula UNA vez. `seguir_al_rubro`
borra el tipo escrito a mano de los productos de esos rubros, para que tomen el
tipo del rubro; queda en auditoria como `precios_tipo_manual_quitado`. Un tipo
nuevo escrito con otra mayuscula o con el alias ("liviano", "Baterias") actualiza
el que existe en vez de duplicarlo.

La **procedencia**: escrita a mano > procedencia forzada del rubro > ultima
compra (si la mas reciente esta en el seguimiento de importacion es Importado;
si esta en el nacional, Nacional) > lo que dice el maestro del ERP > `SIN
REVISION` (queda sin precio hasta que alguien decida).

## Las tablas

| Tabla | Que es | Quien la escribe |
|---|---|---|
| `precio_producto` | Una fila por producto con todo lo calculado. Se pisa en cada recalculo. `origen` distingue lo que vino del ERP (`maestro`) de lo creado en la plataforma (`manual`): una recarga del maestro borra solo lo primero. | el recalculo y las cargas |
| `precio_override` | Precio fijo, margen fijo, congelar, tipo/procedencia a mano, "no es producto", observacion. | solo personas |
| `politica_precio` | Factor por (tipo, procedencia). | admin |
| `politica_rubro` | Tipo y procedencia forzada por rubro. | admin |
| `precio_cambio` | Que cambio en cada recalculo (procedencia, costo, stock, precio, tipo), pendiente hasta que alguien lo marca visto. | el recalculo |
| `precio_envio` | Que precio y costo se mando al ERP, cuando y quien. Es lo que hace posible exportar solo las diferencias. | la exportacion |

## Permisos

- Ver y exportar: cualquiera de Abastecimiento.
- Editar un precio, crear un producto, recalcular, marcar cambios vistos:
  admin o email en `EMAILS_PRECIOS` (variable de entorno, separada por comas).
- La politica (factores y rubros): el mismo permiso que editar un precio.
  Cada cambio queda en `auditoria_log` (`politica_precio_editada` /
  `politica_rubro_editada`) con el usuario y el valor anterior, y se ve en
  la pantalla de Auditoria.

## Cargas

- **Primera carga** desde el Excel: `POST /api/admin/precios/politica` (factores,
  rubros, no-productos, precios sugeridos) y `POST /api/admin/precios/cargar` por
  tandas. Lo humano del Excel (Obs Precio + Precio Fijo, Congelar) se convierte
  en overrides. Un Precio Fijo sin Obs se ignora, igual que lo ignora la
  formula del Excel.
- **Compras** (la regla de procedencia): `POST /api/admin/precios/compras` con
  la ultima recepcion importada y el ultimo P/E nacional por producto. Fusiona:
  nunca borra una fecha.
- **Costos**: `POST /api/admin/precios/costos` con `{producto, costo}` de TODOS
  los productos (columna Costo del Excel de stock del ERP), en la misma corrida
  en que el motor publica el stock. Para lo que el sugerido evalua, ademas manda
  `dim_producto.costo_unitario` (lo reconstruye `cargar-sugerido`). NO se usa
  `producto_catalogo.costo`: es una carga unica sin fecha.
- **Stock, precio del proveedor y ultima venta** los toma el recalculo de las
  tablas que el motor ya publica (`stock_unificado`, `stock_transito`,
  `sugerido`, `venta_historica`). Del stock cuenta solo el de Curifor y solo
  bodegas reales: `stock_unificado` trae tambien Frontera porque el sugerido la
  usa (decision del 07-10-2026). El transito igual: solo las OC de Curifor.

## Editar la lista con Excel (14-10-2026)

Botón "Editar con Excel" en `/precios` (solo quien puede editar precios). Se baja el
archivo, se edita y se vuelve a cargar; antes de guardar se ve que cambia, producto
por producto.

- **Descarga**: `GET /api/precios/exportar?formato=editable` es la lista completa (CSV,
  `;`, BOM) más las columnas `Obs`, `Congelar`, `No es producto` y `Referencia`. El
  factor sale con hasta 4 decimales (un margen fijo da 1,5385). `Obs`, `Glosa`,
  `Rubro` y `Tipo` que empiezan con `=`, `+`, `-` o `@` salen con un apóstrofe delante
  (Excel las abriría como fórmula: "-5% convenio" salía `#NOMBRE?` y un
  `=HYPERLINK(...)` se ejecutaba); al leer, se quita.
- **Lo que se edita** (cada columna hace lo mismo que su equivalente en la ficha; vacío
  quita la decisión): `Tipo` y `Procedencia` (escritos a mano; el tipo se acepta con o
  sin tildes y con los alias de la política), `Factor` (factor propio = margen fijo
  `(1 - 1/f) x 100`), `Precio final` (precio fijo), `Obs`, `Congelar` y `No es
  producto` (Sí/No). Lo demás (costo, stock, precio ERP, estado, descuento) viene del
  ERP y del motor, y si se edita, no se carga. Precio fijo y factor propio no
  conviven: la fila con los dos es un error.
- **La columna `Referencia`** guarda, por producto, lo que mostraba el archivo al
  bajarlo, en 10 partes ASCII (sobreviven a cualquier página de códigos):
  `huella del código|tipo|procedencia|factor|precio|huella de la obs|la misma como la
  deja Excel (cp1252)|congelar|no es producto|huella de las decisiones`. Empieza con un
  hash para que Excel nunca la lea como fórmula. Se carga SOLO lo que la persona cambió respecto de esa
  referencia, no lo que difiere de lo que hay hoy: el motor recalcula los precios cada
  noche y eso no es una edición (compararlo contra hoy habría vuelto precio fijo cada
  precio que se movió). Tres huellas la protegen:
  - la de las **decisiones** resume `precio_override`: si cambió desde la descarga y
    el archivo edita ese producto, es **conflicto** y se omite, porque cargarlo
    desharía en silencio lo que otra persona hizo en la ficha. Si lo que dice el
    archivo ya es lo que hay (el mismo archivo subido dos veces, o una carga cuya
    respuesta se perdió), es "sin cambios", no conflicto;
  - la del **código** ata la referencia a su producto: ordenar o pegar solo esa
    columna la dejaba en otra fila, y los precios de esa fila se volvían precio fijo
    sin que nada avisara. Ahora es un error;
  - la de la **obs** evita que una nota con cualquier carácter parezca una edición, y
    la segunda (cp1252) que no lo parezca cuando Excel guarda como "CSV" y cambia por
    `?` lo que no cabe (emojis, flechas).

  Sin `Referencia` el archivo no se carga. Excel con "disminuir decimales" guarda
  1,1429 como 1,14 o 1,143: si solo cambió ese redondeo (mitad hacia arriba, como
  Excel), no cuenta como edición del factor. Costo conocido: escribir a propósito el
  valor redondeado tampoco se distingue.
- **Carga**: `POST /api/precios/carga/vista-previa` lee y compara sin guardar;
  `POST /api/precios/carga` vuelve a leer el archivo y aplica. **Todo o nada**: un
  error de validación (factor fuera de rango, tipo que no existe en la política,
  código repetido, Referencia de otro producto, precio fijo y factor a la vez...)
  bloquea la carga entera. Se omiten y se listan los conflictos, los códigos que no
  están en la lista y las filas sin `Referencia`. Si el producto cambió en la ficha
  después de bajar el archivo y el archivo lo edita, es conflicto aunque la combinación
  sea inválida (precio fijo y factor puestos por el otro): solo se omite esa fila. Al
  aplicar, las filas se bloquean (`FOR UPDATE`) y se vuelve a calcular contra lo que
  hay AHORA: otra persona que edite justo entre comparar y escribir no se pisa, y el
  reintento de una respuesta perdida da "sin cambios".
- **Quitar decisiones**: una celda vacía quita la decisión, y un `.xlsx` con celdas de
  error (`#N/D`, `#REF!`) las entrega vacías (calamine no distingue). Si una carga
  quita 10 decisiones o más (`UMBRAL_QUITAS`), la pantalla pide marcar una
  confirmación y el servidor exige `confirmar_quitas=true`: un BUSCARV roto no puede
  borrar precios fijos en silencio.
- **Qué deja**: una fila de auditoría `precio_override` por producto ("(carga desde
  Excel)") y una de resumen `precios_carga_excel`, más una notificación. Recalcula SOLO
  los productos editados, con la política cargada una vez y leída ANTES de escribir
  (`politica.factores` se traga los errores y hace rollback: leída después se llevaba
  lo escrito), y no crea "cambios sin revisar": son decisiones de una persona.
- **Formatos**: `.csv` (UTF-8; UTF-16 de "Texto Unicode", con o sin BOM; o la página
  de códigos de Windows: cp1252 de "CSV", cp850 de "CSV MS-DOS" y mac_roman de "CSV
  Macintosh", que se distinguen porque el encabezado `Descuento máximo` solo se lee
  entero con la correcta; separador `;`, `,` o tabulación; fin de línea CRLF, LF o CR)
  y `.xlsx`. El `.xlsx` se lee con `python-calamine`: `openpyxl` tardaba 36 s en 40 mil
  filas en un PC y mucho más en el plan gratis de Render. Calamine arma la hoja entera
  en memoria y `ABORTA el proceso` con una referencia de celda absurda, así que antes
  de abrirlo se escanea el XML de la PRIMERA hoja por bloques: última fila y columna
  con contenido (no cuentan las celdas vacías con formato), referencias dañadas y
  tamaño descomprimido. No se confía en la `<dimension>` declarada (falta en los
  archivos en streaming y una celda de más la hace mentir). Topes: 30 MB, 150 MB
  descomprimido, 250.000 filas y 3 millones de celdas (también en CSV). Cualquier
  archivo que no sirve da un 422 con un mensaje, nunca un 500. Los códigos se recortan
  solo en los bordes: `19  FB5Z15201H` (dos espacios) y `19 FB5Z15201H` son productos
  distintos.
- **Limitación conocida**: Excel reinterpreta al abrir un CSV las notas que parecen
  fecha o número (`31/12` pasa a `31-dic`, `0045` a `45`, `1e3` a `1,00E+03`); al
  volver, parecen una edición de la nota. La vista previa muestra el "antes → después".
  Un `.xlsx` generado por la plataforma evitaría esto, pero tardaba 83 s.
- **Medido** con la copia local de 60 mil productos: bajar el archivo 3,2 s (11 MB);
  leer y comparar sin ediciones 1,5 a 1,9 s (CSV) o 7,7 s (.xlsx, de los cuales ~2 s
  son el escaneo previo); aplicar 1.500 ediciones 2,0 s en total; subir el mismo
  archivo otra vez 1,4 s y "sin cambios"; un recálculo completo después no cambia
  ningún precio.
- **Revisión**: se hicieron tres pasadas de revisión adversarial antes de publicar. Las
  dos primeras encontraron 25 y 29 defectos reales (varios de pérdida silenciosa de
  datos: una Referencia desalineada convertía precios en precio fijo; un `.xlsx` de
  26 KB tumbaba la API; las notas con emojis se sobrescribían con `?`).

## Exportar al ERP

`GET /api/precios/exportar?formato=erp` genera `SKU | Precio_Optimo | Descuento`.
El descuento es el mismo de la columna `Descuento+1` de la lista completa: el
descuento maximo de la politica mas uno, salvo cuando es 0 (desde el 09-10-2026;
antes la tercera columna era el costo). Con `solo_diferencias=true` salen solo los productos cuyo
precio o costo difiere de lo ultimo enviado (o nunca enviados). Cada
exportacion queda registrada en `precio_envio`.

**Que pasa si la descarga se corta (09-10-2026).** El navegador manda `lote=<uuid>`
en cada descarga del archivo del ERP. Si ese lote ya quedo registrado -el servidor
alcanzo a anotar el envio y la respuesta se perdio-, el reintento recibe el MISMO
archivo en vez de uno vacio. La pantalla reintenta sola los cortes de conexion y
los 502, 503 y 504 (hasta 4 veces, unos 76 s), y si el servidor no vuelve dice que
puede estar reiniciandose en vez de mostrar "Failed to fetch". Las filas de
"solo diferencias" salen de SQL con la misma condicion que el numero del boton.

**Codigos con espacio al final (13-10-2026).** En el ERP hay codigos creados con
un espacio al final ("15 MXD1454M "): eran 82 en el stock del 09-10-2026. Por
dentro la lista los guarda sin el espacio (`producto`), que es como cruzan con el
stock, las ventas y el sugerido. El codigo exacto queda en
`precio_producto.codigo_erp` -solo cuando difiere; None en el resto- y es el que
sale en el SKU del archivo del ERP y en el Producto de la lista completa. Lo llena
el feed del ERP (`POST /api/admin/precios/erp`) con el Excel de stock de cada dia;
una fila sin la clave `codigo_erp` no lo toca, y una que la trae en None lo limpia
(el ERP le saco el espacio).
