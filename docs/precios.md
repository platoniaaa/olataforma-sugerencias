# Lista de precios

La lista que se sube al ERP, viva en la plataforma. Reemplaza al Excel
`LISTA DE PRECIOS.xlsx` y al `.exe` que corria en el PC de Hugo: la regla es la
misma, pero corre donde estan los datos (stock, costo, compras y ventas que la
plataforma ya recibe del motor) y las decisiones de las personas quedan en una
tabla que ningun job toca.

Pantallas: `/precios` (la lista) y `/precios/politicas` (factores y rubros).

## Como se decide el precio

En este orden; gana el primero que aplica (`services/precios_service.calcular`):

1. **Precio fijo** (decision humana): ese es el precio, pase lo que pase. Mientras
   su periodo rija, si tiene uno (ver "Vigencia").
2. **Congelado** (decision humana): el precio que tenia al congelar, aunque el
   costo cambie despues. Tambien con periodo.
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
| `precio_producto` | Una fila por producto con todo lo calculado. Se pisa en cada recalculo. `origen` distingue lo que vino del ERP (`maestro`) de lo creado en la plataforma (`manual`): una recarga del maestro borra solo lo primero. `vigencia_aplicada` es el estado del periodo con que se calculo ese precio (interno: la API no lo expone). | el recalculo y las cargas |
| `precio_override` | Precio fijo, margen fijo, congelar, tipo/procedencia a mano, "no es producto", observacion y el periodo de vigencia (`vigente_desde`, `vigente_hasta`). | solo personas |
| `politica_precio` | Factor por (tipo, procedencia). | admin |
| `politica_rubro` | Tipo y procedencia forzada por rubro. | admin |
| `bodega_tipo` | Que bodegas cuentan para el stock: REAL, VIRT, ELIM y NODISP (ver "Bodegas"). | admin (carga) |
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
- Aplicar los vencimientos de vigencia a pedido (`POST /api/admin/precios/vigencias/aplicar`):
  admin. Lo demas de la vigencia lo hace la plataforma sola al leer (ver "Vigencia").

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
  `sugerido`, `venta_historica`). Del stock cuenta solo el de Curifor y de todas
  sus bodegas MENOS danados, devolucion y scrap (ver "Bodegas"): `stock_unificado`
  trae tambien Frontera porque el sugerido la usa (decision del 07-10-2026). El
  transito igual: solo las OC de Curifor, sin mirar bodega.

## Vigencia: precio fijo, margen fijo y congelar con fecha (20-10-2026)

Un precio fijo, un margen fijo o un congelado puede traer un **periodo**: `Desde` y
`Hasta`. Antes eran permanentes hasta que alguien se acordaba de quitarlos (los 342
precios fijos de produccion no tienen fecha y ninguna nota dice si eran temporales).

**Reglas** (`services/precios_service.py`: `estado_vigencia`, `vigencia_de`, `calcular`):

- **Un solo periodo por producto**: gobierna las tres decisiones a la vez. `tipo` y
  `procedencia` a mano, `no es producto` y la `obs` no dependen del periodo.
- **Desde y Hasta son inclusivos y cada uno opcional.** El dia del Hasta todavia rige.
  Solo Hasta: rige desde ya. Solo Desde: empieza ese dia y no termina. Desde = Hasta es un
  periodo de un dia.
- **"Hoy" es el de Chile** (`calendario.hoy_chile`), nunca el del servidor: Render corre en
  UTC y de 21:00 a 24:00 hora de Chile la fecha UTC ya es la del dia siguiente, o sea que un
  Hasta venceria 3 horas antes. Un test impide usar la fecha del servidor en estas funciones.
- **Tres estados, siempre en femenino**: `programada` (hoy < Desde), `vigente` y `vencida`
  (hoy > Hasta). Sin periodo, o sin ninguna de las tres decisiones, no hay estado (`null`).
- **Al vencer no se borra ni se edita nada.** `calcular` ignora precio fijo, margen fijo y
  congelar cuando el periodo esta programado o vencido, ANTES de aplicar el orden de arriba
  (que no cambia): el producto vuelve a la regla. La decision queda guardada, y por eso se
  puede "renovar" con solo cambiar el Hasta. `precio_override` sigue siendo solo de
  personas, y por eso el vencimiento no mueve la huella de la carga por Excel.
- **Tabla de verdad** (costo 10.000, factor 1,78, la regla da 17.800): precio fijo 990, margen
  35 % (15.385) y congelado 12.000 rigen solo en `vigente`; en `programada` y `vencida` el
  producto cae a 17.800, estado `OK`.
- **Sin periodo no cambia nada.** Hay una prueba con 59 combinaciones (fijo, margen, congelado,
  no es producto, sin stock, Sugerido, tipo y procedencia a mano...) cuyos resultados se
  congelaron corriendo la regla anterior, y la huella de decisiones de la carga por Excel
  vale lo mismo de siempre cuando no hay fechas.

