---
description: Verificacion obligatoria (VER) con evidencia antes de cerrar un cambio
---

Cambio realizado: $ARGUMENTS

Cierra el cambio aplicando la regla VER del harness (un agente nunca afirma,
verifica). Requisitos:

1. Ejecuta el check correspondiente y **cita el output real** (pass rate,
   exit code, lineas de error). Para cambios en `harness/`:
   `pytest harness/tests/test_<modulo>.py -q` + `ruff check <archivos>`.
   Para cambios en skills: `python scripts/validate_skills.py --strict`.
2. Si el check falla, corrige y re-ejecuta: no se entrega con check rojo ni se
   parchea el test para pintar verde.
3. Al final reporta: que se cambio, que check corrio, output resumido y
   siguiente accion.
