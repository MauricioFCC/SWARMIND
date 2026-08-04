---




name: frontend-uiux
domain: frontend
description: "Skill profesional de UI/UX con Generative UI 2026: design systems tokenizados (Geeklego, 7onic, useVyre), semantic guidance (Product→DesignSystem→Feature→Component), validacion UX (WiserUI-Bench, WCAG 2.2 AA), interfaces LLM-native (A2UI/OpenUI), StyleSeed | UPG·NAM·FRS (reglas en base_principles.md)"
version: 1.0.0
project_agnostic: true
inherit:
  - core/base_principles.md
  - core/fde_principles.md
variables:
  - UI_FRAMEWORK: react 19, svelte 5, solid 2, astro 5 ({{UI_FRAMEWORK}})
  - DESIGN_SYSTEM: geeklego, 7onic, useVyre, custom ({{DESIGN_SYSTEM}})
  - ACCESSIBILITY_LEVEL: WCAG 2.2 AA (minimo), AAA (recomendado) ({{ACCESSIBILITY_LEVEL}})
metadata:
  author: frontend-uiux-research
  tags: [ui, ux, frontend, generative-ui, design-system, hci, accessibility, a2ui, openui, styleseed, geeklego, web-vitals, visual-testing]
  dependencies: [hedgefund, evolve]
---

# Frontend UI/UX | Generative Design System Professional

⚡ **ROL**: UI/UX Architect & Frontend Engineer
🎯 **STACK**: `{{UI_FRAMEWORK}}` | 📐 Design System: `{{DESIGN_SYSTEM}}` | ♿ Accesibilidad: `{{ACCESSIBILITY_LEVEL}}`
🔀 **ROLE STACKING**: UI Architect + Component Engineer + Accessibility Specialist + Performance Engineer
🔄 **FLUJO PRIORITARIO**: Research -> Design Tokens -> Component Tree -> Interaction -> Validation -> Generative Polish
🛡️ **CAPAS CRITICAS**: Accessibility | Performance | Visual Consistency | Generative Adaptability

---

## 1. RESEARCH FIRST — Estado del Arte UI/UX 2026

**INVESTIGAR antes de disenar.** Antes de generar cualquier interfaz, buscar el estado del arte en:
- Generative UI frameworks (A2UI v0.9, OpenUI, Vercel json-render)
- Design systems AI-native (Geeklego 3-tier, 7onic, useVyre, StyleSeed)
- Papers 2026 (arXiv:2604.09577, ACM Semantic Guidance, ACL WiserUI-Bench)
- metodos de personalizacion (arXiv:2604.09876 Bayesian preference learning)
- Benchmarks UX (WiserUI-Bench 300 pares A/B, ReFinE research-to-design)

Documentar fuente y elegir la tecnica mas avanzada. Solo entonces generar UI.

---

## 2. PRINCIPIOS DE DISENO DE INTERFAZ

### Leyes de UX aplicadas
| Principio | Aplicacion |
|-----------|-----------|
| **Ley de Fitts** | Elementos interactivos grandes y cerca del area de enfoque |
| **Ley de Hick** | Minimizar opciones por pantalla (< 7 +/- 2) |
| **Ley de Jakob** | Usar patrones familiares del ecosistema web |
| **Ley de Miller** | Chunking de informacion en grupos de 5-9 items |
| **Efecto Von Restorff** | Destacar visualmente la accion primaria (CTA) |
| **Regla 80/20** | 80% del uso esta en 20% de las funciones |
| **Ley de Postel** | Ser conservador en lo que envias, liberal en lo que aceptas |

### Principios de Interfaz (Norman)
- **Visibilidad**: el estado del sistema siempre visible
- **Feedback**: toda accion tiene respuesta <100ms
- **Affordance**: los elementos indican su funcion visualmente
- **Mapping**: relacion natural entre control y efecto
- **Constraints**: prevenir errores mediante restricciones visuales
- **Consistency**: mismo patron = mismo significado en todo el sistema
- **Error Prevention**: mejor que error recovery

---

## 3. GENERATIVE UI — Semantic Guidance (ACM 2026)

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

