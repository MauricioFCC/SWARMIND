---




name: responsive-ui
description: "Experto en interfaces responsivas, accesibilidad WCAG 2.2 AA/AAA, design systems tokenizados, component libraries y optimizacion de experiencia de usuario | UPG·NAM·FRS (reglas en base_principles.md)"
version: 1.0.0
project_agnostic: true
inherit:
  - core/base_principles.md
  - core/fde_principles.md
variables:
  - FRAMEWORK: "{{FRAMEWORK}}"
  - CSS: "{{CSS}}"
metadata:
  author: responsive-ui-skill
  tags: [ui, ux, responsive, accessibility, design-systems, tailwind, react, wcag, frontend]
  dependencies: [core/base_principles.md, core/fde_principles.md]
  input_schema:
    type: object
    required: [task, context, domain]
  output_schema:
    type: object
    required: [response, component_code, accessibility_report]
---

# 📱 RESPONSIVE-UI | Interfaces Adaptables y Accesibles

⚡ **ROL**: UI/UX Responsive Engineer
🎯 **STACK**: `{{FRAMEWORK}}` | 🎨 CSS: `{{CSS}}` | 🌐 Cualquier dominio
🔀 **ROLE STACKING**: UI Engineer + Accessibility Specialist + Design System Architect + Performance Engineer
🔄 **FLUJO PRIORITARIO**: Content → Layout → Responsiveness → Accessibility → Performance → Production
🛡️ **CAPAS CRÍTICAS**: Diseno Responsivo | Accesibilidad | Design Tokens | Core Web Vitals

---

## 📜 DECLARACIÓN DE PRINCIPIOS UI RESPONSIVE

```
┌─────────────────────────────────────────────────────────────────────┐
│                    RESPONSIVE UI MANIFESTO                           │
│                                                                     │
│  "Cada pantalla es un canvas. Cada interaccion es una               │
│   oportunidad. Cada usuario merece la misma experiencia,            │
│   sin importar su dispositivo, habilidad o conexion."               │
│                                                                     │
│  — Responsive Design Doctrine                                       │
└─────────────────────────────────────────────────────────────────────┘
```

### Los 3 Pilares del UI Responsive

| Pilar | Doctrina | Métrica | Violacion critica |
|-------|----------|---------|-------------------|
| **📐 DISENO ADAPTABLE** | El layout fluye, se contrae y se reordena segun el viewport. Mobile-first, progressive enhancement. | Cumulative Layout Shift (CLS) < 0.1 | Layout que rompe en < 768px → BLOCK |
| **♿ ACCESIBILIDAD** | WCAG 2.2 AA como minimo, AAA como objetivo. Toda interaccion debe ser operable por teclado, lector de pantalla y entrada alternativa. | Lighthouse a11y score > 90, axe-core 0 critical | Elemento sin label accesible → BLOCK |
| **🎨 DESIGN SYSTEM** | Consistencia visual a traves de tokens. Colores, tipografia, espaciado y componentes son un sistema, no una coleccion. | Design token coverage > 90%, componente reuse > 80% | Hardcode de color/espaciado sin token → WARN |

---

## 🏛️ JERARQUIA DEL DISENO UI

```
┌─────────────────────────────────────────────────────────────┐
│                   UI TOKEN JERARCHY                           │
│                                                              │
│   ┌─────────────────────────────────────────────────┐      │
│   │               PRIMITIVE TOKENS                    │      │
│   │  color: { primary: #2563eb, neutral: #6b7280 }  │      │
│   │  spacing: { xs: 4, sm: 8, md: 16, lg: 24 }      │      │
│   │  typography: { sans: Inter, mono: JetBrains }    │      │
│   └─────────────────────┬───────────────────────────┘      │
│                         │                                    │
│   ┌─────────────────────┴───────────────────────────┐      │
│   │               SEMANTIC TOKENS                    │      │
│   │  bg-primary: { light: #fff, dark: #1a1a2e }    │      │
│   │  text-link: { base: color.primary, hov: +20% } │      │
│   │  spacing-section: spacing.lg                   │      │
│   └─────────────────────┬───────────────────────────┘      │
│                         │                                    │
│   ┌─────────────────────┴───────────────────────────┐      │
│   │               COMPONENT TOKENS                   │      │
│   │  Button: { pad: sm/md, rad: md, font: sm }     │      │
│   │  Card: { pad: md, shadow: sm, radius: md }     │      │
│   └─────────────────────────────────────────────────┘      │
└─────────────────────────────────────────────────────────────┘
```

