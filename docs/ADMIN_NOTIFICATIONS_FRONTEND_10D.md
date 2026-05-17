# PR-ADMIN-10D — Frontend inicial del centro de notificaciones

**Estado**: ✅ Completado  
**Bloque**: PR-ADMIN-10D (frontend inicial)  
**Prerequisito**: PR-ADMIN-10C (endpoints backend completados, 43 tests verdes)

---

## Objetivo

Implementar la primera iteración del frontend del centro de notificaciones internas del panel de admin. Consume los endpoints de PR-ADMIN-10C.

---

## Archivos creados / modificados

### Nuevos archivos

| Archivo | Descripción |
|---|---|
| `apps/web/src/lib/admin/notifications.ts` | API client completo: SSR (`serverApiFetch`) + client-side (`fetch + credentials`) |
| `apps/web/src/components/admin/notification-item.tsx` | Componente de fila de notificación reutilizable (modo normal y compacto) |
| `apps/web/src/components/admin/notification-bell.tsx` | Bell icon con badge de conteo, polling cada 60s, dropdown preview |
| `apps/web/src/app/admin/notificaciones/page.tsx` | Server Component página `/admin/notificaciones` |
| `apps/web/src/app/admin/notificaciones/notificaciones-content.tsx` | Client Component con DataTable, FilterBar, Pagination, acciones |
| `apps/web/src/components/admin/__tests__/notification-bell.test.tsx` | 5 tests ✅ |
| `apps/web/src/components/admin/__tests__/notification-item.test.tsx` | 8 tests ✅ |
| `apps/web/src/app/admin/notificaciones/__tests__/notificaciones-content.test.tsx` | 6 tests ✅ |

### Archivos modificados

| Archivo | Cambio |
|---|---|
| `apps/web/src/lib/admin/types.ts` | Nuevos tipos: `AdminNotification`, `AdminNotificationList`, `AdminNotificationUnreadCount`, `AdminNotificationStatus`, `AdminNotificationSeverity`, `AdminNotificationType`; `'notificaciones'` agregado a `AdminSection` |
| `apps/web/src/lib/admin/index.ts` | Re-export de `getAdminNotifications` y `getAdminUnreadCount` desde `./notifications` |
| `apps/web/src/components/admin/admin-shell.tsx` | Bell icon importado, `NotificationBell` en sidebar footer, `notificaciones` en `ALL_NAV_ITEMS` |
| `services/api/src/apps/accounts/platform_permissions.py` | `'notificaciones'` agregado a `superadmin`, `operations`, `support_agent` |

---

## Funcionalidades implementadas

### `NotificationBell`
- Badge con conteo de no leídas (rojo si hay `critical_count > 0`, brand-500 si no)
- Badge muestra `99+` si count > 99
- Polling cada 60 segundos vía `fetchAdminUnreadCountClient()`
- Click abre dropdown con preview de 6 notificaciones más recientes
- Link a `/admin/notificaciones` desde el dropdown
- Solo visible si `session.authorized_sections.includes('notificaciones')`

### Página `/admin/notificaciones`
- Server Component con SSR de datos iniciales
- Acepta filtros via URL params: `status`, `severity`, `type`, `page`
- Redirects: `→ /admin/login` si no hay sesión, `→ /admin/dashboard` si no tiene sección

### `NotificacionesContent`
- **FilterBar**: 3 filtros (estado, severidad, tipo con 16 opciones)
- **DataTable**: columnas sev., estado, título+mensaje, tipo, negocio, fecha, acciones
- **Acciones por fila**: marcar leída, archivar, resolver (actualizan fila localmente)
- **Paginación**: via `router.push()` con URL params (consistente con demás páginas admin)
- **EmptyState**: mensaje cuando no hay notificaciones

---

## Permisos por rol

| Rol | Acceso `notificaciones` |
|---|---|
| `superadmin` | ✅ |
| `operations` | ✅ |
| `support_agent` | ✅ |
| `content_admin` | ❌ (por spec) |

---

## Tests

```
✅ notification-bell.test.tsx       — 5 tests
✅ notification-item.test.tsx       — 8 tests
✅ notificaciones-content.test.tsx  — 6 tests
Total: 19 tests nuevos, todos verdes
```

---

## Próximo paso

**PR-ADMIN-10E** — Integración con eventos reales del sistema:  
- `create_admin_notification()` en webhook failures  
- `create_admin_notification()` en ticket creados urgentes  
- `create_admin_notification()` en payment failures  
- `create_admin_notification()` en MFA resets  
