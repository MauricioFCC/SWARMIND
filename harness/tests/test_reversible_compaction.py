"""
Tests para reversible_compaction — CCR (Compress-Cache-Retrieve).

Extiende ``structured_compact`` (ADR-0033 / Headroom): el original se cachea
en disco y se recupera por hash con busqueda BM25-like opcional.

Cubre:
  - compact() retorna (compacto, hash, cacheado) con hash estable
  - Marcador de recuperacion presente en el texto compacto
  - Texto corto (< min_chars) no se cachea
  - retrieve() byte-exacto y con query (subconjunto de lineas)
  - Hash inexistente -> None
  - stats() refleja hits/misses/total_cached
  - Idempotencia: 2 compact -> mismo hash; retrieve no modifica el cache
  - bm25_like_search: ranking y fallback a primeras 5 lineas
"""

from __future__ import annotations

import json

from harness.memory_rag.reversible_compaction import (
    ReversibleCompactor,
    bm25_like_search,
)

SAMPLE_TEXT = "\n".join([
    "# Informe de compilacion",
    "El proyecto axion-core compila correctamente en modo release.",
    "Se detectaron 3 warnings de dependencias obsoletas.",
    "Output: " + "x" * 240,
    "Output: " + "y" * 240,
    "Output: " + "z" * 240,
    "Output: " + "w" * 240,
    "Linea final del informe con detalles de cobertura.",
])


# ===========================================================================
# Tests: compact()
# ===========================================================================


class TestCompact:
    """Verifica el contrato de compact(): (compacto, hash, cacheado)."""

    def test_retorna_tupla_compacto_hash_cacheado(self, tmp_path):
        """compact retorna (texto_compacto, hash_12_chars, original_byte_exacto)."""
        comp = ReversibleCompactor(cache_dir=tmp_path)
        compacto, h, cacheado = comp.compact(SAMPLE_TEXT)
        assert isinstance(compacto, str)
        assert isinstance(h, str) and len(h) == 12
        assert cacheado == SAMPLE_TEXT

    def test_hash_estable_mismo_texto_mismo_hash(self, tmp_path):
        """Dos compact() con el mismo texto producen el mismo hash (idempotencia)."""
        comp = ReversibleCompactor(cache_dir=tmp_path)
        _, h1, _ = comp.compact(SAMPLE_TEXT)
        _, h2, _ = comp.compact(SAMPLE_TEXT)
        assert h1 == h2

    def test_marcador_presente_en_texto_compacto(self, tmp_path):
        """El texto compacto contiene el marcador swarmind_retrieve con el hash."""
        comp = ReversibleCompactor(cache_dir=tmp_path)
        compacto, h, _ = comp.compact(SAMPLE_TEXT)
        assert "[Comprimido. Recupera con: swarmind_retrieve(" in compacto
        assert h in compacto

    def test_texto_corto_no_se_cachea(self, tmp_path):
        """Texto con longitud < min_chars se retorna tal cual sin cachear."""
        comp = ReversibleCompactor(cache_dir=tmp_path)
        texto = "hola"
        compacto, h, cacheado = comp.compact(texto, min_chars=50)
        assert compacto == texto
        assert cacheado == texto
        assert len(h) == 12
        assert comp.stats()["total_cached"] == 0

    def test_texto_vacio_no_se_cachea(self, tmp_path):
        """Texto vacio se retorna sin cachear y sin marcador."""
        comp = ReversibleCompactor(cache_dir=tmp_path)
        compacto, _, cacheado = comp.compact("")
        assert compacto == ""
        assert cacheado == ""
        assert comp.stats()["total_cached"] == 0

    def test_archivo_cache_creado_con_json(self, tmp_path):
        """Se crea {hash}.json con hash, original y created_at."""
        comp = ReversibleCompactor(cache_dir=tmp_path)
        _, h, _ = comp.compact(SAMPLE_TEXT)
        archivo = tmp_path / f"{h}.json"
        assert archivo.exists()
        datos = json.loads(archivo.read_text(encoding="utf-8"))
        assert datos["hash"] == h
        assert datos["original"] == SAMPLE_TEXT
        assert "created_at" in datos

    def test_compact_reduce_longitud_con_tool_outputs(self, tmp_path):
        """Con tool outputs comprimibles, el compacto es mas corto que el original."""
        comp = ReversibleCompactor(cache_dir=tmp_path)
        compacto, _, _ = comp.compact(SAMPLE_TEXT)
        assert len(compacto) < len(SAMPLE_TEXT)


# ===========================================================================
# Tests: retrieve() y retrieve_full()
# ===========================================================================