**Que ve la API** (`GET /api/precios`, `GET /api/precios/{producto}` y la respuesta del PUT):

| Campo | Que es |
|---|---|
| `vigente_desde`, `vigente_hasta` | El periodo guardado, `aaaa-mm-dd` o `null`. |
| `vigencia` | `programada`, `vigente`, `vencida` o `null`. Se calcula en vivo contra hoy. |
| `vigencia_dias` | Vigente con Hasta: dias hasta el Hasta (0 = ultimo dia). Programada: dias hasta el Desde. Vencida: dias desde que vencio. Vigente sin Hasta: `null`. |
| `precio_regla` | Solo en la ficha y solo si la vigencia es `vigente`: el precio al que vuelve cuando termine. |
| `precio_fijo`, `margen_fijo`, `congelar` | La decision GUARDADA, aunque no rija. |
| `estado`, `factor`, `precio_final` | Lo que rige HOY segun el ultimo recalculo: una decision programada o vencida no aparece como FIJO, MARGEN ni CONGELADO. |

**Guardar un periodo** (`PUT /api/precios/{producto}/override`). `vigente_desde` y
`vigente_hasta` van como `aaaa-mm-dd`: ausente = no tocar, `null` = quitar ese extremo (otro
formato da 422). Las reglas viven en `validar_vigencia`, una funcion pura que tambien usa
la carga por Excel:

- El Desde no puede ser posterior al Hasta.
- Ninguna fecha puede estar a mas de 3 anos de hoy (frena el 2206 por el 2026).
- El periodo no puede nacer vencido: si la llamada pone o cambia una decision o las fechas y el
  Hasta ya paso, es 422. **Reenviar el estado completo de un producto ya vencido para cambiar
  solo la nota se guarda**, porque la ficha manda todo en cada guardado. Quitar una decision
  tampoco lo bloquea.
- Congelar toma el precio de hoy: no se puede programar con un Desde futuro (se usa precio fijo).
- Las fechas solo existen con una de las tres decisiones: si la llamada quita la ultima se
  borran solas; si solo trae fechas, 422.
- El aviso de "precio fijo o margen fijo, no los dos" dice cuando el que estorba es una
  decision guardada vencida o programada (hay que borrarla o renovarla).

Un congelado **vuelve a tomar el precio de hoy cada vez que pasa a regir**: al congelar, o al
renovar uno vencido (el precio de hoy es el que da la regla, no el de la decision vencida).
Renovar uno que todavia regia conserva su precio. La auditoria de cada guardado dice
`periodo <antes> -> <despues>`.

**Recalcular.** `recalcular` resuelve `hoy` UNA vez por corrida y se lo pasa a todas las filas
(una corrida de 4 minutos que cruza la medianoche no puede dejar la lista con dos fechas). Acepta
`hoy`, `accion` y `titulo` opcionales; sin ellos deja la misma fila de auditoria y la misma
notificacion de siempre. Escribe `precio_producto.vigencia_aplicada` en cada recalculo, igual que
`estado`. Un vencimiento solo deja una fila en `precio_cambio` si el precio cambio de verdad.

**El barrido: como llega el vencimiento al precio.** `calcular` ya ignora una decision fuera de
su periodo, pero el precio guardado solo cambia cuando alguien lo recalcula, y el motor solo
corre cuando se aprieta el boton (el cron de GitHub que debia hacerlo falla con 403). Por eso
`aplicar_vigencias` (`services/precios_service.py`) lleva los vencimientos al precio solo, al leer:

1. **Candidatos, sin escribir.** Una consulta compara el marcador `vigencia_aplicada` de cada
   producto con el estado de hoy. Candidato = el marcador no coincide: el periodo vencio, empezo,
   o quedo un marcador huerfano de un periodo que ya no existe.
2. **Sin candidatos no se escribe nada**: ni auditoria, ni notificacion, ni `actualizado_en`.
   `recalcular` siempre deja una fila de auditoria, aunque de 0 cambios, y un barrido en cada
   lectura llenaria la tabla de filas vacias. Es idempotente: la segunda corrida seguida da ceros.
3. **Con candidatos** toma un candado del proceso (la API corre en un solo proceso,
   `services/operacion_pesada.py`), vuelve a leer los candidatos (otro barrido pudo haber hecho
   el trabajo mientras esperaba) y llama a `recalcular(productos=candidatos,
   refrescar_insumos=False, accion="precios_vigencias")`: UNA fila de auditoria y UNA
   notificacion ("Vigencias de precios: 3 volvieron a la regla, 1 empezo"), no una por producto.
   No relee stock ni costo. Un vencimiento deja una fila en `precio_cambio` solo si el precio
   cambio de verdad. Si otro barrido tiene el candado y no lo suelta en el plazo, responde
   `omitido` y no hace nada. Si fueran mas de 5.000 y mas de la mitad de la lista, `recalcular`
   lee la lista entera, como siempre hizo.
