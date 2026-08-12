"""SQLiteVecAdapter — Backend vectorial ligero via sqlite-vec.

Este paquete reemplaza al modulo ``sqlite_vec_adapter.py`` (regla AGR:
archivo < 500 lineas). ``SQLiteVecAdapter`` se re-exporta desde aqui, por
lo que los imports existentes
(``from harness.memory_rag.sqlite_vec_adapter import SQLiteVecAdapter``)
siguen funcionando identicos.

Proporciona almacenamiento vectorial portable sin dependencias externas.
Ideal para edge computing, dispositivos sin GPU, y entornos offline.

Basado en: github.com/asg017/sqlite-vec (extension vectorial para SQLite).

Ventajas:
- Zero dependencias externas (solo sqlite3 + numpy).
- Base de datos portable (un solo .db file).
- Sincronizable via Git (archivos pequenos).
- Ideal para CI/CD y tests sin infraestructura.
"""
from __future__ import annotations

from .core import SQLiteVecAdapter

__all__ = [
    "SQLiteVecAdapter",
]
