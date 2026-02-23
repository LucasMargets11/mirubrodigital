# Gestión Comercial - Planes y Límites

## Resumen de Planes

Los planes del servicio **Gestión Comercial** (`gestion`) están diseñados para escalar con el negocio, desde emprendedores individuales hasta empresas multi-sucursal.

---

## Tabla Comparativa de Planes

| Feature / Límite | START | PRO | BUSINESS | ENTERPRISE |
|------------------|-------|-----|----------|------------|
| **Precio** | Gratis / Entry | $X/mes | $Y/mes | Custom |
| **Max Sucursales (base)** | 1 | 1 | 5 | Ilimitado |
| **Add-on Branches** | ❌ No | ✅ Hasta 3 total | ✅ Ilimitadas desde 6ta | N/A |
| **Max Seats (usuarios)** | 1-2 | 5-10 | 20+ | Ilimitado |
| **Max Cajas Registradoras** | N/A (no incluye) | 2-3 | Ilimitadas | Ilimitadas |
| | | | | |
| **Productos** | ✅ | ✅ | ✅ | ✅ |
| **Inventario Básico** | ✅ | ✅ | ✅ | ✅ |
| **Ventas Básicas** | ✅ | ✅ | ✅ | ✅ |
| **Dashboard Básico** | ✅ | ✅ | ✅ | ✅ |
| **Configuración Comercial** | ✅ Básico | ✅ Completo | ✅ Completo | ✅ Completo |
| **RBAC (Roles)** | ✅ Mínimo | ✅ Completo + Auditoría | ✅ Completo + Auditoría | ✅ Custom |
| | | | | |
| **Clientes** | 🔌 Add-on | ✅ | ✅ | ✅ |
| **Caja / Sesiones** | ❌ | ✅ | ✅ | ✅ |
| **Cotizaciones + PDF** | ❌ | ✅ | ✅ | ✅ |
| **Reportes + Export** | ❌ | ✅ | ✅ | ✅ |
| **Inventario Avanzado** | ❌ | ✅ | ✅ | ✅ |
| **Ventas Avanzado** | ❌ | ✅ | ✅ | ✅ |
| **Tesorería / Finanzas** | ❌ | ✅ | ✅ | ✅ |
| | | | | |
| **Facturación Electrónica** | 🔌 Add-on | ✅ Incluido | ✅ Incluido | ✅ Incluido |
| **Multi-sucursal Consolidado** | ❌ | ❌ | ✅ | ✅ |
| **Soporte** | Comunidad | Email | Prioritario | Dedicado |

---

## Descripción de Planes

### 🚀 START
**Para**: Emprendedores individuales, freelancers, pequeños negocios.

**Incluye**:
- Gestión de productos y catálogo
- Inventario básico (entradas, salidas, stock actual)
- Ventas simples (sin caja registradora)
- Dashboard básico con métricas esenciales
- Configuración comercial básica
- RBAC mínimo (owner + 1 staff)

**Add-ons disponibles**:
- **Gestión de Clientes** ($A/mes): CRM básico, historial de compras
- **Facturación Electrónica** ($Z/mes): Emisión de facturas válidas (AFIP, SAT)

**NO incluido por defecto**:
- Caja / Sesiones de caja
- Cotizaciones
- Reportes avanzados / Exportación
- Tesorería / Finanzas

**Límites**:
- **Sucursales**: 1 fija (sin add-on de branches)
- **Usuarios**: 1-2 seats
- **Cajas**: N/A

---

### ⭐ PRO
**Para**: Negocios establecidos con operación completa.

**Incluye** (todo START +):
- **Gestión de clientes** (CRM básico)
- **Facturación Electrónica INCLUIDA** (AFIP, SAT, etc.)
- Caja / Sesiones de caja registradora
- Cotizaciones con generación de PDF
- Reportes avanzados + Exportación (Excel/CSV)
- RBAC completo + Auditoría de cambios
- Inventario avanzado (traspasos, ajustes, lotes)
- Ventas avanzado (descuentos, notas, tipos de pago)
- **Tesorería / Finanzas** (cuentas, movimientos, conciliaciones)