4. **Nunca escribe `precio_override`**: es solo de personas (`editado_por` y `editado_en` no se
   mueven), por eso el vencimiento tampoco mueve la huella de la carga por Excel.

| Donde corre | Tope | Espera el candado |
|---|---|---|
| `GET /api/precios/resumen` | 500 productos | hasta 20 s |
| `GET /api/precios` (la lista) | 500 productos | hasta 20 s |
| `GET /api/precios/exportar`, cualquier formato | sin tope | hasta 30 s |
| `POST /api/admin/precios/vigencias/aplicar` | sin tope | no espera: `omitido` |
| Recalcular completo (boton o motor) | no hace falta | -- (ya respeta el periodo) |

La pantalla pide el resumen al abrir y la lista 300 ms despues, asi que la lista tambien barre
y espera al barrido que el resumen tenga en curso. El tope de 500 (unos 4-5 s, estimado a 7 ms
por producto) protege la pantalla; lo que quede lo completa la lectura siguiente o la descarga.
Un fallo del barrido nunca rompe la lectura: se deshace, queda en el log (`vigencias: el barrido
fallo`) y la pantalla muestra lo que ya habia; `vigencias.por_aplicar` dice cuantos quedaron sin
aplicar.

**Que suma la API** (el paso del motor para aplicar vigencias de noche NO se hizo: seria
redundante y vive en otro repositorio):

- `GET /api/precios?vigencia=...`, repetible y en union: `programada`, `vigente`, `vencida` o
  `vence_7d` (vigente con el Hasta entre hoy y hoy + 7, ambos incluidos). Usa el marcador
  guardado, que el barrido deja al dia antes de consultar. Un valor que no existe da 422.
- `GET /api/precios/resumen` suma `vigencias`: `{hoy, vigentes, programadas, vencidas,
  vencen_7_dias, por_aplicar}`. `hoy` viene del servidor para que los atajos de la ficha (30/60/90
  dias, fin de mes) no dependan del reloj del navegador. `por_aplicar` son los vencimientos que
  el tope dejo pendientes. `pendientes_envio` ya incluye lo que acaba de vencer.
- `POST /api/admin/precios/vigencias/aplicar` (admin; cuerpo opcional `{"previsualizar": true}`).
  Responde `{hoy, con_periodo, al_dia, pendientes, vencieron, comenzaron, recalculados,
  precios_cambiados, omitido, previsualizar, ejemplos}`, con hasta 20 ejemplos (`producto`,
  `vigencia_antes`, `vigencia_despues`, `precio_antes`, `precio_despues`). `al_dia` y
  `pendientes` son los de ANTES de aplicar. Con `previsualizar` cuenta y simula, sin escribir ni
  tomar el candado. La segunda llamada seguida responde ceros y no escribe ninguna fila.

**Lo que NO hace.** El vencimiento ocurre en la plataforma, no en el ERP: **el ERP conserva el
precio de la campana hasta que alguien suba el archivo**. Nada se empuja solo. El producto que
vence entra a "solo diferencias" y suma en `pendientes_envio` desde la primera lectura del dia
(solo si el ERP tenia el precio anterior; si nunca se envio, no aparece). Tampoco hay aviso
previo en la campanita. El archivo para editar de Excel SI trae `Precio fijo`, `Margen fijo %`,
`Desde`, `Hasta` y `Vigencia`, y la carga las lee (ver "Editar la lista con Excel"); "Exportar
completa" y el archivo del ERP no. Cambiar el precio de un producto con la decision vencida
desde el Excel da un error ("El periodo ya terminó") hasta que se renueve el Hasta en la misma
fila. Los vencidos se quedan visibles hasta que alguien los renueve o los quite.

**Migracion.** `db.py` agrega `precio_override.vigente_desde`, `precio_override.vigente_hasta` y
`precio_producto.vigencia_aplicada` (las tres nullable, sin relleno: ningun precio cambia al
desplegar). Una prueba quita las tres columnas, corre `create_all()` y comprueba que vuelven.
**Volver atras**: las columnas extra no estorban a la version anterior, pero esa trataria una
decision vencida como vigente; no se vuelve atras una vez que el equipo use periodos sin quitarlos.

## Bodegas: que stock cuenta (20-10-2026)

El ERP mezcla bodegas fisicas con bodegas de proceso. La lista cuenta el stock de
**todas las bodegas de Curifor menos danados, devolucion y scrap**. Hasta esa fecha
solo contaban las marcadas REAL, y 248 productos que si se pueden vender (PE por
regularizar, COMEX, importacion de motos) salian SIN STOCK y sin precio.

