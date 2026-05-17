# Carteles QR de Reseñas PRO

## Objetivo

Permitir a negocios con plan Reseñas PRO generar carteles imprimibles (PDF) con su código QR de reseñas de Google. El cartel puede colocarse físicamente en el negocio para incentivar más reseñas.

## Alcance MVP

- Disponible **solo** para plan Reseñas PRO.
- Plan QR Reseñas básico no ve el módulo y es redirigido a `/app/resenas/qr` si entra manualmente.
- PDF imprimible generado en el backend con ReportLab + segno.
- 6 tamaños de cartel.
- 3 templates de diseño.
- Texto principal editable (máx. 80 caracteres).
- Subtítulo opcional.
- 6 opciones de color de fondo.
- Logo del negocio opcional (4 variantes).
- El QR del cartel apunta a `/r/[slug]/` (landing de reseñas del negocio).

## Tamaños disponibles

| Código | Label | Dimensiones |
|---|---|---|
| `a4_portrait` | A4 vertical | 21 × 29.7 cm |
| `a4_landscape` | A4 horizontal | 29.7 × 21 cm |
| `a5_portrait` | A5 vertical | 14.8 × 21 cm |
| `half_a4` | Media A4 | 21 × 14.85 cm |
| `desk_card` | Tarjeta mostrador | 15 × 10 cm |
| `sticker_square` | Sticker cuadrado | 10 × 10 cm |

## Templates disponibles

| Código | Label | Descripción |
|---|---|---|
| `simple_centered` | Clásico centrado | Logo, texto y QR centrados verticalmente |
| `qr_left` | QR lateral | QR a la izquierda, texto a la derecha (activo en landscape) |
| `bold_cta` | Llamado destacado | Texto grande, QR en caja blanca |

## Rutas

**Frontend:**
```
/app/resenas/carteles
```

**Backend:**
```
POST /api/v1/reviews/qr-posters/generate-pdf/
```

## Entitlement

```
qr_reviews.print_posters
```

Asignado al plan `qr_reviews_pro`. El backend valida este entitlement en cada request; el frontend solo es la primera capa de control.

## Payload del endpoint

### Modo color (JSON)

```json
{
  "poster_size": "a4_portrait",
  "template_code": "simple_centered",
  "main_text": "Escaneá y dejanos tu opinión",
  "subtitle": "Tu reseña nos ayuda a mejorar",
  "include_logo": true,
  "logo_variant": "default",
  "background_color": "#FFFFFF",
  "background_mode": "color",
  "title_font": "sans_bold",
  "main_text_color": null,
  "subtitle_text_color": null,
  "main_text_outline_enabled": false,
  "main_text_outline_color": "#000000",
  "subtitle_text_outline_enabled": false,
  "subtitle_text_outline_color": "#000000",
  "text_outline_width": 0.4,
  "qr_scale": "medium",
  "text_spacing": "normal",
  "uppercase_mode": "none"
}
```

### Modo imagen (multipart/form-data)

Mismos campos enviados como strings + el archivo:

| Campo | Tipo |
|---|---|
| `poster_size` | string |
| `template_code` | string |
| `main_text` | string |
| `subtitle` | string (opcional) |
| `include_logo` | `"true"` / `"false"` |
| `logo_variant` | string |
| `background_color` | string |
| `background_mode` | `"image"` |
| `background_image` | File (JPG o PNG) |
| `title_font` | `"sans_bold"` / `"serif_bold"` / `"mono_bold"` |
| `main_text_color` | hex string o ausente |
| `subtitle_text_color` | hex string o ausente |
| `main_text_outline_enabled` | `"true"` / `"false"` |
| `main_text_outline_color` | hex string |
| `subtitle_text_outline_enabled` | `"true"` / `"false"` |
| `subtitle_text_outline_color` | hex string |
| `text_outline_width` | `"0.25"` / `"0.4"` / `"0.6"` / `"0.8"` |
| `qr_scale` | `"small"` / `"medium"` / `"large"` |
| `text_spacing` | `"tight"` / `"normal"` / `"loose"` |
| `uppercase_mode` | `"none"` / `"title"` / `"all"` |

El frontend no setea `Content-Type` manualmente — el browser agrega el boundary automáticamente.

## Comportamiento por plan

| Plan | Acceso |
|---|---|
| QR Reseñas básico | No ve tab, no ve módulo. Si entra a `/app/resenas/carteles` manualmente → redirige a `/app/resenas/qr`. |
| Reseñas PRO | Ve tab "Carteles" en navegación de Reseñas. Puede generar y descargar PDF. |

## Archivos principales

### Backend

