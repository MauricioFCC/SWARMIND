"""Constantes del tier frugal de edits (spec ``model-free-edits.md``).

Nombres de env y claves del SSOT agrupadas aqui (MAG: sin literales magicos
en las funciones). No lleva imports de I/O: es solo definiciones.
"""

#: Default del tier frugal: gratis (top de la escalera, N9).
DEFAULT_EDITS_MODEL = "opencode-go/beam-free"

#: Fallback de pago si no hay gratis disponibles (backend frugal sigue payload).
DEFAULT_FALLBACK_MODEL = "opencode-go/deepseek-v4.1-flash"

#: Env override del modelo frugal (precedence top, N5).
ENV_EDITS_MODEL = "SWARMIND_EDITS_MODEL"

#: Env override del flag de routing frugal (1/0).
ENV_FRUGAL_ROUTING = "SWARMIND_FRUGAL_ROUTING"

#: Agente OpenCode del tier (subagente con edits allowed).
EDIT_AGENT_ID = "beam-patcher"

#: Comando OpenCode ligado al agente del tier (entry point en el TUI).
EDIT_COMMAND_ID = "patch-free"

#: Ruta relativa del SSOT runtime yaml (spec N4).
RUNTIME_YAML_RELPATH = ".opencode/config/model_runtime.yaml"

#: Claves leidas del SSOT (sin magic strings en las funciones).
YAML_DEFAULTS_BLOCK = "defaults"
YAML_KEY_EDITS_MODEL = "edits_model"
YAML_KEY_FALLBACK_MODEL = "fallback_model"
YAML_KEY_AGENT_ID = "agent_id"
YAML_KEY_COMMAND_ID = "command_id"
YAML_KEY_FRUGAL_ENABLED = "frugal_routing_enabled"
YAML_LADDER_BLOCK = "frugal_ladder"
YAML_KEY_FREE = "free"
YAML_KEY_PAID = "paid"

__all__ = [
    "DEFAULT_EDITS_MODEL",
    "DEFAULT_FALLBACK_MODEL",
    "EDIT_AGENT_ID",
    "EDIT_COMMAND_ID",
    "ENV_EDITS_MODEL",
    "ENV_FRUGAL_ROUTING",
    "RUNTIME_YAML_RELPATH",
    "YAML_DEFAULTS_BLOCK",
    "YAML_KEY_AGENT_ID",
    "YAML_KEY_COMMAND_ID",
    "YAML_KEY_EDITS_MODEL",
    "YAML_KEY_FALLBACK_MODEL",
    "YAML_KEY_FREE",
    "YAML_KEY_FRUGAL_ENABLED",
    "YAML_KEY_PAID",
    "YAML_LADDER_BLOCK",
]