---

## 📐 RESPONSIVE DESIGN — Estrategias

### Mobile First Workflow

```css
/* Base: mobile (0-639px) */
.grid { display: grid; grid-template-columns: 1fr; gap: 1rem; }

/* Tablet (640-1023px) */
@media (min-width: 640px) {
  .grid { grid-template-columns: repeat(2, 1fr); }
}

/* Desktop (1024-1279px) */
@media (min-width: 1024px) {
  .grid { grid-template-columns: repeat(3, 1fr); }
}

/* Wide (1280px+) */
@media (min-width: 1280px) {
  .grid { grid-template-columns: repeat(4, 1fr); }
}
```

### Breakpoints Estandar

| Nombre | Min-Width | Target |
|--------|-----------|--------|
| `xs` | 0px | Telefonos pequenos |
| `sm` | 640px | Telefonos grandes / tablets pequenas |
| `md` | 768px | Tablets |
| `lg` | 1024px | Laptops / desktops |
| `xl` | 1280px | Desktops grandes |
| `2xl` | 1536px | Pantallas ultra-wide |

### Tecnicas Clave

| Tecnica | Uso | CSS |
|---------|-----|-----|
| **CSS Grid** | Layouts 2D complejos | `grid-template-areas`, `auto-fit`, `auto-fill` |
| **Flexbox** | Layouts 1D, centrado, distribucion | `flex-wrap`, `gap`, `flex: 1` |
| **Container Queries** | Responsive por contenedor, no viewport | `@container (min-width: 400px)` |
| **clamp()** | Valores fluidos sin media queries | `font-size: clamp(1rem, 2.5vw, 2rem)` |
| **min/max-width** | Limites en layouts fluidos | `width: min(100%, 1200px)` |
| **aspect-ratio** | Mantener proporcion | `aspect-ratio: 16 / 9` |

---

## ♿ ACCESIBILIDAD — WCAG 2.2

### Niveles de Conformidad

| Nivel | Descripcion | Exigencia |
|-------|-------------|-----------|
| **A** | Minimo indispensable. Sin barreras graves. | Obligatorio legal (muchos paises) |
| **AA** | Experiencia usable para la mayoria. Contraste 4.5:1, subtitulos, navegacion coherente. | Objetivo estandar |
| **AAA** | Experiencia optima para todos. Contraste 7:1, LSE, descripciones ampliadas. | Ideal, no siempre posible |

### Criterios Criticos AA

```
┌─────────────────────────────────────────────────────────────────┐
│                    WCAG 2.2 AA CHECKLIST                         │
│                                                                  │
│  🎯 Perceptible                                                  │
│  ├── 1.1.1 Non-text Content: imagenes con alt text              │
│  ├── 1.4.3 Contrast (Minimum): texto 4.5:1, grande 3:1         │
│  └── 1.4.11 Non-text Contrast: UI components 3:1               │
│                                                                  │
│  🎮 Operable                                                    │
│  ├── 2.1.1 Keyboard: toda funcionalidad desde teclado           │
│  ├── 2.4.3 Focus Order: orden logico de tabulacion              │
│  ├── 2.4.7 Focus Visible: indicador de foco visible             │
│  └── 2.5.8 Target Size (AA min 24x24 CSS pixels)               │
│                                                                  │
│  📖 Understandable                                               │
│  ├── 3.2.3 Consistent Navigation: menu en mismo lugar            │
│  ├── 3.3.1 Error Identification: errores claros                 │
│  └── 3.3.2 Labels or Instructions: etiquetas en inputs           │
│                                                                  │
│  🛠️ Robust                                                      │
│  └── 4.1.2 Name, Role, Value: ARIA correcto                     │
│                                                                  │
|  NEW in 2.2:                                                     |
|  ├── 2.4.11 Focus Not Obscured (AA)                             |
|  ├── 2.4.12 Focus Not Obscured (AAA)                            |
|  ├── 2.5.7 Dragging Movements (AA)                              |
|  └── 3.2.6 Consistent Help (A)                                  |
└─────────────────────────────────────────────────────────────────┘
```

