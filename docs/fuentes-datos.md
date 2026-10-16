# Fuentes de datos

De dónde saca el motor cada archivo, qué encontró en cada corrida y si está bien.
Antes la configuración vivía en el `.env` del PC del motor (`MOTOR_CRUDOS_DIR`,
`MOTOR_STOCK_DIR`) y en patrones escritos en el código del motor: un archivo nuevo en
la carpeta botó la corrida diaria tres veces y nadie podía ver qué archivo se había
leído ni de qué fecha era. Ahora la configuración es un dato que edita un admin, y
cada corrida deja un reporte que la plataforma convierte en un semáforo.

Pantalla: `/cargar/fuentes` (solo admin, sin ítem en el menú; se entra desde la
tarjeta de `/cargar`). API: `/api/admin/fuentes` (`routers/fuentes.py`,
`services/fuentes_service.py`, contratos en `schemas/fuentes.py`).

Fase 1 (oct-2026): el motor sigue corriendo en un PC y lee carpetas locales que
OneDrive mantiene sincronizadas. Sin TI: no se registran apps ni se usa Graph.

## Los tres modos

1. **Sin configurar** (el día del deploy). La tabla `fuente_config` está vacía,
   `GET /config` responde `{"modo": "sin_configurar"}` y el motor sigue usando su
   `.env`, como siempre. Cada reporte trae `config_efectiva`: lo que el motor usa hoy.
2. **En prueba**. Un admin aprieta "Usar la configuración del PC … como punto de
   partida" (`POST /sembrar`): se copia esa `config_efectiva`, el modo queda en
   `prueba` y el PC de esa corrida queda como titular. Se puede sembrar desde una
   corrida `probar` (`--probar --reportar`), sin esperar a la oficial. El motor
   sigue usando el `.env`, pero además resuelve cada fuente con la configuración de
   la plataforma y reporta si coincide. Se puede editar como **ensayo** (por ejemplo,
   apuntar el stock a otra carpeta) marcando "Es una diferencia esperada".
3. **Activa**. El motor lee lo que dice la plataforma. El botón "Activar" se habilita
   con `CORRIDAS_PARA_ACTIVAR` (= 2) corridas oficiales seguidas del PC titular que
   cumplan todo esto:
   - terminaron `ok` y usaron la configuración de la plataforma (`config_origen=plataforma`);
   - cada fuente que el motor lee (las 13 `lee`, activas) está en `coincide` o
     `difiere_esperado`. Una fuente no obligatoria puede estar en `falta` si el `.env`
     tampoco la encontró: activar no cambia nada para ella;
   - ninguna obligatoria está en `falta`;
   - la configuración no cambió después de esas corridas (salvo el modo o el nombre de
     un PC): si cambió, lo que se comparó ya no es lo que se activaría.

   Si no se cumple, `POST /modo` responde 409 con el motivo. La activación rige desde
   la corrida siguiente.

**Volver atrás**: "Volver a prueba" en el panel (rige desde la corrida siguiente), o
`MOTOR_FUENTES=env` en el `.env` del PC (rige de inmediato e ignora la plataforma por
completo, titular incluido). "Volver a esta versión" (`POST /revertir/{version}`)
inserta una copia de las carpetas y fuentes de esa versión; con `clave`, solo de esa
fuente. El modo, el titular, los nombres de los PCs y el catálogo no se revierten:
revertir a una versión que estaba activa no puede saltarse la condición para activar,
ni cambiar de titular sin pasar por `POST /titular`.

## PC titular

Solo el PC titular publica: si una corrida `--oficial` se lanza en otro PC, el motor
no calcula ni publica y reporta `no_titular`. El titular solo puede ser un PC que ya
reportó alguna corrida (aunque sea un `--probar`). Cada PC se identifica por su
hostname; en el panel se le pone un nombre ("PC de la jefa", `PUT /pcs/{hostname}`).

## Las tablas

