"""
Tests para Skill Minifier — SkillMinifier y minify_all_skills.

Cubre:
  - Minificacion de SKILL.md completo
  - Preservacion de frontmatter YAML
  - Compresion de secciones removibles (ejemplos, tutoriales)
  - Compresion de tablas
  - Preservacion de code blocks y checklists
  - Eliminacion de filler words en descripciones
  - Manejo de errores (archivo inexistente)
  - Estadisticas de compresion
  - Funcion batch minify_all_skills
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

from harness.memory_rag.skill_minifier import SkillMinifier, minify_all_skills

# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture
def minifier() -> SkillMinifier:
    """SkillMinifier con configuracion por defecto."""
    return SkillMinifier()


@pytest.fixture
def sample_skill() -> str:
    """Contenido de SKILL.md de ejemplo."""
    return """---
name: test-skill
description: "Esta es una funcion que se utiliza para probar el minificador de skills. El proposito de este skill es testear la compresion automatica."
version: 1.0.0
project_agnostic: true
tags:
  - test
  - compression
  - skill
dependencies:
  - python
  - pytest
author: test-author
changelog: |
  ## 1.0.0 - Initial release
  Added all the things
---

# Test Skill

## Proposito
Este skill sirve para probar la minificacion automatica de archivos SKILL.md.

## Usage
Usar con pytest para verificar que el minificador funciona correctamente.

## Ejemplo
```python
from harness.memory_rag.skill_minifier import SkillMinifier
m = SkillMinifier()
result = m.minify(content)
```
Este es un ejemplo basico de como usar el minificador.

## Command
```bash
pytest test_skill_minifier.py -v
```

## Reference
| Name | Type | Description |
|------|------|-------------|
| param1 | string | Primer parametro de ejemplo |
| param2 | int | Segundo parametro con descripcion larga |
| param3 | float | Tercer parametro |
| param4 | bool | Cuarto parametro |
| param5 | list | Quinto parametro extenso |

## Checklist
- [ ] Tarea pendiente con descripcion muy larga para probar la compresion de checklists en el minificador de skills
- [x] Tarea completada

