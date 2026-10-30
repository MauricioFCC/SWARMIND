"""Wrapper Python (ctypes) sobre el C-ABI estable de RuscaDB.

Carga la biblioteca dinamica `ruscadb_ffi` compilada con
``cargo build -p ruscadb-ffi`` y expone una API delgada: ``open``,
``read_page``, ``write_page``, ``commit``, ``close``, ``execute`` y
``last_error``. No reimplementa logica: todo el trabajo lo hace el motor Rust
a traves del ABI.

Uso:
    import ruscadb

    handle = ruscadb.open("mi.db", pool_capacity=8)
    ruscadb.write_page(handle, 0, bytes(ruscadb.PAGE_SIZE))
    ruscadb.commit(handle)
    ruscadb.close(handle)

La ruta de la biblioteca se toma de ``RUSCADB_FFI_LIB`` o de
``target/{debug,release}`` (ver :func:`load_library`).
"""

from __future__ import annotations

import ctypes
import json as _json
import os
import sys
from ctypes import POINTER, c_char_p, c_int, c_size_t, c_uint32, c_uint64, c_void_p
from pathlib import Path
from typing import Any

#: Tamano de pagina de RuscaDB (4 KiB), espejo del C-ABI.
PAGE_SIZE = 4096

#: Codigos de retorno del C-ABI.
RC_OK = 0
RC_NULL_POINTER = 1
RC_INVALID_HANDLE = 2
RC_DOMAIN_ERROR = 3
RC_PANIC = 4
RC_BUFFER_TOO_SMALL = 5

_U8P = POINTER(ctypes.c_uint8)
_HANDLE_P = POINTER(c_void_p)

# Biblioteca cargada de forma perezosa (una sola vez por proceso).
_LIB: ctypes.CDLL | None = None

#: Funciones extendidas que ``capabilities()`` reporta (contrato estable).
_CAPABILITY_NAMES: tuple[str, ...] = (
    "ruscadb_open_opts",
    "ruscadb_create_index",
    "ruscadb_update_record",
    "ruscadb_delete_record",
    "ruscadb_get_record",
    "ruscadb_put_blob",
    "ruscadb_get_blob",
    "ruscadb_gc_blobs",
    "ruscadb_last_lsn",
    "ruscadb_integrity_check",
    "ruscadb_backup",
    "ruscadb_explain",
    "ruscadb_execute_at",
    "ruscadb_open_encrypted",
    "ruscadb_alter_table",
    "ruscadb_quantize",
    "ruscadb_search_bq",
)


class RuscadbError(RuntimeError):
    """Error devuelto por el C-ABI de RuscaDB."""

    def __init__(self, code: int, message: str) -> None:
        """Inicializa el error con el codigo y el mensaje del ABI.

        Args:
            code: Codigo de retorno devuelto por el ABI.
            message: Mensaje legible obtenido con ``ruscadb_last_error``.
        """
        super().__init__(f"ruscadb: codigo {code}: {message}")
        self.code = code
        self.message = message


def _library_names() -> list[str]:
    """Nombres candidatos del artefacto dinamico segun la plataforma."""
    if sys.platform.startswith("win"):
        return ["ruscadb_ffi.dll", "ruscadb.dll"]
    if sys.platform == "darwin":
        return ["libruscadb_ffi.dylib", "libruscadb.dylib"]
    return ["libruscadb_ffi.so", "libruscadb.so"]


def _library_candidates(path: str | os.PathLike[str] | None) -> list[Path]:
    """Construye las rutas probables de la biblioteca en orden de prioridad.

    Args:
        path: Ruta explicita indicada por el llamador, o None.

    Returns:
        Lista de rutas candidatas a probar.
    """
    candidates: list[Path] = []
    if path is not None:
        candidates.append(Path(path))
    explicit = os.environ.get("RUSCADB_FFI_LIB")
    if explicit:
        candidates.append(Path(explicit))
    # buscar en el directorio del propio modulo (dll embebida)
    _self_dir = Path(__file__).resolve().parent
    for _name in _library_names():
        candidates.append(_self_dir / _name)
    for profile in ("debug", "release"):
        for name in _library_names():
            candidates.append(Path("target") / profile / name)
    # rutas del proyecto RuscaDB via env (portable, ADR-0035)
    rusca_root = os.environ.get("RUSCADB_ROOT")
    if rusca_root:
        for profile in ("debug", "release"):
            for name in _library_names():
                candidates.append(Path(rusca_root) / "target" / profile / name)
    return candidates