La tabla `bodega_tipo` clasifica cada bodega en uno de cuatro tipos. Solo el
cuarto decide algo:

| Tipo | Que es | Cuenta |
|---|---|---|
| `REAL` | Bodega fisica de la que se vende. | Si |
| `VIRT` | Bodega de proceso (PE por regularizar, COMEX, importacion). | Si |
| `ELIM` | Bodega dada de baja; si aun tiene stock, esta ahi. | Si |
| `NODISP` | **No disponible**: danados (dos grafias en la tabla), devolucion, scrap y la bodega sin nombre. | **No** |

Reglas que conviene saber (`services/precios_service.bodega_cuenta`):

- **Sin tabla, sin filtro.** Con `bodega_tipo` vacia no se excluye nada.
- **Una bodega nueva o sin clasificar cuenta**, salvo que su nombre diga danados,
  scrap o devolucion. Es la red de seguridad: el ERP ya trae tres grafias de
  danados ("DAÑADOS", la misma con la letra rota "DAÃ‘ADOS" y "DA?ADOS") y una
  cuarta, o una tabla a la que le falte NODISP, sumaria stock que no existe. La red
  actua solo sobre VIRT y sin clasificar: un `REAL` o `ELIM` explicito le gana, para
  que el cambio de criterio sea una fila de la tabla y no un deploy.
- **La bodega sin nombre no cuenta** mientras el responsable de Abastecimiento no
  confirme que ese stock se puede vender (53 filas, 345 unidades en 29 productos: el
  ERP no dice donde estan). Es decision conservadora. Si dice que cuenta, se marca
  `REAL` en la tabla y se aplica en el proximo recalculo.
- **No cambian a proposito**: el transito, el stock de Frontera, la clase ABC
  (`abc_stock_service`, que no filtra bodegas), el stock operativo del sugerido y el
  chequeo FORD (usan `dim_sucursal`: otro concepto) y el feed de altas, que sigue
  sumando todas las bodegas del Excel del ERP (un producto con stock solo en
  danados se da de alta y queda SIN STOCK; arreglarlo exige que el motor mande el
  desglose por bodega).

**Quien la mantiene y como.** La tabla de produccion es el maestro, no el Excel
local de origen (`1 Tipo bodega.xlsx`, descarga del 08-09, sin NODISP): recargarlo
volveria a contar danados y devolucion.

1. Bajar la tabla actual: `python scripts/precios/bodegas_tipo.py --exportar
   bodegas.xlsx --env <.env>`. Trae las bodegas clasificadas y, al final, las que
   tienen stock y nadie clasifico.
2. Editar el tipo (acepta "NO DISPONIBLE", "no_disp" y variantes como NODISP).
3. Subirla: `python scripts/precios/bodegas_tipo.py bodegas.xlsx --env <.env>`
   (`--simular` no escribe). Equivale a `POST /api/admin/precios/bodegas-tipo`.

La carga se rechaza (422) si trae un tipo que no existe o si no trae ninguna
NODISP (salvo `sin_no_disponibles: true` / `--sin-no-disponibles`), y no escribe
nada. Queda guardado quien la cargo. La respuesta nombra las bodegas NODISP y las
que tienen stock de Curifor sin clasificar. `GET /api/precios/bodegas` dice, por
fila, si la bodega `cuenta`, y lista al final las `sin_clasificar`. La ficha de un
producto (`GET /api/precios/{producto}`) trae `stock_bodegas`: de que bodegas sale
su stock y si cada una cuenta.

**Siembra.** Al arrancar, `db.py` marca NODISP a Danados (las dos grafias),
Devolucion, Scrap y la bodega sin nombre, UNA sola vez: la sentencia no hace nada si
ya existe una NODISP o si alguna fila la cargo una persona (`actualizado_por`), asi
un reinicio nunca revierte una decision del admin.

**Cuando se aplica.** Cargar la tabla no recalcula nada: la regla entra en el
proximo recalculo que relea el stock (el del motor o el boton Recalcular, unos 4,5
min). Guardar una ficha o la politica no relee el stock, asi que no hay saltos de
precio a mitad del dia. Medido sobre el stock publicado el 19-10-2026, el primer
recalculo tras el cambio mueve ~528 productos (254 pasan de 0 a stock positivo;
ningun producto que ya tenia precio cambia de precio, que es costo por factor) y
deja ~248 precios nuevos en "Solo diferencias" del archivo del ERP, para revisar
antes de subirlos. Las cifras exactas del dia variaran unas decenas.

**Volver atras.** El dato `NODISP` es compatible con el codigo anterior (que excluia
todo lo que no fuera `REAL`), asi que revertir el despliegue deja la lista como
estaba sin tocar datos.

## Editar la lista con Excel (14-10-2026)