| Archivo | Rol |
|---|---|
| `services/api/src/apps/reviews/qr_posters.py` | Generación PDF con ReportLab + segno |
| `services/api/src/apps/reviews/qr_poster_serializer.py` | Validación del payload |
| `services/api/src/apps/reviews/views.py` | `GenerateQrPosterPdfView` |
| `services/api/src/apps/reviews/urls.py` | Ruta `qr-posters/generate-pdf/` |
| `services/api/src/apps/reviews/tests/test_qr_posters.py` | 78 tests (Fases 1A–4C + 6A) |

### Frontend

| Archivo | Rol |
|---|---|
| `apps/web/src/app/app/resenas/carteles/page.tsx` | Server component: auth + permiso `manage_reviews` |
| `apps/web/src/app/app/resenas/carteles/qr-posters-client.tsx` | Client: carga config, gating PRO, layout editor + preview |
| `apps/web/src/features/reviews/qr-posters/types.ts` | Tipos TypeScript |
| `apps/web/src/features/reviews/qr-posters/constants.ts` | Tamaños, templates, colores, defaults |
| `apps/web/src/features/reviews/qr-posters/api.ts` | `generateQrPosterPdf()` + re-export `downloadBlob` |
| `apps/web/src/features/reviews/qr-posters/hooks.ts` | `useGenerateQrPosterPdf()` |
| `apps/web/src/features/reviews/qr-posters/components/QrPosterEditor.tsx` | Editor de parámetros + botón descarga |
| `apps/web/src/features/reviews/qr-posters/components/QrPosterPreview.tsx` | Preview CSS proporcional |
| `apps/web/src/app/app/resenas/resenas-nav.tsx` | Tab "Carteles" condicionado a `is_reviews_pro` |

## Tipografía del título

Disponible desde Fase 4A/4B.

| Valor | Label | Clase CSS |
|---|---|---|
| `sans_bold` | Sans moderna | `font-sans font-bold` |
| `serif_bold` | Serif elegante | `font-serif font-bold` |
| `mono_bold` | Mono fuerte | `font-mono font-bold` |

- Default: `sans_bold`.
- El backend mapea los valores a familias de fuente de ReportLab (Helvetica-Bold, Times-Bold, Courier-Bold).
- El preview refleja la tipografía con las mismas clases CSS de Tailwind.

## Colores de título y subtítulo

Disponible desde Fase 4A/4B.

- `main_text_color`: color hex del título. Si es `null`, el backend usa contraste automático (blanco en fondo oscuro, `#111827` en fondo claro).
- `subtitle_text_color`: ídem para el subtítulo (`null` → `#D1D5DB` oscuro / `#64748B` claro).
- Validación: si se envía, debe ser hex válido (`#RRGGBB`).
- El editor muestra una paleta de 7 colores + botón "Automático" (null).

## Borde de letra

Disponible desde Fase 4C (backend) / 4D (frontend).

### Campos

| Campo | Tipo | Default | Descripción |
|---|---|---|---|
| `main_text_outline_enabled` | boolean | `false` | Activa borde en el título |
| `main_text_outline_color` | hex string | `#000000` | Color del borde del título |
| `subtitle_text_outline_enabled` | boolean | `false` | Activa borde en el subtítulo |
| `subtitle_text_outline_color` | hex string | `#000000` | Color del borde del subtítulo |
| `text_outline_width` | float | `0.4` | Grosor del borde (valores: 0.25, 0.4, 0.6, 0.8) |

### Anchos disponibles

| Valor | Label |
|---|---|
| `0.25` | Fino |
| `0.4` | Medio |
| `0.6` | Grueso |
| `0.8` | Muy grueso |

### Backend

- Usa PDF text render mode 2 (`fill + stroke`) vía `beginText()` + `t.setTextRenderMode(2)` + `t.textOut()` + `pdf.drawText(t)` dentro de `saveState/restoreState`.
- No duplica texto — modo nativo de ReportLab/PDF.
- Helper `_draw_text_with_optional_outline` usado en los 3 templates.

### Frontend preview

- Aproximación CSS con 4 sombras en esquinas: `-Xpx -Xpx 0 color, Xpx -Xpx 0 color, -Xpx Xpx 0 color, Xpx Xpx 0 color`.
- `X = 1px` para anchos 0.25/0.4; `X = 2px` para anchos 0.6/0.8.
- Si el borde está apagado, `textShadow` es `undefined` (sin efecto).

## Historial de diseños guardados

Disponible desde Fase 5C/5D. Solo para Reseñas PRO.

### Descripción

Permite guardar hasta **5 diseños** por negocio para reutilizarlos sin reconfigurar el cartel desde cero. Cada diseño guarda nombre, payload completo e imagen de fondo opcional.

### Operaciones disponibles

