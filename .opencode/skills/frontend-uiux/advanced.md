# Frontend UI/UX — advanced.md (bajo demanda)

Carga este archivo **solo bajo demanda**: accesibilidad detallada, rendimiento,
personalización Bayesian, validación UX, testing visual + PBT, estado global,
renderizado, patrones UX avanzados, frameworks 2026, integración con skills
y referencias. Índice esencial en `SKILL.md`.

---

## 1. ACCESIBILIDAD — WCAG 2.2 AA/AAA (detalle)

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

## 2. RENDIMIENTO — Core Web Vitals (detalle)

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

## 3. PERSONALIZACION — Sample-Efficient Preference Learning

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

## 4. VALIDACION UX — WiserUI-Bench + ReFinE

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

## 5. TESTING VISUAL Y DE COMPONENTES

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

## 6. MANEJO DE ESTADO GLOBAL

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

## 7. RENDERIZADO — SSR / SSG / ISR / RSC

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

## 8. PATRONES DE UX AVANZADOS

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

## 9. FRAMEWORKS GENERATIVE UI 2026

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

## 10. INTEGRACION CON SKILLS EXISTENTES

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

## 11. REFERENCIAS 2026

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