class TestRetrieve:
    """Verifica la recuperacion por hash, con y sin query."""

    def test_retrieve_devuelve_original_byte_exacto(self, tmp_path):
        """retrieve(hash) sin query devuelve el original identico."""
        comp = ReversibleCompactor(cache_dir=tmp_path)
        _, h, _ = comp.compact(SAMPLE_TEXT)
        assert comp.retrieve(h) == SAMPLE_TEXT

    def test_retrieve_con_query_devuelve_subconjunto_relevante(self, tmp_path):
        """retrieve con query devuelve lineas del original (subconjunto)."""
        comp = ReversibleCompactor(cache_dir=tmp_path)
        _, h, _ = comp.compact(SAMPLE_TEXT)
        resultado = comp.retrieve(h, query="axion-core release")
        lineas_originales = set(SAMPLE_TEXT.splitlines())
        for linea in resultado.splitlines():
            assert linea in lineas_originales
        assert "El proyecto axion-core compila correctamente en modo release." in resultado

    def test_retrieve_hash_inexistente_retorna_none(self, tmp_path):
        """Un hash nunca cacheado retorna None (miss con log)."""
        comp = ReversibleCompactor(cache_dir=tmp_path)
        assert comp.retrieve("000000000000") is None

    def test_retrieve_full_devuelve_original(self, tmp_path):
        """retrieve_full(hash) devuelve el original completo."""
        comp = ReversibleCompactor(cache_dir=tmp_path)
        _, h, _ = comp.compact(SAMPLE_TEXT)
        assert comp.retrieve_full(h) == SAMPLE_TEXT
        assert comp.retrieve_full("000000000000") is None

    def test_retrieve_no_modifica_el_cache(self, tmp_path):
        """retrieve/retrieve_full son de solo lectura sobre el cache."""
        comp = ReversibleCompactor(cache_dir=tmp_path)
        _, h, _ = comp.compact(SAMPLE_TEXT)
        archivo = tmp_path / f"{h}.json"
        antes = archivo.read_bytes()
        comp.retrieve(h)
        comp.retrieve(h, query="compila")
        comp.retrieve_full(h)
        assert archivo.read_bytes() == antes
        assert comp.stats()["total_cached"] == 1


# ===========================================================================
# Tests: stats()
# ===========================================================================


class TestStats:
    """Verifica las metricas expuestas por stats()."""

    def test_stats_refleja_hits_y_misses(self, tmp_path):
        """Tras un hit y un miss, stats los refleja correctamente."""
        comp = ReversibleCompactor(cache_dir=tmp_path)
        _, h, _ = comp.compact(SAMPLE_TEXT)
        comp.retrieve(h)
        comp.retrieve("nope")
        st = comp.stats()
        assert st["hits"] == 1
        assert st["misses"] == 1
        assert st["total_retrievals"] == 2
        assert st["total_cached"] == 1
        assert st["cache_size_bytes"] > 0

    def test_stats_cache_dir_por_defecto(self):
        """Sin cache_dir usa un tempdir y arranca vacio."""
        comp = ReversibleCompactor()
        st = comp.stats()
        assert st["total_cached"] == 0
        assert st["hits"] == 0
        assert st["misses"] == 0


# ===========================================================================
# Tests: bm25_like_search()
# ===========================================================================


class TestBm25LikeSearch:
    """Verifica el ranking simple BM25-like y su fallback."""

    def test_query_con_ambas_palabras_prioriza_linea(self):
        """La linea con ambos tokens del query aparece primero."""
        original = "Linea sin relevancia para la consulta.\nalpha y beta aparecen juntos aqui.\nalpha aparece sola en esta linea.\nbeta aparece sola en esta otra."
        resultado = bm25_like_search(original, "alpha beta")
        assert resultado[0] == "alpha y beta aparecen juntos aqui."

    def test_sin_coincidencias_retorna_primeras_cinco(self):
        """Sin coincidencias retorna las primeras 5 lineas."""
        original = "\n".join([f"linea {i}" for i in range(10)])
        resultado = bm25_like_search(original, "zzz qqq")
        assert resultado == original.splitlines()[:5]

    def test_top_k_respetado(self):
        """top_k limita el numero de lineas retornadas."""
        original = "alpha uno\nalpha dos\nalpha tres\nalpha cuatro\nalpha cinco\nalpha seis"
        resultado = bm25_like_search(original, "alpha", top_k=3)
        assert len(resultado) == 3

    def test_query_case_insensitive(self):
        """El matching de tokens es insensible a mayusculas."""
        original = "Linea alpha minuscula.\nOtra linea sin match."
        resultado = bm25_like_search(original, "ALPHA")
        assert resultado == ["Linea alpha minuscula."]
