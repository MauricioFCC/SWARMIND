#!/usr/bin/env python3
"""
Generador de paginas de skills para docs/src/skills/
Lee SKILL.md de cada skill en .opencode/skills/ y crea pagina .md en docs/src/skills/
"""

import os
import re
import yaml
from pathlib import Path

SKILLS_DIR = Path(r"C:\Users\USUARIO\Documents\DEV-SPACE\AGENTIC\.opencode\skills")
OUTPUT_DIR = Path(r"C:\Users\USUARIO\Documents\DEV-SPACE\AGENTIC\docs\src\skills")

# Mapeo de dominio a categoria
DOMAIN_CATEGORY = {
    "marketing": "Marketing",
    "research": "Investigacion",
    "economics": "Finanzas y Economia",
    "business": "Negocio y Gestion",
    "communication": "Comunicacion",
    "design": "Diseno y Creatividad",
    "devops": "DevOps e Infraestructura",
    "education": "Educacion",
    "philosophy": "Filosofia y Etica",
    "frontend": "Frontend y UI/UX",
    "healthtech": "Salud y HealthTech",
    "trading": "Trading y Finanzas",
    "linguistics": "Linguistica",
    "math": "Matematicas",
    "science": "Ciencias",
    "pos-retail": "Retail y Punto de Venta",
    "management": "Gestion de Proyectos",
    "psychology": "Psicologia",
    "risk": "Gestion de Riesgos",
    "security": "Seguridad",
    "sociology": "Sociologia",
    "environment": "Sostenibilidad y ESG",
    "software": "Arquitectura de Software",
    "systems": "Sistemas y Lenguajes",
    "data": "Data Science y ML",
    "finance": "Finanzas",
    "legal": "Legal",
    "academic": "Academico",
    "health": "Salud",
    "retail": "Retail",
    "meta": "Meta-Skills",
    "": "General",
}

def extract_frontmatter(content):
    """Extrae el frontmatter YAML de un SKILL.md"""
    match = re.match(r'^---\s*\n(.*?)\n---', content, re.DOTALL)
    if match:
        try:
            return yaml.safe_load(match.group(1))
        except yaml.YAMLError:
            return {}
    return {}

def get_skill_name_from_dir(dir_name):
    """Convierte nombre de directorio a nombre legible"""
    replacements = {
        "ads-optimizer": "Ads Optimizer",
        "alpha-research": "Alpha Research",
        "architecture": "Arquitectura de Software",
        "behavioral-economics": "Behavioral Economics",
        "business-strategy": "Business Strategy",
        "communication": "Communication",
        "creative-design": "Creative Design",
        "data-science": "Data Science",
        "devops-infra": "DevOps e Infraestructura",
        "education": "Education",
        "ethics": "Ethics",
        "evolve": "Evolve",
        "frontend-uiux": "Frontend UI/UX",
        "healthtech": "HealthTech",
        "hedgefund": "Hedge Fund",
        "legal-doc": "Legal Doc",
        "linguistics": "Linguistics",
        "math-doc": "Math Doc",
        "physical-sciences": "Physical Sciences",
        "pos-retail": "POS Retail",
        "project-management": "Project Management",
        "psychology": "Psychology",
        "quant-trading": "Quant Trading",
        "responsive-ui": "Responsive UI",
        "risk-execution": "Risk Execution",
        "risk-intelligence": "Risk Intelligence",
        "rust-lang": "Rust Lang",
        "science-doc": "Science Doc",
        "security-audit": "Security Audit",
        "sociology": "Sociology",
        "sustainability": "Sustainability",
    }
    return replacements.get(dir_name, dir_name.replace("-", " ").title())

