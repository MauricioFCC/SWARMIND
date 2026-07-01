# skill: python-web
**Dominio**: Python Web (FastAPI, Django, Flask)
**Tech Stack**: Python + Web Framework
**Patrones comunes**:
- API REST con Pydantic schemas para validación
- SQLAlchemy o asyncpg para DB relacional
- Celery/ARQ para tareas async
- JWT para autenticación
**Anti-patrones**:
- NO exponer SQL raw en endpoints
- NO usar sync I/O en endpoints async
- NO hardcodear secrets en código
**Ejemplos**:
- Endpoint REST: `@router.get("/items/{id}")` con response_model
- DB session: dependency injection con `async def get_db()`