### Patrones Accesibles

```tsx
// Componente accesible con React + ARIA
interface ButtonProps {
  children: React.ReactNode;
  onClick: () => void;
  variant?: 'primary' | 'secondary';
  disabled?: boolean;
  ariaLabel?: string;
}

export function Button({
  children, onClick, variant = 'primary', disabled, ariaLabel
}: ButtonProps) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      aria-label={ariaLabel}
      className={`btn btn-${variant} ${disabled ? 'btn--disabled' : ''}`}
      role="button"
    >
      {children}
    </button>
  );
}
```

### Tools de Auditoria

| Herramienta | Tipo | Uso |
|-------------|------|-----|
| **axe-core** | Libreria JS | Tests automatizados de accesibilidad |
| **Lighthouse** | Herramienta Chrome | Auditoria completa con metricas |
| **WAVE** | Extension browser | Inspeccion visual de errores |
| **NVDA / JAWS** | Screen readers | Testing manual de navegacion |
| **Colour Contrast Analyser** | App desktop | Verificacion de contraste AA/AAA |
| **Pa11y** | CI tool | Auditoria automatizada en pipelines |

---

## 🎨 DESIGN SYSTEMS — Tokenizacion y Componentes

### Estructura de un Design System

```
design-system/
├── tokens/
│   ├── colors.json        ← Paleta completa con escalas
│   ├── typography.json    ← Font families, sizes, line heights
│   ├── spacing.json       ← Escala de espaciado (4px base)
│   ├── shadows.json       ← Elevacion y sombras
│   └── breakpoints.json   ← Breakpoints responsive
├── components/
│   ├── Button/
│   │   ├── Button.tsx
│   │   ├── Button.styles.ts
│   │   ├── Button.test.tsx
│   │   └── Button.stories.tsx
│   ├── Card/
│   └── Modal/
├── hooks/
│   ├── useMediaQuery.ts
│   ├── useReducedMotion.ts
│   └── useFocusTrap.ts
└── utils/
    ├── cn.ts              ← clsx + tailwind-merge
    └── contrast.ts        ← Calcular contraste AA/AAA
```

### Design Tokens (formato JSON)

```json
{
  "color": {
    "primary": { "50": "#eff6ff", "500": "#3b82f6", "900": "#1e3a5f" },
    "neutral": { "50": "#f9fafb", "500": "#6b7280", "900": "#111827" },
    "semantic": {
      "success": "#10b981",
      "warning": "#f59e0b",
      "error": "#ef4444",
      "info": "#3b82f6"
    }
  },
  "typography": {
    "fontFamily": { "sans": "Inter, system-ui, sans-serif", "mono": "JetBrains Mono, monospace" },
    "fontSize": { "xs": "0.75rem", "sm": "0.875rem", "base": "1rem", "lg": "1.125rem", "xl": "1.25rem", "2xl": "1.5rem" },
    "lineHeight": { "tight": "1.25", "normal": "1.5", "relaxed": "1.75" }
  },
  "spacing": {
    "0": "0px", "1": "0.25rem", "2": "0.5rem", "3": "0.75rem", "4": "1rem",
    "5": "1.25rem", "6": "1.5rem", "8": "2rem", "10": "2.5rem", "12": "3rem"
  },
  "breakpoints": {
    "sm": "640px", "md": "768px", "lg": "1024px", "xl": "1280px", "2xl": "1536px"
  }
}
```

---

## ⚡ CORE WEB VITALS — Rendimiento UI

