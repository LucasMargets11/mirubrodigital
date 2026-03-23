# Phase 5 — Blog / CMS Interno: Entrega

## 1. Archivos creados

### Backend (`services/api/src/`)

| Archivo | Descripción |
|---------|-------------|
| `apps/blog/__init__.py` | App package init |
| `apps/blog/migrations/__init__.py` | Migrations package init |
| `apps/blog/models.py` | `BlogCategory`, `BlogPost` (UUID PK, status workflow, ContentBlock JSON, SEO) |
| `apps/blog/service.py` | Capa de servicio editorial — transiciones, slug, publish/unpublish/archive/schedule |
| `apps/blog/tasks.py` | Celery task `blog.publish_scheduled_posts` |
| `apps/blog/admin_views.py` | 11 vistas DRF con permisos `IsPlatformStaff + HasInternalRole` |
| `apps/blog/migrations/0001_initial.py` | Tablas `blog_blogcategory`, `blog_blogpost` + índices |
| `apps/accounts/migrations/0022_blog_phase5_audit_actions.py` | 7 nuevas acciones de auditoría |

### Frontend (`apps/web/src/`)

| Archivo | Descripción |
|---------|-------------|
| `app/admin/blog/blog-content.tsx` | Client component: KPIs, filtros, DataTable, paginación, link a nuevo |
| `app/admin/blog/_components/blog-post-form.tsx` | Formulario compartido create/edit con acciones editoriales |
| `app/admin/blog/nuevo/page.tsx` | SSR page: crear nuevo post |
| `app/admin/blog/[postId]/page.tsx` | SSR page: editar post existente |

## 2. Archivos modificados

| Archivo | Cambio |
|---------|--------|
| `services/api/src/config/settings.py` | `apps.blog` en INSTALLED_APPS + `blog-publish-scheduled` en CELERY_BEAT_SCHEDULE |
| `services/api/src/apps/accounts/platform_admin_urls.py` | 11 URLs de blog bajo `blog/` prefix |
| `services/api/src/apps/accounts/models.py` | 7 nuevas acciones de auditoría en ACTION_CHOICES |
| `apps/web/src/lib/admin/types.ts` | Tipos: `BlogPostStatus`, `AdminBlogPostRow`, `AdminBlogPostList`, `AdminBlogPostKPIs`, `AdminBlogPostDetail`, `AdminBlogCategory` |
| `apps/web/src/lib/admin/index.ts` | 4 fetchers SSR: posts (paginado/filtrado), detail, KPIs, categories |
| `apps/web/src/lib/admin/display.ts` | `blogStatusLabel()`, `blogStatusColor()`, constantes BLOG_STATUS_* |
| `apps/web/src/app/admin/blog/page.tsx` | Reemplazado placeholder con página SSR real |
| `apps/web/src/components/admin/admin-page-header.tsx` | Agregados props `backHref`/`backLabel` para navegación de retorno |

## 3. Modelos

### BlogCategory
- `id` (AutoField PK), `slug` (unique), `label`, `created_at`, `updated_at`

### BlogPost
- `id` (UUIDField PK)
- **Contenido**: `title`, `slug` (unique, max 280), `excerpt`, `body_content` (JSONField — ContentBlock[]), `cover_image_url`, `reading_time`, `source_label`
- **Taxonomía**: `category` (FK → BlogCategory), `tags` (JSONField — string[])
- **Estado**: `status` (draft | published | scheduled | archived), `published_at`, `scheduled_publish_at`
- **SEO**: `meta_title`, `meta_description`, `og_title`, `og_description`, `og_image_url`, `canonical_url`
- **Tracking**: `author` (FK → User), `last_editor` (FK → User), `created_at`, `updated_at`
- **Índices**: `(status, -published_at)`, `(-created_at)`
- **Métodos**: `generate_unique_slug()`, `seo_missing_fields()`, `validate_for_publish()`

## 4. Endpoints API

| Método | URL | Descripción |
|--------|-----|-------------|
| GET | `/api/v1/platform-admin/blog/posts/` | Listar posts (paginado, filtros: search, status, category, author, sort) |
| POST | `/api/v1/platform-admin/blog/posts/create/` | Crear post (borrador) |
| GET | `/api/v1/platform-admin/blog/posts/kpis/` | KPIs (total, draft, published, scheduled, archived) |
| GET | `/api/v1/platform-admin/blog/posts/<id>/` | Detalle completo con validación y preview URL |
| PATCH | `/api/v1/platform-admin/blog/posts/<id>/update/` | Actualizar campos |
| POST | `/api/v1/platform-admin/blog/posts/<id>/publish/` | Publicar (valida campos requeridos + transición) |
| POST | `/api/v1/platform-admin/blog/posts/<id>/unpublish/` | Despublicar (→ draft) |
| POST | `/api/v1/platform-admin/blog/posts/<id>/archive/` | Archivar |
| POST | `/api/v1/platform-admin/blog/posts/<id>/schedule/` | Programar publicación (body: publish_at ISO) |
| GET | `/api/v1/platform-admin/blog/categories/` | Listar categorías |
| POST | `/api/v1/platform-admin/blog/categories/` | Crear categoría |
| PATCH | `/api/v1/platform-admin/blog/categories/<id>/` | Actualizar categoría |

