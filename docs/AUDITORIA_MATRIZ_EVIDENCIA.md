# MATRIZ DE EVIDENCIA TÉCNICA — Segunda Pasada

**Fecha:** Marzo 2026  
**Objetivo:** Verificar con código fuente real los 9 hallazgos críticos y altos del informe anterior  
**Resultado:** 1 hallazgo REVOCADO, 1 RECLASIFICADO, 7 CONFIRMADOS

---

## RBAC-1 — ~~Backend no verifica permisos granulares~~

| Campo | Valor |
|---|---|
| **Severidad original** | CRÍTICO |
| **Severidad corregida** | **REVOCADO — HALLAZGO FALSO** |
| **Conclusión** | El backend SÍ verifica permisos granulares por endpoint, vía la clase `HasPermission` y atributos `permission_map`/`required_permission` presentes en las 11 apps operativas (~123 endpoints auditados). |

**Archivos involucrados:**

| Archivo | Relevancia |
|---|---|
| `apps/accounts/permissions.py` L203-220 | Clase `HasPermission` — lee `permission_map` o `required_permission` del view |
| `apps/accounts/permissions.py` L222-234 | `request_has_permission()` — resuelve membership, carga permisos de `rbac.py`, verifica |
| `apps/catalog/views.py` L13-18 | Ejemplo: `permission_classes = [IsAuthenticated, HasBusinessMembership, HasPermission]` + `permission_map = {'GET': 'view_products', 'POST': 'manage_products'}` |
| Todos los `views.py` de las 11 apps | Todas usan el patrón `HasPermission` + `permission_map`/`required_permission` |

**Evidencia concreta:**

```python
# accounts/permissions.py L203-220
class HasPermission(BasePermission):
    message = 'No tenes permisos para operar este recurso.'

    def has_permission(self, request: Request, view) -> bool:
        required_permission = None
        permission_map = getattr(view, 'permission_map', None)
        if isinstance(permission_map, dict):
            required_permission = permission_map.get(request.method.upper())
        if required_permission is None:
            required_permission = getattr(view, 'required_permission', None)
        if not required_permission:
            return True  # ← fallback si no se define permiso
        ...
        return request_has_permission(request, required_permission)
```

```python
# accounts/permissions.py L222-234
def request_has_permission(request, permission_code):
    membership = resolve_request_membership(request)
    if membership is None:
        return False
    context = resolve_business_context(request, membership)
    permission_map = permissions_for_service(context['service'], membership.role)
    return bool(permission_map.get(permission_code, False))
```

**Cobertura por app:**

| App | Endpoints con HasPermission | Método de definición |
|---|---|---|
| catalog | 4 | `permission_map` |
| inventory | 15+ | `required_permission` y `permission_map` |
| invoices | 8 | mixto |
| orders | 17 | mixto |
| cash | 9 | `required_permission` y `permission_map` |
| sales | 7+ | mixto, incluyendo `@action(permission_map=...)` |
| menu | 21 | mixto |
| resto | 8+ | `required_permission` |
| customers | 4 | `permission_map` |
| reports | 10+ | `required_permission` |
| treasury | 13+ | `BaseTreasuryViewSet.permission_map` + herencia |

**Excepción encontrada (no crítica):**
- `BranchViewSet` (`business/views.py` L75-76): usa `[IsAuthenticated, HasBusinessMembership]` sin `HasPermission`. Cualquier miembro autenticado puede CRUD branches. Protegido solo por `max_branches` del plan.
- `ServiceHubView` (`business/views.py` L32-33): usa `[IsAuthenticated, HasBusinessMembership]` sin `HasPermission`. Es un endpoint GET informativo — riesgo bajo.

**Comportamiento real hoy:** Un `viewer` que intente `POST /api/v1/products/` recibe `403 "No tenes permisos para operar este recurso."` porque `HasPermission` verifica `manage_products` contra su rol, y `viewer` no tiene ese permiso en `SERVICE_ROLE_PERMISSIONS`.

**Riesgo real en producción:** Ninguno. Los permisos se verifican server-side.

**Nivel de certeza:** **Confirmado por código** — RBAC-1 fue un error de la primera auditoría.

---

## USR-1 — No existe sistema de invitación

| Campo | Valor |
|---|---|
| **Severidad** | CRÍTICO |
| **Conclusión** | No existe ningún endpoint API que permita a un owner crear una Membership para otro usuario en su negocio. |

