// compaction-context.js — ADR-0039 #3: inyectar/preservar contexto persistente
// al compactar (estado de tarea, decisiones, archivos activos, hand-offs).
//
// PORT A LA API DE PLUGINS DE OPENCODE V2 (2026-10).
//   V1: `export default async ({...}) => ({ "experimental.session.compacting": fn })`
//        ya NO se ejecuta en V2 (runtime log: "PluginModule.LoadError: Plugin must
//        export a default definition with an id and an effect or setup function").
//   V2: default export = objeto con `id` + `setup(ctx)`; los hooks se REGISTRAN
//        sobre el dominio que los posee:
//          experimental.session.compacting -> ctx.session.hook("compaction", ...)
//
// Carga: opencode auto-descubre `.opencode/plugin/` (y `.opencode/plugins/`).
// Sin dependencias: NO importa `@opencode/plugin` (este repo no instala npm;
// un import romperia la carga con ERR_MODULE_NOT_FOUND).
//
// Mutacion SEGURA: solo agrega texto al bloque `system` del pedido de resumen
// si el evento lo expone; nunca lanza ni pisa `result` (si `result` esta set,
// opencode omite la llamada al modelo y nosotros no la interceptamos).
//
// Logging: process.stderr.write (console.error NO permitido en este repo).

const PERSISTENT_CONTEXT = `## Contexto persistente (compaction-context plugin, ADR-0039 #3)
Preserva en el resumen de compactacion el estado que debe sobrevivir a la sesion:
- Estado de la tarea actual: objetivo, progreso, bloqueos y siguiente accion.
- Decisiones tomadas: que se decidio, por que, y que archivos las registran.
- Archivos activos: rutas y rol de cada archivo en la tarea.
- Hand-offs de subagentes: que se delego, a quien, y que artefactos produjo cada uno.`;

export default {
  id: "swarmind.compaction-context",

  async setup(ctx) {
    try {
      await ctx.session.hook("compaction", (event) => {
        if (!event) return;
        if (Array.isArray(event.system)) {
          event.system.push({ type: "text", text: PERSISTENT_CONTEXT });
        } else if (typeof event.system === "string") {
          event.system = `${event.system}\n\n${PERSISTENT_CONTEXT}`;
        }
      });
    } catch (err) {
      // nunca romper la carga del plugin: log y seguir
      process.stderr.write(
        "[compaction-context] no se pudo registrar session.hook('compaction'): " +
          (err && err.message) +
          "\n"
      );
    }
  },
};
