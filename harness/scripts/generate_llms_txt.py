"""
Generate /llms.txt and /llms-full.txt for LLM consumption (Hermes-inspired standard).
Concatenates key documentation files into a single LLM-friendly context file.
"""
import os
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
DOCS_DIR = ROOT / "docs"
LLMS_TXT = ROOT / "docs" / "llms.txt"
LLMS_FULL_TXT = ROOT / "docs" / "llms-full.txt"

KEY_FILES = [
    "index.md",
    "arquitectura/index.md",
    "arquitectura/adr-001-base-datos.md",
    "dominios_negocio/sistema-agentes.md",
    "dominios_negocio/context-engineering.md",
    "manual_usuario/agentes.md",
    "manual_usuario/cli.md",
]

def generate_llms_txt():
    lines = []
    lines.append("# Onyx Multi-Agent System")
    lines.append("## LLMs.txt — Contexto curado para LLMs")
    lines.append("")
    lines.append("> Generado automáticamente. Última actualización: ver git log.")
    lines.append("")
    lines.append("## Enlaces a documentación clave")
    lines.append("")
    for f in KEY_FILES:
        path = DOCS_DIR / f
        if path.exists():
            relative = f"docs/{f}"
            with open(path, encoding="utf-8") as fp:
                content = fp.read()
            title_line = content.split("\n")[0] if content else f
            lines.append(f"- [{title_line.strip('# ')}]({relative})")
    lines.append("")
    lines.append("## Skills Activos (19)")
    lines.append("")
    lines.append("| Skill | Descripción |")
    lines.append("|-------|-------------|")
    skills = [
        ("project-manager", "Orquestación F.R.A.M.E."),
        ("context-engineer", "Context curation, compactación, memoria"),
        ("tool-mcp-engineer", "Ecosistema de herramientas MCP"),
        ("software-engineer", "Full-stack, APIs, servicios"),
        ("data-architect", "Schemas, modelos, migraciones"),
        ("devops-sre", "CI/CD, Docker, infraestructura"),
        ("security-engineer", "Seguridad, compliance, hardening"),
        ("frontend-engineer", "UI/UX, dashboards, visualizaciones"),
        ("mobile-engineer", "Apps móviles"),
        ("ai-engineer", "ML/AI, pipelines, LLMOps"),
        ("quality-gate", "QA, test strategy, cobertura"),
        ("documentation-specialist", "Documentación técnica"),
        ("requirements-analyst", "Análisis de requerimientos"),
        ("enterprise-architect", "Arquitectura de sistemas, ADR"),
        ("quant-developer", "Estrategias cuantitativas"),
        ("quant-scientist", "Validación estadística, experimentos"),
        ("risk-manager", "Gestión de riesgo, position sizing"),
        ("trading-operations", "Operaciones en vivo, monitoreo"),
        ("evolve", "Meta-skill de auto-mejora"),
    ]
    for name, desc in skills:
        lines.append(f"| @{name} | {desc} |")
    lines.append("")
    lines.append("## Comandos Rápidos")
    lines.append("")
    lines.append("- `@rol: mensaje` — Delegación directa a un agente")
    lines.append("- `!evolve status` — Estado del loop de mejora")
    lines.append("- `!evolve run <skill> <rounds>` — Ejecutar mejora")
    lines.append("- `!evolve cognition add <title> <content>` — Añadir conocimiento")
    lines.append("- `!evolve cognition search <query>` — Buscar en memoria")
    lines.append("")
    lines.append("---")
    lines.append("*Powered by Onyx Multi-Agent Framework*")
    
    content = "\n".join(lines)
    with open(LLMS_TXT, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"[OK] {LLMS_TXT} — {len(content)} caracteres")

def generate_llms_full_txt():
    sections = []
    for f in KEY_FILES:
        path = DOCS_DIR / f
        if path.exists():
            with open(path, encoding="utf-8") as fp:
                content = fp.read()
            sections.append(f"# === docs/{f} ===\n\n{content}")
    
    content = "\n\n".join(sections)
    with open(LLMS_FULL_TXT, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"[OK] {LLMS_FULL_TXT} — {len(content)} caracteres, ~{len(content)//4} tokens estimados")

if __name__ == "__main__":
    print("Generando /llms.txt y /llms-full.txt...")
    generate_llms_txt()
    generate_llms_full_txt()
    print("Done. Los LLMs externos pueden consumir docs/llms.txt")
