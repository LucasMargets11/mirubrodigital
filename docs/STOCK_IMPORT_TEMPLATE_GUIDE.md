# Guía de Importación de Stock - Plantilla Excel

## 📋 Resumen

Sistema de importación masiva de productos e inventario mediante archivos Excel (.xlsx), diseñado para sincronizar catálogos desde sistemas externos o inicializar inventarios.

**Ubicación**: `/app/gestion/stock/importar`  
**Plantilla**: `/plantillas/importar-stock.xlsx`  
**Formato**: Excel (.xlsx)  
**Límites**: 10 MB, hasta 2000 filas  

---

## 📊 Especificación de Campos

### Campos de la Plantilla

| Campo | Obligatorio | Tipo | Validación | Descripción | Ejemplo |
|-------|------------|------|------------|-------------|---------|
| **Nombre** | ✅ SÍ | Texto | 2-200 caracteres | Nombre descriptivo del producto | `Café en grano Colombia 500g` |
| **SKU** | ❌ No | Texto | Alfanumérico único | Código identificador del producto | `CF-COL-500` |
| **Precio** | ❌ No | Número | ≥ 0 | Precio de venta (sin símbolos) | `3500` |
| **Costo** | ❌ No | Número | ≥ 0 | Costo de adquisición (sin símbolos) | `1800` |
| **Stock** | ❌ No | Número | ≥ 0 | Cantidad actual en inventario | `25` |
| **Stock mínimo** | ❌ No | Número | ≥ 0 | Nivel de alerta para reposición | `5` |
| **Código de barras** | ❌ No | Texto | Alfanumérico | Código EAN, UPC, EAN-13, etc. | `7790000000012` |
| **Nota** | ❌ No | Texto | Libre | Observaciones o comentarios | `Precio minorista sugerido` |

### Aliases de Columnas Aceptados

El sistema reconoce múltiples nombres de columna para facilitar importaciones desde diferentes fuentes:

```
Nombre → "Nombre", "Producto"
SKU → "SKU", "Codigo", "Código"
Código de barras → "Código de barras", "Codigo de barras", "Barcode"
Precio → "Precio", "Precio venta"
Costo → "Costo"
Stock → "Stock"
Stock mínimo → "Stock mínimo", "Stock minimo", "stock_min"
Nota → "Nota", "Notas"
```

---

## 🔄 Comportamiento de la Importación

### 1. Detección de Productos

El sistema identifica productos existentes mediante:

1. **Coincidencia por SKU** (si está presente y no está vacío)
2. **Coincidencia por nombre exacto** (case-insensitive, trimmed)

### 2. Acciones Automáticas

#### CREAR Producto Nuevo
**Cuándo**: No existe coincidencia por SKU ni por nombre.

**Qué se crea**:
- Registro de producto con todos los campos proporcionados
- Registro de stock inicial (si se especificó cantidad)
- Movimiento de stock tipo "ADJUST" con nota "Importación de stock (.xlsx)"

**Ejemplo**:
```
Nombre: "Yerba mate orgánica 1kg"
SKU: "YM-ORG-1K"
Stock: 50
→ Resultado: Producto creado + Stock inicial 50 unidades
```

#### ACTUALIZAR Producto Existente
**Cuándo**: Existe coincidencia por SKU o nombre.

**Qué se actualiza**:
- Precio (si se proporciona y es diferente)
- Costo (si se proporciona y es diferente)
- Stock mínimo (si se proporciona y es diferente)
- Código de barras (si se proporciona y es diferente)

**NO se actualiza**: 
- Nombre (se mantiene el original)
- Stock (se gestiona por separado, ver siguiente punto)

**Ejemplo**:
```
SKU existente: "CF-001"
Precio nuevo: 4000 (antes 3500)
Costo nuevo: 2000 (antes 1800)
→ Resultado: Producto actualizado con nuevos valores
```

#### AJUSTAR Stock
**Cuándo**: 
- El producto existe (o se acaba de crear)
- Se proporciona un valor en la columna Stock
- El valor es diferente al stock actual

**Qué se crea**:
- Movimiento de inventario tipo "ADJUST"
- La cantidad del movimiento es la diferencia: `nuevo_stock - stock_actual`
- Nota automática: "Importación de stock (.xlsx)"