## 4. ARQUITECTURA DE COMPONENTES

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

## 5. DESIGN SYSTEM — 3-Tier Token Architecture

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

## 6. DESIGN JUDGMENT RULES (StyleSeed Approach)

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

---

## 7. ACCESIBILIDAD — WCAG 2.2 AA/AAA

### Principios POUR
| Principio | Cobertura minima | Verificacion |
|-----------|-----------------|--------------|
| **Perceivable** | Texto alternativo, subtitulos, contraste >=4.5:1 | axe-core, Lighthouse |
| **Operable** | Navegacion teclado, foco visible, sin destellos | Playwright tab test |
| **Understandable** | Idioma declarado, labels, errores claros | Lectura por screen reader |
| **Robust** | HTML semantico, ARIA cuando necesario, validacion W3C | Validator checker |

### Reglas Fijas de Accesibilidad
1. **Toda interaccion tiene foco visible**: `:focus-visible` outline >=2px
2. **Todo formulario tiene label**: `<label for="id">` o `aria-label`, nunca placeholder como label
3. **Toda imagen tiene alt descriptivo**: `alt="Grafico de ventas Q3 2026"` no `alt="imagen"`
4. **Todo cambio de estado se anuncia**: `aria-live="polite"` para regiones dinamicas
5. **Contraste minimo 4.5:1** para texto normal, 3:1 para large text (WCAG AA)
6. **Navegacion completa por teclado**: Tab, Shift+Tab, Enter, Escape, Arrow keys
7. **Skip to content link** como primer elemento del body
8. **Titulo de pagina unico y descriptivo**: `<title>Ventas — Dashboard</title>`
9. **Idioma definido**: `<html lang="es">` con cambios usando `lang` en secciones
10. **No bloquear zoom**: viewport con `user-scalable=yes`, maximo escala 500%

### Testing Automatico de a11y
- **Static**: `eslint-plugin-jsx-a11y` + `@axe-core/react` en desarrollo
- **CI**: `axe-playwright` en cada spec E2E, umbral de violaciones = 0
- **Visual**: `pa11y-ci` para auditoria periodica
- **Screen Reader**: pruebas manuales con NVDA/VoiceOver en flujos criticos

---

## 8. RENDIMIENTO — Core Web Vitals

### Metricas Objetivo
| Metrica | Bueno | Necesita mejora | Pobre |
|---------|-------|-----------------|-------|
| **LCP** (Largest Contentful Paint) | <=2.5s | 2.5s–4.0s | >4.0s |
| **INP** (Interaction to Next Paint) | <=200ms | 200ms–500ms | >500ms |
| **CLS** (Cumulative Layout Shift) | <=0.1 | 0.1–0.25 | >0.25 |
| **FCP** (First Contentful Paint) | <=1.8s | 1.8s–3.0s | >3.0s |
| **TTFB** (Time to First Byte) | <=800ms | 800ms–1.8s | >1.8s |

### Estrategias de Optimizacion
1. **Code Splitting**: `React.lazy()` + `Suspense` por ruta y componente pesado
2. **Bundle Analysis**: `vite-plugin-visualizer`, chunk < 200KB
3. **Image Optimization**: `<img loading="lazy">`, WebP/AVIF, srcset, CDN, blur placeholder
4. **Font Loading**: `font-display: swap`, preload, subsetting, variable fonts
5. **Caching Estrategico**: Service Worker para assets estaticos, stale-while-revalidate para API
6. **Reduccion de JavaScript**: Tree-shaking, dead code elimination, import dinamicos
7. **CSS critico inline**: Primer pintado con estilos minimos, diferir el resto
8. **Progressive Enhancement**: Funcionalidad base sin JS, mejorar con JS disponible
9. **Streaming SSR**: Renderizar HTML progresivamente, suspender componentes pesados
10. **Signals / Fine-grained Reactivity**: Svelte 5 runes, SolidJS signals, Preact Signals

---

## 9. PERSONALIZACION — Sample-Efficient Preference Learning

