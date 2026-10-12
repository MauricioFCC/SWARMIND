# Redes y SNA — detalle bajo demanda

> Migrado de `SKILL.md` a `references/` por política "focused beats comprehensive"
> (SkillsBench 2026, arXiv:2602.12670). El protocolo SNA (5 pasos) permanece en
> `SKILL.md`; aqui viven las metricas, topologias y el metodo de analisis.

## Teoria de Redes Aplicada a Topologias de Comunicacion

### Metricas de Red

| Metrica | Definicion | Interpretacion en Agentes |
|---------|------------|--------------------------|
| **Centralidad de grado** | Numero de conexiones directas | Agente mas conectado, hub de comunicacion |
| **Centralidad de intermediacion** | Frecuencia en caminos mas cortos entre pares | Broker, controla flujo de informacion |
| **Centralidad de vector propio** | Importancia basada en conexiones importantes | Agente influyente conectado a otros influyentes |
| **Densidad** | Proporcion de conexiones existentes vs posibles | Cohesion general del equipo, redundancia |
| **Coeficiente de clustering** | Proporcion de triangulos cerrados vs posibles | Formacion de subgrupos, camarillas |
| **Homofilia** | Tendencia a conectarse con similares | Especializacion vs diversidad funcional |
| **Distancia media** | Promedio de pasos entre cualquier par | Eficiencia de difusion de informacion |

### Topologias de Red para Agentes

| Topologia | Estructura | Ventajas | Desventajas | Uso Recomendado |
|-----------|------------|----------|-------------|-----------------|
| **Completamente conectada** | Todos con todos | Maxima redundancia, minima latencia | Costo O(n), ruido informativo | Equipos pequenos (<5 agentes) |
| **Estrella** | Un nodo central conectado a periferia | Control centralizado, facil coordinacion | Cuello de botella, punto unico de fallo | Arquitecturas coordinador-subordinado |
| **Anillo** | Conexion secuencial cerrada | Simetrica, sin jerarquia | Latencia O(n) para mensajes lejanos | Flujos de trabajo secuenciales |
| **Arbol** | Jerarquica con ramas | Escalable, modular | Flujo vertical limitado | Organizaciones jerarquicas |
| **Malla parcial** | Conexiones selectivas | Balance costo-redundancia | Compleja de disenar | Equipos medianos |
| **Small-world** | Clusters locales con puentes largos | Baja distancia media, alta cohesion | Puntos de fallo en puentes | Equipos grandes colaborativos |
| **Scale-free** | Pocos hubs muy conectados | Robusta a fallos aleatorios, crecimiento natural | Vulnerable a ataques dirigidos a hubs | Redes abiertas en crecimiento |

### Analisis de Estructura Social (SNA)

```
1. MAPEAR: Identificar nodos (agentes) y edges (canales de comunicacion)
2. MEDIR: Calcular metricas de red (centralidad, densidad, clustering)
3. DIAGNOSTICAR: 
   - ?Hay cuellos de botella? (alta intermediacion en pocos nodos)
   - ?Hay aislamiento? (bajo grado en algunos agentes)
   - ?Hay camarillas excesivas? (clustering alto, poca integracion)
   - ?La red es eficiente? (distancia media optima)
4. INTERVENIR: 
   - Agregar/quitar conexiones
   - Reasignar roles
   - Crear puentes entre clusters
5. MONITOREAR: Evolucion de metricas en el tiempo
```