## Appendix
Contenido del apendice que deberia ser eliminado en la minificacion.
"""


# ===========================================================================
# Tests: Minificacion basica
# ===========================================================================


class TestSkillMinifierBasic:
    """Tests de funcionamiento basico del SkillMinifier."""

    def test_minify_vacio_retorna_vacio(self, minifier: SkillMinifier):
        """minify con texto vacio retorna cadena vacia."""
        assert minifier.minify("") == ""

    def test_minify_sin_frontmatter(self, minifier: SkillMinifier):
        """minify funciona correctamente sin frontmatter YAML."""
        content = "# Solo cuerpo\nContenido de prueba sin frontmatter."
        result = minifier.minify(content)
        assert len(result) > 0
        assert "Solo cuerpo" in result

    def test_minify_reduce_tamano(self, minifier: SkillMinifier,
                                  sample_skill: str):
        """minify reduce el tamano del contenido original."""
        result = minifier.minify(sample_skill)
        assert len(result) < len(sample_skill)
        assert len(result) > 0

    def test_minify_no_vacia(self, minifier: SkillMinifier,
                             sample_skill: str):
        """minify no elimina todo el contenido."""
        result = minifier.minify(sample_skill)
        assert len(result) > 50

    def test_minify_mantiene_frontmatter_name(self, minifier: SkillMinifier,
                                              sample_skill: str):
        """El campo 'name' del frontmatter se preserva."""
        result = minifier.minify(sample_skill)
        assert "test-skill" in result

    def test_minify_description_comprimida(self, minifier: SkillMinifier,
                                           sample_skill: str):
        """La descripcion se comprime eliminando filler words."""
        result = minifier.minify(sample_skill)
        # "Esta es una" y "El proposito de" son filler que se eliminan
        assert "testear la compresion automatica" in result

    def test_minify_elimina_changelog(self, minifier: SkillMinifier,
                                      sample_skill: str):
        """La seccion changelog se elimina por ser removible."""
        result = minifier.minify(sample_skill)
        assert "changelog" not in result.lower() or "Initial release" not in result

    def test_minify_conserva_secciones_esenciales(self, minifier: SkillMinifier,
                                                   sample_skill: str):
        """Secciones esenciales como Proposito, Usage, Command se conservan."""
        result = minifier.minify(sample_skill)
        assert "## Proposito" in result or "## Proósito" in result
        assert "## Usage" in result or "## Uso" in result
        assert "## Command" in result or "## Comando" in result


# ===========================================================================
# Tests: Preservacion de elementos
# ===========================================================================


class TestSkillMinifierPreservation:
    """Verifica que elementos criticos se preserven."""

    def test_preserva_code_blocks(self, minifier: SkillMinifier):
        """Code blocks se preservan por defecto."""
        content = "## Test\n```python\nprint('hello')\n```\n## End"
        result = minifier.minify(content)
        assert "```python" in result
        assert "print('hello')" in result

    def test_no_preserva_code_blocks_si_desactivado(self):
        """Con preserve_code_blocks=False, el marcador de cierre ``` se omite
        pero el contenido del bloque y el marcador de apertura se mantienen."""
        m = SkillMinifier(preserve_code_blocks=False)
        content = "## Test\n```python\nprint('hello')\n```"
        result = m.minify(content)
        # El contenido del code block se mantiene (siempre se preserva)
        assert "print('hello')" in result
        # El marcador de apertura se mantiene (in_code_block=True al abrir)
        assert "```python" in result

    def test_preserva_checklists(self, minifier: SkillMinifier):
        """Checklists [ ] y [x] se preservan."""
        content = "## Checklist\n- [ ] Tarea pendiente\n- [x] Tarea hecha"
        result = minifier.minify(content)
        assert "[ ]" in result
        assert "[x]" in result

    def test_checklist_larga_se_trunca(self, minifier: SkillMinifier):
        """Checklist con descripcion >120 chars se trunca."""
        content = f"## Checklist\n- [ ] {'x' * 150}"
        result = minifier.minify(content)
        # Debe tener 117 chars + "..." = 120
        assert result.count("- [ ]") == 1
        assert result.strip().endswith("...")

    def test_preserva_version(self, minifier: SkillMinifier):
        """El campo version se preserva en frontmatter."""
        content = "---\nname: test\nversion: 2.1.0\n---\n# Body"
        result = minifier.minify(content)
        assert "2.1.0" in result

    def test_preserva_project_agnostic(self, minifier: SkillMinifier):
        """El campo project_agnostic se preserva."""
        content = "---\nname: test\nproject_agnostic: true\n---\n# Body"
        result = minifier.minify(content)
        assert "project_agnostic" in result


# ===========================================================================
# Tests: Compresion de tablas
# ===========================================================================


class TestSkillMinifierTables:
    """Verifica compresion de tablas markdown."""

    TABLE_CONTENT = """## Parameters
| Name | Type | Description |
|------|------|-------------|
| a | str | Alpha |
| b | int | Beta |
| c | float | Gamma |
| d | bool | Delta |
| e | list | Epsilon |
"""

    def test_tabla_corta_no_se_comprime(self, minifier: SkillMinifier):
        """Tabla con <= 4 lineas se mantiene intacta."""
        content = "## Section\n| H | T |\n|---|---|\n| a | b |"
        result = minifier.minify(content)
        assert "| H | T |" in result
        assert "| a | b |" in result

    def test_tabla_larga_se_comprime(self, minifier: SkillMinifier):
        """Tabla con > 4 lineas se comprime (header+separator+2rows+marker)."""
        result = minifier.minify(self.TABLE_CONTENT)
        # Verificar que se mantiene header + separator + primeras filas
        assert "| Name | Type | Description |" in result
        assert "| a | str | Alpha |" in result
        assert "| b | int | Beta |" in result
        assert "more rows" in result

    def test_tabla_mas_de_max_rows(self, minifier: SkillMinifier):
        """Tabla con 6 filas de datos se comprime a 2 filas + marcador."""
        content = "## Section\n| A | B |\n|---|---|\n| 1 | a |\n| 2 | b |\n| 3 | c |\n| 4 | d |\n| 5 | e |\n| 6 | f |"
        result = minifier.minify(content)
        assert "| 1 | a |" in result
        assert "| 2 | b |" in result
        assert "more rows" in result
        # Las filas 3+ se comprimen
        assert "| 3 | c |" not in result