Basado en **arXiv:2604.09876** (Efficient Personalization of Generative User Interfaces).
Las preferencias de diseno son subjetivas (kappa=0.25 entre disenadores).

### Bayesian Active Preference Learning
```
Fase 1 — Cold Start:
  - Generar N=5 propuestas de UI con variaciones controladas
  - Usuario rankea (no puntua) — mas robusto cognitivamente

Fase 2 — Bayesian Update:
  - Modelo probit: P(user prefers A > B) = PHI(u(A) - u(B))
  - Prior: distribucion normal sobre pesos de atributos
  - Posterior: actualizada con cada ranking

Fase 3 — Active Query:
  - Maximizar expected information gain
  - Query las comparaciones mas informativas (mutual information)

Fase 4 — Convergence:
  - Detener cuando incertidumbre < threshold
  - Generar UI final optimizada para preferencias aprendidas

Target: kappa agreement > 0.6 con 10-15 queries (vs 50+ sin active learning)
```

---

## 10. VALIDACION UX — WiserUI-Bench + ReFinE

Basado en **WiserUI-Bench** (ACL 2026, 300 pares A/B reales) y **ReFinE** (DIS 2026).

### Tests de Validacion
```
1. Visual Reasoning Test
   Input: UI mockup + pregunta comportamental
   Ej: "Que accion tomaria un usuario para cerrar sesion?"
   Metrica: Accuracy sobre 300 pares WiserUI-Bench
   Target: >85%

2. Preference Test
   Input: 2 versiones de UI generadas por diferentes approaches
   Evaluacion: Preferencia humana ciega (A/B test)
   Target: >70% para la version generada vs baseline markdown

3. Gulf Evaluation (ACM 2026)
   Gulf of Execution: El usuario sabe que hacer?
   Gulf of Evaluation: El usuario entiende lo que paso?
   Metrica: Task completion rate + Time-on-task

4. WCAG 2.2 AA Audit (Automated)
   axe-core + pa11y + Lighthouse integration
   Target: >95% AA compliance, 0 critical violations

5. ReFinE Iteration Loop
   Research Findings -> Design Modifications -> Validation -> Repeat
   Cada iteracion mide mejora en metricas UX (generativity, inspirability, actionability)
```

---

## 11. TESTING VISUAL Y DE COMPONENTES

| Tipo | Herramienta | Cobertura minima |
|------|-------------|------------------|
| **Unit (componentes)** | Vitest / Testing Library | 90% logica de componentes |
| **Snapshot visual** | Chromatic / Percy / Loki | 100% componentes del DS |
| **Interaccion** | Playwright Component Testing | 80% flujos criticos |
| **E2E** | Playwright / Cypress | 100% user journeys |
| **Accesibilidad** | axe-playwright + pa11y-ci | 0 violaciones bloqueantes |
| **Rendimiento** | Lighthouse CI + WebPageTest | Scores >=90 |
| **Responsive** | Playwright (3 viewports) | Mobile 375 + Tablet 768 + Desktop 1280 |

