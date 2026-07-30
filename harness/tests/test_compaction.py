"""
Tests para compaction — structured_compact() y _flush_buffer().

Evalua:
  - Texto vacio / corto (< min_chars)
  - Cabeceras preservadas (#, ##, ###, **, ---)
  - Bloques de codigo grandes comprimidos (>20 lines)
  - Tool outputs largos comprimidos (>200 chars)
  - Budget ratio respetado
  - _flush_buffer con diferentes tamanos de buffer
"""

from __future__ import annotations

from harness.memory_rag.compaction import _flush_buffer, structured_compact

# ===========================================================================
# Tests: structured_compact — edge cases
# ===========================================================================


class TestStructuredCompactEdgeCases:
    """Tests de casos limite para structured_compact."""

    def test_vacio_retorna_vacio(self):
        """structured_compact('') retorna cadena vacia."""
        assert structured_compact("") == ""

    def test_solo_espacios_retorna_original(self):
        """structured_compact con solo espacios y len < min_chars retorna original."""
        text = "   "
        result = structured_compact(text, min_chars=50)
        # len("   ") = 3 < 50, retorna text (no vacio porque text no es falsy)
        assert result == text

    def test_corto_retorna_original(self):
        """Texto con longitud menor a min_chars se retorna sin cambios."""
        text = "Hola mundo, esto es corto."
        result = structured_compact(text, min_chars=100)
        assert result == text

    def test_texto_vacio_con_none_retorna_vacio(self):
        """structured_compact(None) debe retornar '' (None es falsy)."""
        assert structured_compact(None) == ""  # type: ignore[arg-type]


# ===========================================================================
# Tests: structured_compact — preservacion de cabeceras
# ===========================================================================


class TestStructuredCompactHeaders:
    """Verifica que las cabeceras/marcadores se preserven siempre."""

    HEADER_TEXT = """# Titulo principal
## Subtitulo
### Seccion detallada
**Texto en negrita**
---
Linea normal de contenido
"""

    def test_headers_preservados(self):
        """Cabeceras #, ##, ###, **, --- se preservan en el output."""
        result = structured_compact(self.HEADER_TEXT, budget_ratio=0.2)
        assert "# Titulo principal" in result
        assert "## Subtitulo" in result
        assert "### Seccion detallada" in result
        assert "**Texto en negrita**" in result
        assert "---" in result

    def test_cabeceras_con_espacios_previos(self):
        """Cabeceras con indentacion tambien se preservan."""
        text = "  # Titulo indentado\n  ## Subindentado"
        result = structured_compact(text, budget_ratio=0.1, min_chars=10)
        assert "# Titulo indentado" in result
        assert "## Subindentado" in result


# ===========================================================================
# Tests: structured_compact — compresion de bloques de codigo
# ===========================================================================


class TestStructuredCompactCodeBlocks:
    """Verifica compresion de bloques de codigo grandes."""

    def _make_code_block(self, n_lines: int) -> str:
        """Crea un bloque de codigo con n_lines de contenido."""
        lines = ["```python"]
        for i in range(n_lines):
            lines.append(f"print('linea {i}')  # test")
        lines.append("```")
        return "\n".join(lines)

    def test_code_block_pequeno_no_se_comprime(self):
        """Bloque de codigo <= 20 lines se mantiene intacto."""
        code = self._make_code_block(5)
        result = structured_compact(code, budget_ratio=1.0)
        assert "```python" in result
        for i in range(5):
            assert f"print('linea {i}')" in result
        assert "```" in result

    def test_code_block_grande_se_comprime(self):
        """Bloque de codigo > 20 lines se comprime a marcador.
        El buffer incluye la linea de apertura ```, por eso 26 para 25 de contenido.
        Se usa min_chars bajo para evitar que el fallback por longitud devuelva
        el texto original truncado.
        """
        code = self._make_code_block(25)
        result = structured_compact(code, budget_ratio=0.5, min_chars=10)
        assert "``` ... [26 lines compressed] ... ```" in result

    def test_code_block_exacto_20_no_se_comprime(self):
        """Bloque exactamente de 20 lines NO se comprime."""
        code = self._make_code_block(20)
        result = structured_compact(code, budget_ratio=1.0)
        # 20 lines no supera el umbral, se mantiene
        assert "[20 lines compressed]" not in result

    def test_multiplos_code_blocks_grandes(self):
        """Multiples bloques grandes: cada uno se comprime independientemente.
        El buffer incluye la linea de apertura ```, asi que 31 lines por bloque.
        """
        lines = []
        for b in range(3):
            lines.append("```rust")
            for i in range(30):
                lines.append(f"let x = {i};")
            lines.append("```")
        text = "\n".join(lines)
        result = structured_compact(text, budget_ratio=0.3)
        assert result.count("``` ... [31 lines compressed] ... ```") == 3


