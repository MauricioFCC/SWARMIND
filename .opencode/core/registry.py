"""
Skill Registry with semantic versioning, contracts & dependency tracking.
Enterprise pattern for managing AI agent skills with validation.
"""
from dataclasses import dataclass, field
from typing import Dict, Optional, List, Any, Set
from enum import Enum
import json
import re


class SkillStatus(Enum):
    """SkillStatus."""
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    EXPERIMENTAL = "experimental"
    ARCHIVED = "archived"


@dataclass
class SkillContract:
    """Contrato explícito para un skill - define inputs, outputs y garantías."""
    name: str
    version: str  # SemVer: MAJOR.MINOR.PATCH
    description: str
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]
    preconditions: List[str]
    postconditions: List[str]
    requires_tools: List[str]
    dependencies: List[str] = field(default_factory=list)
    status: SkillStatus = SkillStatus.ACTIVE
    author: str = "onyx-team"
    tags: List[str] = field(default_factory=list)
    
    def validate_version(self) -> bool:
        """Valida que la versión siga SemVer."""
        pattern = r"^\d+\.\d+\.\d+(-[\w.]+)?(\+[\w.]+)?$"
        return bool(re.match(pattern, self.version))
    
    def to_dict(self) -> Dict[str, Any]:
        """Serializa el contrato para almacenamiento/transferencia."""
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "preconditions": self.preconditions,
            "postconditions": self.postconditions,
            "requires_tools": self.requires_tools,
            "dependencies": self.dependencies,
            "status": self.status.value,
            "author": self.author,
            "tags": self.tags
        }


