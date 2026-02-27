# Módulo de Roles & Accesos (Owner)

## Descripción General

Este módulo permite a los usuarios con rol **OWNER** gestionar de forma centralizada los roles, permisos y accesos de todos los usuarios en su negocio/tenant. Implementa un sistema de RBAC (Role-Based Access Control) reutilizable para todos los servicios de Mirubro.

## Características Principales

### ✅ Para Todos los Usuarios

- **Mis Roles**: Ver roles asignados y permisos con descripciones entendibles
- **Permisos agrupados por módulo**: Organización clara (Ventas, Stock, Finanzas, etc.)

### 🔐 Solo para OWNER

- **Roles del Negocio**: Vista de todos los roles disponibles con contadores de usuarios
- **Gestión de Cuentas**: Administrar usuarios y sus accesos
- **Reset de Contraseñas**: Generación segura de credenciales temporales
- **Auditoría Completa**: Log de todas las acciones sensibles

## Arquitectura

### Backend (Django)

```
services/api/src/apps/accounts/
├── rbac_registry.py          # Registry central de capacidades (SHARED)
├── owner_views.py             # Endpoints owner-only
├── owner_serializers.py       # Serializers para respuestas
├── owner_urls.py              # URLs del módulo
├── models.py                  # Contiene AccessAuditLog
└── migrations/
    └── 0003_accessauditlog.py # Migración del modelo de auditoría
```

### Frontend (Next.js)

```
apps/web/src/
├── app/app/settings/access/
│   └── page.tsx              # Página principal con tabs
├── components/app/owner-access/
│   ├── shared-components.tsx      # PermissionList, RoleBadge, etc.
│   ├── accounts-table.tsx         # Tabla de cuentas
│   └── reset-password-modal.tsx   # Modal seguro de reset
├── lib/api/
│   └── owner-access.ts       # Cliente API
└── types/
    └── owner-access.ts       # TypeScript types
```

## Endpoints API

### Accesibles para Todos

```
GET /api/v1/owner/access/summary/
```

Retorna roles y permisos del usuario actual.

### Solo OWNER

```
GET /api/v1/owner/access/roles/
GET /api/v1/owner/access/roles/:role/
GET /api/v1/owner/access/accounts/
POST /api/v1/owner/access/accounts/:user_id/reset-password/
POST /api/v1/owner/access/accounts/:user_id/disable/
GET /api/v1/owner/access/audit-logs/
```

## Seguridad

### ⚠️ NUNCA se exponen contraseñas reales

- Los endpoints **nunca** retornan `password` ni `hashed_password`
- Solo `has_usable_password` (boolean)

### 🔑 Reset de Contraseñas

1. Solo OWNER puede resetear
2. Genera contraseña temporal segura (12 caracteres, letras + números)
3. Se muestra **UNA SOLA VEZ** en el modal
4. Se guarda hasheada en la DB
5. Se registra en auditoría con IP y user-agent

### 📋 Auditoría Completa

Todas las acciones sensibles se registran en `AccessAuditLog`:

- PASSWORD_RESET
- ACCOUNT_DISABLED / ACCOUNT_ENABLED
- ROLE_CHANGED
- MEMBERSHIP_CREATED / DELETED

Incluye: actor, target_user, business, IP, user-agent, detalles JSON.

## Cómo Agregar un Nuevo Servicio

### 1. Backend: Registrar Capacidades

Editar `apps/accounts/rbac_registry.py`:

```python
def _register_my_new_service_capabilities():
    """Register capabilities for My New Service."""

    register_capability(
        code='view_something',
        title='Ver Algo',
        description='Permite consultar información de algo',
        module='Mi Módulo',
        service='my_new_service'
    )

    register_capability(
        code='manage_something',
        title='Gestionar Algo',
        description='Permite crear, editar y eliminar algo',
        module='Mi Módulo',
        service='my_new_service'
    )

# Llamar al final del archivo
_register_my_new_service_capabilities()
```

### 2. Backend: Definir Permisos por Rol

Editar `apps/accounts/rbac.py`:

