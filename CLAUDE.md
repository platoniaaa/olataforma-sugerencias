# Sugerido de compras CURIFOR

Monorepo: `apps/api` (FastAPI + SQLAlchemy, Postgres/Supabase) y `apps/web` (Next.js 14).

## Varias sesiones trabajan en este repo al mismo tiempo

Este proyecto se trabaja con **varias sesiones de Claude Code en paralelo**, muchas veces
sobre el mismo working tree. Git no las aísla: todas ven y escriben los mismos archivos.
Antes de tocar nada, asume que hay trabajo ajeno a medio hacer alrededor.

### Reglas duras

1. **Nunca `git add -A`, `git add .`, `git add -u` ni `git commit -am`.**
   Commitea siempre con rutas explícitas:
   `git commit ruta/uno.py ruta/dos.tsx -m "..."`.
   Un `add -A` se lleva el trabajo a medias de otra sesión dentro de tu commit.

2. **Nunca `git stash`, `git reset --hard`, `git checkout .`, `git restore .` ni `git clean`.**
   Son globales sobre el working tree: borran lo de las otras sesiones sin avisar.
   Si el working tree está sucio con trabajo que no es tuyo, trabaja alrededor o abre un
   worktree. El 30-07-2026 una sesión stasheó trabajo ajeno ("trabajo previo no mio");
   se recuperó de milagro porque quien lo hizo se acordó de devolverlo.

3. **Nunca `git push --force`** a `main`. El historial remoto solo crece.

4. **No toques archivos fuera del alcance de tu tarea**, aunque se vean rotos o a medio
   escribir. Es otra sesión trabajando, no un descuido.

### Antes de empezar

```bash
git log --oneline -3        # qué se commiteó recién
git status --short          # qué hay a medio hacer (tuyo y ajeno)
git stash list              # si hay algo guardado, avisa antes de tocarlo
cat "$(git rev-parse --git-common-dir)/EN-CURSO.md"
```

Anota tu tarea en ese `EN-CURSO.md` (una línea: fecha, rama, archivos que vas a tocar) y
bórrala al terminar. Vive en el directorio común de git, así que es el mismo archivo para
todos los worktrees y no ensucia el historial. Es el único lugar donde las sesiones se
enteran unas de otras: no hay ningún otro canal entre ellas.

Si otra sesión ya declaró los mismos archivos, **no trabajes ahí en paralelo**: la segunda
escritura gana y la primera desaparece sin dejar rastro en git.

### El usuario no sabe que archivos toca cada tarea — y no tiene por que saberlo

Pide en lenguaje natural ("que la carga masiva avise si no tiene fecha limite") y no
programa. **Nunca le preguntes si dos tareas se solapan, ni le pidas que decida entre
sesiones segun archivos o carpetas: no puede responder eso.** Averigualo tu:

1. Apenas sepas que archivos vas a tocar, anotalos en `EN-CURSO.md` (antes de editar,
   no despues).
2. Revisa si otra sesion ya declaro alguno de esos archivos.
3. Si hay choque, **avisale en lenguaje simple, antes de escribir una sola linea**, y
   ofrecele la salida. Por ejemplo:

   > Hay otra sesion trabajando en el sugerido, que toca los mismos archivos que esto.
   > Dos opciones: espero a que termine, o lo hago en una copia aparte y lo junto
   > despues. ¿Que prefieres?

   No sigas hasta que responda: si escribes igual, la otra sesion pierde su trabajo.
4. Si no hay choque, sigue sin molestarlo con detalles de archivos.

Traduccion practica de "se tocan entre si": si dos sesiones estan hablando del **mismo
tema de negocio** (sugerencias manuales, el modelo/sugerido, InStock, compras, el
dashboard), casi seguro comparten archivos. Temas distintos, casi nunca. Pero la
verificacion la haces tu con `EN-CURSO.md` y `git status`, no el usuario a ojo.

### Revisar si se perdio trabajo

Cuando pregunte algo como "¿se habran borrado cambios?", esto es lo que responde de
verdad (todo solo lectura):

```bash
git reflog show origin/main --date=iso | head -20   # "forced-update" = alguien reescribio el remoto
git reflog --date=iso -30                           # reset --hard, rebases, amends de todas las sesiones
git stash list                                      # stashes vivos (ojo si alguien guardo trabajo ajeno)
git fsck --unreachable 2>/dev/null | grep commit    # stashes dropeados y commits huerfanos
```

Si aparece un stash sospechoso, compara sus lineas contra los archivos actuales antes de
afirmar que no se perdio nada. Lo que nunca se commiteo ni stasheo no deja rastro en git:
ahi la unica red es el **Historial de versiones de OneDrive** (el repo esta sincronizado),
y conviene decirselo en vez de dar por hecho que no habia nada.

### Antes de pushear

```bash
git pull --rebase
```

Y commitea solo tus rutas. Si al hacer `status` aparece trabajo ajeno, déjalo donde está.

### Trabajo aislado (recomendado para tareas largas)

```bash
git worktree add C:/dev/curifor-<tarea> -b <rama>
```

Fuera de OneDrive (el repo está sincronizado y tres copias generan conflictos de sync).
Cada worktree necesita su propio `npm install` y su `.venv`.

## Verificar los cambios

- Front: `cd apps/web && npm test` y `node_modules/.bin/tsc --noEmit -p apps/web/tsconfig.json`
  desde la raíz.
- `npm run lint` **no funciona**: ESLint no está configurado y abre un asistente interactivo.

## Datos

`.env` en la raíz apunta a la base **de producción** (Supabase). Cualquier script que la
consulte debe ser de solo lectura salvo que el usuario pida explícitamente lo contrario.
