# skill: go-web
**Dominio**: Go Web (Gin, Chi, Svelte frontend)
**Tech Stack**: Go + Svelte + SQLite
**Patrones comunes**:
- Clean Architecture: handler → service → repository
- Svelte 5 con runes (`$state`, `$derived`, `$effect`)
- SQLite con WAL mode para concurrencia
- Chi/Gin router con middleware de logging, CORS, recovery
**Anti-patrones**:
- NO usar `init()` para lógica de negocio
- NO ignorar errores con `_`
- NO SQL sin prepared statements