**Ejemplo**:
```
Producto: "Café en grano"
Stock actual: 25
Stock en Excel: 40
→ Movimiento ADJUST: +15 unidades
→ Stock final: 40 unidades
```

#### OMITIR (Skip)
**Cuándo**:
- El producto existe
- No se proporciona valor de Stock, o es igual al actual
- No hay cambios en otros campos

**Resultado**: No se genera ningún movimiento de stock.

---

## 📝 Estructura del Archivo Excel

### Formato Requerido

```xlsx
Hoja 1: "Productos" (nombre libre)
┌───────────────────────────────────────────────────────────────────────────────────┐
│ Fila 1: ENCABEZADOS                                                               │
│ ├─ Nombre | SKU | Precio | Costo | Stock | Stock mínimo | Código de barras | Nota│
├───────────────────────────────────────────────────────────────────────────────────┤
│ Fila 2+: DATOS                                                                    │
│ ├─ Café... | CF-001 | 3500 | 1800 | 25 | 5 | 7790... | ...                      │
│ ├─ Filtros | FIL-004| 2500 | 900  | 40 | 10|         | ...                      │
│ └─ ...                                                                            │
└───────────────────────────────────────────────────────────────────────────────────┘

Hoja 2: "Instrucciones" (opcional, para referencia del usuario)
```

### Reglas de Formato

1. **Primera fila = Encabezados**
   - Debe contener al menos la columna "Nombre"
   - Acepta aliases (ver lista arriba)
   - No distingue mayúsculas/minúsculas
   - Ignora espacios adicionales

2. **Datos desde fila 2**
   - Filas vacías se ignoran automáticamente
   - Máximo 2000 filas con datos
   - Celdas vacías = "no proporcionar ese campo"

3. **Tipos de datos**
   - Texto: sin restricciones especiales
   - Números: sin símbolos ($, %, comas de miles)
   - Decimales: usar punto o coma según locale (se normalizan)

4. **Validaciones automáticas**
   - Números negativos → Error
   - Nombres duplicados en el archivo → Advertencia
   - SKU duplicados en el archivo → Error
   - Campos faltantes obligatorios → Error

---

## 🎯 Flujo de Uso

### Paso 1: Descargar Plantilla
```
/app/gestion/stock/importar
→ "Descargar plantilla Excel"
→ Se descarga: importar-stock-plantilla.xlsx
```

La plantilla incluye:
- ✅ Encabezados correctos
- ✅ 4 filas de ejemplo con casos de uso
- ✅ Hoja "Instrucciones" con documentación completa
- ✅ Anchos de columna optimizados

### Paso 2: Completar Datos
1. Abrir en Excel, Google Sheets o LibreOffice
2. **NO modificar** los encabezados de la fila 1
3. Llenar datos desde la fila 2
4. Eliminar filas de ejemplo si no las necesitas
5. Guardar como .xlsx

### Paso 3: Subir Archivo
```
/app/gestion/stock/importar
→ "Subir Excel" (máx. 10 MB)
→ Procesamiento automático
→ Vista previa generada
```

### Paso 4: Revisar Vista Previa
La vista previa muestra hasta 200 filas con:
- **Línea**: Número de fila en Excel
- **Producto**: Nombre del producto
- **SKU**: Código (si existe)
- **Acción**: "Crear" o "Actualizar"
- **Stock**: "Ajustar stock" o "Sin cambios"
- **Estado**: ✅ OK | ⚠️ Warning | ❌ Error
- **Mensajes**: Detalles de validación

**Estados posibles**:
- ✅ **OK**: Se procesará correctamente
- ⚠️ **Warning**: Se procesará pero con advertencias (ej: SKU faltante)
- ❌ **Error**: NO se procesará, debe corregirse

### Paso 5: Aplicar Importación
```
→ "Aplicar importación"
→ Procesamiento en background
→ Notificación al completar
```

**Resultado**:
- Productos creados/actualizados
- Movimientos de stock tipo ADJUST generados
- Registros de auditoría completos

---

## 📊 Ejemplos de Casos de Uso