def _locate_library(path: str | os.PathLike[str] | None) -> Path:
    """Encuentra la primera biblioteca existente.

    Args:
        path: Ruta explicita indicada por el llamador, o None.

    Returns:
        La ruta de la biblioteca encontrada.

    Raises:
        FileNotFoundError: si ninguna candidata existe.
    """
    candidates = _library_candidates(path)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    searched = ", ".join(str(candidate) for candidate in candidates)
    raise FileNotFoundError(
        "no se encontro la biblioteca del C-ABI; compila con "
        f"`cargo build -p ruscadb-ffi` o define RUSCADB_FFI_LIB (probadas: {searched})"
    )


def load_library(path: str | os.PathLike[str] | None = None) -> ctypes.CDLL:
    """Carga la biblioteca del C-ABI y enlaza sus firmas.

    Args:
        path: Ruta explicita de la biblioteca; si es None se busca en
            ``RUSCADB_FFI_LIB`` y en ``target/{debug,release}``.

    Returns:
        La biblioteca cargada con ``argtypes``/``restype`` configurados.

    Raises:
        FileNotFoundError: si no se encuentra la biblioteca.
    """
    library = ctypes.CDLL(str(_locate_library(path)))

    library.ruscadb_open.argtypes = [c_char_p, c_uint32, _HANDLE_P]
    library.ruscadb_open.restype = c_int
    library.ruscadb_read_page.argtypes = [c_void_p, c_uint64, _U8P, c_size_t]
    library.ruscadb_read_page.restype = c_int
    library.ruscadb_write_page.argtypes = [c_void_p, c_uint64, _U8P, c_size_t]
    library.ruscadb_write_page.restype = c_int
    library.ruscadb_commit.argtypes = [c_void_p]
    library.ruscadb_commit.restype = c_int
    library.ruscadb_close.argtypes = [c_void_p]
    library.ruscadb_close.restype = c_int
    library.ruscadb_execute_len.argtypes = [c_void_p, c_char_p]
    library.ruscadb_execute_len.restype = c_size_t
    library.ruscadb_execute.argtypes = [c_void_p, c_char_p, c_char_p, c_size_t]
    library.ruscadb_execute.restype = c_int
    library.ruscadb_create_table.argtypes = [c_void_p, c_char_p, c_char_p]
    library.ruscadb_create_table.restype = c_int
    library.ruscadb_insert_record.argtypes = [c_void_p, c_char_p, c_char_p]
    library.ruscadb_insert_record.restype = c_int
    library.ruscadb_list_tables.argtypes = [c_void_p, ctypes.c_char_p, c_size_t]
    library.ruscadb_list_tables.restype = c_int
    library.ruscadb_last_inserted_id.argtypes = [ctypes.c_char_p, c_size_t]
    library.ruscadb_last_inserted_id.restype = c_size_t
    library.ruscadb_last_error.argtypes = [c_char_p, c_size_t]
    library.ruscadb_last_error.restype = c_size_t
    _bind_extended(library)
    return library


def _bind_optional(
    library: ctypes.CDLL,
    name: str,
    argtypes: list[Any],
    restype: Any,
) -> bool:
    """Enlaza una funcion del ABI solo si la DLL la exporta.

    Permite que una DLL antigua siga funcionando con las funciones basicas
    mientras el adaptador degrada las capacidades extendidas.

    Args:
        library: Biblioteca ya cargada.
        name: Nombre del simbolo C.
        argtypes: Tipos de los argumentos.
        restype: Tipo de retorno.

    Returns:
        True si el simbolo existe y quedo enlazado.
    """
    symbol = getattr(library, name, None)
    if symbol is None:
        return False
    symbol.argtypes = argtypes
    symbol.restype = restype
    return True