**Archivos involucrados:**

| Archivo | Relevancia |
|---|---|
| `apps/accounts/views.py` L93-114 | `_ensure_membership()` — única creación de Membership vía API, se auto-ejecuta en login |
| `apps/accounts/services.py` L145+ | `MembershipService.create_membership_safely()` — existe como servicio, pero NO tiene endpoint |
| `apps/business/views.py` L119 | `BranchViewSet.create()` — crea Membership(owner) automáticamente al crear branch |
| `apps/billing/subscription_activator.py` L308 | `_ensure_owner_membership()` — crea Membership(owner) en activación de suscripción |
| `apps/accounts/owner_views.py` completo | 11 endpoints de gestión — NINGUNO crea nuevas Memberships |
| Todos los `urls.py` de accounts | No existe ruta `/invite/`, `/add-member/`, ni similar |

**Evidencia concreta:**

Búsqueda exhaustiva en todo `services/api/src/` por `invite|invitation|add_member|InviteView|create_member`:
- 0 resultados en código de producción
- Solo aparece en `tests/test_refinement_suite.py` (tests unitarios) y `seed_gestion_comercial_test_data.py` (management command)

Los owner endpoints (`owner_views.py`) soportan:
- `change_role` — cambia rol de miembro EXISTENTE
- `suspend_member` — suspende miembro EXISTENTE
- `remove_member` — elimina miembro EXISTENTE
- `disable_account` — desactiva cuenta de miembro EXISTENTE
- `reset_password` — resetea password de miembro EXISTENTE

Ninguno crea un nuevo vínculo usuario↔negocio.

**Comportamiento real hoy:** Un owner NO puede agregar colaboradores a su negocio desde la plataforma. La única forma de que un usuario aparezca como miembro es que ese usuario se registre E inicie sesión (lo que crea su PROPIO negocio), y luego no existe mecanismo para "unirlo" a otro negocio existente.

**Riesgo real en producción:** Bloquea completamente el modelo multi-seat. El sistema está diseñado para soportarlo (roles, seat limits, permisos), pero no hay forma de usarlo.

**Qué habría que cambiar:** Crear endpoint `POST /owner/access/accounts/invite/` que: (a) reciba email + rol, (b) si el usuario existe → crear Membership directamente, (c) si no existe → generar invitación con token + enviar email, (d) respetar seat limits vía `MembershipService.create_membership_safely()`.

**Nivel de certeza:** **Confirmado por código** — no existe código de invitación en ninguna parte del backend.

---

## JWT-1 — `BLACKLIST_AFTER_ROTATION: False`

| Campo | Valor |
|---|---|
| **Severidad** | CRÍTICO |
| **Conclusión** | `BLACKLIST_AFTER_ROTATION` está explícitamente en `False`, y el módulo `token_blacklist` no está instalado, por lo que los refresh tokens rotados siguen siendo válidos. |

**Archivos involucrados:**

| Archivo | Relevancia |
|---|---|
| `config/settings.py` L171 | `'BLACKLIST_AFTER_ROTATION': False` |
| `config/settings.py` L27-49 | `INSTALLED_APPS` — no contiene `rest_framework_simplejwt.token_blacklist` |

**Evidencia concreta:**

```python
# config/settings.py L167-175
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=ACCESS_TOKEN_MINUTES),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=REFRESH_TOKEN_DAYS),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': False,   # ← EVIDENCIA
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,
    'AUTH_HEADER_TYPES': ('Bearer',),
}
```

```python
# config/settings.py L27-49 (INSTALLED_APPS completo)
INSTALLED_APPS = [
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'rest_framework_simplejwt',          # ← SIN token_blacklist
    'drf_spectacular',
    'corsheaders',
    'apps.accounts',
    'apps.business',
    # ... (14 apps) ...
    'apps.treasury',
]
# rest_framework_simplejwt.token_blacklist NO está presente
```

**Comportamiento real hoy:** Cuando `RefreshView` rota el refresh token, el token anterior sigue siendo válido hasta su expiración natural (7 días). `ROTATE_REFRESH_TOKENS: True` genera un nuevo token, pero el viejo NO se invalida porque blacklisting está desactivado.

**Riesgo real en producción:** Si un atacante obtiene un refresh token (vía XSS, MITM, o acceso físico), puede usarlo durante 7 días completos para obtener access tokens nuevos. Incluso si el usuario hace logout (que solo borra cookies client-side) o cambia su contraseña, el token robado sigue funcionando.

