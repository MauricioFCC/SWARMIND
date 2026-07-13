# Velocidad y Paralelismo

## Principio: Plan rapido + Ejecucion consciente

Nivel 0: 2-3 agentes en paralelo (sin dependencias)
Nivel 1: 3-7 agentes en paralelo (builders en directorios DIFERENTES)
Nivel 2: Bugfix (1 agente)
Nivel 3: Consolidacion

## Reglas
- Builder: solo src/
- Guardian: solo tests/
- Scientist: solo texto
- Coordinator: solo consolida