| Acción | Descripción |
|---|---|
| Guardar diseño actual | Abre diálogo con campo nombre. Guarda payload + imagen actual del editor. |
| Cargar diseño | Aplica el payload guardado al editor. La imagen guardada se muestra en preview. |
| Actualizar diseño | Reemplaza el payload y/o imagen del diseño activo con el estado actual del editor. |
| Eliminar diseño | Confirmación inline. Libera un slot del límite de 5. |
| Descargar PDF | Genera PDF desde el diseño guardado directamente, sin necesidad de recargar imagen. |

### Límite de diseños

- Máximo 5 diseños por negocio.
- El contador `X/5` se muestra en el panel. En ámbar cuando se alcanza el límite.
- El botón "Guardar diseño actual" se deshabilita al llegar a 5.
- El backend retorna `400 { code: "design_limit_reached" }` si se intenta crear el sexto.

### Imagen de fondo

- Almacenada en el storage del proyecto (no en URL pública directa).
- El preview muestra la imagen guardada vía `savedBgUrl` cuando el usuario carga un diseño.
- El PDF desde diseño guardado lee los bytes desde el storage directamente — sin URL pública, sin re-upload.
- Si el usuario sube una nueva imagen, `savedBgUrl` se limpia y el diseño queda editable.

### Endpoints

| Método | URL | Descripción |
|---|---|---|
| `GET` | `/api/v1/reviews/qr-posters/designs/` | Lista diseños del business (con límite) |
| `POST` | `/api/v1/reviews/qr-posters/designs/` | Crea nuevo diseño (JSON o multipart) |
| `GET` | `/api/v1/reviews/qr-posters/designs/<id>/` | Obtiene un diseño |
| `PATCH` | `/api/v1/reviews/qr-posters/designs/<id>/` | Actualiza nombre, payload y/o imagen |
| `DELETE` | `/api/v1/reviews/qr-posters/designs/<id>/` | Elimina diseño |
| `POST` | `/api/v1/reviews/qr-posters/designs/<id>/generate-pdf/` | Genera PDF desde diseño guardado |

Todos los endpoints requieren entitlement `qr_reviews.print_posters` y filtran por `business=request.business` (tenant isolation).

### Códigos de error específicos

| Code | Status | Descripción |
|---|---|---|
| `design_limit_reached` | 400 | Se intentó crear más de 5 diseños |
| `missing_design_background_image` | 400 | Diseño con `background_mode=image` pero sin imagen persistida |
| `pdf_generation_error` | 500 | Fallo interno en ReportLab al generar PDF |

### Archivos del historial

#### Backend

| Archivo | Rol |
|---|---|
| `services/api/src/apps/reviews/models.py` | Modelo `ReviewQrPosterDesign` |
| `services/api/src/apps/reviews/views.py` | `QrPosterDesignListCreateView`, `QrPosterDesignDetailView`, `GenerateQrPosterPdfFromDesignView` |
| `services/api/src/apps/reviews/urls.py` | Rutas CRUD + `generate-pdf` |
| `services/api/src/apps/reviews/tests/test_qr_poster_designs.py` | 32 tests (Fases 5A–5D) |

#### Frontend

| Archivo | Rol |
|---|---|
| `apps/web/src/features/reviews/qr-posters/designs-types.ts` | Tipos TypeScript (`QrPosterDesign`, `QrPosterDesignPayload`, etc.) |
| `apps/web/src/features/reviews/qr-posters/designs-api.ts` | CRUD + `generatePdfFromDesign()` |
| `apps/web/src/features/reviews/qr-posters/designs-hooks.ts` | `useQrPosterDesigns()` hook con `useReducer` |
| `apps/web/src/features/reviews/qr-posters/components/SavedDesignsPanel.tsx` | Panel completo: contador, guardar, lista |
| `apps/web/src/features/reviews/qr-posters/components/SavedDesignCard.tsx` | Card individual: preview, acciones, descarga |
| `apps/web/src/features/reviews/qr-posters/components/SaveDesignDialog.tsx` | Diálogo modal para nombrar un nuevo diseño |
| `apps/web/src/features/reviews/qr-posters/components/QrPosterPreview.tsx` | Preview con soporte `savedBgUrl` |
| `apps/web/src/app/app/resenas/carteles/qr-posters-client.tsx` | Integra editor + preview + panel de diseños |

### Tests actualizados

| Suite | Tests | Estado |
|---|---|---|
| `test_qr_poster_designs` | 32 | OK |
| `test_qr_posters` | 78 | OK |
| **Total** | **110** | **OK** |

### Editor

- Toggle on/off independiente para título y subtítulo.
- Paleta de 5 colores (negro, blanco, gris oscuro, amarillo, azul).
- Selector de grosor compartido (grid 4 columnas), visible solo si al menos un borde está activo.

## Controles avanzados de layout

Disponibles desde Fase 6A (backend) / 6B (frontend).

