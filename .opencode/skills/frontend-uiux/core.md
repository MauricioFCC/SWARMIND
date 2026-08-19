# Frontend UI/UX — core.md (esencial)

Carga este archivo **bajo demanda** al construir interfaces: principios de
interfaz, pipeline Generative UI, arquitectura de componentes, design system
3-tier y design judgment rules. Índice esencial en `SKILL.md`.

---

## 1. Principios de Interfaz (Norman)

- **Visibilidad**: el estado del sistema siempre visible
- **Feedback**: toda accion tiene respuesta <100ms
- **Affordance**: los elementos indican su funcion visualmente
- **Mapping**: relacion natural entre control y efecto
- **Constraints**: prevenir errores mediante restricciones visuales
- **Consistency**: mismo patron = mismo significado en todo el sistema
- **Error Prevention**: mejor que error recovery

---

## 2. GENERATIVE UI — Semantic Guidance (ACM 2026)

Basado en **arXiv:2604.09577** (LLMs as UI Generators, 83% preferencia vs markdown)
y **ACM 2026** (Bridging Gulfs through Semantic Guidance).

### Jerarquia Semantica de Generacion

```
NIVEL 1 — PRODUCTO (Que se construye, para quien, por que)
  ├── Description: que se esta construyendo
  ├── Target User: quien lo usara
  └── Goal: para que existe

NIVEL 2 — DESIGN SYSTEM (Lenguaje visual y de experiencia)
  ├── Design Style: minimalista, glassmorphic, corporativo
  ├── Color: paleta y esquema
  ├── Typography: fuentes, jerarquia, tamanos
  └── Visual: sombras, radios, espaciado, motion

NIVEL 3 — FEATURE (Funcionalidad especifica)
  ├── Accion: crear, modificar, analizar
  ├── Alcance: app completa, seccion, elemento individual
  └── Datos: fuentes, formato, actualizacion

NIVEL 4 — COMPONENTE (Elementos UI concretos)
  ├── Tipo: boton, tabla, grafico, formulario, modal
  ├── Props: parametros especificos del componente
  └── Estado: loading, empty, error, success, disabled
```

### Pipeline de Generacion

```
1. Product Intent (lenguaje natural)
2. -> Semantic Parser extrae: producto, usuario, objetivo
3. -> Design System Selector: tokens + componentes
4. -> Feature Planner: acciones + alcance + datos
5. -> Component Composer: arbol de componentes
6. -> A2UI/OpenUI Spec Output: JSON declarativo
7. -> Validator: WiserUI checks + WCAG audit
8. -> Render: UI final interactiva
```

### Patrones Generative UI

| Patron | Descripcion | Caso de uso |
|--------|-------------|-------------|
| **Dashboard Generator** | IA elige KPIs, charts y layout segun contexto | Reportes, monitoreo |
| **Adaptive Form** | Campos que aparecen/desaparecen segun respuestas | Onboarding, configuracion |
| **Smart Filter Bar** | Filtros que la IA sugiere segun datos actuales | Tablas grandes, dashboards |
| **Contextual Help** | Tooltips y micro-guias generados para la pantalla actual | Software complejo |
| **Layout Personalization** | IA reorganiza paneles segun frecuencia de uso | Home page, dashboards |
| **Natural Language to UI** | Usuario describe -> IA genera UI | Consultas, reportes ad-hoc |

---

## 3. ARQUITECTURA DE COMPONENTES

### Patrones de Componentes

| Patron | Uso | Ejemplo |
|--------|-----|---------|
| **Atomic Design** | Sistema de atomo -> organismo | `Button` -> `InputGroup` -> `SearchForm` |
| **Compound Components** | Estado implicito compartido | `<Select><Select.Option>...</Select.Option></Select>` |
| **Headless UI** | Logica sin markup (Render Props / Slots) | `useDropdown()` + markup propio |
| **Slot Pattern** | Holes de contenido con fallback | `<Card><Card.Header>...</Card.Header></Card>` |
| **Polymorphic Component** | Un componente, multiples tags HTML | `<Text as="h1"/>` o `<Text as="p"/>` |
| **Provider Pattern** | Contexto global tipado | `<ThemeProvider><App/></ThemeProvider>` |

