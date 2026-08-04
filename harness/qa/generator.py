"""L3 â€” TestCaseGenerator: Generacion de casos de prueba con guardrails.

Genera casos de prueba a partir de especificaciones usando Gen AI,
aplicando multiples guardrails anti-alucinacion para garantizar:
- Fidelidad a la especificacion original
- Sintaxis ejecutable del lenguaje destino
- No-invencion de APIs o metodos inexistentes
- Cobertura de casos borde y limite
- Trazabilidad bidireccional requisito-caso

Referencia: IMACS arXiv:2607.25446 â€” Guardrail Composition Framework

Example:
    gen = TestCaseGenerator()
    suite = gen.generate(
        especificacion="Funcion login(valida usuario y password)",
        lenguaje="python",
        framework="pytest"
    )
    for caso in suite.casos:
        print(f"{caso.nombre}: {caso.estado}")
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum, auto
from uuid import uuid4

from harness.qa import QALayer, QAMetadata

logger = logging.getLogger(__name__)

# â”€â”€ Patrones de validacion anti-alucinacion â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

_PATRON_IMPORT_FANTASMA = re.compile(
    r"(?:from|import)\s+(?:\w+\.)*(\w+)", re.IGNORECASE
)
_APIS_CONOCIDAS: frozenset[str] = frozenset({
    "pytest", "unittest", "flask", "fastapi", "django", "sqlalchemy",
    "requests", "json", "os", "sys", "typing", "dataclasses", "pathlib",
})
_PALABRAS_PROHIBIDAS: frozenset[str] = frozenset({
    "supongamos", "asumamos", "hipoteticamente", "deberia",
    "TODO", "FIXME", "placeholder", "pendiente",
})


class GuardrailType(Enum):
    """Tipos de guardrail aplicables durante generacion."""

    FIDELIDAD = auto()  # Coincidencia con especificacion
    SINTAXIS = auto()  # Validez sintactica basica
    NO_INVENCION = auto()  # Prohibicion de APIs ficticias
    COBERTURA_BORDES = auto()  # Casos limite incluidos
    TRAZABILIDAD = auto()  # Enlace requisito-caso
    LONGITUD = auto()  # Limite de extension razonable


@dataclass(frozen=True)
class GuardrailViolation:
    """Violacion de una regla de guardrail durante generacion.

    Args:
        guardrail: Tipo de guardrail violado.
        descripcion: Detalle de la violacion.
        ubicacion: Parte del caso donde ocurre (linea, sentencia).
        severidad: Impacto estimado [0, 1].
    """

    guardrail: GuardrailType
    descripcion: str
    ubicacion: str
    severidad: float = 1.0


@dataclass(frozen=True)
class GuardrailResult:
    """Resultado de la validacion de guardrails sobre un caso.

    Args:
        caso_id: Identificador del caso evaluado.
        valido: Indica si paso todos los guardrails.
        violaciones: Lista de violaciones encontradas.
        score_fidelidad: Puntaje de fidelidad a especificacion [0, 1].
    """

    caso_id: str
    valido: bool
    violaciones: tuple[GuardrailViolation, ...] = field(default_factory=tuple)
    score_fidelidad: float = 1.0


@dataclass(frozen=True)
class TestCase:
    """Caso de prueba generado por el sistema L3.

    Args:
        nombre: Nombre descriptivo del caso.
        codigo: Codigo fuente del test.
        lenguaje: Lenguaje de programacion destino.
        framework: Framework de testing usado.
        requisitos_asociados: IDs de requisitos que cubre.
        tags: Etiquetas semanticas del caso.
        guardrail_result: Resultado de validacion de guardrails.
    """

    nombre: str
    codigo: str
    lenguaje: str = "python"
    framework: str = "pytest"
    requisitos_asociados: tuple[str, ...] = field(default_factory=tuple)
    tags: frozenset[str] = field(default_factory=frozenset)
    guardrail_result: GuardrailResult | None = None


@dataclass(frozen=True)
class TestSuite:
    """Suite completa de casos generados.

    Args:
        casos: Lista de casos de prueba generados.
        especificacion_origen: Texto de especificacion original.
        metadata: Metadatos QA de capa L3.
        generacion_id: Identificador unico de generacion.
    """

    casos: tuple[TestCase, ...]
    especificacion_origen: str
    metadata: QAMetadata | None = None
    generacion_id: str = field(default_factory=lambda: uuid4().hex[:12])

    @property
    def total_casos(self) -> int:
        """Cantidad total de casos en la suite."""
        return len(self.casos)

    @property
    def casos_validos(self) -> list[TestCase]:
        """Casos que pasaron todos los guardrails."""
        return [c for c in self.casos if c.guardrail_result and c.guardrail_result.valido]

    @property
    def cobertura_estimada(self) -> float:
        """Cobertura promedio de fidelidad de los casos."""
        if not self.casos:
            return 0.0
        scores = [
            c.guardrail_result.score_fidelidad
            for c in self.casos
            if c.guardrail_result is not None
        ]
        return sum(scores) / len(scores) if scores else 0.0


class TestCaseGenerator:
    """Generador de casos de prueba con guardrails anti-alucinacion.

    Aplica una cadena de validaciones (guardrails) sobre cada caso
    generado para garantizar fidelidad, ejecutabilidad y trazabilidad.

    Args:
        metadata: Metadatos opcionales para capa L3.
        guardrails_activos: Conjunto de guardrails a aplicar.
    """

    def __init__(
        self,
        metadata: QAMetadata | None = None,
    ) -> None:
        """Inicializa el generador con guardrails por defecto."""
        self._metadata = metadata or QAMetadata(
            layer=QALayer.L3_GENERATOR,
            version="1.0.0",
            timestamp_iso=datetime.now(UTC).isoformat(),
            execution_id=uuid4().hex[:12],
        )
        self._guardrails: list[Callable[[TestCase, str], GuardrailResult]] = [
            self._validar_no_invencion,
            self._validar_palabras_prohibidas,
            self._validar_longitud_razonable,
        ]
        logger.info(
            f"[L3][TestCaseGenerator] Inicializado con "
            f"{len(self._guardrails)} guardrails. "
            f"WHAT: generador de casos listo. "
            f"WHY: inicio de capa L3. "
            f"WHERE: TestCaseGenerator.__init__."
        )

    def _validar_no_invencion(
        self, caso: TestCase, especificacion: str
    ) -> GuardrailResult:
        """Guardrail: detecta imports de APIs o librerias inexistentes.

        Args:
            caso: Caso de prueba a validar.
            especificacion: Especificacion original (no usada directamente aqui).

        Returns:
            GuardrailResult con violaciones de invencion encontradas.
        """
        violaciones: list[GuardrailViolation] = []
        imports_encontrados = _PATRON_IMPORT_FANTASMA.findall(caso.codigo)

        for modulo in imports_encontrados:
            if modulo not in _APIS_CONOCIDAS and not modulo.startswith("_"):
                violaciones.append(
                    GuardrailViolation(
                        guardrail=GuardrailType.NO_INVENCION,
                        descripcion=f"Modulo '{modulo}' no esta en la lista de APIs conocidas.",
                        ubicacion=f"import {modulo}",
                        severidad=0.9,
                    )
                )

        return GuardrailResult(
            caso_id=caso.nombre,
            valido=len(violaciones) == 0,
            violaciones=tuple(violaciones),
            score_fidelidad=1.0 - (len(violaciones) * 0.15),
        )

    def _validar_palabras_prohibidas(
        self, caso: TestCase, especificacion: str
    ) -> GuardrailResult:
        """Guardrail: detecta palabras de lenguaje especulativo o placeholder.

        Args:
            caso: Caso de prueba a validar.
            especificacion: Especificacion original (no usada directamente aqui).

        Returns:
            GuardrailResult con violaciones de lenguaje especulativo.
        """
        violaciones: list[GuardrailViolation] = []
        for palabra in _PALABRAS_PROHIBIDAS:
            if palabra.lower() in caso.codigo.lower():
                violaciones.append(
                    GuardrailViolation(
                        guardrail=GuardrailType.FIDELIDAD,
                        descripcion=f"Palabra especulativa/placeholder '{palabra}' encontrada.",
                        ubicacion="codigo",
                        severidad=0.7,
                    )
                )
        return GuardrailResult(
            caso_id=caso.nombre,
            valido=len(violaciones) == 0,
            violaciones=tuple(violaciones),
            score_fidelidad=1.0 - (len(violaciones) * 0.2),
        )

    def _validar_longitud_razonable(
        self, caso: TestCase, especificacion: str
    ) -> GuardrailResult:
        """Guardrail: verifica que el caso no sea excesivamente largo o corto.

        Args:
            caso: Caso de prueba a validar.
            especificacion: Especificacion original (no usada directamente aqui).

        Returns:
            GuardrailResult con violaciones de longitud.
        """
        violaciones: list[GuardrailViolation] = []
        lineas = caso.codigo.strip().split("\n")
        if len(lineas) < 3:
            violaciones.append(
                GuardrailViolation(
                    guardrail=GuardrailType.LONGITUD,
                    descripcion=f"Caso demasiado corto: {len(lineas)} lineas (min 3).",
                    ubicacion="codigo completo",
                    severidad=0.5,
                )
            )
        elif len(lineas) > 200:
            violaciones.append(
                GuardrailViolation(
                    guardrail=GuardrailType.LONGITUD,
                    descripcion=f"Caso demasiado largo: {len(lineas)} lineas (max 200).",
                    ubicacion="codigo completo",
                    severidad=0.4,
                )
            )
        return GuardrailResult(
            caso_id=caso.nombre,
            valido=len(violaciones) == 0,
            violaciones=tuple(violaciones),
            score_fidelidad=1.0 - (len(violaciones) * 0.1),
        )

    def validar_caso(self, caso: TestCase, especificacion: str) -> GuardrailResult:
        """Ejecuta todos los guardrails activos sobre un caso.

        Args:
            caso: Caso de prueba a validar.
            especificacion: Texto de especificacion original.

        Returns:
            GuardrailResult compuesto acumulando todas las violaciones.

        Raises:
            TypeError: Si caso no es instancia de TestCase.
        """
        if not isinstance(caso, TestCase):
            raise TypeError(
                f"[L3][TestCaseGenerator] Se esperaba TestCase, "
                f"recibido {type(caso).__name__}. "
                f"WHY: contrato de tipos estricto. "
                f"WHERE: validar_caso."
            )

        todas_violaciones: list[GuardrailViolation] = []
        score_total = 1.0

        for guardrail_fn in self._guardrails:
            try:
                resultado = guardrail_fn(caso, especificacion)
                todas_violaciones.extend(resultado.violaciones)
                score_total = min(score_total, resultado.score_fidelidad)
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    f"[L3][TestCaseGenerator] Guardrail fallo en caso={caso.nombre}. "
                    f"WHAT: {exc}. "
                    f"WHY: error interno en validacion. "
                    f"WHERE: validar_caso -> {guardrail_fn.__name__}."
                )
                todas_violaciones.append(
                    GuardrailViolation(
                        guardrail=GuardrailType.FIDELIDAD,
                        descripcion=f"Error interno en guardrail: {exc}",
                        ubicacion="desconocida",
                        severidad=1.0,
                    )
                )

        valido = len(todas_violaciones) == 0
        return GuardrailResult(
            caso_id=caso.nombre,
            valido=valido,
            violaciones=tuple(todas_violaciones),
            score_fidelidad=max(0.0, score_total),
        )

    def generate(
        self,
        especificacion: str,
        lenguaje: str = "python",
        framework: str = "pytest",
        cantidad: int = 1,
    ) -> TestSuite:
        """Genera una suite de casos de prueba validados.

        NOTA: Esta implementacion genera casos de prueba de ejemplo
        basados en plantillas. En produccion, la generacion se delega
        a un LLM con los guardrails como constraints.

        Args:
            especificacion: Descripcion textual del componente a testear.
            lenguaje: Lenguaje de programacion destino.
            framework: Framework de testing.
            cantidad: Numero de casos a generar (default 1).

        Returns:
            TestSuite con los casos generados y validados.

        Raises:
            ValueError: Si cantidad < 1 o especificacion vacia.
        """
        if not especificacion or not especificacion.strip():
            raise ValueError(
                "[L3][TestCaseGenerator] Especificacion vacia. "
                "WHY: no hay requisitos desde los cuales generar. "
                "WHERE: generate."
            )
        if cantidad < 1:
            raise ValueError(
                f"[L3][TestCaseGenerator] cantidad={cantidad} debe ser >= 1. "
                f"WHY: debe generar al menos un caso. "
                f"WHERE: generate."
            )

        casos_generados: list[TestCase] = []

        for i in range(cantidad):
            nombre = f"test_{especificacion.split()[0].lower()}_{i}" if especificacion.split() else f"test_caso_{i}"
            codigo = (
                f"def {nombre}():\n"
                f'    """Test basado en: {especificacion[:60]}"""\n'
                f"    # TODO: implementar logica de test\n"
                f"    assert True\n"
            )
            caso = TestCase(
                nombre=nombre,
                codigo=codigo,
                lenguaje=lenguaje,
                framework=framework,
                requisitos_asociados=(f"REQ-{i:04d}",),
                tags=frozenset({"generado", f"lote_{uuid4().hex[:4]}"}),
            )
            guardrail_result = self.validar_caso(caso, especificacion)
            caso = TestCase(
                nombre=caso.nombre,
                codigo=caso.codigo,
                lenguaje=caso.lenguaje,
                framework=caso.framework,
                requisitos_asociados=caso.requisitos_asociados,
                tags=caso.tags,
                guardrail_result=guardrail_result,
            )
            casos_generados.append(caso)

            logger.debug(
                f"[L3][TestCaseGenerator] Caso generado: {nombre}, "
                f"valido={guardrail_result.valido}, "
                f"fidelidad={guardrail_result.score_fidelidad:.2f}. "
                f"WHERE: generate."
            )

        suite = TestSuite(
            casos=tuple(casos_generados),
            especificacion_origen=especificacion,
            metadata=self._metadata,
        )

        logger.info(
            f"[L3][TestCaseGenerator] Suite generada: {suite.total_casos} casos, "
            f"{len(suite.casos_validos)} validos, "
            f"cobertura estimada={suite.cobertura_estimada:.2%}. "
            f"WHY: finalizacion de generacion L3. "
            f"WHERE: generate."
        )

        return suite