| Campo | Valores | Default | Descripción |
|---|---|---|---|
| `qr_scale` | `small`, `medium`, `large` | `medium` | Tamaño relativo del código QR en el cartel |
| `text_spacing` | `tight`, `normal`, `loose` | `normal` | Separación entre título y subtítulo |
| `uppercase_mode` | `none`, `title`, `all` | `none` | Transformación de mayúsculas del texto |

### Semántica

- **`qr_scale`**: factor multiplicador sobre el tamaño base del QR. `small=0.85`, `medium=1.0`, `large=1.15`. El backend aplica `min(size * factor, usable_width)` para evitar overflow.
- **`text_spacing`**: espacio entre bloque de título y subtítulo. `tight=0.1 cm`, `normal=0.25 cm`, `loose=0.45 cm`.
- **`uppercase_mode`**: `none` = sin transformación; `title` = solo el título en mayúsculas; `all` = título y subtítulo en mayúsculas. La transformación se aplica en el backend antes de renderizar — el texto original del input no se modifica.

### Compatibilidad con diseños guardados

- Los diseños guardados antes de esta versión no tienen estos campos en su payload.
- Al cargar un diseño sin los campos, el frontend aplica los defaults seguros (`medium`, `normal`, `none`) antes de spreads el payload del diseño.
- El backend tiene `required=False` + `default=` para los 3 campos — acepta sin ellos sin error.

### Labels en el editor

| Campo | Labels UI |
|---|---|
| `qr_scale` | Chico / Mediano / Grande |
| `text_spacing` | Compacta / Normal / Amplia |
| `uppercase_mode` | Normal / Título / Todo |

## Imagen de fondo

Disponible desde Fase 3B. Solo para plan Reseñas PRO.

### Características

- El usuario sube una imagen JPG o PNG desde el editor.
- La imagen **no se persiste** en el servidor — se usa solo para generar el PDF y se descarta.
- Tamaño máximo: **10 MB**.
- El PDF renderiza la imagen en modo cover (proporcional, sin distorsión).
- Se aplica un overlay semitransparente para garantizar legibilidad del texto.
- El QR se coloca en una caja blanca para asegurar contraste.

### Validaciones backend

| Condición | Respuesta |
|---|---|
| `background_mode=image` sin archivo | 400, campo `background_image` |
| Archivo no es imagen válida (JPG/PNG) | 400, campo `background_image` |
| Archivo > 10 MB | 400, campo `background_image` |
| Plan básico con imagen | 403, `code: plan_entitlement_required` |
| Plan PRO + JPG/PNG válido | 200, PDF |

### Validaciones frontend

| Condición | Respuesta |
|---|---|
| Archivo > 10 MB | Error inline "La imagen no puede superar 10 MB." |
| Extensión fuera de `.jpg/.jpeg/.png` | Error inline "Solo se aceptan JPG o PNG." |
| Modo imagen sin archivo | Botón Descargar deshabilitado |

### Preview

- Usa `URL.createObjectURL` para renderizar la imagen localmente sin servidor.
- El object URL se libera con `URL.revokeObjectURL` al desmontar o cambiar imagen.
- Muestra overlay oscuro (`rgba(0,0,0,0.45)`) sobre la imagen.
- El contenido (texto + QR) queda sobre el overlay con `zIndex`.
- Al volver a modo color, la imagen y el overlay desaparecen automáticamente.

## Seguridad

- El servidor valida entitlement `qr_reviews.print_posters` en cada POST.
- El frontend es una capa de UX, no de seguridad real.
- 403 del backend muestra mensaje localizado en el cliente.
- El server component valida permiso `manage_reviews` antes de renderizar.
- Las imágenes de fondo subidas no se persisten — se procesan en memoria y se descartan.

## Tests

| Suite | Cantidad |
|---|---|
| Fases 1A + 1B (básicos, validaciones) | 21 + 16 |
| Fase 1C + 2 (templates, tamaños) | parte de los 43 base |
| Fase 3B (BackgroundImageTests) | 6 |
| Fase 4A (TypographyTests) | 10 |
| Fase 4C (OutlineTests) | 9 |
| Fase 6A (NewFieldsTests) | 15 |
| **`test_qr_posters` total** | **78** |
| **`test_qr_poster_designs`** | **32** |
| **Total combinado** | **110** |

Ejecutar con:
```bash
cd infra
docker exec mirubro-api python manage.py test apps.reviews.tests.test_qr_posters apps.reviews.tests.test_qr_poster_designs --verbosity=1
```

## Pendientes futuros

- Descarga en PNG para formatos digitales (redes sociales, WhatsApp).
- Más templates (tent card, banner horizontal).
- Historial de diseños guardados.
- Previsualización en full resolution antes de descargar.