Botón "Editar con Excel" en `/precios` (solo quien puede editar precios). Se baja el
archivo, se edita y se vuelve a cargar; antes de guardar se ve que cambia, producto
por producto.

- **Descarga** (20-10-2026): `GET /api/precios/exportar?formato=editable` son **25
  columnas** (CSV, `;`, BOM), en este orden: las 16 de "Exportar completa" (`Producto`,
  `Glosa`, `Rubro`, `Tipo`, `Procedencia`, `Factor`, `Costo`, `Precio ERP`, `Precio
  calculado`, `Precio final`, `Estado`, `Stock`, `En transito`, `Ultima venta`,
  `Descuento máximo`, `Descuento+1`) y después `Obs`, `Congelar`, `No es producto`,
  `Precio fijo`, `Margen fijo %`, `Desde`, `Hasta`, `Vigencia` y `Referencia`. Las 16
  primeras son **idénticas, en el mismo orden y contenido**, a las de "Exportar completa"
  (que no cambia: sigue con sus 16): lo ata un test y salen de la misma lista
  (`COLUMNAS_ARCHIVO`, en `services/precios_carga_service.py`, que también arma el
  encabezado y la lista de editables y de solo lectura). Antes eran 20; los archivos
  bajados antes siguen cargando (ver "Archivos bajados antes"). El factor sale con hasta 4
  decimales (un margen fijo da 1,5385) y el margen con hasta 2, con coma. `Desde` y
  `Hasta` salen en ISO (`2026-10-31`): Excel en Chile las convierte a fecha y al guardar
  como CSV las escribe `31-10-2026`; el lector acepta las dos. `Obs`, `Glosa`, `Rubro` y
  `Tipo` que empiezan con `=`, `+`, `-` o `@` salen con un apóstrofe delante (Excel las
  abriría como fórmula: "-5% convenio" salía `#NOMBRE?` y un `=HYPERLINK(...)` se
  ejecutaba); al leer, se quita.
- **Lo que se edita**: 11 columnas (cada una hace lo mismo que su equivalente en la
  ficha; vacío quita la decisión): `Tipo` y `Procedencia` (escritos a mano; el tipo se
  acepta con o sin tildes y con los alias de la política), `Factor` (factor propio =
  margen fijo `(1 - 1/f) x 100`), `Precio final` (precio fijo), `Obs`, `Congelar` y `No
  es producto` (Sí/No), y las nuevas `Precio fijo`, `Margen fijo %`, `Desde` y `Hasta`
  (ver "Precio fijo, margen y periodo"). Las otras 13 son de solo lectura y si se editan,
  no se cargan: `Producto`, `Glosa` y `Rubro` vienen del maestro del ERP; `Costo`,
  `Precio ERP`, `Stock` y `En transito` los pisa el feed de cada día; `Estado`, `Precio
  calculado` y los dos descuentos son el resultado de la regla y de la política (se
  cambian en `/precios/politicas`); `Vigencia` es el texto del estado del periodo ("Fijo
  hasta 31-10-2026", "Programado desde 01-11-2026", "Vencido el 30-09-2026", vacío si no
  hay periodo o rige sin Hasta). Precio fijo y factor propio no conviven: la fila con los
  dos es un error.
