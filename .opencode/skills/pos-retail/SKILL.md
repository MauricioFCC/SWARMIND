# Pos-Retail Contextual Skill

Skill contextual para el dominio **Pos-Retail** (punto de venta, retail, e-commerce, inventario, facturación).

## Activación
Se activa automáticamente cuando el `router` detecta keywords del dominio retail/POS.

## Keywords de dominio
- `pos`, `point of sale`, `retail`, `e-commerce`, `ecommerce`, `shop`, `store`
- `inventory`, `stock`, `warehouse`, `supply chain`, `logistics`
- `invoice`, `receipt`, `billing`, `payment`, `checkout`, `cart`
- `customer`, `loyalty`, `promotion`, `discount`, `coupon`
- `punto de venta`, `tienda`, `comercio`, `factura`, `inventario`
- `pago`, `tarjeta`, `efectivo`, `terminal`, `caja`

## Reglas contextuales

### 1. Dominios Funcionales

#### POS Core
- **Venta**: Captura de items, cálculo de totales, impuestos, descuentos.
- **Pago**: Múltiples medios (efectivo, tarjeta, bono, mixto), split payment.
- **Devolución**: Procesar devoluciones con trazabilidad al ticket original.
- **Arqueo**: Cuadre de caja al cierre de turno.

#### Inventario
- **Stock**: Control de stock en tiempo real por Sucursal/UUID.
- **Movimientos**: Entradas, salidas, ajustes, transferencias entre sucursales.
- **Valoración**: Costo promedio ponderado, FIFO, LIFO.
- **Pedidos**: Orden de compra, recepción, dropshipping.

#### Clientes
- **Perfil**: Historial de compras, preferencias, crédito.
- **Loyalty**: Puntos, niveles, beneficios.
- **Crédito**: Límite de crédito, estado de cuenta, cobranza.

### 2. Arquitectura Recomendada
- **Backend**: Microservicios (POS, Inventory, Customer, Billing).
- **Event Bus**: RabbitMQ/Kafka para eventos en tiempo real (venta → descuento stock).
- **Caché**: Redis para catálogo de productos y precios.
- **Base de datos**: PostgreSQL (transaccional) + Elasticsearch (búsqueda).
- **Offline-first**: POS debe funcionar sin conexión y sincronizar al reconectar.

### 3. Patrones de Diseño
- **Saga Pattern**: Para flujos distribuidos (venta → descuento stock → registro pago).
- **Outbox Pattern**: Para eventos transaccionales sin pérdida.
- **CQRS**: Separar comandos (venta) de consultas (reportes).
- **Strategy Pattern**: Para cálculos de impuestos (IVA, ISR, regional).

### 4. Manejo de Estados
```
Venta: PENDING → COMPLETED → REFUNDED
       PENDING → CANCELLED

Pago: PENDING → COMPLETED → REFUNDED
      PENDING → FAILED → RETRY → COMPLETED

Pedido: DRAFT → APPROVED → PICKING → SHIPPED → DELIVERED
        DRAFT → CANCELLED
```

### 5. Requisitos No Funcionales
- **Latencia POS**: < 200ms para cobro en caja.
- **Disponibilidad**: 99.9% en horario comercial.
- **Offline**: Capacidad de operar hasta 4h sin conexión.
- **Concurrencia**: Soportar N sucursales en hora pico sin degradación.
- **Audit**: Toda transacción financiera auditada.

### 6. Seguridad
- Pagos: PCI-DSS compliant (tokenización de tarjetas).
- Autenticación: 2FA para operaciones sensibles (devoluciones, ajustes de stock).
- Roles: cajero, supervisor, admin, gerente — cada uno con permisos granulares.

## Output esperado
- Código transaccional con manejo offline.
- Modelo de datos para catálogo, stock, clientes, ventas.
- API RESTful con versionado (ej. /api/v1/pos/sale).
- Tests de concurrencia y consistencia de stock.
- Documentación de flujos de pago y devolución.
