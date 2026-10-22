---
name: cert-master
domain: education
version: 1.0.0
project_agnostic: true
description: "Usar cuando el usuario quiere convertir material de estudio (PDFs, programas, transcripciones) en apuntes para Obsidian, Notion o Markdown, con quizzes y mapas de contenido. Alcance: notas de estudio, resumenes, preparacion de examenes, certificaciones y oposiciones; educacion y estudio. | UPG.NAM.FRS (reglas en base_principles.md)"
license: MIT
---

# CertMaster (min)

Convierte material de estudio (PDFs, syllabi, transcripciones) en apuntes Markdown para Obsidian/Notion con quizzes y mapas de contenido.

## Reglas clave
- Texto es ley: no extrapolar, no inventar compatibilidades.
- Ignorancia explicita si falta dato.
- Chunking: max un capitulo/modulo por vez.
- Dual-Response: Layer1 explicacion pedagogica + Layer2 asset tecnico aislado.
- Plataformas: Obsidian (YAML + callouts) o Notion/Markdown estandar.
- Comandos: /quiz (5 preguntas), /moc (mapa de contenido), /video <url>, /setup, /tools, /audit.

## Plantillas
Obsidian: frontmatter type/cert_name/module/topics/difficulty/last_reviewed/status + secciones (Executive Summary, Blueprint, Implementation, Exam Trap, Vault Connections).
Notion: formato limpio con tags/difficulty/status.

## Sub-sistemas
- Vault Interlinking (links [[Concept]])
- Transcription Sanitizer (filtrar tics/meta)
- Crystalline Code (placeholders <VAR>, comentarios)
- MCP Ecosystem (Filesystem/Notion/Search)