def _bind_extended(library: ctypes.CDLL) -> None:
    """Enlaza las funciones extendidas (opcionales) del C-ABI."""
    _bind_optional(
        library,
        "ruscadb_open_opts",
        [c_char_p, c_uint32, c_char_p, c_int, _HANDLE_P],
        c_int,
    )
    _bind_optional(library, "ruscadb_create_index", [c_void_p, c_char_p, c_char_p], c_int)
    _bind_optional(
        library,
        "ruscadb_update_record",
        [c_void_p, c_char_p, c_char_p, c_char_p],
        c_int,
    )
    _bind_optional(
        library, "ruscadb_delete_record", [c_void_p, c_char_p, c_char_p], c_int
    )
    _bind_optional(library, "ruscadb_last_affected", [], ctypes.c_int64)
    _bind_optional(
        library,
        "ruscadb_get_record",
        [c_void_p, c_char_p, c_char_p, c_char_p, c_size_t],
        c_int,
    )
    _bind_optional(
        library,
        "ruscadb_put_blob",
        [c_void_p, _U8P, c_size_t, c_char_p, c_size_t],
        c_int,
    )
    _bind_optional(library, "ruscadb_blob_len", [c_void_p, c_char_p], c_size_t)
    _bind_optional(
        library, "ruscadb_get_blob", [c_void_p, c_char_p, _U8P, c_size_t], c_int
    )
    _bind_optional(library, "ruscadb_gc_blobs", [c_void_p], c_int)
    _bind_optional(library, "ruscadb_last_lsn", [c_void_p], c_uint64)
    _bind_optional(
        library, "ruscadb_integrity_check", [c_void_p, c_char_p, c_size_t], c_int
    )
    _bind_optional(library, "ruscadb_backup", [c_void_p, c_char_p], c_int)
    _bind_optional(
        library, "ruscadb_explain", [c_void_p, c_char_p, c_char_p, c_size_t], c_int
    )
    _bind_optional(
        library, "ruscadb_execute_at", [c_void_p, c_char_p, c_uint64, c_char_p, c_size_t], c_int
    )
    _bind_optional(
        library, "ruscadb_open_encrypted", [c_char_p, c_uint32, c_char_p, _HANDLE_P], c_int
    )
    _bind_optional(
        library, "ruscadb_alter_table", [c_void_p, c_char_p, c_char_p, c_int], c_int
    )
    _bind_optional(
        library,
        "ruscadb_quantize",
        [ctypes.POINTER(ctypes.c_float), c_size_t, c_size_t,
         ctypes.POINTER(ctypes.c_ubyte), c_size_t,
         ctypes.POINTER(ctypes.c_float), c_size_t],
        c_int,
    )
    _bind_optional(
        library,
        "ruscadb_search_bq",
        [c_void_p, c_char_p, ctypes.POINTER(ctypes.c_float), c_size_t,
         c_size_t, c_size_t, c_char_p, c_size_t],
        c_int,
    )


def _lib() -> ctypes.CDLL:
    """Devuelve la biblioteca global, cargandola en el primer uso."""
    global _LIB
    if _LIB is None:
        _LIB = load_library()
    return _LIB


def last_error() -> str:
    """Devuelve el ultimo mensaje de error del hilo actual.

    Returns:
        El mensaje en UTF-8 (vacio si no hay error registrado).
    """
    library = _lib()
    length = int(library.ruscadb_last_error(None, 0))
    if length <= 0:
        return ""
    buffer = ctypes.create_string_buffer(length + 1)
    library.ruscadb_last_error(buffer, c_size_t(len(buffer)))
    return buffer.value.decode("utf-8", errors="replace")


def _check(code: int) -> None:
    """Convierte un codigo del ABI en excepcion si no es ``RC_OK``.

    Args:
        code: Codigo de retorno del ABI.

    Raises:
        RuscadbError: si ``code`` es distinto de ``RC_OK``.
    """
    if code != RC_OK:
        raise RuscadbError(code, last_error())


def open(
    data_path: str | os.PathLike[str], pool_capacity: int = 8
) -> c_void_p:
    """Abre (o crea) una base RuscaDB.

    Reintenta unas pocas veces ante ``base en uso`` (lock transitorio por
    handles no liberados por el GC) ejecutando ``gc.collect()`` entre intentos.

    Args:
        data_path: Ruta del archivo de paginas.
        pool_capacity: Numero de marcos del buffer pool (>= 1).

    Returns:
        El handle opaco devuelto por el ABI.

    Raises:
        RuscadbError: si el ABI devuelve un error.
    """
    import gc
    import time

    last_exc: RuscadbError | None = None
    for attempt in range(5):
        try:
            return _open_once(data_path, pool_capacity)
        except RuscadbError as exc:
            last_exc = exc
            if "base en uso" not in str(exc) and "bloqueada" not in str(exc):
                raise
            gc.collect()
            time.sleep(0.05 * (attempt + 1))
    if last_exc is not None:
        raise last_exc
    raise RuscadbError(RC_DOMAIN_ERROR, "open fallo sin detalle")