## 5. Estados editoriales y transiciones válidas

```
draft     → published, scheduled, archived
scheduled → published, draft, archived
published → draft, archived
archived  → draft
```

## 6. Reglas de validación para publicar

Un post **no puede publicarse** si le falta:
- `title` (vacío)
- `slug` (vacío)
- `body_content` (vacío o no es lista)
- `excerpt` (vacío)

## 7. Permisos

| Rol | Acceso |
|-----|--------|
| `superadmin` | Full CRUD + acciones editoriales |
| `content_admin` | Full CRUD + acciones editoriales |
| `operations` | Sin acceso (blog no en su `authorized_sections`) |
| `support_agent` | Sin acceso |

Backend: `[IsAuthenticated, IsPlatformStaff, HasInternalRole]` con `allowed_internal_roles = ['superadmin', 'content_admin']`
Frontend: sidebar filtra por `authorized_sections` (blog solo visible para superadmin + content_admin)

## 8. Acciones de auditoría

| Acción | Cuándo |
|--------|--------|
| `BLOG_POST_CREATED` | Al crear un post |
| `BLOG_POST_UPDATED` | Al actualizar campos de un post |
| `BLOG_POST_PUBLISHED` | Al publicar (manual o programado) |
| `BLOG_POST_UNPUBLISHED` | Al despublicar |
| `BLOG_POST_ARCHIVED` | Al archivar |
| `BLOG_POST_SCHEDULED` | Al programar publicación |
| `BLOG_POST_VIEWED` | Al acceder al detalle |

## 9. Supuestos y decisiones de diseño

1. **ContentBlock JSON**: se reutiliza el esquema exacto del blog público (`_data.ts`): tipos `h2`, `h3`, `p`, `ul`, `check`, `cta`, `faq`. El formulario usa textarea JSON (no editor WYSIWYG).
2. **Slug**: se auto-genera del título con `slugify()` con counter de colisión (ej: `mi-post`, `mi-post-2`). Editable manualmente.
3. **Publicación programada**: Celery Beat cada 5 minutos busca posts con `status=scheduled` y `scheduled_publish_at <= now`, los publica automáticamente.
4. **UUID como PK**: consistente con otros modelos del sistema que usan UUIDs para entidades públicas.
5. **Preview URL**: devuelve `/blog/${slug}` — funciona solo si el blog público se conecta a la API (actualmente es estático).
6. **Categorías**: modelo separado para gestión dinámica. Las categorías estáticas de `_data.ts` deben seedearse manualmente.
7. **AdminPageHeader**: se extendió con `backHref`/`backLabel` para navegación de retorno en subpáginas.

## 10. Deuda técnica conocida

1. **Editor de contenido**: el body_content se edita como JSON crudo. Un editor visual de bloques (tipo Notion) mejoraría la UX significativamente.
2. **Preview en vivo**: el blog público aún consume datos estáticos de `_data.ts`. Conectar `/blog/[slug]` al API para preview dinámico.
3. **Subida de imágenes**: `cover_image_url` y `og_image_url` se ingresan como URLs manuales. Falta integrar upload a S3/media.
4. **Seed de categorías**: las categorías del blog estático necesitan migrarse a la tabla `blog_blogcategory`.
5. **Tests**: sin unit/integration tests para el módulo blog (modelos, service, views).
6. **Gestión de categorías UI**: el frontend no tiene pantalla dedicada para CRUD de categorías (solo API está lista).
7. **Soft delete**: no hay soft-delete, `archived` es el estado de "retiro" pero el post persiste en la DB.

## Pasos post-merge

```bash
# 1. Aplicar migraciones
cd services/api
python manage.py migrate

# 2. Seed de categorías (ejemplo)
python manage.py shell -c "
from apps.blog.models import BlogCategory
cats = [
    ('gestion', 'Gestión'), ('inventario', 'Inventario'),
    ('ventas', 'Ventas'), ('caja', 'Caja'),
    ('facturacion', 'Facturación'), ('marketing', 'Marketing'),
    ('menu-qr', 'Menú QR'), ('resenas', 'Reseñas'),
    ('gestion-comercial', 'Gestión Comercial'),
]
for slug, label in cats:
    BlogCategory.objects.get_or_create(slug=slug, defaults={'label': label})
"

# 3. Verificar Celery Beat
# La task blog-publish-scheduled ya está en CELERY_BEAT_SCHEDULE
```
