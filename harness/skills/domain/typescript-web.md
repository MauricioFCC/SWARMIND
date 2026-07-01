# skill: typescript-web
**Dominio**: TypeScript/Node Web
**Tech Stack**: TypeScript + Node + React/Vue
**Patrones comunes**:
- API REST con Express/Fastify + zod para validación
- Prisma o Drizzle ORM para DB relacional
- React/Vue + TanStack Query para data fetching
- JWT o NextAuth para autenticación
**Anti-patrones**:
- NO usar `any` (preferir `unknown` + narrowing)
- NO mezclar async callbacks con promesas
- NO hardcodear secrets en código
**Ejemplos**:
- Endpoint REST: `app.get("/api/items/:id", async (req, res) => {...})`
- Zod schema: `z.object({ name: z.string().min(1) })`