def read_page(handle: c_void_p, page_id: int) -> bytes:
    """Lee una pagina completa (``PAGE_SIZE`` bytes).

    Args:
        handle: Handle devuelto por :func:`open`.
        page_id: Identificador de la pagina.

    Returns:
        El contenido de la pagina como ``bytes``.

    Raises:
        RuscadbError: si el ABI devuelve un error.
    """
    buffer = (ctypes.c_uint8 * PAGE_SIZE)()
    _check(
        _lib().ruscadb_read_page(
            handle, c_uint64(page_id), ctypes.cast(buffer, _U8P), c_size_t(PAGE_SIZE)
        )
    )
    return bytes(buffer)


def write_page(handle: c_void_p, page_id: int, data: bytes) -> None:
    """Escribe una pagina completa (``PAGE_SIZE`` bytes).

    Args:
        handle: Handle devuelto por :func:`open`.
        page_id: Identificador de la pagina.
        data: Contenido de exactamente ``PAGE_SIZE`` bytes.

    Raises:
        ValueError: si ``data`` no mide ``PAGE_SIZE`` bytes.
        RuscadbError: si el ABI devuelve un error.
    """
    payload = bytes(data)
    if len(payload) != PAGE_SIZE:
        raise ValueError(f"data debe medir PAGE_SIZE={PAGE_SIZE} bytes, no {len(payload)}")
    buffer = (ctypes.c_uint8 * PAGE_SIZE).from_buffer_copy(payload)
    _check(
        _lib().ruscadb_write_page(
            handle, c_uint64(page_id), ctypes.cast(buffer, _U8P), c_size_t(PAGE_SIZE)
        )
    )


def commit(handle: c_void_p) -> None:
    """Confirma los cambios pendientes (WAL-first + fsync).

    Args:
        handle: Handle devuelto por :func:`open`.

    Raises:
        RuscadbError: si el ABI devuelve un error.
    """
    _check(_lib().ruscadb_commit(handle))


def close(handle: c_void_p) -> None:
    """Cierra el handle y libera el motor.

    Args:
        handle: Handle devuelto por :func:`open`.

    Raises:
        RuscadbError: si el ABI devuelve un error.
    """
    _check(_lib().ruscadb_close(handle))


def execute(handle: c_void_p, sql: str) -> str:
    """Ejecuta una consulta RQL y devuelve el JSON de las filas.

    Esquema JSON: array de filas; cada fila es un objeto ``columna -> valor``
    y cada valor usa la forma externa de ``ScalarValue`` (por ejemplo
    ``{"Int": 1}`` o ``{"Text": "x"}``).

    Args:
        handle: Handle devuelto por :func:`open`.
        sql: Consulta RQL en texto UTF-8.

    Returns:
        El JSON serializado de las filas.

    Raises:
        RuscadbError: si la consulta o el handle fallan.
    """
    library = _lib()
    encoded = sql.encode("utf-8")
    length = int(library.ruscadb_execute_len(handle, encoded))
    if length <= 0:
        raise RuscadbError(RC_DOMAIN_ERROR, last_error())
    buffer = ctypes.create_string_buffer(length + 1)
    _check(library.ruscadb_execute(handle, encoded, buffer, c_size_t(len(buffer))))
    return buffer.value.decode("utf-8", errors="replace")


def create_table(handle, name, columns):
    import json as _json
    payload = _json.dumps(columns, ensure_ascii=False).encode('utf-8')
    name_b = name.encode('utf-8')
    _check(_lib().ruscadb_create_table(handle, name_b, ctypes.c_char_p(payload + b'\x00')))


def insert_record(handle, table, record):
    import json as _json
    payload = _json.dumps(record, ensure_ascii=False).encode('utf-8')
    table_b = table.encode('utf-8')
    _check(_lib().ruscadb_insert_record(handle, table_b, ctypes.c_char_p(payload + b'\x00')))

def list_tables(handle):
    import json as _json
    buf_size = 65536
    buf = ctypes.create_string_buffer(buf_size)
    rc = _lib().ruscadb_list_tables(handle, buf, c_size_t(buf_size))
    _check(rc)
    text = buf.value.decode('utf-8', errors='replace')
    try:
        return _json.loads(text)
    except _json.JSONDecodeError:
        return [t for t in text.split(',') if t]


def last_inserted_id() -> str:
    """Devuelve el ULID del ultimo registro insertado en este hilo."""
    buf_size = 64
    buf = ctypes.create_string_buffer(buf_size)
    length = int(_lib().ruscadb_last_inserted_id(buf, c_size_t(buf_size)))
    if length <= 0:
        return ''
    return buf.value.decode('utf-8', errors='replace')


