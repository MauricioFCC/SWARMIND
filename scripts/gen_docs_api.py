"""gen_docs_api.py — Genera documentacion API Markdown desde docstrings con Griffe.

Usa **Griffe** (parsing AST, sin ejecutar el codigo) para extraer firma y
docstrings de modulos, clases y funciones de `harness/` y generar una
referencia API en Markdown, lista para commit y push.

Eficiencia (TKN): solo AST, cero ejecucion de codigo, cero LLM. La
referencia generada es 1:1 con el codigo fuente: si cambia la firma,
se regenera con un comando.

Uso:
    python scripts/gen_docs_api.py                          # paquete por defecto: harness
    python scripts/gen_docs_api.py --package memory_rag     # solo un paquete
    python scripts/gen_docs_api.py --output docs/src/es/api # salida custom

Exit codes: 0 = exito, 1 = error de entrada, 2 = error de generacion.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import griffe

# ---------------------------------------------------------------------------
# Constantes (MAG)
# ---------------------------------------------------------------------------
_HARNESS_ROOT = Path(__file__).resolve().parents[1] / "harness"
_DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "docs" / "src" / "es" / "api"
_DEFAULT_PACKAGE = "harness"
_HEADER = "<!-- GENERADO POR scripts/gen_docs_api.py — NO editar a mano. Regenerar con `python scripts/gen_docs_api.py`. -->"
_ESCAPE_TABLE = str.maketrans({"_": r"\_", "*": r"\*", "|": r"\|"})
# Submodulos sin valor de API publica (tests, internos de build).
_SKIP_SUBMODULES = frozenset({"tests"})


def _escape(text: str) -> str:
    """Escapa caracteres Markdown reservados en texto plano.

    Args:
        text: Texto original.

    Returns:
        Texto con caracteres reservados escapados para Markdown.
    """
    return text.translate(_ESCAPE_TABLE)


def _docstring_summary(docstring: griffe.Docstring | None) -> str:
    """Extrae la primera linea (summary) de un docstring.

    Args:
        docstring: Docstring griffe o None.

    Returns:
        Primera linea no vacia del docstring, o "Sin docstring".
    """
    if docstring is None:
        return "_Sin docstring._"
    for line in docstring.value.splitlines():
        if line.strip():
            return _escape(line.strip())
    return "_Sin docstring._"


def _render_function(func: griffe.Function) -> str:
    """Renderiza una funcion o metodo como bloque Markdown.

    Args:
        func: Objeto griffe.Function.

    Returns:
        Bloque Markdown con firma y summary del docstring.
    """
    sig = _escape(func.signature()) or "()"
    lines = [
        f"### `{sig}`",
        "",
        _docstring_summary(func.docstring),
        "",
    ]
    if func.docstring is not None:
        for section in func.docstring.parsed:
            if section.kind.name == "PARAMETERS":
                lines.append("**Parámetros:**")
                lines.append("")
                for item in getattr(section, "value", []):
                    lines.append(f"- `{_escape(str(item.name))}`: {_escape(str(item.description or ''))}")
                lines.append("")
            elif section.kind.name == "RETURNS":
                for item in getattr(section, "value", []):
                    lines.append(f"**Retorna:** {_escape(str(item.description or item.name or ''))}")
                    lines.append("")
            elif section.kind.name == "RAISES":
                lines.append("**Lanza:**")
                lines.append("")
                for item in getattr(section, "value", []):
                    lines.append(f"- `{_escape(str(item.annotation or item.name or ''))}`: {_escape(str(item.description or ''))}")
                lines.append("")
    return "\n".join(lines)


def _render_class(cls: griffe.Class) -> str:
    """Renderiza una clase como bloque Markdown con sus metodos.

    Args:
        cls: Objeto griffe.Class.

    Returns:
        Bloque Markdown de la clase y sus metodos publicos.
    """
    bases = f"({_escape(', '.join(str(b) for b in cls.bases))})" if cls.bases else ""
    lines = [
        f"## `{cls.name}{bases}`",
        "",
        _docstring_summary(cls.docstring),
        "",
    ]
    for member in cls.members.values():
        if isinstance(member, griffe.Function) and not member.name.startswith("_"):
            lines.append(_render_function(member))
    return "\n".join(lines)


def _render_module(module: griffe.Module, package_name: str) -> str:
    """Renderiza un modulo como seccion Markdown completa.

    Args:
        module: Objeto griffe.Module.
        package_name: Nombre del paquete al que pertenece.

    Returns:
        Seccion Markdown del modulo (con indice de submódulos si es paquete).
    """
    lines = [
        _HEADER,
        "",
        f"# API — `{package_name}`",
        "",
        _docstring_summary(module.docstring),
        "",
    ]
    submodules = [
        (name, member)
        for name, member in module.members.items()
        if isinstance(member, griffe.Module)
        and not name.startswith("_")
        and name not in _SKIP_SUBMODULES
    ]
    if submodules:
        lines.append("## Submódulos")
        lines.append("")
        for name, member in sorted(submodules):
            lines.append(f"- [`{package_name}.{name}`]({package_name}.{name}.md)")
        lines.append("")
    for member in module.members.values():
        if member.name.startswith("_"):
            continue
        if isinstance(member, griffe.Class):
            lines.append(_render_class(member))
        elif isinstance(member, griffe.Function):
            lines.append(_render_function(member))
    return "\n".join(lines)


def generate(package: str, output: Path) -> Path:
    """Genera la referencia API del paquete indicado en el directorio de salida.

    Args:
        package: Nombre del paquete dentro de harness/ (o "harness").
        output: Directorio donde se escriben los .md generados.

    Returns:
        Ruta del archivo de indice generado.

    Raises:
        FileNotFoundError: Si el paquete no existe en harness/.
    """
    output.mkdir(parents=True, exist_ok=True)
    pkg_path = _HARNESS_ROOT if package == "harness" else _HARNESS_ROOT / package
    if not pkg_path.exists():
        raise FileNotFoundError(
            f"WHAT: paquete '{package}' no existe en harness/"
            f"WHY: la ruta {pkg_path} no se encuentra"
            f"WHERE: scripts/gen_docs_api.py -> generate()"
        )
    full_name = package if package == "harness" else f"harness.{package}"
    top = griffe.load("harness", search_paths=[str(_HARNESS_ROOT.parent)])
    mod = top if package == "harness" else top[package]
    generated: list[Path] = []
    for name, member in mod.members.items():
        if isinstance(member, griffe.Module) and not name.startswith("_"):
            if name in _SKIP_SUBMODULES:
                continue
            out_file = output / f"{full_name}.{name}.md"
            out_file.write_text(
                _render_module(member, f"{full_name}.{name}"), encoding="utf-8"
            )
            generated.append(out_file)
    if package == "harness":
        index = output / "README.md"
    else:
        index = output / f"{full_name}.md"
    index.write_text(_render_module(mod, full_name), encoding="utf-8")
    return index


def main() -> int:
    """Punto de entrada CLI: genera la referencia API y reporta el resultado.

    Returns:
        0 si todo es correcto; 2 si la generacion falla.
    """
    parser = argparse.ArgumentParser(description="Genera API docs con Griffe")
    parser.add_argument("--package", default=_DEFAULT_PACKAGE, help="Paquete a documentar")
    parser.add_argument("--output", type=Path, default=_DEFAULT_OUTPUT, help="Directorio de salida")
    args = parser.parse_args()
    try:
        index = generate(args.package, args.output)
    except FileNotFoundError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    print(f"OK: referencia API generada en {index}")
    return 0


if __name__ == "__main__":
    sys.exit(main())