| Tabla | Qué es | Quién la escribe |
|---|---|---|
| `fuente_config` | **Solo se agregan filas.** La vigente es la de mayor `version` del tenant. `config` es el JSON de `ConfigFuentes` (modo, pc_titular, pcs, catalogo, carpetas, fuentes); `hash` es su sha256 canónico; `claves_cambiadas` dice qué cambió (`["stock_bodegas"]`, `["modo"]`, `["pc_titular"]`, `["pcs"]`, `["carpeta:databi_datos"]`, `["catalogo:motor"]`) y alimenta el historial por fuente; `nota` es obligatoria; `revierte_a` es la versión copiada. Único (`tenant_id`, `version`): dos admins guardando a la vez no crean la misma versión. | admins (pantalla) |
| `motor_corrida` | Una fila por corrida (upsert por el `id` que genera el motor: el reporte de inicio y el de fin caen en la misma fila). `reporte` = `{fuentes: {clave: estado}, carpetas: [listado], avisos: [...]}`; `config_efectiva` = lo que el motor usa hoy. ~300 corridas al año de pocos KB: no hace falta purgar. | el motor |

La configuración y el reporte van como JSON en `Text`: un campo nuevo del motor o un
tipo de carpeta de otra empresa no necesita migración, y las piezas que declara el
motor guardan los campos que la plataforma todavía no conoce. Las dos tablas son
nuevas: las crea `create_all`, sin líneas nuevas en `migraciones`. Todo lleva
`tenant_id` (hoy `settings.default_tenant_id`).

## El catálogo

Lo declara el motor dentro de `config_efectiva`. La plataforma valida contra él y no
tiene ninguna clave de fuente escrita en el código:

- `uso`: `lee` (el motor la usa) o `reconoce` (solo existe para que esos archivos no
  caigan por descarte como respaldos de venta).
- `requerida`: sin ella el motor no calcula; no puede quedar no obligatoria ni inactiva.
- `modos`: cómo se puede elegir el archivo (`archivo_exacto`, `mas_reciente`,
  `por_descarte`).
- `frecuencia_max` y `al_vencer_fijo`: tope de plazo y conducta fija al vencer.
- `efecto_si_falta`: qué pasa si falta, para el texto del panel.
- `controla_filas` (opcional): si el semáforo controla "llegó vacío o incompleto". Si
  el motor no lo declara, aplica a las fuentes con `frecuencia_max` (hoy, los dos
  stocks y el seguimiento nacional).

## Validaciones (422, con el texto en español)

- El modo tiene que estar en `catalogo[clave].modos`. `archivo_exacto` exige el nombre;
  `mas_reciente`, al menos un patrón.
- Patrones y nombre de archivo sin `/`, `\`, `..` ni letra de unidad, hasta 100
  caracteres. La subcarpeta acepta `/` (un `\` se convierte), pero no `..`, ni `/` al
  inicio, ni letra de unidad.
- Las ubicaciones apuntan a carpetas que existen y están activas; una fuente activa
  necesita al menos una. Plazo de 1 a 365 días hábiles o sin plazo.
- Mínimos del catálogo (requerida, `frecuencia_max`, `al_vencer_fijo`).
- Carpetas: `sharepoint` exige `https://<empresa>.sharepoint.com/sites/…`, la
  biblioteca y una ruta de al menos un nivel; `onedrive`, una ruta de al menos un
  nivel. Al editar solo el nombre, las rutas por PC o si está activa, no se exigen
  los parámetros (la carpeta sembrada trae el sitio en blanco: el PC no lo conoce).
  Una carpeta que usa alguna fuente no se puede desactivar.