def alter_table_add_column(
    handle, table: str, column: str, type_code: int = 2
) -> None:
    """Agrega una columna a una tabla existente (ALTER TABLE ADD COLUMN).

    Args:
        handle: Handle abierto.
        table: Tabla a evolucionar.
        column: Columna nueva.
        type_code: 0=INT, 1=FLOAT, 2=TEXT, 3=BOOL.

    Raises:
        RuscadbError: si la DLL no exporta ``ruscadb_alter_table`` o el motor
            rechaza la evolucion.
    """
    _require("ruscadb_alter_table")
    _check(
        _lib().ruscadb_alter_table(
            handle, table.encode("utf-8"), column.encode("utf-8"), c_int(type_code)
        )
    )


def quantize(vectors, dim: int) -> tuple[bytes, list[float]]:
    """Cuantiza vectores f32 a codigos RaBitQ (1 bit por dimension).

    Args:
        vectors: Matriz ``(n, dim)`` o vector unico.
        dim: Dimension de los vectores.

    Returns:
        ``(codigos, normas)``: ``n * ceil(dim/8)`` bytes y ``n`` normas.

    Raises:
        RuscadbError: si la DLL no exporta ``ruscadb_quantize`` o el motor
            rechaza la entrada.
    """
    import numpy as np

    _require("ruscadb_quantize")
    array = np.asarray(vectors, dtype=np.float32)
    if array.ndim == 1:
        array = array.reshape(1, -1)
    return _run_quantize(array, int(dim))


def _run_quantize(array, dim: int) -> tuple[bytes, list[float]]:
    """Reserva buffers, llama al ABI y devuelve ``(codigos, normas)``."""
    import numpy as np

    count = int(array.shape[0])
    code_len = (dim + 7) // 8
    codes = (ctypes.c_ubyte * max(count * code_len, 1))()
    norms = (ctypes.c_float * max(count, 1))()
    flat = np.ascontiguousarray(array.reshape(-1))
    _check(
        _lib().ruscadb_quantize(
            flat.ctypes.data_as(ctypes.POINTER(ctypes.c_float)),
            c_size_t(count),
            c_size_t(dim),
            codes,
            c_size_t(count * code_len),
            norms,
            c_size_t(count),
        )
    )
    return bytes(codes[: count * code_len]), [float(value) for value in norms[:count]]


def search_bq(
    handle,
    table: str,
    query,
    top_k: int = 10,
    oversample: int = 3,
) -> list[dict[str, object]]:
    """KNN binario RaBitQ con oversampling + rescore exacto float32.

    Args:
        handle: Handle abierto.
        table: Tabla con indice vectorial.
        query: Vector de consulta.
        top_k: Resultados deseados.
        oversample: Candidatos antes del rescore (>= 1).

    Returns:
        Lista de ``{"id": RecordId, "distance": float}`` ordenada por distancia.

    Raises:
        RuscadbError: si la DLL no exporta ``ruscadb_search_bq`` o el motor
            rechaza la consulta.
    """
    import json as _json

    import numpy as np

    _require("ruscadb_search_bq")
    vector = np.ascontiguousarray(np.asarray(query, dtype=np.float32).reshape(-1))
    text = _search_bq_payload(
        handle,
        table,
        vector.ctypes.data_as(ctypes.POINTER(ctypes.c_float)),
        vector.size,
        top_k,
        oversample,
    )
    return _parse_bq_hits(text, _json)


def _parse_bq_hits(text: str, json_module) -> list[dict[str, object]]:
    """Parsea el JSON de hits y descarta elementos no-dict."""
    parsed = json_module.loads(text) if text else []
    return [hit for hit in parsed if isinstance(hit, dict)]


def _search_bq_payload(
    handle,
    table: str,
    pointer,
    dim: int,
    top_k: int,
    oversample: int,
) -> str:
    """Llama a ``ruscadb_search_bq`` reintentando con buffers mayores."""
    for size in (65536, 1 << 20, 1 << 22):
        buffer = ctypes.create_string_buffer(size)
        rc = _lib().ruscadb_search_bq(
            handle,
            table.encode("utf-8"),
            pointer,
            c_size_t(dim),
            c_size_t(int(top_k)),
            c_size_t(max(int(oversample), 1)),
            buffer,
            c_size_t(size),
        )
        if rc == RC_OK:
            return buffer.value.decode("utf-8", errors="replace")
        if rc != RC_BUFFER_TOO_SMALL:
            _check(rc)
    raise RuscadbError(
        RC_BUFFER_TOO_SMALL,
        "ruscadb_search_bq: buffer insuficiente incluso con 4 MiB",
    )


