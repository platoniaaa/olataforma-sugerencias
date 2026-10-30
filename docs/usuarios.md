# Usuarios

Quien entra a la plataforma y con que permisos. Hasta el 16-10-2026 los usuarios
se manejaban solo por la API (`POST /api/admin/usuarios`) o con
`scripts/clave_usuario.py`; desde esa fecha hay pantalla para que cualquier admin
los administre sin tocar la base ni un script.

Pantalla: `/usuarios`, item "Usuarios" del menu. Solo la ve un admin; quien no lo
es y escribe la URL vuelve al inicio. El gate real es el servidor: el router
entero exige admin (`main.py`, `dependencies=[Depends(requiere_admin)]`).

## Que se puede hacer

- **Crear**: correo, nombre, clave inicial, roles y sucursales. La clave tiene
  que tener al menos `LARGO_MINIMO_CLAVE` caracteres (`routers/usuarios.py`, hoy
  4; la pantalla lo lee de `GET /api/admin/usuarios/reglas`). Si el correo ya
  tiene cuenta no se crea nada: la pantalla lo dice al escribirlo ("Ya existe un
  usuario con ese correo...") y manda `solo_crear: true`, con lo que el servidor
  responde 409 si llega igual (por ejemplo, desde otra pestaña). Antes de eso,
  crear con el correo del motor le cambiaba la clave y le quitaba el admin.
- **Editar**: nombre, roles, sucursales y si la cuenta esta activa. Viaja solo lo
  que cambio: el servidor deja igual lo que no llega, asi que cambiar un nombre no
  puede quitarle el admin a nadie.
- **Desactivar, no borrar**: un usuario borrado se llevaria la trazabilidad de lo
  que creo (sugerencias, requerimientos, auditoria). Desactivado no puede entrar,
  y si tenia la sesion abierta queda afuera en su siguiente accion:
  `requiere_auth` (services/auth.py) revisa en cada peticion que la cuenta exista
  y este activa, y responde 401 si no. Hasta el 16-10-2026 solo lo revisaba el
  login, y un admin desactivado seguia siendo admin con su sesion hasta 12 horas.
- **Cambiar clave**: la nueva se escribe dos veces o se genera al azar en el
  navegador. La guardada nunca se muestra: el servidor solo tiene un hash
  (PBKDF2) y no hay forma de recuperarla. La anterior deja de servir para entrar,
  pero una sesion ya abierta sigue hasta que vence (`token_horas`, hoy 12; la
  pantalla lo dice con `horas_sesion` de `/reglas`). Para sacar a alguien de
  inmediato hay que desactivarlo. Cortar las sesiones al cambiar la clave pide
  guardar en `usuario` desde cuando valen: queda pendiente.

Un admin no puede quitarse el admin, desactivarse ni marcarse vendedor a si mismo
(la pantalla bloquea esas casillas y el servidor responde 400 si llega igual):
como vendedor perderia todo Abastecimiento y el menu de admin. Los errores 400 y
409 del servidor se muestran tal cual.

Los dialogos llevan el foco al primer campo al abrirse (Correo, Nombre o Clave
nueva) y lo devuelven al boton que los abrio al cerrarse. Lo escrito en las
claves se borra al cerrar o guardar.

## Roles y sucursales

| Rol | Que cambia |
|---|---|
| Admin | Administra la plataforma: usuarios, carga de datos y todo lo demas. Tiene todos los permisos especiales. |
| Solo lectura | Ve todo pero no crea ni modifica sugerencias manuales, pedidos de compra ni la lista InStock (`requiere_escritura`). Los requerimientos de sucursal no pasan por ahi: los puede procesar o rechazar. |
| Vendedor de sucursal | Menu propio: consulta productos (`Productos`, sin costo; ver `docs/consulta-productos.md`), arma y sigue requerimientos (`requiere_comprador` lo saca del resto, incluido el chat). |

**Sucursales** (`sucursales_permitidas`): para un vendedor son por las que puede
pedir, y necesita al menos una (si no, el servidor rechaza el alta). Para el
resto restringen lo que ve; sin ninguna ve todas. La lista sale de
`GET /api/admin/usuarios/sucursales`: la misma consulta de `GET /api/sucursales`
(con las sucursales ocultas fuera), pero sin filtrar por las sucursales del admin
que mira; si no, un admin restringido solo podria asignar las suyas. Una API
anterior a esa ruta responde 404 y la pantalla usa la lista general.

Si un usuario tiene una sucursal que ya no esta en la lista, la pantalla la
muestra igual con "(ya no está en la lista)" para no quitarsela al guardar, y se
puede desmarcar y volver a marcar. Mientras la lista no llega, o si fallo, no se
pone esa etiqueta.

## Permisos especiales (solo lectura)

No estan en la base sino en la configuracion del servidor, por correo
(`config.py`, separados por coma). La pantalla los muestra con la nota "Se
definen en la configuracion del servidor"; para cambiarlos hay que editar la
variable en Render.

| Permiso | Variable | Se evalua en |
|---|---|---|
| Editar la lista de precios | `EMAILS_PRECIOS` | `auth.puede_precios` |
| Configurar el modelo | `EMAILS_CALIBRACION` | `auth.puede_calibrar` |
| Ver los accesos en Auditoria | `EMAILS_VER_ACCESOS` | `auth.requiere_ver_accesos` |
| Pedir "Actualizar ahora" | `EMAILS_ACTUALIZAR` | `auth.puede_actualizar` |

"Actualizar motor" (que el PC del motor baje la ultima version desde GitHub) es solo
de admin: estar en `EMAILS_ACTUALIZAR` no alcanza, porque cambia el programa que
calcula para todo el equipo (`routers/actualizacion.py`, `solicitar`).

La API los devuelve en `permisos_especiales` con la misma comparacion (correo en
minusculas contra la lista), sin el "o es admin": un admin ya los tiene todos.
`tests/test_usuarios_pantalla.py` compara las dos evaluaciones para que no se
desfasen.

## La cuenta del motor

El motor publica el sugerido entrando con una cuenta admin de la plataforma
(`PLATAFORMA_EMAIL` y `PLATAFORMA_PASSWORD` en el `.env` del PC donde corre).
`EMAILS_MOTOR` (por defecto `admin@curifor.com`) dice cual es; no da ningun
permiso, solo marca la cuenta con "La usa el motor".

Cambiarle la clave, quitarle el admin o desactivarla deja al motor sin publicar.
La pantalla avisa "Si cambias esto, el motor deja de publicar hasta que se
actualice la clave en el PC donde corre" y no deja guardar hasta marcar que se
entiende. Despues del cambio hay que actualizar `PLATAFORMA_PASSWORD` en ese
`.env` (o devolverle el admin o reactivarla). Desactivarla corta tambien una
corrida que este en curso, a mitad de la publicacion.

Marcarla como vendedor la rompe de otra forma: `requiere_comprador` le responde
403 en `/api/ventas-historicas/meta`, `/api/requerimiento/sku-proveedor` y
`/api/precios/recalcular`, que el motor llama en cada corrida, mientras
`/api/admin/cargar-sugerido` sigue publicando (publicacion a medias). Por eso la
pantalla no ofrece Vendedor para esa cuenta y el servidor responde 400. Solo
lectura y sucursales no la afectan: el motor no usa rutas que miren esos campos.

## API

| Endpoint | Que hace |
|---|---|
| `GET /api/admin/usuarios` | Lista. Nunca trae la clave ni el hash. |
| `GET /api/admin/usuarios/reglas` | `{"largo_minimo_clave": 4, "horas_sesion": 12}` para validar y avisar antes de mandar. |
| `GET /api/admin/usuarios/sucursales` | Todas las sucursales que se pueden asignar, sin el filtro del admin que pregunta. |
| `POST /api/admin/usuarios` | Crea o actualiza por correo (idempotente). Solo cambia los campos que llegan; con `password` reemplaza la clave. Con `solo_crear: true` responde 409 si el correo ya existe. |
| `POST /api/admin/usuarios/{email}/desactivar` | Desactiva. La pantalla no lo usa: manda `activo: false` por el POST. |

La respuesta sumo dos campos el 16-10-2026, al final y con valor por defecto, asi
que quien ya la leia (`scripts/clave_usuario.py`) no ve cambios:
`es_cuenta_motor` (bool) y `permisos_especiales` (lista con `precios`,
`calibracion`, `ver_accesos`, `actualizar`).

Cada alta o edicion queda en Auditoria (`usuario_creado`, `usuario_actualizado`)
con quien la hizo. El detalle dice `clave=cambiada` cuando se reemplazo la clave
de un usuario existente y `cuenta_motor=si` cuando es la del motor; la clave
nunca se escribe.

## Archivos

- API: `apps/api/src/routers/usuarios.py`, `schemas/usuario.py`, `config.py`
  (`emails_motor`).
- Web: `apps/web/app/usuarios/page.tsx`, `components/usuarios/`,
  `lib/usuarios.ts`, item en `components/sidebar.tsx`.
- API: `services/auth.py` (`requiere_auth` y `requiere_admin` revisan `activo`).
- Pruebas: `apps/api/tests/test_usuarios.py`, `tests/test_usuarios_pantalla.py`,
  `tests/test_usuarios_revision.py`, `apps/web/__tests__/usuarios-page.test.tsx`,
  `usuarios-lib.test.ts`, `usuarios-clave-memoria.test.tsx`,
  `sidebar-usuarios.test.tsx`.