**Add-ons disponibles**:
- **Sucursales extra**: hasta 3 sucursales totales

**NO incluido por defecto**:
- Multi-sucursal consolidado (limitado a operación independiente por sucursal)

**Límites**:
- **Sucursales**: 1 base, con add-on hasta 3 máximo
- **Usuarios**: 5-10 seats
- **Cajas**: 2-3 registradoras

---

### 💼 BUSINESS
**Para**: Empresas multi-sucursal con operaciones consolidadas.

**Incluye** (todo PRO +):
- **Multi-sucursal consolidado**: dashboards, reportes e inventario unificado
- Transferencias entre sucursales
- Reportes corporativos consolidados
- Gestión centralizada de catálogo

**Add-ons disponibles**:
- **Sucursales extra**: ilimitadas desde la 6ta en adelante

**Límites**:
- **Sucursales**: 5 incluidas, ilimitadas con add-on desde la 6ta
- **Usuarios**: 20+ seats
- **Cajas**: Ilimitadas

---

### 🏢 ENTERPRISE
**Para**: Grandes empresas con necesidades personalizadas.

**Incluye**:
- Todo BUSINESS
- Personalización de features
- Soporte dedicado
- SLA garantizado
- Configuración custom

**Límites**: Negociables según contrato.

---

## Add-ons

### � Gestión de Clientes (customers_module)
- **Disponible para**: START
- **Incluido en**: PRO, BUSINESS, ENTERPRISE
- **Descripción**: CRM básico con historial de compras, datos fiscales y contacto.
- **Precio**: $A/mes

### 🔌 Facturación Electrónica (invoices_module)
- **Disponible para**: START
- **Incluido en**: PRO, BUSINESS, ENTERPRISE
- **Descripción**: Integración con AFIP (Argentina), SAT (México), u otros entes fiscales para emisión de facturas electrónicas válidas.
- **Precio**: $Z/mes

### 🏢 Sucursales Extra (extra_branch)
- **Disponible para**: PRO (hasta 3 total), BUSINESS (desde la 6ta)
- **Descripción**: Habilita una sucursal adicional.
- **Límite PRO**: Solo hasta 2 add-ons (total 3 branches)
- **Límite BUSINESS**: Ilimitado desde la 6ta
- **Precio**: $W/mes por sucursal

### � Asientos Extra (extra_seat)
- **Disponible para**: Todos los planes
- **Descripción**: Agrega un usuario adicional más allá del límite del plan.
- **Precio**: $V/mes por seat

---

## Migración desde Planes Legacy

Los planes anteriores (`STARTER`, `PRO`, `PLUS`) se mapean de la siguiente forma:

| Plan Legacy | Plan Nuevo | Notas |
|-------------|------------|-------|
| `STARTER` | `START` | Mismo nivel de funcionalidad |
| `PRO` | `PRO` | Ahora incluye Treasury/Finance |
| `PLUS` | `BUSINESS` | Mayor énfasis en multi-sucursal |
| `MENU_QR` | — | Se mantiene separado como servicio independiente |

---

## FAQ

**¿Por qué Facturación ahora está incluida en PRO?**  
A partir de esta actualización, la facturación electrónica se incluye en PRO y superiores, reconociendo que es una necesidad básica para negocios establecidos. Para el plan START, está disponible como add-on.

**¿Puedo tener más de 3 sucursales en PRO?**  
No. Para más de 3 sucursales debes upgraded a BUSINESS, que incluye además reportes consolidados desde la 1ra sucursal.

**¿Qué significa "Multi-sucursal consolidado"?**  
En BUSINESS, puedes ver dashboards, reportes e inventario unificado de todas tus sucursales. En PRO, cada sucursal opera de forma independiente.

**¿Cómo se calculan los límites efectivos si tengo add-ons?**  
Los límites se suman: `effective_max_branches = plan_base_branches + addon_branches`, respetando el máximo permitido por plan (`max_addon_branches_allowed`).

---

**Última actualización**: Febrero 2026  
**Versión**: 1.0