### Arbol de Componentes (Design System)

```
Design System
+-- Tokens
|   +-- colors (primitives + semantic)
|   +-- typography (scale, font-family, line-height)
|   +-- spacing (4px base grid)
|   +-- shadows (elevation scale)
|   +-- motion (duration, easing curves)
+-- Atoms
|   +-- Button / IconButton / LinkButton
|   +-- Input / Textarea / Select / Checkbox / Radio
|   +-- Badge / Tag / Avatar
|   +-- Icon (SVG sprite, lazy)
|   +-- Text / Heading / Code
+-- Molecules
|   +-- InputGroup (label + input + error + hint)
|   +-- Card (header + body + footer)
|   +-- Modal / Dialog
|   +-- Tooltip / Popover
|   +-- Tabs / Accordion / Pagination
+-- Organisms
|   +-- DataTable (sort, filter, pagination, selection)
|   +-- Form (validation, submission, dirty tracking)
|   +-- Navigation (sidebar, topbar, breadcrumb)
|   +-- Toast / Notification Center
|   +-- FileUpload / Dropzone
+-- Templates
    +-- DashboardLayout (sidebar + header + content)
    +-- AuthLayout (centered card)
    +-- ErrorLayout (full-page error)
```

---

## 4. DESIGN SYSTEM — 3-Tier Token Architecture

Basado en **Geeklego** (AI-native, 3-tier tokens, 81 componentes),
**7onic** (zero design-code drift, Figma -> CSS/Tailwind/JS, AI-ready con llms.txt),
**useVyre** (semantic tokens + AI context blocks inline).

### TIER 1 — Design Tokens Primitivos

```yaml
color:
  primary: { 50: "#eff6ff", 500: "#3b82f6", 900: "#1e3a5f" }
  semantic: { success: "#10b981", warning: "#f59e0b", error: "#ef4444", info: "#3b82f6" }
  surface: { page: "#ffffff", card: "#f8fafc", modal: "#ffffff" }
  text: { primary: "#0f172a", secondary: "#475569", disabled: "#94a3b8" }
spacing: { base: 4, scale: [0, 1, 2, 3, 4, 5, 6, 8, 10, 12, 16, 20, 24] }
typography:
  fontFamily: { sans: "Inter, system-ui, sans-serif", mono: "JetBrains Mono, monospace" }
  scale: { xs: 11, sm: 13, base: 16, lg: 18, xl: 22, 2xl: 28, 3xl: 36, 4xl: 48, 5xl: 60, 6xl: 72 }
shadow: { sm: "0 1px 2px rgba(0,0,0,0.05)", md: "0 4px 6px -1px rgba(0,0,0,0.1)" }
motion: { fast: "150ms ease", normal: "250ms ease", slow: "400ms ease" }
radius: { none: 0, sm: 4, md: 8, lg: 12, xl: 16, full: 9999 }
```

### TIER 2 — Component Tokens

```yaml
button:
  bg: "{color.primary.500}"
  text: "#ffffff"
  hover: "{color.primary.700}"
  disabled: "{color.neutral.300}"
  focus-ring: "{color.primary.300}"
input:
  bg: "{color.surface.page}"
  border: "{color.neutral.300}"
  focus: "{color.primary.500}"
  error: "{color.semantic.error}"
  placeholder: "{color.text.disabled}"
card:
  bg: "{color.surface.card}"
  shadow: "{shadow.sm}"
  radius: "{radius.md}"
```

### TIER 3 — Semantic Tokens (Contextuales)