### Property-Based Testing (PBT) Templates para UI
```python
# Template 1: Invariantes de Componentes
@given(st.builds(ButtonProps,
    label=st.text(min_size=0, max_size=100),
    variant=st.sampled_from(["primary", "secondary", "ghost", "danger"]),
    disabled=st.booleans(),
    loading=st.booleans(),
))
def test_button_props_invariants(props):
    """disabled+loading mutuamente exclusivos"""
    if props.disabled:
        assert not button.is_focusable(), "[FOCUS-1] disabled no focusable"
    if props.loading:
        assert "Cargando" in button.aria_label, "[ARIA-1] loading indica estado"

# Template 2: Contraste WCAG
@given(background=st.sampled_from(TOKENS.colors),
       foreground=st.sampled_from(TOKENS.colors))
def test_contrast_ratio(background, foreground):
    """WCAG 2.2 AA: ratio >= 4.5:1 para texto normal"""
    ratio = wcag_contrast_ratio(background, foreground)
    assert ratio >= 4.5, f"[WCAG-AA-1.4.3] {background}/{foreground}: {ratio:.2f}:1"

# Template 3: Navegacion por Teclado
@given(st.lists(st.builds(MenuItem, disabled=st.booleans())))
def test_keyboard_navigation(items):
    """Tab debe recorrer items enabled en orden"""
    focus_order = menu.get_focus_order()
    enabled = [i for i, item in enumerate(items) if not item.disabled]
    assert focus_order == enabled, f"[KEY-2.1.1] focus_order mismatch"

# Template 4: Responsive Breakpoints
@given(viewport=st.integers(min_value=320, max_value=2560))
def test_responsive_layout(viewport):
    """No layout shift ni overflow en ningun viewport"""
    rendered = component.render(viewport_width=viewport)
    assert not rendered.has_horizontal_scroll(), f"[RESP-1] overflow en {viewport}px"

# Template 5: Design Token Consistency
@given(token_path=st.sampled_from(ALL_TOKEN_PATHS))
def test_design_token_resolution(token_path):
    """Todo token debe resolverse a un valor valido"""
    value = resolve_token(token_path)
    assert value is not None, f"[TOKEN-1] {token_path} no resuelve"

# Template 6: Chart Invariants
@given(data=st.lists(st.floats(min_value=-1e6, max_value=1e6), min_size=1))
def test_chart_invariants(data):
    """Chart siempre debe mostrar datos proporcionados sin distorsion"""
    chart = BarChart(data)
    rendered = chart.render()
    assert len(rendered.bars) == len(data), "[CHART-1] barras != datos"
    assert rendered.y_scale_type == "linear", "[CHART-2] escala debe ser lineal"

# Template 7: State Machine Invariants
@given(actions=st.lists(st.sampled_from(["open", "close", "submit", "reset"])))
def test_modal_state_machine(actions):
    """Modal sigue maquina de estados: closed->open->closed"""
    modal = Modal()
    for action in actions:
        modal.dispatch(action)
    assert modal.state in {"open", "closed"}, f"[STATE-1] estado invalido"
```

---

## 12. MANEJO DE ESTADO GLOBAL

### Estrategia por tamano de app
| Tamano App | Solucion | Cuando usar |
|-----------|----------|-------------|
| **Pequena** (< 5 screens) | React Context + useReducer | Sin dependencies externas |
| **Mediana** (5-15 screens) | Zustand / Jotai | Estado compartido moderado |
| **Grande** (> 15 screens) | Zustand + TanStack Query | Separacion estado servidor/cliente |
| **Multi-widget** | Signals (Preact/Solid) | Alta frecuencia de actualizacion |
| **Data-heavy** | TanStack Query + Zustand | Caching + sincronizacion server state |

### Server State vs Client State
```typescript
// TanStack Query para server state (datos de API)
function useVentas(filtros: Filtros) {
  return useQuery({
    queryKey: ['ventas', filtros],
    queryFn: () => api.getVentas(filtros),
    staleTime: 30_000,
    gcTime: 5 * 60_000,
  });
}

// Zustand para client state (UI state)
const useUIStore = create<UIStore>((set) => ({
  sidebarOpen: true,
  toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
}));
```

---

## 13. RENDERIZADO — SSR / SSG / ISR / RSC

| Estrategia | Caso de uso | Framework |
|-----------|-------------|-----------|
| **SSR** (Server-Side Rendering) | Contenido dinamico por request | Next.js, SvelteKit, Remix |
| **SSG** (Static Site Generation) | Contenido que cambia poco | Next.js static export, Astro |
| **ISR** (Incremental Static Regeneration) | Contenido semi-estatico actualizable | Next.js `revalidate` |
| **RSC** (React Server Components) | Componentes solo en server | Next.js App Router |
| **Streaming SSR** | Render progresivo con Suspense | React 18+ `renderToPipeableStream` |
| **Partial Hydration** | Hidratar solo componentes interactivos | Astro islands |
| **Edge SSR** | SSR en edge functions (baja latencia) | Next.js Edge Runtime, Cloudflare Workers |

---

## 14. PATRONES DE UX AVANZADOS

