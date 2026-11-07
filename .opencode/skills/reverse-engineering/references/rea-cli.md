# CLI REA — comandos y flags (detalle bajo demanda)

> Fuente: docs de REA (rea.tools).

REA (“Reverse Engineer Anything”) expone una CLI global `rea` (Node 22+/24+/26+).
Instalación: `npm install --global rea-agents`. Alternativa sin instalar: vía MCP
con `npx -y rea-agents@latest mcp`.

## Descubrimiento / entorno
```bash
rea doctor --json        # diagnóstico de entorno (engine, rutas, providers)
rea providers --json     # proveedores disponibles (hopper | ghidra | ida)
rea capabilities --json  # capacidades por tipo de target
```

## Análisis
```bash
rea analyze PATH --json                              # análisis genérico dirigido por tipo
rea analyze PATH --provider hopper|ghidra|ida --json # binario nativo con provider explícito
rea analyze-javascript-application PATH --json       # JS/Electron (.asar), estático
```

## Inspección (inspect-*)
```bash
rea inspect-binary PATH --json        # formato, secciones, entropía
rea inspect-metadata PATH --json      # .NET/metadata (ensamblados)
rea inspect-website URL --json        # endpoints, assets, rutas
rea inspect-sqlite FILE --json        # esquema y tablas
```

## Consulta sobre el análisis
```bash
rea search PATH --pattern REGEX --json     # busca strings/símbolos
rea function PATH --name SYMBOL --json     # recupera una función
rea decompile PATH --function SYMBOL --json# pseudocódigo
rea xrefs PATH --symbol SYMBOL --json       # referencias cruzadas (quién usa qué)
rea trace PATH --entry SYMBOL --json        # rastrea flujo de datos/ejecución
```

## Comparación y evidencia
```bash
rea compare A B --json                # diff entre dos artefactos (versiones/parches)
rea evidence-import FILE --json       # reimporta evidencia serializada
rea evidence-export --json            # exporta evidencia reproducible del hallazgo
```

## Flags transversales
- `--json` — salida estructurada (usar SIEMPRE para encadenar al harness).
- `--provider <hopper|ghidra|ida>` — motor de decompilación para binarios nativos.
- PATH/URL aceptan ficheros (`.asar`, `.dll`, `.exe`, `.so`, `.db`) o endpoints.

## Notas de operación
- Sin engine nativo, REA cubre JS/Electron estático, .NET, websites, Go/Rust.
- `doctor`/`providers` primero: la mayoría de fallos son de entorno, no de REA.
- Encadenar `analyze → search → xrefs → decompile → evidence-export` para trazabilidad.