def determine_category(metadata):
    """Determina la categoria basada en domain y name"""
    domain = metadata.get("domain", "")
    name = metadata.get("name", "")
    
    # Mapeo directo por nombre
    name_category = {
        "architecture": "Arquitectura de Software",
        "ads-optimizer": "Marketing Digital",
        "alpha-research": "Investigacion Cuantitativa",
        "behavioral-economics": "Finanzas y Economia del Comportamiento",
        "business-strategy": "Estrategia de Negocio",
        "communication": "Comunicacion Profesional",
        "creative-design": "Diseno y Creatividad",
        "data-science": "Data Science y Machine Learning",
        "devops-infra": "DevOps e Infraestructura",
        "education": "Ciencias de la Educacion",
        "ethics": "Etica de IA",
        "evolve": "Meta-Skill de Auto-mejora",
        "frontend-uiux": "Frontend Engineering y UI/UX",
        "healthtech": "HealthTech y Salud Digital",
        "hedgefund": "Doctrina Hedge Fund",
        "linguistics": "Linguistica Aplicada",
        "math-doc": "Documentacion Matematica",
        "physical-sciences": "Ciencias Naturales",
        "pos-retail": "Retail y Punto de Venta",
        "project-management": "Gestion de Proyectos",
        "psychology": "Psicologia Aplicada",
        "quant-trading": "Trading Cuantitativo",
        "responsive-ui": "UI/UX Responsivo",
        "risk-execution": "Gestion de Riesgo y Ejecucion",
        "risk-intelligence": "Inteligencia de Riesgos",
        "rust-lang": "Lenguaje Rust",
        "science-doc": "Documentacion Cientifica",
        "security-audit": "Seguridad y Auditoria",
        "sociology": "Sociologia Aplicada",
        "sustainability": "Sostenibilidad y ESG",
    }
    
    if name in name_category:
        return name_category[name]
    
    # Fallback a mapeo por dominio
    if domain in DOMAIN_CATEGORY:
        return DOMAIN_CATEGORY[domain]
    
    return domain.capitalize() if domain else "General"


def generate_page(name, metadata, description):
    """Genera el contenido de la pagina markdown"""
    skill_name = get_skill_name_from_dir(name)
    category = determine_category(metadata)
    domain = metadata.get("domain", name)
    
    # Construir descripcion
    if not description:
        description = metadata.get("description", f"Skill contextual para el dominio {domain}.")
    
    # Limpiar description de comillas y saltos de linea
    description = description.strip().strip('"').strip("'")
    description = re.sub(r'\s+', ' ', description)
    
    lines = [
        f"# {skill_name}",
        "",
        f"> {description}",
        "",
        "## Categoria",
        "",
        category,
        "",
        "## Proposito",
        "",
        f"{description}",
        "",
        "## Agentes que lo usan",
        "",
        "- Consultar [Registro de Skills](registry.md) para ver los agentes que utilizan este skill.",
        "",
    ]
    
    return "\n".join(lines)


def main():
    output_dir = OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Skills que ya tienen pagina
    existing = {f.stem for f in output_dir.glob("*.md")}
    # Excluir archivos no-skill
    existing.discard("otras")
    existing.discard("registry")
    
    created = []
    skipped = []
    
    # Procesar cada directorio de skill
    for skill_dir in sorted(SKILLS_DIR.iterdir()):
        if not skill_dir.is_dir():
            continue
        
        name = skill_dir.name
        skill_file = skill_dir / "SKILL.md"
        
        if not skill_file.exists():
            skipped.append((name, "No SKILL.md"))
            continue
        
        if name in existing:
            skipped.append((name, "Ya existe pagina"))
            continue
        
        # Leer SKILL.md (manejo robusto de encoding)
        raw = skill_file.read_bytes()
        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError:
            content = raw.decode("windows-1252", errors="replace")
        
        # Extraer frontmatter
        metadata = extract_frontmatter(content)
        if not metadata:
            # Sin frontmatter, usar primera linea heading
            heading_match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
            description = heading_match.group(1) if heading_match else f"Skill {name}"
            metadata = {"name": name, "domain": "", "description": description}
        
        description = metadata.get("description", "")
        
        # Generar pagina
        page_content = generate_page(name, metadata, description)
        
        # Escribir archivo
        output_file = output_dir / f"{name}.md"
        output_file.write_text(page_content, encoding="utf-8")
        created.append(name)
        
        print(f"  -> {name}.md")
    
    # Reporte final
    print(f"\n{'='*60}")
    print(f"Creados: {len(created)} skill pages")
    print(f"Saltados: {len(skipped)}")
    print(f"{'='*60}")
    print("\nCreados:")
    for s in created:
        print(f"  - {s}")
    if skipped:
        print("\nSaltados:")
        for s, reason in skipped:
            print(f"  - {s}: {reason}")


if __name__ == "__main__":
    main()