| Patron | Descripcion | Implementacion |
|--------|-------------|----------------|
| **Optimistic UI** | Reflejar cambio inmediato, confirmar despues | `useMutation.onMutate` + rollback |
| **Skeleton Screens** | Placeholder del layout mientras carga | `<Skeleton variant="card"/>` |
| **Progressive Loading** | Cargar contenido critico primero, diferir el resto | `@defer` / `lazy` |
| **Infinite Scroll** | Cargar mas datos cuando el usuario llega al final | `IntersectionObserver` |
| **Virtual Scrolling** | Renderizar solo items visibles en listas grandes | `TanStack Virtual` |
| **Debounced Search** | Buscar despues de que el usuario deja de escribir | `useDebouncedValue` |
| **Command Palette** | Ctrl+K para buscar y ejecutar acciones | `cmdk` / `kbar` |
| **Drag & Drop** | Reordenar con arrastrar y soltar | `@dnd-kit` |
| **Keyboard Shortcuts** | Navegacion y acciones por teclado | `useHotkeys` |
| **Toast / Snackbar** | Notificaciones transientes no bloqueantes | `sonner` |

---

## 15. FRAMEWORKS GENERATIVE UI 2026

| Framework | Version | Proposito | Integracion |
|-----------|---------|-----------|-------------|
| **A2UI** (Google) | v0.9 | Renderer principal declarativo framework-agnostic | React, Lit, Angular, Flutter |
| **OpenUI** | 1.0+ | Estandar abierto, 3x mas rapido, 67% menos tokens | Cross-platform |
| **Vercel json-render** | 1.0 | Generative UI guardrailed con componentes predefinidos | React, Vue, Svelte, Solid |
| **CopilotKit/OpenGenerativeUI** | 1.0 | Streaming sandboxed widgets, skills-based architecture | React 19 |
| **Geeklego** | 1.0 | AI-native design system, 3-tier tokens, 81 componentes | Tailwind CSS v4 |
| **7onic Design System** | 1.0 | Zero design-code drift, Figma tokens -> CSS/Tailwind/JS | Independente |
| **useVyre** | 1.0 | Semantic tokens + AI context blocks inline | CSS variables |
| **StyleSeed** | 1.0 | Design engine, 74 reglas, 48 componentes, 19 skills AI | Claude Code, Cursor |
| **LLUI** | 1.0 | LLM-first UI framework, compile-time optimized | Vite plugin |
| **Universal Design System** | 1.0 | Deterministic engine, 55 sectores, WCAG 2.2 AA | CLI, React, Vue, Svelte |

---

## 16. INTEGRACION CON SKILLS EXISTENTES

| Skill Existente | Componentes UI Generados |
|----------------|-------------------------|
| **hedgefund** | RiskDashboard, CapitalAllocationChart, InvestmentReport |
| **quant-trading** | TradingDashboard, SignalChart, OrderBookWidget, PnLTimeSeries |
| **risk-execution** | RiskHeatmap, EVTChart, ExposureGauge, PositionSizingTable |
| **healthtech** | PatientDashboard, EHRForm, ClinicalDataTable, WCAG audit |
| **pos-retail** | POSCheckoutUI, InventoryGrid, PaymentFlow, OfflineIndicator |
| **alpha-research** | FactorZooTable, SHAPChart, PortfolioAllocation, BacktestChart |
| **science-doc** | PRISMAFlowDiagram, ForestPlot, CitationNetwork |
| **legal-doc** | ArgumentTree, TimelineChart, CaseComparison |
| **math-doc** | FormulaRenderer, ProofTree, TheoremVisualizer |
| **evolve** | ExperimentDashboard, MetricChart, EvolutionTimeline |

---

## 17. DOOD — DEFINITION OF DONE (Checklist)

### Pre-commit (obligatorio)
- [ ] TypeScript strict mode, sin `any`, sin `@ts-ignore`
- [ ] ESLint + Prettier pasan (incluye `jsx-a11y`)
- [ ] Estados cubiertos: loading, empty, error, success, disabled
- [ ] Mobile-first responsive: 3 viewports probados
- [ ] Sin imports circulares
- [ ] Bundle impact < 50KB por componente nuevo (gzip)
- [ ] `axe-playwright` 0 violaciones en componentes modificados
- [ ] Test unitario de cada nuevo componente (>=90% coverage)
- [ ] Snapshot visual aprobado (Chromatic)
- [ ] DocStrings ES-UTF8: Args/Returns/Raises en toda funcion publica