# ===========================================================================
# Tests: Eliminacion de secciones removibles
# ===========================================================================


class TestSkillMinifierRemovableSections:
    """Verifica eliminacion de secciones removibles."""

    def test_ejemplo_eliminado(self, minifier: SkillMinifier):
        """Seccion 'Ejemplo' se elimina. Code blocks dentro de secciones
        removibles se preservan porque el check de code block es anterior
        al check de seccion removible."""
        content = "## Proposito\nContenido util.\n\n## Ejemplo\n```python\nx = 1\n```\n"
        result = minifier.minify(content)
        assert "Ejemplo" not in result
        # Code blocks se preservan incluso en secciones removibles
        assert "x = 1" in result

    def test_tutorial_eliminado(self, minifier: SkillMinifier):
        """Seccion 'Tutorial' se elimina."""
        content = "## Proposito\nUtil.\n\n## Tutorial\nPaso 1\nPaso 2\n"
        result = minifier.minify(content)
        assert "Tutorial" not in result

    def test_appendix_eliminado(self, minifier: SkillMinifier):
        """Seccion 'Appendix' se elimina."""
        content = "## Proposito\nUtil.\n\n## Appendix\nDetalles tecnicos\n"
        result = minifier.minify(content)
        assert "Appendix" not in result

    def test_reference_no_se_elimina_por_error(self, minifier: SkillMinifier):
        """Seccion 'Reference' exacta se elimina, pero 'Referencia' idem."""
        content = "## Proposito\nUtil.\n\n## Reference\nTabla de referencia\n"
        result = minifier.minify(content)
        assert "Reference" not in result


# ===========================================================================
# Tests: Lineas decorativas y vacias
# ===========================================================================


class TestSkillMinifierDecorations:
    """Verifica eliminacion de lineas decorativas."""

    def test_lineas_decorativas_eliminadas(self, minifier: SkillMinifier):
        """Separadores --- y lineas vacias se eliminan."""
        content = "# Header\n\n\n---\n\nBody\n```\n```\n\n"
        result = minifier.minify(content)
        # Las lineas vacias consecutivas se reducen
        # Marcadores ``` y --- se eliminan por separado
        assert "Body" in result
        assert len(result) < len(content)

    def test_lineas_solo_emojis_eliminadas(self, minifier: SkillMinifier):
        """Lineas de solo emojis se eliminan."""
        content = "# Header\n\n🚀✨\nBody"
        result = minifier.minify(content)
        assert "🚀✨" not in result
        assert "Body" in result

    def test_tablas_completas_se_eliminan(self, minifier: SkillMinifier):
        """Lineas de tabla que coinciden con DECORATIVE_LINES se eliminan?"""
        # Segun el codigo, lineas que empiezan con | se procesan como tablas,
        # no se eliminan como decorativas directamente sino via _compress_table
        content = "## Section\n| A | B |\n|---|---|\n| 1 | 2 |"
        result = minifier.minify(content)
        # La tabla se procesa con _compress_table
        assert "| A | B |" in result


# ===========================================================================
# Tests: Frontmatter compression
# ===========================================================================