def _require(name: str) -> None:
    """Verifica que la DLL exporte una funcion extendida.

    Args:
        name: Simbolo C requerido.

    Raises:
        RuscadbError: si la DLL cargada no lo exporta (version antigua).
    """
    if getattr(_lib(), name, None) is None:
        raise RuscadbError(
            RC_DOMAIN_ERROR,
            f"la DLL de RuscaDB no exporta {name}; recompila con "
            "`cargo build -p ruscadb-ffi`",
        )


def capabilities() -> dict[str, bool]:
    """Devuelve que funciones extendidas expone la DLL cargada.

    Si la biblioteca no esta disponible en la plataforma (p. ej. Linux sin
    artefacto compilado), devuelve todas las capacidades en ``False`` en lugar
    de lanzar: el import del paquete y los smokes de instalacion deben pasar.

    Returns:
        Mapa ``nombre -> disponible`` para las capacidades extendidas.
    """
    try:
        library = _lib()
    except (OSError, ImportError):
        return {name: False for name in _CAPABILITY_NAMES}
    return {
        name: getattr(library, name, None) is not None
        for name in _CAPABILITY_NAMES
    }


def _open_once(data_path: str | os.PathLike[str], pool_capacity: int) -> c_void_p:
    """Apertura unica sin reintentos (implementacion de :func:`open`).

    Args:
        data_path: Ruta del archivo de paginas.
        pool_capacity: Numero de marcos del buffer pool.

    Returns:
        El handle opaco del ABI.

    Raises:
        RuscadbError: si el ABI devuelve un error.
    """
    handle = c_void_p()
    bytes_path = os.fsencode(os.fspath(data_path))
    _check(
        _lib().ruscadb_open(bytes_path, c_uint32(pool_capacity), ctypes.byref(handle))
    )
    return handle


def open_with_options(
    data_path: str | os.PathLike[str],
    pool_capacity: int = 8,
    blob_path: str | os.PathLike[str] | None = None,
    readonly: bool = False,
) -> c_void_p:
    """Abre una base con blob store opcional y modo solo lectura.

    Args:
        data_path: Ruta del archivo de paginas.
        pool_capacity: Numero de marcos del buffer pool.
        blob_path: Directorio del blob store, o None.
        readonly: Abre en modo solo lectura (lectores concurrentes).

    Returns:
        El handle opaco del ABI.

    Raises:
        RuscadbError: si el ABI devuelve un error.
    """
    library = _lib()
    if getattr(library, "ruscadb_open_opts", None) is None:
        return open(data_path, pool_capacity)
    import gc
    import time

    last_exc: RuscadbError | None = None
    for attempt in range(5):
        try:
            handle = c_void_p()
            bytes_path = os.fsencode(os.fspath(data_path))
            blob_bytes = os.fsencode(os.fspath(blob_path)) if blob_path else None
            _check(
                library.ruscadb_open_opts(
                    bytes_path,
                    c_uint32(pool_capacity),
                    blob_bytes,
                    c_int(1 if readonly else 0),
                    ctypes.byref(handle),
                )
            )
            return handle
        except RuscadbError as exc:
            last_exc = exc
            if "base en uso" not in str(exc) and "bloqueada" not in str(exc):
                raise
            gc.collect()
            time.sleep(0.05 * (attempt + 1))
    if last_exc is not None:
        raise last_exc
    raise RuscadbError(RC_DOMAIN_ERROR, "open_with_options fallo sin detalle")


def create_index(handle: c_void_p, table: str, column: str) -> None:
    """Crea un indice secundario sobre ``table.column``.

    Args:
        handle: Handle devuelto por :func:`open`.
        table: Tabla destino.
        column: Columna a indexar.

    Raises:
        RuscadbError: si la DLL no lo soporta o el motor falla.
    """
    _require("ruscadb_create_index")
    _check(_lib().ruscadb_create_index(handle, table.encode("utf-8"), column.encode("utf-8")))


def last_affected() -> int:
    """Devuelve las filas afectadas por el ultimo update/delete.

    Returns:
        Numero de filas (0 si no hubo cambios).
    """
    library = _lib()
    if getattr(library, "ruscadb_last_affected", None) is None:
        return 0
    return int(library.ruscadb_last_affected())