**Qué habría que cambiar:**
1. Agregar `'rest_framework_simplejwt.token_blacklist'` a `INSTALLED_APPS`
2. Ejecutar `python manage.py migrate` (crea tablas `OutstandingToken` + `BlacklistedToken`)
3. Cambiar `'BLACKLIST_AFTER_ROTATION': True`

**Nivel de certeza:** **Confirmado por código** — el valor es explícito en settings.py.

---

## JWT-2 — No hay mecanismo de revocación de tokens

| Campo | Valor |
|---|---|
| **Severidad** | CRÍTICO |
| **Conclusión** | No existe endpoint de logout server-side ni mecanismo para invalidar tokens. El logout solo borra cookies en el cliente. |

**Archivos involucrados:**

| Archivo | Relevancia |
|---|---|
| `apps/accounts/views.py` L259-267 | `LogoutView` — solo borra cookies |
| `config/settings.py` L27-49 | `INSTALLED_APPS` sin `token_blacklist` |

**Evidencia concreta:**

```python
# accounts/views.py L259-267
class LogoutView(APIView):
    permission_classes = [AllowAny]

    def post(self, _request: Request) -> Response:
        response = Response({'status': 'ok'})
        _clear_session_cookies(response)   # ← Solo borra cookies
        return response
```

`_clear_session_cookies` (L87-89) llama a `_clear_auth_cookies` + `_clear_business_cookie`, que ejecutan `response.delete_cookie(...)`. No hay ninguna llamada a `token.blacklist()`, `OutstandingToken`, ni cualquier invalidación server-side.

**Comportamiento real hoy:** Cuando un usuario hace logout, sus cookies se eliminan del navegador. Pero los tokens JWT siguen siendo criptográficamente válidos. Si alguien copió el refresh token antes del logout, puede seguir usándolo.

**Riesgo real en producción:** Combinado con JWT-1, no hay forma de forzar el cierre de sesión de un usuario comprometido. Ni el usuario ni un admin pueden invalidar tokens existentes.

**Qué habría que cambiar:**
1. Resolver JWT-1 primero (activar blacklist)
2. En `LogoutView.post()`: extraer refresh token del request, instanciar `RefreshToken(token_str)`, llamar `token.blacklist()`
3. Opcionalmente: endpoint admin para invalidar todos los tokens de un usuario

**Nivel de certeza:** **Confirmado por código** — el LogoutView no tiene lógica server-side.

---

## JWT-3 — Cambio de password no invalida tokens existentes

| Campo | Valor |
|---|---|
| **Severidad** | ALTO |
| **Conclusión** | `ResetPasswordView` hace `user.set_password()` + `user.save()` sin invalidar tokens JWT previos. |

**Archivos involucrados:**

| Archivo | Relevancia |
|---|---|
| `apps/accounts/views.py` L528-529 | `user.set_password(new_password)` + `user.save(update_fields=['password'])` |
| `apps/accounts/owner_views.py` (reset_password) | El owner genera password temporal — misma ausencia de invalidación |

**Evidencia concreta:**

```python
# accounts/views.py L526-531 (ResetPasswordView.post)
user = profile.user
user.set_password(new_password)
user.save(update_fields=['password'])
# ← NO hay: RefreshToken.objects.filter(user=user).delete()
# ← NO hay: OutstandingToken.objects.filter(user=user).update(...)
# ← NO hay: ninguna invalidación de tokens
```

**Comportamiento real hoy:** SimpleJWT valida tokens verificando la firma HMAC con `SECRET_KEY`. No verifica el hash del password del usuario. Por lo tanto, un token emitido antes del cambio de password sigue siendo válido hasta su expiración natural.

**Nota técnica:** Django's `AbstractBaseUser` actualiza `password` en la DB pero no tiene hook hacia JWT. SimpleJWT NO consulta la DB en cada request para validar el token — solo verifica la firma criptográfica. La única forma de invalidar sería via blacklist (que no está activo) o cambiando `SECRET_KEY` (invalidaría TODOS los tokens de TODOS los usuarios).

**Riesgo real en producción:** Un usuario que cambia su password (porque sospecha compromiso) no logra revocar el acceso del atacante. El atacante con un refresh token previo puede seguir operando hasta 7 días.

**Qué habría que cambiar:**
1. Activar blacklisting (JWT-1)
2. En `ResetPasswordView` y `reset_password` (owner): blacklistear todos los refresh tokens del usuario post-cambio