# ===========================================================================
# Tests: structured_compact — compresion de tool outputs
# ===========================================================================


class TestStructuredCompactToolOutputs:
    """Verifica compresion de tool outputs largos."""

    def test_tool_output_corto_no_se_comprime(self):
        """Tool output < 200 chars no se comprime."""
        text = "Output: resultado breve"
        result = structured_compact(text, budget_ratio=1.0)
        assert "Output: resultado breve" in result

    def test_tool_output_largo_se_comprime(self):
        """Tool outputs > 200 chars se acumulan y comprimen (>3 lines, >500 chars)."""
        text = "\n".join(["Output: " + "x" * 200 for _ in range(4)]) + "\nlinea normal"
        result = structured_compact(text, budget_ratio=0.3, min_chars=10)
        assert "[... " in result
        assert "chars compressed" in result

    def test_tool_output_una_sola_linea_no_se_comprime(self):
        """Una sola linea tool output (aunque larga) no se comprime por flush_buffer."""
        text = "Output: " + "x" * 250
        result = structured_compact(text, budget_ratio=0.3, min_chars=10)
        # flush_buffer solo comprime si >3 lines, 1 sola linea se mantiene
        assert "Output:" in result
        assert "[... " not in result

    def test_multiple_tool_outputs_se_comprimen(self):
        """Multiples tool outputs se comprimen todos."""
        lines = []
        for i in range(4):
            lines.append(f"Result: {i} " + "x" * 200)
        lines.append("linea normal final")
        text = "\n".join(lines)
        result = structured_compact(text, budget_ratio=0.2, min_chars=20)
        assert "[... 4 lines" in result
        assert "chars compressed" in result
        assert "linea normal final" in result

    def test_tool_output_sin_keyword_no_se_comprime(self):
        """Lineas largas SIN keyword Output:/Result:/STDOUT:/STDERR: no se comprimen."""
        text = "A" * 250  # Largo pero sin keyword
        result = structured_compact(text, budget_ratio=0.5)
        # Se mantiene porque no tiene marcador de tool output
        assert "A" * 250 in result

    def test_tool_output_variantes_keyword(self):
        """Todas las variantes de keywords de tool output se bufferizan."""
        for keyword in ("Output:", "Result:", "STDOUT:", "STDERR:"):
            text = "\n".join([f"{keyword} " + "x" * 200 for _ in range(4)])
            result = structured_compact(text, budget_ratio=0.3, min_chars=10)
            assert "[... " in result, f"Fallo para keyword: {keyword}"


# ===========================================================================
# Tests: structured_compact — budget ratio
# ===========================================================================


