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
  4; la pantalla lo lee de `GET /api/admin/usuarios/reglas`).
- **Editar**: nombre, roles, sucursales y si la cuenta esta activa. Viaja solo lo
  que cambio: el servidor deja igual lo que no llega, asi que cambiar un nombre no
  puede quitarle el admin a nadie.
- **Desactivar, no borrar**: un usuario borrado se llevaria la trazabilidad de lo
  que creo (sugerencias, requerimientos, auditoria). Desactivado no puede entrar.
- **Cambiar clave**: la nueva se escribe dos veces o se genera al azar en el
  navegador. La guardada nunca se muestra: el servidor solo tiene un hash
  (PBKDF2) y no hay forma de recuperarla.

Un admin no puede quitarse el admin ni desactivarse a si mismo (la pantalla
bloquea esas casillas y el servidor responde 400 si llega igual). Los errores
400 del servidor se muestran tal cual.

## Roles y sucursales

| Rol | Que cambia |
|---|---|
| Admin | Administra la plataforma: usuarios, carga de datos y todo lo demas. Tiene todos los permisos especiales. |
| Solo lectura | Ve todo pero no crea ni modifica sugerencias ni requerimientos (`requiere_escritura`). |
| Vendedor de sucursal | Menu propio: solo arma y sigue requerimientos (`requiere_comprador` lo saca del resto). |

**Sucursales** (`sucursales_permitidas`): para un vendedor son por las que puede
pedir, y necesita al menos una (si no, el servidor rechaza el alta). Para el
resto restringen lo que ve; sin ninguna ve todas. La lista sale de
`GET /api/sucursales`, la misma de los filtros del sugerido. Si un usuario tiene
una sucursal que ya no esta en esa lista, la pantalla la muestra igual para no
quitarsela al guardar.

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
`.env` (o devolverle el admin o reactivarla).

## API

| Endpoint | Que hace |
|---|---|
| `GET /api/admin/usuarios` | Lista. Nunca trae la clave ni el hash. |
| `GET /api/admin/usuarios/reglas` | `{"largo_minimo_clave": 4}` para validar antes de mandar. |
| `POST /api/admin/usuarios` | Crea o actualiza por correo (idempotente). Solo cambia los campos que llegan; con `password` reemplaza la clave. |
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
- Pruebas: `apps/api/tests/test_usuarios.py`, `tests/test_usuarios_pantalla.py`,
  `apps/web/__tests__/usuarios-page.test.tsx`, `usuarios-lib.test.ts`,
  `sidebar-usuarios.test.tsx`.