**Nivel de certeza:** **Confirmado por código** — `set_password()` no interactúa con SimpleJWT.

---

## BIL-1 — Triple modelo de suscripción

| Campo | Valor |
|---|---|
| **Severidad** | ALTO |
| **Conclusión** | Existen 3 modelos de suscripción en 2 apps. El código de runtime ya prioriza V2, pero el modelo legacy `business.Subscription` sigue activo y es necesario para seat limits y branch limits. |

**Archivos involucrados:**

| Archivo | Relevancia |
|---|---|
| `apps/business/models.py` | `Subscription` (legacy) — OneToOneField a Business |
| `apps/billing/models.py` | `Subscription` (billing legacy) — OneToOneField a Business |
| `apps/billing/models.py` | `SubscriptionV2` — FK a Business (canónico) |
| `apps/billing/runtime.py` | `resolve_subscription()` — V2-first con fallback a legacy |
| `apps/accounts/models.py` L222-237 | `check_seat_limit` — usa `hq.subscription` (legacy) |
| `apps/business/views.py` L103-109 | `BranchViewSet.create()` — usa `hq.subscription` para `max_branches` y crea `Subscription` legacy para la branch |

**Evidencia concreta:**

```python
# accounts/models.py L222-223 (check_seat_limit signal)
sub = getattr(hq, 'subscription', None)   # ← business.Subscription (legacy)
if not sub:
    return
max_seats = getattr(sub, 'max_seats', 0)
```

```python
# business/views.py L103-107 (BranchViewSet.create)
sub = getattr(hq, 'subscription', None)   # ← business.Subscription (legacy)
max_branches = sub.effective_max_branches if sub else 0
# ...
Subscription.objects.create(              # ← crea legacy Subscription para branch
    business=branch,
    plan=sub.plan if sub else BusinessPlan.STARTER,
    service=sub.service if sub else hq.default_service,
)
```

```python
# billing/runtime.py — resolve_subscription() busca V2 primero, fallback a legacy
# El billing enforcement usa resolve_subscription(), que ya funciona con V2
```

**Comportamiento real hoy:** La coexistencia funciona porque:
- Billing enforcement → usa `resolve_subscription()` → prioriza V2
- Seat limits → usa `business.Subscription` (legacy) directamente
- Branch limits → usa `business.Subscription` (legacy) directamente

Si un negocio tiene SubscriptionV2 pero NO tiene `business.Subscription`, el billing enforcement funciona (acceso permitido) pero seat limits y branch limits no se aplican (se ignoran silenciosamente porque `getattr(hq, 'subscription', None)` retorna `None` → `return`).

**Riesgo real en producción:** Complejidad de mantenimiento. Si se eliminan los modelos legacy sin migrar la lógica de seats/branches a V2, se pierden esos límites. No es un bug actual sino una deuda técnica que condiciona futuras migraciones.

**Qué habría que cambiar:** Migrar `check_seat_limit` y `BranchViewSet.create` para obtener `max_seats`/`max_branches` desde `SubscriptionV2` o desde `Plan` directamente.

**Nivel de certeza:** **Confirmado por código** — los 3 modelos coexisten y se usan en contextos diferentes.

---

## BIL-2 — `check_seat_limit` depende del modelo legacy

| Campo | Valor |
|---|---|
| **Severidad original** | ALTO |
| **Severidad corregida** | **MEDIO** — depende del estado de migración |
| **Conclusión** | El signal `check_seat_limit` accede a `business.Subscription` (legacy). Si un negocio solo tiene `SubscriptionV2` y no tiene el legacy, el signal no bloquea excesos de seats. |

**Archivos involucrados:**

| Archivo | Relevancia |
|---|---|
| `apps/accounts/models.py` L196-237 | Signal `check_seat_limit` completo |

**Evidencia concreta:**

```python
# accounts/models.py L222-237
sub = getattr(hq, 'subscription', None)   # ← business.Subscription (NOT SubscriptionV2)
if not sub:
    return                                  # ← Si no hay legacy subscription, NO VALIDA NADA

max_seats = getattr(sub, 'max_seats', 0)
if max_seats <= 0:
    return                                  # ← Si max_seats es 0, NO VALIDA NADA

family_ids = [hq.id] + list(hq.branches.values_list('id', flat=True))
current_count = Membership.objects.filter(business__id__in=family_ids).count()

if current_count >= max_seats:
    raise ValidationError(f"Límite de usuarios ({max_seats}) alcanzado...")
```