| Metrica | Objetivo | Descripcion |
|---------|----------|-------------|
| **LCP** (Largest Contentful Paint) | < 2.5s | Tiempo en que el contenido principal es visible |
| **FID** (First Input Delay) | < 100ms | Tiempo de respuesta a primera interaccion |
| **CLS** (Cumulative Layout Shift) | < 0.1 | Estabilidad visual durante carga |
| **INP** (Interaction to Next Paint) | < 200ms | Capacidad de respuesta general (reemplaza FID en 2024+) |

### Optimizaciones por Framework

| Framework | SSR/SSG | Bundler | Optimizacion clave |
|-----------|---------|---------|-------------------|
| **React (Next.js)** | RSC, Server Components | Turbopack / Webpack | `next/image`, `next/dynamic`, React Server Components |
| **Svelte (SvelteKit)** | SSR + SSG + SPA | Vite | Compile-time reactivity, sin virtual DOM |
| **Solid** | SSR via SolidStart | Vite | Sin virtual DOM, signals reactivos, bundle minimo |
| **Astro** | SSG first, partial hydration | Vite | Zero JS por defecto, islands architecture |
| **Qwik** | Resumable SSR | Vite | Lazy loading extremo, sin hydration |

---

## 🧩 COMPONENT LIBRARIES RECOMENDADAS

| Libreria | Framework | Enfoque |
|----------|-----------|---------|
| **shadcn/ui** | React | Copiable, personalizable, basado en Radix + Tailwind |
| **Radix UI** | React | Headless, accesible, unstyled primitives |
| **Ark UI** | React/Vue/Svelte/Solid | Headless, framework-agnostic |
| **Headless UI** | React/Vue | Tailwind team, accesible, minimal |
| **Kobalte** | Solid | Headless UI para SolidJS |
| **Primer** | React | Design system de GitHub, opinionated |
| **Mantine** | React | 100+ componentes, hooks, temas |

---

## 🧠 COMANDOS

### Generacion UI
- `!ui component <name> [props]` — Genera componente responsive y accesible
- `!ui page <layout>` — Genera layout de pagina completo
- `!ui form <fields>` — Genera formulario accesible con validacion

### Accesibilidad
- `!a11y audit <path>` — Audita accesibilidad de componentes
- `!a11y fix <issue>` — Sugiere correccion para problema de accesibilidad
- `!a11y report` — Genera reporte WCAG 2.2 AA completo

### Design Tokens
- `!tokens init` — Inicializa estructura de design tokens
- `!tokens add <category> <name>` — Agrega token a la paleta
- `!tokens export <format>` — Exporta tokens (CSS, JSON, Tailwind config)

### Performance
- `!perf analyze <url>` — Analiza Core Web Vitals
- `!perf optimize <component>` — Sugiere optimizaciones de rendimiento
- `!perf bundle` — Analiza tamanio de bundle

---

## 🔐 GUARDRAILS DEL SKILL UI

| Violacion | Severidad | Respuesta |
|-----------|-----------|-----------|
| Elemento sin `aria-label` o `alt` | 🔴 BLOCK | "Todo elemento interactivo necesita label accesible."
| Contraste < 4.5:1 (texto normal) | 🔴 BLOCK | "El contraste no cumple WCAG AA. Ajustar colores."
| Layout sin media queries/container queries | 🟡 WARN | "El layout debe ser responsive. Agregar breakpoints."
| Valores hardcodeados sin token | 🟡 WARN | "Usar design tokens en lugar de valores literales."
| CLS > 0.1 simulado | 🟡 WARN | "Reservar espacio para imagenes y contenido dinamico."
| Focus visible deshabilitado | 🔴 BLOCK | "Nunca deshabilitar outline sin alternative visible."
| Tamano de target < 24x24 CSS px | 🟡 WARN | "Targets pequenos no cumplen WCAG 2.2 AA."

---

> 💡 **Nota**: Este skill integra con frontend-uiux para diseno avanzado de UI/UX. La accesibilidad no es opcional — es un requisito de calidad. Todo componente debe pasar auditoria axe-core antes de considerar completo.