- **Vista previa** (`POST /{clave}/vista-previa`, no guarda): prueba la configuración
  propuesta contra el último listado de carpetas del PC titular, con la misma regla
  del motor (minúsculas, sin tildes, el más nuevo gana; `por_descarte` toma los
  `.xlsx` que no calzan con ninguna otra fuente y traen en el nombre el año en curso o
  el anterior). Devuelve "tomaría X / hoy toma Y", conflictos y avisos. Al guardar
  (`PUT /{clave}`), un conflicto da 422: dos fuentes `lee` con el mismo archivo, o en
  `activa` una obligatoria sin archivo ("Con este cambio el motor no encontraría el
  archivo y la publicación se frenaría"). Entre una `lee` y una `reconoce` es solo
  aviso (la lista de Ford es de `precios_ford` y de `precios_proveedor`). En `prueba`,
  la obligatoria sin archivo es aviso.
- Toda escritura lleva `base_version`: si otro admin guardó antes, 409 "Otro admin
  guardó un cambio; recarga".

## El semáforo

Lo calcula el servidor (`fuentes_service.semaforo`, función pura) con el estado de
la última corrida del titular, la configuración vigente (o la efectiva, sin
configurar) y la corrida anterior del mismo PC. La edad de cada archivo se recalcula
**hoy**, en días hábiles (sábado y domingo no cuentan; feriados todavía no) y en hora
de Chile: a las 22:00 "hoy" sigue siendo hoy. Se evalúan todas las reglas; manda la
primera de la peor, y las demás quedan en `alertas`.

| Nivel | Color | Etiqueta | Regla |
|---|---|---|---|
| Franja | Rojo | El PC titular no corrió hoy | día hábil, desde las 11:00, sin corrida `oficial` del titular de hoy |
| Franja | Rojo | La última corrida se cortó | `cortada`, o `en_curso` por más de 75 min |
| Franja | Rojo | Corrió con la configuración del PC | `config_origen=env` con la configuración en `activa` |
| Franja | Amarillo | Usó la configuración guardada | `config_origen=cache` (con su antigüedad) |
| Franja | Amarillo | Hoy corrieron dos PCs | más de un PC con corrida `oficial` hoy |
| Franja | Amarillo | OneDrive cerrado | `reporte.onedrive_corriendo = false` |
| Fuente | Rojo | Vencido | edad > plazo y frena |
| Fuente | Rojo | Falta | sin archivo y obligatoria |
| Fuente | Rojo | Carpeta no encontrada | ninguna ubicación existe en el PC |
| Fuente | Rojo | Llegó vacío o incompleto | 0 filas o menos del 60 % de la corrida anterior (donde el catálogo lo controla) |
| Fuente | Rojo | No se pudo leer | `error_lectura` |
| Fuente | Rojo | Ventas sin el mes cerrado | la venta del mes cerrado viene en cero, o el periodo quedó atrás; los días 1 a 3, amarillo |
| Fuente | Amarillo | Atrasado, no frena | edad > plazo y solo avisa |
| Fuente | Amarillo | Falta (no frena) | sin archivo y no obligatoria; el texto lleva `efecto_si_falta` |
| Fuente | Amarillo | Mismo contenido que ayer | `mismo_contenido_que_anterior` y plazo ≤ 2 |
| Fuente | Amarillo | Bajando de OneDrive | `inestable` |
| Fuente | Amarillo | Abierto en Excel | `abierto_en_excel` |
| Fuente | Amarillo | Archivo nuevo en la carpeta | un descartado que no estaba en la corrida anterior |
| Fuente | Amarillo | Cambió de carpeta | el ganador viene de otra carpeta que en la corrida anterior |
| Fuente | Verde | Al día | encontrado y edad ≤ plazo |
| Fuente | Verde | Encontrado, sin plazo | encontrado y sin plazo |

La competencia entre carpetas y los descartados de siempre no cambian el color: se
ven en el detalle. Si el titular no corrió hoy, cada fila dice "Dato de la corrida del
…". Los textos siempre dicen qué hacer, y los motivos del log se traducen: el "corre
con --ignorar-frescura" queda solo en el log.

## Aviso por campanita a los admins (aprobado el 16-10-2026)

Al recibir el reporte de **fin** de una corrida **oficial** que terminó `frenada`,
`fallo` o `incompleta`, o con alguna fuente en rojo, la plataforma deja un aviso
**personal** (`notificar(para_email=…)`) a cada admin activo, sin el usuario que
reporta (el del motor), como máximo uno al día por admin y por motivo (el motivo va
en `notificacion.tipo`: `fuentes_datos:frenada`, `fuentes_datos:rojo:stock_bodegas`).
Una corrida `no_titular`, `probar` o `comparacion` no avisa. "El PC titular no corrió
hoy" queda solo en el panel: si no corre nada, no hay quién lo revise. Si algo falla
al avisar, el reporte igual queda guardado.

## La pantalla

`/cargar/fuentes` (`app/cargar/fuentes/page.tsx`, componentes en `components/fuentes/`,
cliente en `lib/fuentes-datos.ts`). Si quien entra no es admin vuelve al inicio; un 403
del servidor se muestra como falta de permiso. Arriba va "← Cargar datos". En orden:

1. **Franja**: modo, PC titular, última corrida (resultado, cuándo, cuánto duró y qué
   configuración usó) y las alertas globales. Según el modo, el botón para sembrar
   ("Usar la configuración del PC … como punto de partida"), "Activar" (apagado hasta
   tener las corridas en verde, con el motivo a la vista) o "Volver a prueba".
2. **Fuentes**: las `lee`, de la peor a la mejor, con su semáforo (icono y etiqueta,
   nunca solo el color), archivo, carpeta, fecha relativa y absoluta en hora de Chile,
   filas, el texto del servidor y, en prueba, lo que tomaría la configuración de la
   plataforma. Un clic abre el detalle.
3. **Carpetas por PC**: si existe cada carpeta, cuántos archivos tiene, la ruta
   portable y el método. "Ponerle nombre" y "Hacer titular" por PC.
4. **Detalle de una fuente** (diálogo): cómo elige el archivo, los archivos que calzan
   en cada carpeta (aquí sí la ruta absoluta), descartados, últimas 20 corridas y las
   versiones que la cambiaron, con "Volver a esta versión".
5. **Avanzado** (plegado): las `reconoce`, los patrones de cada fuente, las carpetas
   configuradas (alta y edición), el listado completo de una carpeta y las últimas 30
   corridas.

El **editor** arma las listas de carpeta, subcarpeta y archivos con el último listado
del titular, propone el patrón a partir de un archivo y pide la vista previa sola
mientras se edita. Manda solo los campos que cambiaron, con la nota y `base_version`;
en prueba ofrece la casilla "Es una diferencia esperada (ensayo)". Los controles que
fija el catálogo quedan bloqueados con su explicación, y hoja y fila se ven en solo
lectura. El 409 se muestra con el texto del servidor y un botón para recargar.

**Guía para el día a día** (`/cargar/fuentes/guia`, solo admin): qué mirar cada
mañana, qué hacer en los casos más comunes, cómo dejar el PC listo ("Mantener siempre
en este dispositivo") y el paso mensual del respaldo de ventas.

## Lo que el equipo no ve

- Todo es solo admin. Nada pasa por `auditoria_log` (lo ve todo el que no es
  vendedor) ni por `notificar()` sin `para_email` (le llegaría a todo el equipo).
- No se tocan `/api/ultima-sincronizacion`, el banner del sugerido ni `/modelo`.
- La ruta absoluta de cada carpeta (trae el usuario de Windows) sale solo en el
  detalle de una fuente y en el listado de una carpeta, no en el panel.

## Endpoints

Todos bajo `/api/admin/fuentes`, solo admin. El motor entra con su usuario admin y
el mismo token de siempre.

| Método y ruta | Qué hace |
|---|---|
| `GET /config` | (motor) Configuración vigente + `anterior` (sha256, fecha y filas de la última corrida oficial `ok` del titular). Sin filas: `{"modo": "sin_configurar"}`. |
| `POST /reporte` | (motor) Upsert por `id`, `fase` `inicio` o `fin`. Una clave de fuente desconocida se guarda con aviso. Sobre 2 MB, 413. Un inicio que llega después del fin no lo pisa; una corrida huérfana reportada como `cortada` sin manifiesto conserva lo que trajo su inicio. Una hora sin zona se toma como hora de Chile. |
| `GET ` (la raíz) | Panel: franja, fuentes `lee` de la peor a la mejor, las `reconoce`, carpetas por PC, modo, si se puede activar y desde qué corridas sembrar. |
| `GET /corridas?limit=30` | Historial, con cuántas fuentes quedaron en cada color (a la hora de cada corrida). |
| `GET /carpetas/{clave}/archivos?pc=` | Último listado de esa carpeta (por defecto en el titular), con subcarpetas y un patrón propuesto por archivo, para los selectores. |
| `GET /{clave}` | Configuración, controles bloqueados por el catálogo, estado en las últimas 20 corridas, competencia entre carpetas, descartados y versiones que la cambiaron. |
| `POST /{clave}/vista-previa` | `{cambios}` → `{elegiria, hoy_toma, conflictos, avisos, listado}`. No guarda. |
| `PUT /{clave}` | `{cambios, nota, base_version}`. |
| `POST /carpetas`, `PUT /carpetas/{clave}` | Alta y edición de carpetas, con `nota` y `base_version`. |
| `PUT /pcs/{hostname}` | `{alias, base_version, nota?}`. |
| `POST /titular` | `{pc, nota, base_version}`. |
| `POST /modo` | `{modo: prueba\|activa, nota, base_version}`. |
| `POST /sembrar` | `{corrida_id, nota?}`. Con configuración ya hecha, 409. |
| `POST /revertir/{version}` | `{nota?, base_version?, clave?}`. |

Errores: 422 con el texto para la persona, 409 (otro admin guardó antes, ya hay
configuración, o no se cumple la condición para activar), 404 (no existe esa fuente,
carpeta, versión, corrida o PC).