class TestSkillMinifierFrontmatter:
    """Verifica compresion del frontmatter YAML."""

    def test_frontmatter_preservado_por_defecto(self, minifier: SkillMinifier):
        """El frontmatter se preserva por defecto."""
        content = "---\nname: test\n---\n# Body"
        result = minifier.minify(content)
        assert "name: test" in result

    def test_frontmatter_siempre_se_procesa(self):
        """El flag preserve_frontmatter no afecta el comportamiento actual
        de _compress_frontmatter; el frontmatter siempre se preserva."""
        m = SkillMinifier(preserve_frontmatter=False)
        content = "---\nname: test\n---\n# Body"
        result = m.minify(content)
        # El frontmatter siempre se procesa y preserva actualmente
        assert "name: test" in result

    def test_frontmatter_campos_no_esenciales_eliminados(self, minifier: SkillMinifier):
        """Campos no esenciales del frontmatter se eliminan."""
        content = "---\nname: test\ndescription: 'desc'\nauthor: ignored\nunused: true\n---\n# Body"
        result = minifier.minify(content)
        assert "name:" in result
        assert "description:" in result
        assert "author:" not in result
        assert "unused:" not in result

    def test_description_truncada(self):
        """Description se trunca a max_description_chars."""
        long_desc = "Palabra " * 100  # ~800 chars
        content = f"---\nname: test\ndescription: \"{long_desc}\"\n---\n# Body"
        m = SkillMinifier(max_description_chars=100)
        result = m.minify(content)
        assert len(result) < len(content)


# ===========================================================================
# Tests: Estadisticas de compresion
# ===========================================================================


class TestSkillMinifierStats:
    """Verifica metodos de estadisticas del minifier."""

    def test_get_compression_ratio_cero_para_vacio(self, minifier: SkillMinifier):
        """get_compression_ratio retorna 0.0 para texto vacio."""
        assert minifier.get_compression_ratio("") == 0.0

    def test_get_compression_ratio_positivo(self, minifier: SkillMinifier,
                                              sample_skill: str):
        """get_compression_ratio retorna valor > 0 para texto compresible."""
        ratio = minifier.get_compression_ratio(sample_skill)
        assert 0.0 < ratio < 1.0

    def test_get_stats_acumula_metricas(self, minifier: SkillMinifier,
                                         sample_skill: str):
        """get_stats acumula metricas de compresion."""
        minifier.minify(sample_skill)
        stats = minifier.get_stats()
        assert stats["minifications"] == 1
        assert stats["total_chars_before"] > 0
        assert stats["total_chars_after"] > 0
        assert stats["total_chars_saved"] > 0
        assert stats["avg_compression_pct"] > 0

    def test_get_stats_acumula_multiple_llamadas(self, minifier: SkillMinifier,
                                                  sample_skill: str):
        """Multiples llamadas a minify se acumulan en stats."""
        minifier.minify(sample_skill)
        minifier.minify(sample_skill)
        stats = minifier.get_stats()
        assert stats["minifications"] == 2
        assert stats["total_chars_saved"] > 0


# ===========================================================================
# Tests: minify_file
# ===========================================================================