### Ejemplo 1: Crear Producto Completo
```xlsx
Nombre                    | SKU       | Precio | Costo | Stock | Stock mínimo | Código de barras | Nota
Café en grano Colombia    | CF-COL-500| 3500   | 1800  | 25    | 5            | 7790000000012    | Precio minorista
```
**Resultado**:
- ✅ Producto creado
- ✅ Stock inicial: 25 unidades
- ✅ Movimiento ADJUST: +25

### Ejemplo 2: Crear Producto Básico
```xlsx
Nombre                    | SKU | Precio | Costo | Stock | Stock mínimo | Código de barras | Nota
Azúcar blanca 1kg         |     | 1200   |       | 100   | 20           |                  |
```
**Resultado**:
- ✅ Producto creado
- ⚠️ SKU generado automáticamente
- ✅ Stock inicial: 100 unidades
- ℹ️ Costo=0 (no proporcionado)

### Ejemplo 3: Actualizar Precio y Ajustar Stock
```xlsx
Nombre                    | SKU       | Precio | Costo | Stock | Stock mínimo | Código de barras | Nota
Leche descremada 1L       | LAC-DES-1L| 850    | 420   | 15    |              |                  |
```
**Suponiendo que el producto existe con stock actual=25**:

**Resultado**:
- ✅ Producto actualizado (precio, costo)
- ✅ Stock ajustado a 15
- ✅ Movimiento ADJUST: -10 (de 25 a 15)

### Ejemplo 4: Solo Actualizar Datos (Sin Cambiar Stock)
```xlsx
Nombre                    | SKU       | Precio | Costo | Stock | Stock mínimo | Código de barras | Nota
Filtros #4                | FIL-004   | 2700   | 1000  |       | 10           |                  | Nuevo precio
```
**Resultado**:
- ✅ Producto actualizado (precio, costo, stock_min)
- ℹ️ Stock sin cambios (celda vacía)
- ℹ️ No se genera movimiento

### Ejemplo 5: Importar Solo para Inventario Inicial
```xlsx
Nombre           | SKU | Precio | Costo | Stock | Stock mínimo | Código de barras | Nota
Producto A       |     |        |       | 50    |              |                  | Inventario inicial
Producto B       |     |        |       | 30    |              |                  | Inventario inicial
Producto C       |     |        |       | 75    |              |                  | Inventario inicial
```
**Resultado**:
- ✅ 3 productos creados
- ✅ Stocks iniciales: 50, 30, 75
- ⚠️ Precio y costo = 0 (deben actualizarse después)

---

## ⚠️ Validaciones y Errores Comunes

### Errores que Bloquean la Importación

| Error | Causa | Solución |
|-------|-------|----------|
| `No encontramos filas con datos` | Archivo vacío o solo headers | Agregar datos desde fila 2 |
| `La plantilla debe incluir la columna "Nombre"` | Falta columna obligatoria | Verificar encabezados en fila 1 |
| `No pudimos leer el archivo` | Archivo corrupto o formato inválido | Guardar como .xlsx válido |
| `Archivo muy grande` | Supera 10 MB | Dividir en múltiples archivos |
| `Excede el límite de 2000 filas` | Demasiadas filas | Importar en lotes |

### Advertencias (Procesan pero Alertan)

| Advertencia | Causa | Recomendación |
|-------------|-------|---------------|
| `SKU faltante, se generará automáticamente` | Celda SKU vacía | Proporcionar SKU personalizado si es importante |
| `Producto duplicado en el archivo` | Mismo nombre/SKU aparece 2+ veces | Consolidar en una fila |
| `Stock sin cambios` | Valor idéntico al actual | Normal, no genera movimiento |
| `Código de barras ya existe en otro producto` | Barcode duplicado | Verificar error de carga |

### Validaciones por Campo

#### Nombre
- ✅ Válido: "Café en grano Colombia 500g"
- ❌ Inválido: (vacío)
- ❌ Inválido: "A" (muy corto)

#### SKU
- ✅ Válido: "CF-001", "PROD-ABC-123"
- ✅ Válido: (vacío, se genera auto)
- ⚠️ Advertencia: Duplicado en archivo
- ❌ Error: Duplicado con diferente producto

#### Números (Precio, Costo, Stock, Stock mínimo)
- ✅ Válido: `3500`, `0`, `125.50`
- ❌ Inválido: `-10` (negativo)
- ❌ Inválido: `$3500` (con símbolo)
- ❌ Inválido: `tres mil` (texto)