**Comportamiento real hoy:** Depende de si la migración a V2 ya reemplazó completamente al legacy:
- Si `business.Subscription` todavía se crea para todos los negocios → seats se validan correctamente
- Si algún negocio solo tiene `SubscriptionV2` → seats NO se validan para ese negocio

**Riesgo real en producción:** Si la invitación de miembros (USR-1) se implementa ANTES de migrar este signal, los negocios sin legacy Subscription podrían agregar miembros ilimitados.

**Qué habría que cambiar:** Refactorizar el signal para obtener `max_seats` de `SubscriptionV2` → `plan.max_seats` (o del modelo `Plan` vinculado).

**Nivel de certeza:** **Parcialmente confirmado** — el signal depende de un modelo legacy, pero el impacto depende de si TODOS los negocios actuales aún tienen ese modelo legacy creado. Sin acceso a la DB de producción, no se puede confirmar si existen negocios sin `business.Subscription`.

---

## BIL-3 — `StartSubscriptionView` es AllowAny sin rate limit

| Campo | Valor |
|---|---|
| **Severidad** | MEDIO |
| **Conclusión** | `StartSubscriptionView` permite requests anónimos, crea usuarios y negocios, y no tiene ningún throttle configurado. |

**Archivos involucrados:**

| Archivo | Relevancia |
|---|---|
| `apps/billing/views.py` L332-367 | `StartSubscriptionView` definición |
| `config/settings.py` L146-150 | `DEFAULT_THROTTLE_RATES` — solo `employee_login` y `employee_change_pin` |

**Evidencia concreta:**

```python
# billing/views.py L332, L367
class StartSubscriptionView(APIView):
    """POST /billing/start-subscription — Idempotent signup + subscription checkout."""
    permission_classes = [AllowAny]       # ← Sin autenticación
    # ← Sin throttle_classes
    # ← Sin throttle_scope

    def post(self, request):
        email = (request.data.get('email') or '').strip()
        password = request.data.get('password')
        business_name = (request.data.get('business_name') or '').strip()
        plan_code = (request.data.get('plan_code') or '').strip()
        # ...crea User, Business, Membership, Subscription, MpCheckoutSession...
```

No hay `DEFAULT_THROTTLE_CLASSES` en settings.py — throttles solo se aplican donde se declaran explícitamente.

**Comportamiento real hoy:** Un actor puede enviar requests ilimitados a `POST /billing/start-subscription` con emails diferentes y crear usuarios + negocios masivamente. El único costo para el servidor es la creación de registros en DB + llamadas a la API de MercadoPago.

**Riesgo real en producción:** Spam de cuentas, posible facturación no deseada en MercadoPago (cada request crea un preapproval plan en MP), y crecimiento descontrolado de la DB.

**Nota atenuante:** El endpoint tiene lógica de idempotencia (si el mismo email+plan ya tiene sesión abierta, la reutiliza). Esto limita el daño por email repetido, pero no por emails diferentes.

**Qué habría que cambiar:** Agregar `throttle_classes = [AnonRateThrottle]` con un rate restrictivo (ej. 3/min por IP).

**Nivel de certeza:** **Confirmado por código** — no hay throttle en la clase ni en el default global.

---

## RATE-1 — No hay rate limiting en login, register, forgot-password

| Campo | Valor |
|---|---|
| **Severidad** | ALTO |
| **Conclusión** | Los endpoints `LoginView`, `RegisterView`, `ForgotPasswordView`, `ResetPasswordView` no tienen throttles. Solo `EmployeeLoginView` tiene throttle (10/min). |

**Archivos involucrados:**

| Archivo | Relevancia |
|---|---|
| `apps/accounts/views.py` L190-191 | `LoginView`: `permission_classes = [AllowAny]` — sin throttle |
| `apps/accounts/views.py` L220-221 | `RegisterView`: `permission_classes = [AllowAny]` — sin throttle |
| `apps/accounts/views.py` L461-462 | `ForgotPasswordView`: `permission_classes = [AllowAny]` — sin throttle |
| `apps/accounts/views.py` L495-496 | `ResetPasswordView`: `permission_classes = [AllowAny]` — sin throttle |
| `config/settings.py` L141-150 | `REST_FRAMEWORK` — sin `DEFAULT_THROTTLE_CLASSES`, solo 2 rates (`employee_login`, `employee_change_pin`) |