```yaml
risk-status: { low: "{color.semantic.success}", medium: "{color.semantic.warning}", high: "{color.semantic.error}" }
signal-strength: { strong: "{color.semantic.success}", neutral: "{color.text.secondary}", weak: "{color.semantic.warning}" }
data-freshness: { realtime: "{color.semantic.success}", delayed: "{color.semantic.warning}", stale: "{color.semantic.error}" }
user-role: { admin: "full-access", trader: "read-write", analyst: "read-only", viewer: "read-only-limited" }
```

### Machine-Readable Spec (CLAUDE.md / AGENTS.md pattern)

```yaml
# .opencode/design-system/manifest.yaml
design_system:
  name: "Swarmind-ui"
  version: "1.0.0"
  framework: "a2ui"  # Framework-agnostic via A2UI
  layers:
    - tier: 1  # Primitivos
      tokens:
        color_primary: "#1a73e8"
        spacing_base: 4
        font_family: "Inter, system-ui, sans-serif"
    - tier: 2  # Componentes
      components:
        - name: "RiskHeatmap"
          tokens:
            bg_cell: "{color_neutral_100}"
            text_value: "{color_neutral_900}"
    - tier: 3  # Semanticos
      context:
        - role: "trader"
          components: ["RiskHeatmap", "ExposureGauge", "OrderBook"]
```

---

## 5. DESIGN JUDGMENT RULES (StyleSeed Approach)

Basado en **StyleSeed** (74 reglas, 48 componentes, 19 skills AI, named motion system).
Cada regla es un check automatico que el LLM aplica antes de generar UI.

### Reglas de Composicion (12 reglas)

```yaml
R1: "Todo layout debe tener jerarquia visual clara (header -> content -> actions)"
R2: "Elementos relacionados deben agruparse visualmente (proximidad + contenedor)"
R3: "El espaciado debe seguir la progresion geometrica de tokens (4px base)"
R4: "Maximo 3 niveles de jerarquia visual por pantalla"
```

### Reglas de Tipografia (8 reglas)

```yaml
R5: "Maximo 2 familias tipograficas por interfaz"
R6: "Jerarquia tipografica: ratio 1.25 (minor third)"
R7: "Longitud de linea: 45-75 caracteres para texto continuo"
R8: "Tamano minimo de texto: 14px (0.875rem) para UI, 16px (1rem) para body"
```

### Reglas de Color (10 reglas)

```yaml
R9: "Ratio de contraste WCAG 2.2 AA: 4.5:1 texto normal, 3:1 texto grande"
R10: "Color semantico para estados: success/warning/error/info"
R11: "No usar color como unico diferenciador semantico (agregar icono/texto)"
R12: "Paleta limitada: maximo 3 colores de acento por interfaz"
```

### Reglas de Interaccion (14 reglas)

```yaml
R15: "Feedback visual <100ms para respuesta inmediata"
R16: "Transiciones animadas: 200-300ms, easing ease-in-out"
R17: "Named motion: fade, slide, scale, spring (StyleSeed system)"
R18: "Hover states en todos los elementos clickeables"
```

### Reglas de Data Visualization (10 reglas)

```yaml
R22: "Elegir chart type segun relacion: comparacion, composicion, distribucion, tendencia"
R23: "Toda visualizacion debe tener: titulo, ejes etiquetados, leyenda"
R24: "Evitar 3D charts: distorsionan la percepcion de datos"
```

### Reglas de Accesibilidad (12 reglas)

```yaml
R30: "Keyboard navigation: Tab order logico + skip links + focus visible"
R31: "ARIA labels en todos los elementos interactivos"
R32: "Modo de alto contraste soportado"
R33: "Target size minimo 44x44px (WCAG 2.2 nuevo criterio 2.5.8)"
```

### Reglas de Responsive (8 reglas)

```yaml
R42: "Mobile-first: 3 breakpoints (sm: 640px, md: 1024px, lg: 1440px)"
R43: "Touch targets: minimo 44x44px en mobile"
R44: "Contenido prioritario arriba del pliegue (above the fold)"
```