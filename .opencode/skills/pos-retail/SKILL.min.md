---
name: pos-retail
domain: pos-retail
description: "Skill contextual para el dominio Pos-Retail — punto de venta, retail, e-commerce, inventario, facturación, pagos y logística"
version: 1.0.0
project_agnostic: true
---

# Pos-Retail Contextual Skill
Skill contextual para el dominio **Pos-Retail** (punto de venta, retail, e-commerce, inventario, facturación).
## Activación
Se activa cuando el `router` detecta keywords del dominio retail/POS.
## Keywords
pos, point of sale, retail, e-commerce, shop, store, inventory, stock, warehouse, supply chain, invoice, receipt, billing, payment, checkout, cart, loyalty, promotion, discount, punto de venta, tienda, factura, inventario, pago, caja
## Dominios funcionales
- **POS Core**: venta (items, totales, impuestos, descuentos), pago multi-medio (split), devolución con trazabilidad al ticket, arqueo de caja.
- **Inventario**: stock en tiempo real por Sucursal/UUID, movimientos (entradas/salidas/ajustes/transferencias), valoración (promedio, FIFO, LIFO), pedidos (OC, recepción, dropshipping).
- **Clientes**: historial de compras, loyalty (puntos/niveles), crédito (límite, estado de cuenta, cobranza).
## Arquitectura
Microservicios (POS, Inventory, Customer, Billing); Event Bus RabbitMQ/Kafka (venta → descuento stock); Redis (catálogo/precios); PostgreSQL transaccional + Elasticsearch búsqueda; **offline-first** con sincronización al reconectar.
## Patrones
Saga (venta → stock → pago), Outbox (eventos sin pérdida), CQRS (comandos vs reportes), Strategy (impuestos IVA/ISR/regional).
## Estados
```
Venta: PENDING → COMPLETED → REFUNDED | PENDING → CANCELLED
Pago: PENDING → COMPLETED → REFUNDED | PENDING → FAILED → RETRY → COMPLETED
Pedido: DRAFT → APPROVED → PICKING → SHIPPED → DELIVERED | DRAFT → CANCELLED
```
## NFR y Seguridad
Latencia cobro < 200ms; disponibilidad 99.9% horario comercial; offline hasta 4h; concurrencia multi-sucursal en hora pico; auditoría financiera total. Pagos PCI-DSS (tokenización); 2FA en devoluciones/ajustes de stock; roles granulares (cajero, supervisor, admin, gerente).
## Output esperado
Código transaccional offline-first, modelo de datos (catálogo/stock/clientes/ventas), API REST versionada (/api/v1/pos/sale), tests de concurrencia y consistencia de stock, documentación de pagos/devoluciones.