def update_record(handle: c_void_p, table: str, rid: str, scalars: dict[str, Any]) -> int:
    """Actualiza columnas de una fila por su ``RecordId`` (ULID).

    Args:
        handle: Handle devuelto por :func:`open`.
        table: Tabla destino.
        rid: ULID del registro.
        scalars: Columnas nuevas (parciales).

    Returns:
        1 si actualizo, 0 si la fila no existia.

    Raises:
        RuscadbError: si la DLL no lo soporta o el motor falla.
    """
    _require("ruscadb_update_record")
    payload = _json.dumps(scalars, ensure_ascii=False).encode("utf-8")
    _check(
        _lib().ruscadb_update_record(
            handle, table.encode("utf-8"), rid.encode("utf-8"), payload
        )
    )
    return last_affected()


def delete_record(handle: c_void_p, table: str, rid: str) -> int:
    """Borra logicamente (MVCC) una fila por su ``RecordId``.

    Args:
        handle: Handle devuelto por :func:`open`.
        table: Tabla destino.
        rid: ULID del registro.

    Returns:
        1 si borro, 0 si no existia.

    Raises:
        RuscadbError: si la DLL no lo soporta o el motor falla.
    """
    _require("ruscadb_delete_record")
    _check(
        _lib().ruscadb_delete_record(
            handle, table.encode("utf-8"), rid.encode("utf-8")
        )
    )
    return last_affected()


def get_record(handle: c_void_p, table: str, rid: str) -> dict[str, Any] | None:
    """Devuelve el registro completo (escalares, doc, aristas, vector).

    Args:
        handle: Handle devuelto por :func:`open`.
        table: Tabla destino.
        rid: ULID del registro.

    Returns:
        El registro como dict, o None si no existe.

    Raises:
        RuscadbError: si la DLL no lo soporta o el motor falla.
    """
    _require("ruscadb_get_record")
    size = 65536
    for _ in range(8):
        buffer = ctypes.create_string_buffer(size)
        code = int(
            _lib().ruscadb_get_record(
                handle,
                table.encode("utf-8"),
                rid.encode("utf-8"),
                buffer,
                c_size_t(size),
            )
        )
        if code == RC_BUFFER_TOO_SMALL:
            size *= 4
            continue
        _check(code)
        text = buffer.value.decode("utf-8", errors="replace")
        return _json.loads(text) if text else None
    raise RuscadbError(RC_BUFFER_TOO_SMALL, last_error())


def put_blob(handle: c_void_p, data: bytes) -> str:
    """Almacena un blob content-addressed y devuelve su hash SHA-256.

    Args:
        handle: Handle abierto con ``blob_path``.
        data: Contenido binario.

    Returns:
        El hash hexadecimal del blob.

    Raises:
        RuscadbError: si la DLL no lo soporta o el motor falla.
    """
    _require("ruscadb_put_blob")
    payload = bytes(data)
    buffer = (ctypes.c_uint8 * len(payload)).from_buffer_copy(payload)
    out = ctypes.create_string_buffer(128)
    _check(
        _lib().ruscadb_put_blob(
            handle, ctypes.cast(buffer, _U8P), c_size_t(len(payload)), out, c_size_t(len(out))
        )
    )
    return out.value.decode("utf-8", errors="replace")


def blob_len(handle: c_void_p, blob_hash: str) -> int:
    """Devuelve la longitud en bytes de un blob.

    Args:
        handle: Handle abierto con ``blob_path``.
        blob_hash: Hash devuelto por :func:`put_blob`.

    Returns:
        Longitud en bytes (0 si no existe).
    """
    library = _lib()
    if getattr(library, "ruscadb_blob_len", None) is None:
        return 0
    return int(library.ruscadb_blob_len(handle, blob_hash.encode("utf-8")))


def get_blob(handle: c_void_p, blob_hash: str) -> bytes:
    """Lee el contenido binario de un blob.

    Args:
        handle: Handle abierto con ``blob_path``.
        blob_hash: Hash devuelto por :func:`put_blob`.

    Returns:
        Los bytes del blob (vacio si no existe).

    Raises:
        RuscadbError: si la DLL no lo soporta o la lectura falla.
    """
    _require("ruscadb_get_blob")
    size = blob_len(handle, blob_hash)
    if size <= 0:
        return b""
    buffer = (ctypes.c_uint8 * size)()
    _check(
        _lib().ruscadb_get_blob(
            handle, blob_hash.encode("utf-8"), ctypes.cast(buffer, _U8P), c_size_t(size)
        )
    )
    return bytes(buffer)


def gc_blobs(handle: c_void_p) -> int:
    """Purga blobs sin referencias vivas.

    Args:
        handle: Handle abierto con ``blob_path``.

    Returns:
        Numero de blobs eliminados.
    """
    _require("ruscadb_gc_blobs")
    _check(_lib().ruscadb_gc_blobs(handle))
    return last_affected()


