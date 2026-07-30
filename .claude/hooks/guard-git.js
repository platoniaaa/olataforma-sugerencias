/**
 * Bloquea los comandos de git que arrasan con el working tree compartido.
 *
 * Varias sesiones de Claude Code trabajan este repo a la vez sobre los mismos
 * archivos. Un `git add -A` se lleva el trabajo a medias de otra sesion dentro de un
 * commit ajeno, y `stash`/`reset --hard`/`clean` lo borran sin dejar rastro en git
 * (lo que nunca se commiteo no se puede recuperar). El 30-07-2026 una sesion stasheo
 * trabajo de otra; se salvo porque quien lo hizo se acordo de devolverlo.
 *
 * Se ejecuta como hook PreToolUse: recibe el tool_input por stdin y corta con exit 2.
 */

let raw = "";
process.stdin.on("data", (c) => (raw += c));
process.stdin.on("end", () => {
  let cmd = "";
  try {
    cmd = JSON.parse(raw)?.tool_input?.command ?? "";
  } catch {
    process.exit(0); // Sin comando que revisar, no estorbamos.
  }
  if (!cmd || !/\bgit\b/.test(cmd)) process.exit(0);

  // Un solo Bash puede encadenar varios comandos; cada uno se revisa por separado.
  for (const segmento of cmd.split(/&&|\|\||\||;|\n/g)) {
    const problema = revisar(segmento);
    if (problema) {
      process.stderr.write(
        `BLOQUEADO: ${problema.motivo}\n\n` +
          `Este repo lo trabajan varias sesiones a la vez sobre el mismo working tree ` +
          `(ver CLAUDE.md). ${problema.alternativa}\n`
      );
      process.exit(2);
    }
  }
  process.exit(0);
});

function revisar(segmento) {
  const toks = segmento.trim().split(/\s+/).filter(Boolean);
  const i = toks.findIndex(
    (t) => t === "git" || t.endsWith("/git") || t.endsWith("git.exe")
  );
  if (i === -1) return null;
  const sub = toks[i + 1];
  const resto = toks.slice(i + 2);
  // Todo lo que va despues de -m es el mensaje, no flags.
  const corte = resto.findIndex((t) => t === "-m" || t === "--message");
  const flags = (corte === -1 ? resto : resto.slice(0, corte)).filter((t) =>
    t.startsWith("-")
  );
  const flagCorta = (letra) =>
    flags.some((f) => /^-[a-zA-Z]+$/.test(f) && f.includes(letra));

  if (sub === "add" && (flagCorta("A") || flagCorta("u") || flags.includes("--all")))
    return {
      motivo: "`git add -A` / `-u` agrega TODO el working tree, incluido el trabajo de otras sesiones.",
      alternativa: "Commitea con rutas explicitas: git commit ruta/a.py ruta/b.tsx -m \"...\".",
    };

  if (sub === "add" && resto.includes("."))
    return {
      motivo: "`git add .` agrega TODO el working tree, incluido el trabajo de otras sesiones.",
      alternativa: "Commitea con rutas explicitas: git commit ruta/a.py ruta/b.tsx -m \"...\".",
    };

  if (sub === "commit" && (flagCorta("a") || flags.includes("--all")))
    return {
      motivo: "`git commit -a` mete en tu commit todos los archivos modificados, tambien los ajenos.",
      alternativa: "Nombra los archivos: git commit ruta/a.py ruta/b.tsx -m \"...\".",
    };

  if (sub === "stash" && !["list", "show"].includes(resto[0]))
    return {
      motivo: "`git stash` guarda (y esconde) el trabajo no commiteado de TODAS las sesiones.",
      alternativa:
        "Trabaja alrededor de lo que este sucio, o aisla la tarea con: git worktree add C:/dev/curifor-<tarea> -b <rama>.",
    };

  if (sub === "reset" && resto.includes("--hard"))
    return {
      motivo: "`git reset --hard` descarta el working tree completo. Lo no commiteado no se recupera.",
      alternativa: "Revierte solo tus archivos: git checkout HEAD -- ruta/que/tocaste.",
    };

  if ((sub === "checkout" || sub === "restore") && resto.includes("."))
    return {
      motivo: `\`git ${sub} .\` descarta los cambios de todo el repo, no solo los tuyos.`,
      alternativa: "Nombra los archivos: git checkout HEAD -- ruta/que/tocaste.",
    };

  // -n / --dry-run solo lista lo que se borraria: sirve para inspeccionar sin riesgo.
  const simulacion = flagCorta("n") || flags.includes("--dry-run");
  if (sub === "clean" && flagCorta("f") && !simulacion)
    return {
      motivo: "`git clean -f` borra archivos sin trackear, incluidos los que otra sesion acaba de crear.",
      alternativa: "Borra a mano solo lo que creaste tu.",
    };

  if (sub === "push" && (flagCorta("f") || flags.some((f) => f.startsWith("--force"))))
    return {
      motivo: "`git push --force` reescribe el historial remoto y puede borrar commits de otras sesiones.",
      alternativa: "Integra con git pull --rebase y vuelve a pushear normal.",
    };

  return null;
}