class TestStructuredCompactBudget:
    """Verifica que el budget_ratio se respete."""

    LONG_TEXT = "\n".join(
        [f"Linea normal {i} - " + "contenido extra para alargar la linea" * 5
         for i in range(20)]
    )

    def test_min_chars_respetado(self):
        """Min chars se respeta incluso si budget_ratio daria menos."""
        text = "Hola" * 30  # 120 chars
        result = structured_compact(text, budget_ratio=0.01, min_chars=100)
        assert len(result) >= 100

    def test_budget_ratio_un_entero(self):
        """Budget ratio = 1.0 mantiene el texto completo (si no hay compresiones)."""
        text = "\n".join([f"linea {i}" for i in range(10)])
        result = structured_compact(text, budget_ratio=1.0, min_chars=10)
        assert len(result) == len(text)

    def test_budget_ratio_cero(self):
        """Budget ratio = 0 fuerza al min_chars."""
        text = "contenido de prueba " * 50  # ~950 chars
        result = structured_compact(text, budget_ratio=0.0, min_chars=50)
        # Debe retornar al menos min_chars
        assert len(result) >= 50

    def test_lineas_normales_se_preservan_sin_patron_compresible(self):
        """Lineas normales (sin headers/tool outputs/code blocks) se preservan
        porque el algoritmo solo comprime patrones especificos."""
        text = "\n".join([f"detalle irrelevante {i}" for i in range(10)])
        result = structured_compact(text, budget_ratio=0.1, min_chars=20)
        # Sin patrones compresibles, el texto se mantiene completo
        assert len(result) == len(text)

    def test_budget_ratio_con_compresion_reduce_longitud(self):
        """La compresion de tool outputs reduce la longitud total."""
        text = "# Header\n" + "\n".join(
            ["Output: " + "x" * 300 for _ in range(5)]
        ) + "\n# Footer"
        original_len = len(text)
        result = structured_compact(text, budget_ratio=0.5, min_chars=20)
        assert len(result) < original_len
        assert "# Header" in result
        assert "# Footer" in result


# ===========================================================================
# Tests: _flush_buffer
# ===========================================================================


class TestFlushBuffer:
    """Tests para la funcion interna _flush_buffer."""

    def test_buffer_vacio_no_anade_nada(self):
        """Buffer vacio no anade nada al target."""
        target: list[str] = ["linea existente"]
        _flush_buffer([], target)
        assert target == ["linea existente"]

    def test_buffer_corto_se_anade_completo(self):
        """Buffer con <= 3 lineas se anade completo."""
        target: list[str] = []
        buf = ["a", "b", "c"]
        _flush_buffer(buf, target)
        assert target == ["a", "b", "c"]

    def test_buffer_3_lineas_pocos_chars_se_anade(self):
        """Buffer de 3 lineas con total <= 500 chars se anade completo."""
        target: list[str] = []
        buf = ["abc", "def", "ghi"]  # 9 chars total
        _flush_buffer(buf, target)
        assert target == ["abc", "def", "ghi"]

    def test_buffer_4_lineas_muchos_chars_se_comprime(self):
        """Buffer > 3 lineas con total > 500 chars se comprime a marcador."""
        target: list[str] = []
        buf = ["x" * 200, "y" * 200, "z" * 200, "w" * 200]  # 800 chars
        _flush_buffer(buf, target)
        assert len(target) == 1
        assert target[0].startswith("[...")
        assert "4 lines" in target[0]
        assert "chars compressed" in target[0]

    def test_buffer_4_lineas_pocos_chars_no_se_comprime(self):
        """Buffer > 3 lineas pero con total <= 500 chars no se comprime."""
        target: list[str] = []
        buf = ["a", "b", "c", "d"]  # 4 chars total
        _flush_buffer(buf, target)
        assert target == ["a", "b", "c", "d"]

    def test_buffer_limpia_despues_de_vaciar(self):
        """El buffer se limpia (clear) despues de procesar."""
        buf = ["a", "b", "c"]
        target: list[str] = []
        _flush_buffer(buf, target)
        assert len(buf) == 0

    def test_buffer_grande_se_comprime_con_conteo_correcto(self):
        """Marcador contiene el numero exacto de lines y chars."""
        target: list[str] = []
        buf = ["x" * 200] * 5  # 5 lines, 1000 chars total
        _flush_buffer(buf, target)
        marker = target[0]
        assert "5 lines" in marker
        assert "1000 chars" in marker