- **Precio fijo, margen y periodo** (20-10-2026). `Precio final` y `Factor` siguen siendo
  atajos y muestran lo que **rige hoy**; `Precio fijo` y `Margen fijo %` son la misma
  decisión pero con lo **guardado**, aunque su periodo esté programado o vencido (sin
  ellas, un precio de campaña vencido no se vería en el archivo y se escribiría de nuevo
  sin saber que ya existe). Reglas:
  - Si cambia solo una de las dos columnas, vale esa. Si cambian las dos y dicen lo mismo
    (el factor de ese margen a 4 decimales; o el mismo precio) se aplica **una vez**; si
    discrepan, es un error del archivo que bloquea todo. Vacío en una de las dos y valor
    en la otra también es error; los dos vacíos quitan la decisión.
  - `Margen fijo %` es en % sobre la venta: `35` es 35 %. **Menor que 1 es error** ("escribe
    35 para 35 %, no 0,35": una celda con formato de porcentaje entrega 0,35) y 100 o más
    también. `Precio fijo` negativo es error.
  - `Desde` y `Hasta` son el periodo de las **tres** decisiones (precio fijo, margen y
    congelar), inclusivos y cada uno opcional. Las reglas son las de la ficha
    (`validar_vigencia`, la misma función): el Desde no puede ser posterior al Hasta;
    ninguna fecha a más de 3 años de hoy; el periodo no puede nacer vencido (un Hasta
    anterior a hoy, en hora de Chile, es error); Congelar con un Desde futuro es error
    (congelar toma el precio de hoy); fechas sin ninguna decisión que las use son un
    error, salvo que la propia carga quite la última decisión, y entonces las fechas se
    borran solas. **Renovar un vencido es cambiar solo el Hasta.** Editar solo la nota de
    un vencido se guarda, como en la ficha.
  - Los errores que dependen de lo que **ya estaba guardado** (un periodo que otra
    persona dejó vencido, precio fijo y margen a la vez) y no de lo que trae el archivo,
    son un **conflicto** de esa fila si el producto cambió después de bajar el archivo, y
    un error si no. Los del propio archivo (un Desde mayor que el Hasta que escribió la
    carga, una fecha que no se entiende) bloquean todo, hayan editado el producto o no.
  - Si el aviso es por precio fijo y margen a la vez y lo que estorba está vencido o
    programado, el mensaje lo dice ("el margen fijo guardado está vencido: bórralo o
    renuévalo").
  - Un congelado que **pasa a regir** (se congela o se renueva uno vencido) toma el precio
    de hoy, el que da la regla, no el que pueda mostrar la fila.
- **Fechas aceptadas**: `date` y `datetime` de un `.xlsx`, el número de serie de Excel (entre
  2000 y 2100), ISO (`2026-10-31`), `dd-mm-aaaa` y `dd/mm/aaaa`, y el año de 2 dígitos como
  20aa. **Nunca mes/día**: `10/11/2026` es el 10 de noviembre, y `10/13/2026` es un error.
  Un mes con nombre (`31-oct`) o una fecha que no existe (`31-02-2026`) es un error con el
  texto "usa dd-mm-aaaa". La vista previa muestra la vigencia ya interpretada ("Rige del
  20-10-2026 al 31-10-2026", en `cambios[].vigencia`), que es la forma de notar un día y
  un mes cambiados.
- **Archivos bajados antes**: uno con la Referencia v1 (10 partes, 20 columnas) sigue
  cargando. Lee solo las 7 columnas de antes; si trae `Precio fijo`, `Margen fijo %`,
  `Desde` o `Hasta` en esas filas, no se leen, y las filas con Referencia v1 se cuentan en
  `archivo_viejo_total` de la vista previa. Un archivo que baja con Referencia v2 (14
  partes) y al que le faltan esas cuatro columnas es un error global ("Faltan las
  columnas: ...") porque se las tomaría por vacías, o sea, por quitas. Un archivo v2 en un
  servidor viejo falla seguro: "referencia dañada", sin escribir nada.
- **La columna `Referencia`** guarda, por producto, lo que mostraba el archivo al
  bajarlo, en 14 partes ASCII (sobreviven a cualquier página de códigos):
  `huella del código|tipo|procedencia|factor|precio final|huella de la obs|la misma como
  la deja Excel (cp1252)|congelar|no es producto|precio fijo|margen fijo|desde|hasta|huella
  de las decisiones`. (La v1 eran 10: las mismas sin las cuatro del medio. Cualquier otro
  largo es "referencia dañada".) Empieza con un hash para que Excel nunca la lea como
  fórmula. Se carga SOLO lo que la persona cambió respecto de esa
  referencia, no lo que difiere de lo que hay hoy: el motor recalcula los precios cada
  noche y eso no es una edición (compararlo contra hoy habría vuelto precio fijo cada
  precio que se movió). Tres huellas la protegen:
  - la de las **decisiones** resume `precio_override`: si cambió desde la descarga y
    el archivo edita ese producto, es **conflicto** y se omite, porque cargarlo
    desharía en silencio lo que otra persona hizo en la ficha. Si lo que dice el
    archivo ya es lo que hay (el mismo archivo subido dos veces, o una carga cuya
    respuesta se perdió), es "sin cambios", no conflicto. El periodo entra a la huella
    SOLO si el producto tiene alguna fecha: para los que no tienen (los 3.163 de hoy) vale
    lo mismo de siempre, que es lo que viaja en cada archivo ya bajado. Tampoco depende de
    la fecha de hoy: un periodo que vence no escribe en `precio_override`, así que no
    mueve la huella ni crea conflictos falsos de noche;
  - la del **código** ata la referencia a su producto: ordenar o pegar solo esa
    columna la dejaba en otra fila, y los precios de esa fila se volvían precio fijo
    sin que nada avisara. Ahora es un error;
  - la de la **obs** evita que una nota con cualquier carácter parezca una edición, y
    la segunda (cp1252) que no lo parezca cuando Excel guarda como "CSV" y cambia por
    `?` lo que no cabe (flechas, espacio fino). Excel escribe un `?` por unidad UTF-16:
    un emoji queda como `??`. El `?` se calcula ANTES de colapsar los espacios, porque
    el espacio fino (U+2009) no cabe en cp1252 y Excel lo escribe como `?`. Para "CSV
    MS-DOS" (cp850) y "CSV Macintosh" (mac_roman), que pierden otros caracteres (`€ – “ ”
    • ™`, `² ½ ×`), la Referencia no lleva más huellas: la nota del archivo se compara
    contra la que hay en la plataforma pasada por esa página de códigos, y solo si
    nadie editó la ficha desde la descarga.

  Sin `Referencia` el archivo no se carga. Excel con "disminuir decimales" guarda
  1,1429 como 1,14 o 1,143: si el factor del archivo es el de la referencia redondeado
  a 2 o a 3 decimales (mitad hacia arriba, como Excel), no cuenta como edición. Se
  compara con el valor ya canónico, sin ceros finales: 1,4993 mostrado como `1,50`
  llega como `1.5`. Costo conocido: escribir a propósito el valor redondeado tampoco
  se distingue; por eso la vista previa cuenta esos productos y los lista
  (`factor_redondeado_total`, `factor_redondeado`) en un aviso amarillo.
- **Carga**: `POST /api/precios/carga/vista-previa` lee y compara sin guardar;
  `POST /api/precios/carga` vuelve a leer el archivo y aplica. **Todo o nada**: un
  error de validación (factor fuera de rango, tipo que no existe en la política,
  código repetido, Referencia de otro producto, precio fijo y factor a la vez...)
  bloquea la carga entera. Se omiten y se listan los conflictos, los códigos que no
  están en la lista y las filas sin `Referencia`. Si el producto cambió en la ficha
  después de bajar el archivo y el archivo lo edita, es conflicto aunque la combinación
  sea inválida (precio fijo y factor puestos por el otro): solo se omite esa fila. Eso
  vale SOLO para el error de combinación, que puede venir de lo que dejó la otra
  persona; un error de valor (tipo que no existe, factor fuera de rango) es del
  archivo y bloquea igual, haya editado alguien el producto o no. Al
  aplicar, las filas se bloquean (`FOR UPDATE`) y se vuelve a calcular contra lo que
  hay AHORA: otra persona que edite justo entre comparar y escribir no se pisa, y el
  reintento de una respuesta perdida da "sin cambios".
- **Quitar decisiones**: una celda vacía quita la decisión, y un `.xlsx` con celdas de
  error (`#N/D`, `#REF!`) las entrega vacías (calamine no distingue). Si una carga
  quita 10 decisiones o más (`UMBRAL_QUITAS`), la pantalla pide marcar una
  confirmación y el servidor exige `confirmar_quitas=true`: un BUSCARV roto no puede
  borrar precios fijos en silencio. **Vaciar `Desde` o `Hasta` cuenta como quita** (clave
  `desde` / `hasta` en `quitan`): vuelve permanente un precio temporal, que es la dirección
  peligrosa si un BUSCARV roto vacía las celdas.
- **Poner muchos a la vez**: si una carga deja más de 200 precios fijos, factores
  propios, congelados o fechas de periodo nuevos (`UMBRAL_MASIVA`), la pantalla pide otra
  confirmación y el servidor exige `confirmar_masiva=true`. Ordenar una sola columna
  (Precio final, Factor, Precio fijo, Hasta) deja cada valor en la fila de otro producto,
  y cada fila parece una edición válida: la Referencia detecta el código, pero no que un
  valor cambió de dueño. **Congelar = Sí cuenta** (clave `congelar`) desde el 20-10-2026:
  antes ordenar solo esa columna no disparaba ningún freno. La vista previa trae
  `fijan_total`, `fijan` (con las claves `precio_fijo`, `factor`, `congelar`, `desde` y
  `hasta`), `umbral_masiva`, y también `programados_total` (cuántos quedan con un Desde
  futuro: hoy su precio no cambia) y `archivo_viejo_total`.
- **Qué deja**: una fila de auditoría `precio_override` por producto ("(carga desde
  Excel)") y una de resumen `precios_carga_excel`, más una notificación. Recalcula SOLO
  los productos editados, con la política cargada una vez y leída ANTES de escribir
  (`politica.factores` se traga los errores y hace rollback: leída después se llevaba
  lo escrito), y no crea "cambios sin revisar": son decisiones de una persona.
- **Formatos**: `.csv` (UTF-8; UTF-16 de "Texto Unicode", con o sin BOM; o la página
  de códigos de Windows: cp1252 de "CSV", cp850 de "CSV MS-DOS" y mac_roman de "CSV
  Macintosh", que se distinguen porque el encabezado `Descuento máximo` solo se lee
  entero con la correcta; si borraron las columnas de descuento (no son obligatorias),
  gana la página en que más celdas dicen `Sí`; separador `;`, `,` o tabulación; fin de
  línea CRLF, LF o CR) y `.xlsx`. El `.xlsx` se lee con `python-calamine`: `openpyxl`
  tardaba 36 s en 40 mil filas en un PC y mucho más en el plan gratis de Render.
  Calamine arma la hoja entera en memoria y `ABORTA el proceso` con una referencia de
  celda absurda, así que antes de abrirlo se escanea el XML de la PRIMERA hoja por
  bloques: última fila y columna con contenido (no cuentan las celdas vacías con
  formato, ni `<c .../>` ni `<c ...></c>`), referencias dañadas, tamaño descomprimido y
  texto sin etiquetas (más de 1 MB seguido: Excel admite 32.767 caracteres por
  celda). Las etiquetas de Excel, openpyxl y xlsxwriter se leen con un regex rápido;
  desde el primer bloque con una etiqueta de otra forma (prefijo `<x:c`, comillas
  simples, otro orden de atributos, celdas sin `r`) se lee con uno general, más lento,
  que usa `<row r=` para las celdas sin referencia. No se confía en la `<dimension>`
  declarada (falta en los archivos en streaming y una celda de más la hace mentir).
  Topes: 30 MB, 100 MB descomprimido, 250.000 filas y 2 millones de celdas con texto
  (también en CSV; las filas vacías `;;;;` que Excel deja al final no cuentan).
  Cualquier archivo que no sirve da un 422 con un mensaje, nunca un 500; si los datos
  no están en la primera hoja, el mensaje lo dice. Los códigos se recortan solo en los
  bordes: `19  FB5Z15201H` (dos espacios) y `19 FB5Z15201H` son productos distintos.
- **Notas que Excel lee como número o fecha**: al abrir un CSV, `0123` pasa a `123`,
  `3/4` a `03-abr`, `1E5` a `1,00E+05` y un teléfono de 12 dígitos pierde dígitos. Como
  con las fórmulas, esas notas (número, porcentaje, moneda, fecha, hora, notación
  científica) salen con un apostrofe delante y se lo quita al leer; un entero sin ceros
  a la izquierda de hasta 11 dígitos vuelve igual y no lo lleva. Se ve en la columna
  Obs del archivo.
- **Limitación conocida**: un factor que Excel muestre con 0 o 1 decimal (`1,5` por
  1,5385) sí cuenta como edición, y se ve en la vista previa ("antes → después"). No se
  tolera porque dejaría sin cargar un factor escrito a propósito.
- **Medido** con la copia local de 60 mil productos: bajar el archivo 3,2 s (11 MB);
  leer y comparar sin ediciones 1,5 a 1,9 s (CSV) o 7,7 s (.xlsx, de los cuales ~2 s
  son el escaneo previo); aplicar 1.500 ediciones 2,0 s en total; subir el mismo
  archivo otra vez 1,4 s y "sin cambios"; un recálculo completo después no cambia
  ningún precio.
- **Revisión**: se hicieron tres pasadas de revisión adversarial antes de publicar. Las
  dos primeras encontraron 25 y 29 defectos reales (varios de pérdida silenciosa de
  datos: una Referencia desalineada convertía precios en precio fijo; un `.xlsx` de
  26 KB tumbaba la API; las notas con emojis se sobrescribían con `?`). La tercera
  encontró 25 hallazgos (16 distintos), todos corregidos salvo el factor a 0 o 1
  decimal (ver Limitación conocida): emoji, redondeo del factor que termina en 0, el
  diálogo que se cerraba al tocar la barra de desplazamiento, las otras páginas de
  códigos, el escaneo del `.xlsx`, las filas vacías del CSV, el tope de celdas, un error
  de valor escondido como conflicto, las notas que parecen número, el foco de la vista
  previa y los avisos de descarga y lectura (ahora separados). Se agregó el freno de 200.

## Exportar al ERP

`GET /api/precios/exportar?formato=erp` genera `SKU | Precio_Optimo | Descuento`.
El descuento es el mismo de la columna `Descuento+1` de la lista completa: el
descuento maximo de la politica mas uno, salvo cuando es 0 (desde el 09-10-2026;
antes la tercera columna era el costo). Con `solo_diferencias=true` salen solo los productos cuyo
precio o costo difiere de lo ultimo enviado (o nunca enviados). Cada
exportacion queda registrada en `precio_envio`.

**Vencimientos de vigencia (20-10-2026).** Antes de armar CUALQUIER formato -y de contar las
diferencias- la descarga aplica todos los vencimientos pendientes, sin tope y esperando hasta 30 s
si otro barrido esta en curso (ver "Vigencia"). Asi el archivo y el contador de "solo
diferencias" salen con la regla de hoy aunque nadie haya abierto la pantalla ese dia, tambien
sabado, domingo y feriado. Si el barrido falla y quedan vencimientos sin aplicar, el archivo del
ERP responde 503 (la web reintenta sola) en vez de salir con un precio que ya no rige y quedar
registrado como enviado; la lista completa y la editable salen igual. Los nombres de los archivos
llevan la fecha de Chile: de 21:00 a 24:00 la del servidor, que corre en UTC, ya es la de manana.

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