**Evidencia concreta:**

```python
# config/settings.py L135-150
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [...],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticatedOrReadOnly',
    ],
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_THROTTLE_RATES': {
        'employee_login':      '10/minute',  # ← SOLO para EmployeeLoginView
        'employee_change_pin': '5/minute',   # ← SOLO para employee PIN
    },
    # ← NO HAY 'DEFAULT_THROTTLE_CLASSES'
}
```

```python
# accounts/views.py — las 4 views críticas
class LoginView(APIView):
    permission_classes = [AllowAny]           # ← sin throttle_classes
    authentication_classes: list = []

class RegisterView(APIView):
    permission_classes = [AllowAny]           # ← sin throttle_classes
    authentication_classes: list = []

class ForgotPasswordView(APIView):
    permission_classes = [AllowAny]           # ← sin throttle_classes
    authentication_classes: list = []

class ResetPasswordView(APIView):
    permission_classes = [AllowAny]           # ← sin throttle_classes
    authentication_classes: list = []
```

**Comportamiento real hoy:** Un atacante puede:
1. Brute-force `LoginView` sin límite de intentos (prueba passwords contra un email conocido)
2. Spam `RegisterView` para crear cuentas masivas
3. Spam `ForgotPasswordView` para generar emails de reset masivos (aunque la respuesta es siempre 200 para anti-enumeración, genera carga en el servicio de email)

**Riesgo real en producción:** Brute-force de credenciales es el riesgo principal. El login devuelve feedback diferenciado (`"Credenciales inválidas"` vs `"Usuario inactivo"`) que permite confirmar existencia de cuentas activas vs inactivas.

**Nota:** `ForgotPasswordView` tiene buena práctica de anti-enumeración (siempre retorna 200), pero sin throttle igualmente permite spam.

**Qué habría que cambiar:**
1. Agregar `'DEFAULT_THROTTLE_CLASSES': ['rest_framework.throttling.AnonRateThrottle']` con rate `'anon': '20/minute'` en settings.py
2. Agregar throttles específicos por endpoint:
   - `LoginView`: 5/min por IP
   - `RegisterView`: 3/min por IP
   - `ForgotPasswordView`: 3/min por IP
   - `ResetPasswordView`: 5/min por IP

**Nivel de certeza:** **Confirmado por código** — no hay throttle en ninguno de los 4 endpoints.

---

## Tabla Final de Validación

| Hallazgo | Severidad final | Bloquea producción | Prioridad remediación | Esfuerzo |
|---|---|---|---|---|
| **RBAC-1** | **REVOCADO** | No (hallazgo falso) | N/A | N/A |
| **USR-1** | CRÍTICO | **Sí** — sin invitación no hay multi-seat | 1 | Alto |
| **JWT-1** | CRÍTICO | **Sí** — tokens irrevocables por 7 días | 2 | Bajo |
| **JWT-2** | CRÍTICO | **Sí** — logout no funciona server-side | 2 (junto con JWT-1) | Bajo |
| **JWT-3** | ALTO | No — requiere compromiso previo de token | 3 (después de JWT-1/2) | Bajo |
| **RATE-1** | ALTO | **Sí** — brute-force sin protección | 2 | Bajo |
| **BIL-1** | ALTO → MEDIO | No — funciona hoy, es deuda técnica | 4 | Medio |
| **BIL-2** | ALTO → MEDIO | No — depende del estado de migración legacy | 4 (junto con BIL-1) | Medio |
| **BIL-3** | MEDIO | No — atenuado por idempotencia por email | 3 | Bajo |

### Notas sobre la tabla

- **"Bloquea producción"** = ¿es explotable hoy con impacto directo en usuarios reales?
- **JWT-1 + JWT-2** se resuelven juntos (activar blacklist + modificar logout). Esfuerzo bajo porque solo son cambios de configuración + 5 líneas de código.
- **RATE-1** es bajo esfuerzo: agregar `DEFAULT_THROTTLE_CLASSES` en settings + `throttle_classes` en 4 views.
- **USR-1** es alto esfuerzo: requiere diseñar modelo de invitación, endpoint, email transaccional, token de aceptación, UI frontend.
- **BIL-1 y BIL-2** se reclasifican de ALTO a MEDIO porque el sistema funciona correctamente hoy (asumiendo que todos los negocios tienen `business.Subscription` legacy creado). El riesgo es futuro (durante migración a V2).