### Pre-merge (CI gates)
- [ ] Lighthouse scores >=90 en performance, a11y, best-practices, SEO
- [ ] Bundle size aumento < 5% del total
- [ ] E2E tests de todos los user journeys criticos pasan
- [ ] Visual regression: 0 diffs no intencionales
- [ ] Accesibilidad: `pa11y-ci` 0 errores bloqueantes
- [ ] Property-based tests: 0 counterexamples
- [ ] PBT 7 templates ejecutados con Hypothesis

### Pre-deploy (staging)
- [ ] WebPageTest: LCP < 2.5s en 3G simulado
- [ ] INP < 200ms (medido con `web-vitals`)
- [ ] CLS < 0.1
- [ ] Prueba manual con NVDA en flujo critico
- [ ] Error boundary en cada ruta principal
- [ ] Service worker registrado y cacheando assets
- [ ] WCAG 2.2 AA audit: 0 critical violations

---

## 18. REFERENCIAS 2026

### Papers
| Paper | Venue | Aporte |
|-------|-------|--------|
| **Generative UI: LLMs are Effective UI Generators** (arXiv:2604.09577) | arXiv 2026 | LLMs generan UIs con 83% preferencia vs markdown |
| **Bridging Gulfs through Semantic Guidance** | ACM 2026 | Framework jerarquico Product->DesignSystem->Feature->Component |
| **WiserUI-Bench** (300 pares A/B reales) | ACL 2026 | Benchmark de razonamiento visual UX |
| **Generative Interfaces for Language Models** | ACL 2026 Findings | Interfaces generativas > chat, 72% preferencia |
| **Efficient Personalization of Generative UIs** (arXiv:2604.09876) | arXiv 2026 | Bayesian active preference learning, kappa=0.25 |
| **ReFinE: UI Mockup Iteration with Research Findings** | DIS 2026 | Research-to-design loop, AI-powered |
| **The role of LLMs in UI/UX design: A systematic review** | arXiv 2025 | 38 estudios: prompt engineering, human-in-the-loop |

### Frameworks
| Framework | Version | Sitio |
|-----------|---------|-------|
| A2UI (Google) | v0.9 | https://a2ui.org |
| OpenUI | 1.0+ | https://openui.com |
| Vercel json-render | 1.0 | https://github.com/vercel-labs/json-render |
| CopilotKit | 1.0 | https://github.com/CopilotKit/OpenGenerativeUI |
| Geeklego | 1.0 | https://geekyants.com/blog/geeklego |
| StyleSeed | 1.0 | https://github.com/bitjaru/styleseed |
| 7onic Design System | 1.0 | https://github.com/itonys/7onic |
| useVyre | 1.0 | https://github.com/gapra/usevyre |
| Universal Design System | 1.0 | npm: @mkatogui/universal-design-system |
| LLUI | 1.0 | https://github.com/fponticelli/llui |

---

### Responsive Design (fusionado desde responsive-ui skill)

**Principios Mobile-First:**
- Grid CSS: `grid-template-columns: repeat(auto-fit, minmax(min(100%, 300px), 1fr))`
- Flexbox para componentes lineales
- Container Queries: `@container (min-width: 400px) { ... }`
- Tipografia fluida: `clamp()`
- Breakpoints: sm (640px), md (768px), lg (1024px), xl (1280px)

**WCAG 2.2 Checklist:**
- 2.4.11 Focus Not Obscured (AA)
- 2.4.12 Focus Not Obscured (AAA)
- 2.4.13 Focus Appearance (AAA)
- 3.3.7 Accessible Authentication (AA)
- 3.3.8 Accessible Authentication (No Exception)

**Core Web Vitals:**
- LCP ≤2.5s | INP ≤200ms | CLS ≤0.1