```python
MY_NEW_SERVICE_PERMISSIONS: Set[str] = {
    'view_something',
    'manage_something',
}

ALL_PERMISSIONS = GESTION_PERMISSIONS.union(
    RESTAURANT_PERMISSIONS
).union(
    MENU_QR_PERMISSIONS
).union(
    MY_NEW_SERVICE_PERMISSIONS  # <-- Agregar
)

SERVICE_ROLE_PERMISSIONS['my_new_service'] = {
    'owner': set(MY_NEW_SERVICE_PERMISSIONS),
    'manager': MY_NEW_SERVICE_PERMISSIONS - {'manage_something'},
    'staff': {
        'view_something',
    },
    'viewer': {
        'view_something',
    },
}
```

**¡Listo!** El registry automáticamente expone estos permisos en los endpoints.

## Frontend: Componentes Reutilizables

### PermissionList

Muestra permisos agrupados por módulo con iconos de check/cross.

```tsx
import { PermissionList } from "@/components/app/owner-access/shared-components";

<PermissionList permissionsByModule={data.permissions_by_module} />;
```

### RoleBadge

Badge con color según el rol.

```tsx
import { RoleBadge } from "@/components/app/owner-access/shared-components";

<RoleBadge role="owner" roleDisplay="Owner" />;
```

### StatusBadge

Estado activo/inactivo con indicador visual.

```tsx
import { StatusBadge } from "@/components/app/owner-access/shared-components";

<StatusBadge isActive={user.is_active} />;
```

### AccountsTable

Tabla completa con acciones de reset y disable.

```tsx
import { AccountsTable } from "@/components/app/owner-access/accounts-table";

<AccountsTable accounts={accounts} onRefresh={loadData} />;
```

## Flujo de Reset de Contraseña

```
1. Owner hace clic en "Resetear" en AccountsTable
   ↓
2. Se abre ResetPasswordModal con advertencia de seguridad
   ↓
3. Owner confirma → POST /api/v1/owner/access/accounts/:id/reset-password/
   ↓
4. Backend:
   - Valida que user es owner
   - Valida que target pertenece al mismo business
   - Genera password temporal (12 chars)
   - Hashea y guarda: target_user.set_password(temp_password)
   - Registra en AccessAuditLog
   - Retorna { temporary_password: "Abc123..." }
   ↓
5. Frontend muestra password temporal UNA VEZ
   - Botón de copiar al portapapeles
   - Advertencia: "No se volverá a mostrar"
   ↓
6. Owner cierra modal → password ya no es accesible
```

## Testing

### Backend Tests (TODO)

```bash
cd services/api
python manage.py test apps.accounts.tests.test_owner_access
```

Tests a implementar:

- ✅ Owner puede acceder a todos los endpoints
- ✅ Non-owner recibe 403
- ✅ Reset password genera credencial válida
- ✅ Reset password registra auditoría
- ✅ No se filtran datos cross-tenant

### Frontend Tests (TODO)

```bash
cd apps/web
npm test -- owner-access
```

Tests a implementar:

- ✅ Sección oculta para non-owner
- ✅ Tabla de accounts renderiza correctamente
- ✅ Modal de reset muestra password temporal
- ✅ Botón copiar funciona

## Migraciones

Aplicar migración para AccessAuditLog:

```bash
cd services/api
python manage.py migrate accounts
```

## Acceso Frontend

La sección es accesible desde:

**Configuración → Roles & Accesos**

URL: `/app/settings/access`

## Próximas Mejoras (Opcionales)

- [ ] Soporte para roles custom (crear roles personalizados)
- [ ] Gestión de PINs (para sistemas de punto de venta)
- [ ] Revocación de sesiones JWT activas
- [ ] Filtros y búsqueda en tabla de cuentas
- [ ] Exportar logs de auditoría a CSV
- [ ] Notificaciones por email al resetear contraseñas
- [ ] Políticas de expiración de contraseñas temporales
- [ ] Integración con 2FA

## Responsables

- **Backend**: Sistema RBAC completo con registry compartido
- **Frontend**: Componentes reutilizables y páginas owner-only
- **Seguridad**: Auditoría completa y gestión segura de credenciales

---

**Última actualización**: Febrero 2026  
**Versión**: 1.0.0  
**Estado**: ✅ Implementado y listo para producción