class SkillRegistry:
    """Registro centralizado de skills con validación de contratos y versionado."""
    
    def __init__(self, schema_path: Optional[str] = None):
        """Inicializa la instancia de la clase."""
        self._skills: Dict[str, SkillContract] = {}
        self._versions: Dict[str, List[str]] = {}
        self._schema_path = schema_path
        self._load_schema()
    
    def _load_schema(self) -> None:
        """Carga el esquema JSON para validación (opcional)."""
        if self._schema_path:
            try:
                with open(self._schema_path, 'r', encoding='utf-8') as f:
                    self._json_schema = json.load(f)
            except FileNotFoundError:
                self._json_schema = None
    
    def register(self, contract: SkillContract) -> bool:
        """
        Registra un skill con validación de contrato.
        
        Returns:
            bool: True si el registro fue exitoso
        """
        # Validar versión SemVer
        if not contract.validate_version():
            raise ValueError(f"Versión inválida: {contract.version} (debe ser SemVer)")
        
        # Validar esquema JSON si está disponible
        if self._json_schema:
            # Validación simplificada - en prod usar jsonschema library
            required_fields = ["name", "version", "input_schema", "output_schema"]
            for field in required_fields:
                if field not in contract.to_dict():
                    raise ValueError(f"Campo requerido faltante: {field}")
        
        # Registrar
        self._skills[contract.name] = contract
        self._versions.setdefault(contract.name, []).append(contract.version)
        self._versions[contract.name].sort(key=lambda v: [int(x) for x in re.findall(r'\d+', v)])
        
        return True
    
    def get(self, name: str, version: Optional[str] = None) -> Optional[SkillContract]:
        """
        Obtiene un skill por nombre y versión opcional.
        
        Args:
            name: Nombre del skill
            version: Versión específica (opcional, default: última estable)
        
        Returns:
            SkillContract o None si no existe
        """
        if name not in self._skills:
            return None
        
        if version is None:
            # Retornar última versión no-deprecated
            for v in reversed(self._versions[name]):
                skill = self._skills.get(f"{name}@{v}") or self._skills[name]
                if skill.status == SkillStatus.ACTIVE:
                    return skill
            return self._skills[name]
        
        return self._skills.get(f"{name}@{version}") or self._skills.get(name)
    
    def list_available(self, status: Optional[SkillStatus] = None) -> List[Dict[str, str]]:
        """Lista skills disponibles con metadatos básicos."""
        result = []
        for name, contract in self._skills.items():
            if status and contract.status != status:
                continue
            result.append({
                "name": name,
                "version": contract.version,
                "description": contract.description,
                "status": contract.status.value,
                "tags": contract.tags
            })
        return result
    
    def validate_input(self, name: str, data: Dict[str, Any]) -> tuple[bool, str]:
        """
        Valida que los datos de entrada cumplan con el esquema del skill.
        
        Returns:
            tuple[bool, str]: (es_válido, mensaje_de_error_o_exito)
        """
        contract = self.get(name)
        if not contract:
            return False, f"Skill '{name}' no registrado"
        
        # Validación básica de campos requeridos
        required = contract.input_schema.get("required", [])
        missing = [k for k in required if k not in data]
        if missing:
            return False, f"Campos requeridos faltantes: {missing}"
        
        # Validación de tipos (simplificada)
        properties = contract.input_schema.get("properties", {})
        for key, value in data.items():
            if key in properties:
                expected_type = properties[key].get("type")
                if expected_type and not self._check_type(value, expected_type):
                    return False, f"Tipo inválido para '{key}': esperado {expected_type}"
        
        return True, "✅ Input válido"
    
    def validate_output(self, name: str, output: Any) -> tuple[bool, str]:
        """Valida que la salida cumpla con el esquema declarado."""
        contract = self.get(name)
        if not contract:
            return False, f"Skill '{name}' no registrado"
        
        # Validación simplificada - en prod usar jsonschema completo
        if isinstance(output, dict):
            required = contract.output_schema.get("required", [])
            missing = [k for k in required if k not in output]
            if missing:
                return False, f"Campos de salida faltantes: {missing}"
        
        return True, "✅ Output válido"
    
    @staticmethod
    def _check_type(value: Any, expected: str) -> bool:
        """Verifica si un valor coincide con el tipo esperado."""
        type_map = {
            "string": str,
            "integer": int,
            "number": (int, float),
            "boolean": bool,
            "array": list,
            "object": dict,
            "null": type(None)
        }
        expected_type = type_map.get(expected)
        if not expected_type:
            return True  # Tipo desconocido, asumir válido
        return isinstance(value, expected_type)
    
    def get_dependency_graph(self, skill_name: str) -> Dict[str, List[str]]:
        """Obtiene el grafo de dependencias para un skill.

        Returns un diccionario con las dependencias transitivas del skill
        especificado. Si el skill no existe, retorna un dict vacio.
        """
        graph: Dict[str, List[str]] = {}
        visited: Set[str] = set()
        self._traverse_deps(skill_name, graph, visited)
        return graph

    def _traverse_deps(self, name: str, graph: Dict[str, List[str]], visited: Set[str]) -> None:
        """Recorre recursivamente las dependencias de un skill.

        Args:
            name: Nombre del skill a recorrer.
            graph: Diccionario acumulador del grafo de dependencias.
            visited: Conjunto de skills ya visitados (evita ciclos).
        """
        if name in visited:
            return
        visited.add(name)
        contract = self.get(name)
        if contract:
            graph[name] = contract.dependencies
            for dep in contract.dependencies:
                self._traverse_deps(dep, graph, visited)


# Instancia global del registry
registry = SkillRegistry(schema_path=".opencode/core/skill_schema.json")


# Funciones de utilidad para registro rápido
def register_skill(
    name: str,
    version: str,
    description: str,
    input_schema: Dict,
    output_schema: Dict,
    preconditions: List[str],
    postconditions: List[str],
    requires_tools: List[str],
    dependencies: List[str] = None,
    tags: List[str] = None
) -> bool:
    """Función helper para registrar un skill rápidamente."""
    contract = SkillContract(
        name=name,
        version=version,
        description=description,
        input_schema=input_schema,
        output_schema=output_schema,
        preconditions=preconditions,
        postconditions=postconditions,
        requires_tools=requires_tools,
        dependencies=dependencies or [],
        tags=tags or []
    )
    return registry.register(contract)