#### Código de barras
- ✅ Válido: "7790000000012" (EAN-13)
- ✅ Válido: "123456789012" (UPC)
- ✅ Válido: (vacío)
- ⚠️ Advertencia: Formato inusual

---

## 🔍 Vista Previa y Resumen

### Resumen Estadístico

Después de subir el archivo, se muestra:

```
📊 Resumen
├─ Total de filas: 156
├─ Creaciones: 120
├─ Actualizaciones: 36
├─ Ajustes de stock: 98
├─ Sin cambios: 58
├─ Advertencias: 3
└─ Errores: 0
```

### Tabla de Vista Previa

Muestra hasta 200 filas con detalles:

| Línea | Producto | SKU | Acción | Stock | Estado | Mensajes |
|-------|----------|-----|--------|-------|--------|----------|
| 2 | Café Colombia | CF-001 | Actualizar | Ajustar | ✅ OK | Stock: 25→40 (+15) |
| 3 | Filtros #4 | | Crear | Ajustar | ⚠️ Warning | SKU se generará automáticamente |
| 4 | Azúcar 1kg | AZ-1K | Actualizar | Sin cambios | ✅ OK | Precio actualizado |
| 5 | Producto X | | Error | - | ❌ Error | Nombre duplicado en fila 12 |

---

## 🛠️ Implementación Técnica

### Backend (Django)

**Archivo**: `services/api/src/apps/inventory/importer.py`

**Funciones principales**:
- `parse_inventory_import()`: Parsea Excel y valida datos
- `apply_inventory_import()`: Ejecuta creaciones/actualizaciones
- `serialize_preview_rows()`: Genera vista previa

**Límites**:
```python
MAX_ROWS = 2000
PREVIEW_LIMIT = 200
```

**Headers aceptados**:
```python
HEADER_ALIASES = {
    'nombre': 'name',
    'producto': 'name',
    'sku': 'sku',
    'codigo': 'sku',
    'código': 'sku',
    'barcode': 'barcode',
    'codigo de barras': 'barcode',
    'código de barras': 'barcode',
    'precio': 'price',
    'precio venta': 'price',
    'costo': 'cost',
    'stock minimo': 'stock_min',
    'stock mínimo': 'stock_min',
    'stock_min': 'stock_min',
    'stock': 'stock',
    'nota': 'note',
    'notas': 'note',
}
```

### Frontend (Next.js)

**Archivo**: `apps/web/src/app/app/gestion/stock/importar/stock-import-client.tsx`

**Flujo**:
1. Usuario selecciona archivo
2. Upload → POST `/api/v1/inventory/imports/`
3. Vista previa → POST `/api/v1/inventory/imports/{id}/preview/`
4. Aplicar → POST `/api/v1/inventory/imports/{id}/apply/`
5. Polling cada 3s hasta completar

**Plantilla**: `apps/web/src/app/plantillas/importar-stock.xlsx/route.ts`

### Endpoints API

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| POST | `/api/v1/inventory/imports/` | Subir archivo Excel |
| GET | `/api/v1/inventory/imports/{id}/` | Obtener estado del job |
| POST | `/api/v1/inventory/imports/{id}/preview/` | Generar vista previa |
| POST | `/api/v1/inventory/imports/{id}/apply/` | Aplicar importación |

---

## 📈 Métricas y Auditoría

### Registros Generados

Por cada importación se registra:

1. **InventoryImportJob**:
   - ID único
   - Archivo original (nombre)
   - Usuario que ejecutó
   - Estado (pending→processing→done/failed)
   - Estadísticas (creados, actualizados, ajustados)
   - Timestamp de creación/inicio/fin

2. **Product** (creados/actualizados):
   - Auditoría completa (created_at, updated_at)
   - Business scope (multi-tenant)

3. **StockMovement** (por cada ajuste):
   - Tipo: "ADJUST"
   - Nota: "Importación de stock (.xlsx)"
   - Usuario: quien ejecutó la importación
   - Timestamp
   - Cantidad (puede ser negativa si reduce stock)

### Trazabilidad