def last_lsn(handle: c_void_p) -> int:
    """Devuelve el LSN del ultimo commit confirmado."""
    library = _lib()
    if getattr(library, "ruscadb_last_lsn", None) is None:
        return 0
    return int(library.ruscadb_last_lsn(handle))


def integrity_check(handle: c_void_p) -> dict[str, Any]:
    """Ejecuta la verificacion de integridad del motor.

    Args:
        handle: Handle abierto.

    Returns:
        Reporte con ``wal_ok``, ``heap_ok``, ``vector_ok`` y ``details``.
    """
    _require("ruscadb_integrity_check")
    buffer = ctypes.create_string_buffer(65536)
    _check(_lib().ruscadb_integrity_check(handle, buffer, c_size_t(len(buffer))))
    return _json.loads(buffer.value.decode("utf-8", errors="replace"))


def backup(handle: c_void_p, destination: str | os.PathLike[str]) -> int:
    """Crea un backup online de la base en ``destination``.

    Args:
        handle: Handle abierto.
        destination: Ruta destino del backup.

    Returns:
        Numero de archivos copiados.
    """
    _require("ruscadb_backup")
    _check(_lib().ruscadb_backup(handle, os.fsencode(os.fspath(destination))))
    return last_affected()


def explain(handle: c_void_p, sql: str) -> list[str]:
    """Devuelve el plan de ejecucion de una consulta RQL.

    Args:
        handle: Handle abierto.
        sql: Consulta RQL.

    Returns:
        Lineas del plan.
    """
    _require("ruscadb_explain")
    # El motor espera la sentencia `EXPLAIN ...` completa.
    query = sql.strip()
    if not query.upper().startswith("EXPLAIN"):
        query = "EXPLAIN " + query
    buffer = ctypes.create_string_buffer(65536)
    _check(
        _lib().ruscadb_explain(
            handle, query.encode("utf-8"), buffer, c_size_t(len(buffer))
        )
    )
    return _json.loads(buffer.value.decode("utf-8", errors="replace"))


def execute_at(handle: c_void_p, sql: str, snapshot_tx_id: int = 0) -> list[Any]:
    """Ejecuta una consulta en un snapshot historico (time travel, SPEC-0129).

    Args:
        handle: Handle abierto.
        sql: Consulta RQL.
        snapshot_tx_id: TxId (LSN) del snapshot; 0 = snapshot actual.

    Returns:
        Filas visibles en ese snapshot.
    """
    _require("ruscadb_execute_at")
    buffer = ctypes.create_string_buffer(65536)
    _check(
        _lib().ruscadb_execute_at(
            handle, sql.encode("utf-8"), c_uint64(snapshot_tx_id), buffer, c_size_t(len(buffer))
        )
    )
    return _json.loads(buffer.value.decode("utf-8", errors="replace"))


def open_encrypted(
    data_path: str | os.PathLike[str],
    passphrase: str,
    pool_capacity: int = 8,
) -> c_void_p:
    """Abre (o crea) una base cifrada con passphrase (Argon2id).

    Args:
        data_path: Ruta del archivo de paginas.
        passphrase: Secreto del usuario.
        pool_capacity: Numero de marcos del buffer pool.

    Returns:
        El handle opaco del ABI.
    """
    _require("ruscadb_open_encrypted")
    handle = c_void_p()
    _check(
        _lib().ruscadb_open_encrypted(
            os.fsencode(os.fspath(data_path)),
            c_uint32(pool_capacity),
            passphrase.encode("utf-8"),
            ctypes.byref(handle),
        )
    )
    return handle

__all__ = [
    "PAGE_SIZE",
    "RC_BUFFER_TOO_SMALL",
    "RC_DOMAIN_ERROR",
    "RC_INVALID_HANDLE",
    "RC_NULL_POINTER",
    "RC_OK",
    "RC_PANIC",
    "RuscadbError",
    "backup",
    "blob_len",
    "capabilities",
    "close",
    "commit",
    "create_index",
    "create_table",
    "delete_record",
    "execute",
    "execute_at",
    "explain",
    "gc_blobs",
    "get_blob",
    "get_record",
    "insert_record",
    "integrity_check",
    "last_affected",
    "last_error",
    "last_inserted_id",
    "last_lsn",
    "list_tables",
    "load_library",
    "open",
    "open_encrypted",
    "open_with_options",
    "put_blob",
    "read_page",
    "update_record",
    "write_page",
]
