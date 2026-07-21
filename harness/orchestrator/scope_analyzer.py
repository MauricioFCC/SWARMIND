"""
scope_analyzer.py — Analiza el alcance de una tarea para escalar la cuadrilla.

Determina cuantos agentes lanzar segun la cantidad de trabajo detectada:
  - Poco trabajo (1-2 archivos): 1 builder + 1 guardian
  - Trabajo normal (3-5 archivos): 2 builders + 1 guardian + 1 scientist
  - Mucho trabajo (6-10 archivos): 3 builders + 2 guardians + 1 scientist
  - Proyecto completo (10+ archivos): 4+ builders + 2 guardians + 1 scientist + bugfix
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

# Keywords que indican cantidad de modulos/archivos
SCALE_INDICATORS: Dict[str, int] = {
    # Pequeno
    "un modulo": 1,
    "una funcion": 1,
    "un archivo": 1,
    "simple": 1,
    "pequeno": 1,
    "rapido": 1,
    # Mediano
    "modulos": 3,
    "varios": 3,
    "multiples": 3,
    "sistema": 4,
    "completo": 5,
    "full": 5,
    "sistema": 4,
    "completo": 5,
    "completa": 5,
    "grande": 6,
    "construye": 3,
    "construir": 3,
    "desarrolla": 3,
    "genera": 2,
    # Grande
    "arquitectura": 6,
    "proyecto": 8,
    "aplicacion": 8,
    "app": 6,
    "enterprise": 10,
    "enterprice": 10,
    "monorepo": 12,
    "microservicios": 12,
    "microservicio": 8,
    "cola de mensajes": 8,
    "cache": 4,
    "trading": 5,
    "frontend": 3,
    "backend": 3,
}

# Palabras que suman modulos
MODULE_KEYWORDS: List[str] = [
    "modulo", "modulos", "componente", "componentes",
    "servicio", "servicios", "microservicio",
    "api", "endpoint", "endpoints",
    "entidad", "entidades", "modelo", "modelos",
    "tabla", "tablas", "schema", "schemas",
]

# Tech stacks que sugieren mas archivos
TECH_STACK_WEIGHTS: Dict[str, int] = {
    "rust": 2,      # Rust tiene Cargo.toml + src/lib.rs + mod.rs
    "python": 1,
    "go": 2,        # Go tiene go.mod + multiple files
    "typescript": 1,
    "javascript": 1,
}


@dataclass
class ScopeEstimate:
    """Estimacion del alcance de una tarea."""
    estimated_files: int = 1
    estimated_modules: int = 1
    builders_needed: int = 1
    guardians_needed: int = 1
    need_scientist: bool = False
    need_bugfix: bool = False
    level: str = "small"  # small, medium, large, xlarge

    @property
    def total_agents(self) -> int:
        """Total de agentes que se lanzaran."""
        total = self.builders_needed + self.guardians_needed
        if self.need_scientist:
            total += 1
        if self.need_bugfix:
            total += 1
        return total + 1  # +1 coordinator


class ScopeAnalyzer:
    """
    Analiza el mensaje del usuario y determina cuantos agentes lanzar.

    Uso:
        analyzer = ScopeAnalyzer()
        scope = analyzer.analyze("implementa un sistema de trading completo con API o BD")
        # scope.estimated_files = 8
        # scope.builders_needed = 3
        # scope.guardians_needed = 2
        # scope.need_scientist = True
    """

    def analyze(self, message: str) -> ScopeEstimate:
        """
        Analiza el mensaje y retorna una estimacion del alcance.

        Args:
            message: Mensaje del usuario describiendo la tarea.

        Returns:
            ScopeEstimate con numero de agentes necesarios.
        """
        if not message:
            return ScopeEstimate()

        msg_lower = message.lower()

        # 1. Detectar escala por keywords
        files = self._estimate_files(msg_lower)

        # 2. Detectar modulos mencionados
        modules = self._count_modules(msg_lower)

        # 3. Ajustar por tech stack
        stack_weight = self._detect_stack_weight(msg_lower)

        # Combinar estimaciones
        total_work = max(files, modules) + stack_weight

        # 4. Determinar nivel
        if total_work <= 2:
            level = "small"
            builders = 1
            guardians = 1
            scientist = False
            bugfix = False
        elif total_work <= 5:
            level = "medium"
            builders = 2
            guardians = 1
            scientist = True
            bugfix = False
        elif total_work <= 10:
            level = "large"
            builders = 3
            guardians = 2
            scientist = True
            bugfix = True
        else:
            level = "xlarge"
            builders = min(4 + (total_work // 10), 8)  # max 8 builders
            guardians = min(2 + (total_work // 8), 4)   # max 4 guardians
            scientist = True
            bugfix = True

        # Scientist solo si hay investigacion
        has_research = any(w in msg_lower for w in
                          ["investigar", "research", "analizar", "analyze", "estudiar", "study"])
        scientist = scientist or has_research

        return ScopeEstimate(
            estimated_files=total_work,
            estimated_modules=modules,
            builders_needed=builders,
            guardians_needed=guardians,
            need_scientist=scientist,
            need_bugfix=bugfix,
            level=level,
        )

    def _estimate_files(self, msg_lower: str) -> int:
        """Estima numero de archivos basado en keywords de escala."""
        total = 1  # minimo 1

        for keyword, weight in SCALE_INDICATORS.items():
            if keyword in msg_lower:
                total = max(total, weight)

        return total

    def _count_modules(self, msg_lower: str) -> int:
        """Cuenta modulos mencionados explícitamente."""
        count = 0
        for kw in MODULE_KEYWORDS:
            if kw in msg_lower:
                count += 1
        return max(count, 1)

    def _detect_stack_weight(self, msg_lower: str) -> int:
        """Detecta peso extra segun tech stack."""
        for stack, weight in TECH_STACK_WEIGHTS.items():
            if stack in msg_lower:
                return weight
        return 0

    def get_template_name(self, scope: ScopeEstimate) -> str:
        """Retorna nombre descriptivo del template segun scope."""
        return f"dynamic_{scope.level}_{scope.builders_needed}b_{scope.guardians_needed}g"

    def generate_subtasks(self, scope: ScopeEstimate, base_id: int = 0) -> List[Dict]:
        """
        Genera subtareas dinamicamente segun el alcance.
        Usa indices (0-based) para dependencias, como los templates estaticos.

        Args:
            scope: Estimacion del alcance.
            base_id: Ignorado (usamos indices 0-based para compatibilidad).

        Returns:
            Lista de dicts de subtareas con deps por indice.
        """
        subtasks = []
        idx = 0  # indice 0-based para deps

        # Nivel 0: PLAN (coordinador)
        subtasks.append({
            "agent": "coordinator",
            "description": f"PLAN: dividir trabajo en {scope.builders_needed} modulos + tests + docs",
            "deps": [],
            "expected_output": "Plan de trabajo",
            "confidence_impact": "critical",
        })
        plan_idx = idx
        idx += 1

        # Nivel 0: SCIENTIST (paralelo con plan)
        if scope.need_scientist:
            subtasks.append({
                "agent": "scientist",
                "description": "INVESTIGAR: mejores practicas (solo texto, 0 archivos)",
                "deps": [],
                "expected_output": "Recomendaciones tecnicas (solo texto)",
                "confidence_impact": "critical",
            })
            idx += 1

        # Nivel 1: BUILDERS (dependen del plan, paralelos entre si)
        builder_indices = []
        builder_names = ["CORE", "API", "DB", "MOD1", "MOD2", "MOD3", "MOD4", "MOD5"]
        builder_paths = ["src/core/", "src/api/", "src/db/",
                        "src/mod1/", "src/mod2/", "src/mod3/", "src/mod4/", "src/mod5/"]

        for i in range(scope.builders_needed):
            builder_indices.append(idx)
            name = builder_names[i] if i < len(builder_names) else f"MOD{i+1}"
            path = builder_paths[i] if i < len(builder_paths) else f"src/mod{i+1}/"
            subtasks.append({
                "agent": "builder",
                "description": f"{name}: implementar en {path} segun plan",
                "deps": [plan_idx],
                "expected_output": f"Modulo {name} en {path}",
                "confidence_impact": "critical",
            })
            idx += 1

        # Nivel 1: GUARDIAN-TESTS
        guardian_test_idx = None
        if scope.guardians_needed >= 1:
            guardian_test_idx = idx
            subtasks.append({
                "agent": "guardian",
                "description": f"TESTS: escribir tests en tests/ para {scope.builders_needed} modulos",
                "deps": [plan_idx],
                "expected_output": f"Tests en tests/ cubriendo {scope.builders_needed} modulos",
                "confidence_impact": "validation",
            })
            idx += 1

        # Nivel 1: GUARDIAN-DOCS
        if scope.guardians_needed >= 2:
            subtasks.append({
                "agent": "guardian",
                "description": "DOCS: documentar modulos y ejemplos de uso",
                "deps": [plan_idx],
                "expected_output": "Docs en ES-UTF8",
                "confidence_impact": "neutral",
            })
            idx += 1

        # Nivel 2: BUGFIX
        if scope.need_bugfix:
            deps = list(builder_indices)
            if guardian_test_idx is not None:
                deps.append(guardian_test_idx)
            subtasks.append({
                "agent": "guardian",
                "description": "BUGFIX: ejecutar tests, identificar fallos y corregir",
                "deps": deps,
                "expected_output": "Tests verdes, bugs corregidos",
                "confidence_impact": "validation",
            })
            idx += 1

        # Nivel 3: CONSOLIDAR
        consol_deps = list(builder_indices)
        if scope.need_scientist:
            # scientist index = 1 (despues de plan)
            consol_deps.append(1)
        if guardian_test_idx is not None:
            consol_deps.append(guardian_test_idx)

        subtasks.append({
            "agent": "coordinator",
            "description": "CONSOLIDAR: integrar modulos, tests y documentacion",
            "deps": consol_deps,
            "expected_output": "Entrega unificada sin conflictos",
            "confidence_impact": "critical",
        })

        return subtasks