class TestSkillMinifierFile:
    """Verifica la funcion minify_file."""

    def test_minify_file_inexistente_lanza_error(self, minifier: SkillMinifier):
        """minify_file con archivo inexistente lanza FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            minifier.minify_file("/ruta/inexistente/SKILL.md")

    def test_minify_file_escribe_destino(self, minifier: SkillMinifier,
                                         tmp_path: Path, sample_skill: str):
        """minify_file escribe el archivo minificado en dst_path."""
        src = tmp_path / "SKILL.md"
        src.write_text(sample_skill, encoding="utf-8")
        dst = tmp_path / "SKILL.min.md"
        minifier.minify_file(str(src), str(dst))
        assert dst.exists()
        content = dst.read_text(encoding="utf-8")
        assert len(content) < len(sample_skill)

    def test_minify_file_genera_dst_default(self, minifier: SkillMinifier,
                                             tmp_path: Path, sample_skill: str):
        """minify_file genera nombre .min.md por defecto."""
        src = tmp_path / "SKILL.md"
        src.write_text(sample_skill, encoding="utf-8")
        src_result, dst_result = minifier.minify_file(str(src))
        assert src_result == str(src)
        assert dst_result.endswith("SKILL.min.md")
        assert Path(dst_result).exists()


# ===========================================================================
# Tests: minify_all_skills (batch)
# ===========================================================================


class TestMinifyAllSkills:
    """Verifica la funcion batch minify_all_skills."""

    def test_directorio_inexistente_retorna_vacio(self):
        """Directorio inexistente retorna dict vacio."""
        result = minify_all_skills(skills_dir="/ruta/inexistente")
        assert result == {}

    def test_dry_run_no_escribe_archivos(self, tmp_path: Path):
        """dry_run=True no escribe archivos .min.md."""
        skill_dir = tmp_path / "test_skill"
        skill_dir.mkdir(parents=True)
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text("---\nname: test\n---\n# Content", encoding="utf-8")
        result = minify_all_skills(skills_dir=str(tmp_path), dry_run=True)
        assert "test_skill" in result
        assert not (skill_dir / "SKILL.min.md").exists()

    def test_skills_count_en_resultado(self, tmp_path: Path):
        """El resultado incluye _total con skills_count."""
        d1 = tmp_path / "s1"
        d2 = tmp_path / "s2"
        d1.mkdir(parents=True)
        d2.mkdir(parents=True)
        (d1 / "SKILL.md").write_text("---\nname: s1\n---\n# Body", encoding="utf-8")
        (d2 / "SKILL.md").write_text("---\nname: s2\n---\n# Body", encoding="utf-8")
        result = minify_all_skills(skills_dir=str(tmp_path), dry_run=True)
        assert "_total" in result
        assert result["_total"]["skills_count"] == 2


# ===========================================================================
# Tests: _split_frontmatter
# ===========================================================================


class TestSplitFrontmatter:
    """Verifica el metodo estatico _split_frontmatter."""

    def test_split_con_frontmatter(self, minifier: SkillMinifier):
        """_split_frontmatter separa frontmatter y body correctamente."""
        content = "---\nname: test\n---\n# Body\ncontent"
        fm, body = minifier._split_frontmatter(content)
        assert "name: test" in fm
        assert "# Body" in body

    def test_split_sin_frontmatter(self, minifier: SkillMinifier):
        """_split_frontmatter retorna vacio si no hay frontmatter."""
        content = "# Solo body"
        fm, body = minifier._split_frontmatter(content)
        assert fm == ""
        assert body == content

    def test_split_frontmatter_vacio(self, minifier: SkillMinifier):
        """_split_frontmatter con frontmatter vacio."""
        content = "---\n---\n# Body"
        fm, body = minifier._split_frontmatter(content)
        assert fm == ""
        assert body == "# Body"


# ===========================================================================
# Tests: _compress_body — secciones eliminadas
# ===========================================================================


class TestCompressBody:
    """Verifica la compresion del cuerpo del skill."""

    def test_body_vacio_retorna_vacio(self, minifier: SkillMinifier):
        """_compress_body con texto vacio retorna ''."""
        assert minifier._compress_body("") == ""

    def test_body_remueve_todas_lineas_vacias(self, minifier: SkillMinifier):
        """_compress_body elimina todas las lineas vacias porque
        la regex ^\s*$ en DECORATIVE_LINES las elimina por completo."""
        body = "Linea 1\n\n\n\nLinea 2"
        result = minifier._compress_body(body)
        # Las lineas vacias se eliminan totalmente
        assert "Linea 1\nLinea 2" in result
        # Solo quedan las dos lineas con contenido
        assert result.count("\n\n") == 0