```
ImportJob #1234
├─ Archivo: inventario-enero-2026.xlsx
├─ Usuario: admin@negocio.com
├─ Fecha: 2026-02-23 14:35:22
├─ Estado: done
└─ Detalle:
    ├─ Productos creados: 45
    ├─ Productos actualizados: 12
    ├─ Ajustes de stock: 52
    └─ Movimientos generados:
        ├─ [#8901] Café Colombia +15 unidades
        ├─ [#8902] Filtros #4 +40 unidades
        └─ [#8903] Azúcar 1kg -25 unidades
```

---

## 🎓 Mejores Prácticas

### Para Usuarios

1. **Siempre usa la plantilla descargada**
   - Garantiza encabezados correctos
   - Incluye ejemplos de referencia

2. **Mantén archivos pequeños**
   - Divide importaciones grandes en lotes
   - Facilita identificar errores

3. **Revisa la vista previa**
   - Verifica que las acciones sean las esperadas
   - Atiende advertencias y errores

4. **Usa SKU únicos**
   - Facilita actualizaciones posteriores
   - Evita ambigüedades

5. **Documenta en la columna Nota**
   - Útil para rastrear origen de datos
   - Facilita auditorías

### Para Administradores

1. **Capacita usuarios en el formato**
   - Muestra la hoja de Instrucciones
   - Explica diferencia entre crear/actualizar

2. **Verifica permisos**
   - Solo `manage_stock` puede importar
   - Revisa logs de importación regularmente

3. **Monitorea rendimiento**
   - Importaciones grandes pueden demorar
   - Considera horarios de menor carga

4. **Mantén backups**
   - Antes de importaciones masivas
   - Los movimientos ADJUST son irreversibles

---

## 🔐 Seguridad y Permisos

### Control de Acceso

- **Permiso requerido**: `manage_stock`
- **Scope**: Business (multi-tenant automático)
- **Auditoría**: Usuario registrado en cada movimiento

### Validaciones de Seguridad

1. **Archivo**:
   - Solo .xlsx (no .xls, .csv)
   - Máximo 10 MB
   - Validación de magic bytes

2. **Datos**:
   - Sanitización de strings
   - Validación de tipos numéricos
   - Protección contra injection

3. **Business Scope**:
   - Productos solo del negocio actual
   - No puede ver/modificar otros tenants

---

## 🐛 Troubleshooting

### Problema: "No pudimos leer el archivo"
**Solución**:
1. Verificar que sea .xlsx (no .xls ni .ods)
2. Abrir en Excel y "Guardar como" → Excel Workbook (.xlsx)
3. Verificar que no esté protegido con contraseña

### Problema: "La plantilla debe incluir la columna Nombre"
**Solución**:
1. Verificar fila 1 tenga encabezados
2. Al menos debe existir columna "Nombre" o "Producto"
3. No modificar nombres de encabezados de la plantilla

### Problema: Importación se queda en "Procesando"
**Solución**:
1. Archivos grandes (>1000 filas) demoran más
2. Esperar hasta 5 minutos
3. Si persiste, contactar soporte

### Problema: Stock no se actualiza
**Solución**:
1. Verificar que columna "Stock" tenga valor
2. Verificar que valor sea diferente al actual
3. Celdas vacías = "no modificar stock"

### Problema: SKU duplicados en archivo
**Solución**:
1. Buscar SKU duplicado en Excel (Ctrl+F)
2. Consolidar en una sola fila
3. O eliminar duplicados y re-importar

---

## 📚 Referencias

### Archivos Relacionados

- **Backend**:
  - `services/api/src/apps/inventory/importer.py` - Lógica de importación
  - `services/api/src/apps/inventory/views.py` - Endpoints API
  - `services/api/src/apps/inventory/models.py` - Modelos de datos

- **Frontend**:
  - `apps/web/src/app/app/gestion/stock/importar/stock-import-client.tsx` - UI
  - `apps/web/src/features/inventory-imports/` - Hooks y types
  - `apps/web/src/app/plantillas/importar-stock.xlsx/route.ts` - Generador de plantilla

### Documentación Técnica

- [Importaciones de Inventario - API](services/api/src/apps/inventory/README.md)
- [Movimientos de Stock](services/api/src/apps/inventory/services.py)
- [Gestión de Productos](services/api/src/apps/catalog/models.py)

---

**Última actualización**: Febrero 23, 2026  
**Versión**: 2.0  
**Autor**: Sistema Mirubro - Gestión Comercial  
