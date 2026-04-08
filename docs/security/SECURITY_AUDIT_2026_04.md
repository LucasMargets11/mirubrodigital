# 🔒 AUDITORÍA TÉCNICA COMPLETA — Mi Rubro SaaS

**Fecha:** 2026-04-03  
**Auditor:** Principal Security Engineer + Backend Architect + Cloud FinOps  
**Scope:** Auth, Backend, Frontend, Infra (AWS), DB, Redis, Observabilidad, Costos  

---

## 1. 🔍 DIAGNÓSTICO GENERAL

### Nivel de madurez: **MEDIUM** (con debilidades críticas en auth público)

El sistema tiene una base sólida en varias áreas (admin auth con 3D rate limiting, MFA con TOTP, audit logging, timing attack mitigation), pero presenta **brechas críticas en los endpoints de autenticación pública** (login, register, forgot-password) que son los más expuestos a ataques.

### Riesgos Críticos — Top 5

| # | Riesgo | Impacto |
|---|--------|---------|
| 1 | **Zero rate limiting en login/register/forgot-password** | Brute-force, credential stuffing, DoS por hashing |
| 2 | **Enumeración de usuarios via registro** | Cosecha masiva de emails válidos |
| 3 | **DEBUG=True por defecto en producción** | Exposición de SQL, settings, stack traces |
| 4 | **Sin connection pooling en PostgreSQL** | Agotamiento de conexiones bajo carga |
| 5 | **Sin Content-Security-Policy en frontend** | XSS, data exfiltration |

### ¿Qué podría romper el sistema HOY?

1. **Credential stuffing a /api/v1/auth/login/**: Un atacante con una lista de credenciales filtradas puede probar miles de combinaciones/minuto. Cada intento ejecuta `PBKDF2(260K iterations)` → CPU exhaustion. Sin rate limit, el backend colapsa.
2. **Registration flood a /api/v1/auth/register/**: Crear miles de cuentas basura → llena la DB, satura envío de emails de verificación, costos de SES/SMTP.
3. **Password reset flood a /api/v1/auth/forgot-password/**: Aunque no enumera emails, cada request válida genera un token SHA-256, escribe en DB, y dispara un email → costo + saturación.

---

## 2. 🚨 VULNERABILIDADES CRÍTICAS

### VULN-01: Sin Rate Limiting en Auth Endpoints Públicos

- **Severidad:** 🔴 CRITICAL
- **Endpoints afectados:**
  - `POST /api/v1/auth/login/` — [views.py](../../services/api/src/apps/accounts/views.py) LoginView
  - `POST /api/v1/auth/register/` — RegisterView
  - `POST /api/v1/auth/forgot-password/` — ForgotPasswordView
  - `POST /api/v1/auth/reset-password/` — ResetPasswordView
  - `POST /api/v1/auth/verify-email/` — VerifyEmailView
  - `POST /api/v1/auth/refresh/` — RefreshView
- **Impacto:** Brute-force, credential stuffing, CPU DoS via password hashing
- **Probabilidad:** ALTA — estos endpoints son públicos y descubribles
- **Explotación real:**
  ```bash
  # Credential stuffing: 1000 intentos/minuto sin bloqueo
  for cred in credentials_list; do
    curl -X POST https://api.mirubro.com/api/v1/auth/login/ \
      -d '{"email":"'$email'","password":"'$pass'"}'
  done
  # Cada request ejecuta PBKDF2 con 260K iteraciones → CPU spike
  ```
- **Evidencia:** LoginView no tiene `throttle_classes`. No hay `DEFAULT_THROTTLE_CLASSES` global en settings.py.

---

### VULN-02: Enumeración de Usuarios via Registro

- **Severidad:** 🔴 CRITICAL
- **Ubicación:** [views.py RegisterView](../../services/api/src/apps/accounts/views.py) línea ~267
- **Código vulnerable:**
  ```python
  if User.objects.filter(email__iexact=email).exists():
      return Response({'detail': 'El email ya está registrado'}, status=400)
  ```
- **Impacto:** Atacante puede verificar si cualquier email está registrado en la plataforma
- **Probabilidad:** ALTA — trivial de explotar, sin rate limit
- **Explotación:**
  ```bash
  # Enumerar emails de una empresa competidora
  for email in target_emails; do
    resp=$(curl -s -o /dev/null -w "%{http_code}" \
      -X POST https://api.mirubro.com/api/v1/auth/register/ \
      -d '{"email":"'$email'","password":"Test1234!"}')
    if [ "$resp" = "400" ]; then echo "EXISTE: $email"; fi
  done
  ```
- **Nota:** ForgotPasswordView está bien (responde 200 siempre). LoginView también (responde "Credenciales inválidas" en ambos casos).

---

### VULN-03: DEBUG=True por Defecto

- **Severidad:** 🔴 CRITICAL
- **Ubicación:** [settings.py](../../services/api/src/config/settings.py) línea ~25
- **Código:**
  ```python
  DEBUG = os.getenv('DJANGO_DEBUG', 'True').lower() == 'true'
  ```
- **Impacto:** Si `DJANGO_DEBUG` no está configurado en producción → Django expone SQL queries, settings completos, stack traces con variables locales, lista de URLs
- **Probabilidad:** MEDIA — depende de si el env var está seteado en prod
- **Explotación:** Cualquier 500 error muestra el debug page con settings, DB connection strings, SECRET_KEY potencialmente visible

---

### VULN-04: Solo PBKDF2 — Sin Argon2

- **Severidad:** 🟠 HIGH
- **Ubicación:** [settings.py](../../services/api/src/config/settings.py) — `PASSWORD_HASHERS` no definido
- **Impacto:** PBKDF2-SHA256 es vulnerable a ataques por GPU. Argon2id es memory-hard y resiste ASICs/GPUs.
- **Probabilidad:** MEDIA — requiere breach de la DB primero
- **Costo de ataque actual:** Con PBKDF2 a 260K iterations, un atacante con 4x RTX 4090 puede probar ~50K hashes/segundo. Con Argon2id (memory=64MB), baja a ~100/segundo.

---

### VULN-05: Refresh Token No Se Invalida Tras Rotación

- **Severidad:** 🟠 HIGH
- **Ubicación:** [settings.py](../../services/api/src/config/settings.py) SIMPLE_JWT config
- **Código:**
  ```python
  'ROTATE_REFRESH_TOKENS': True,
  'BLACKLIST_AFTER_ROTATION': False,
  ```
- **Impacto:** Un refresh token robado sigue siendo válido incluso después de que el usuario legítimo haga refresh. El atacante puede mantener sesión indefinidamente.
- **Probabilidad:** MEDIA — requiere interceptar un refresh token
- **Explotación:** Intercept refresh token (MITM, XSS en subdomain, log leak) → usar indefinidamente porque nunca se invalida.

---

### VULN-06: Sin Security Headers en Frontend (Next.js)

- **Severidad:** 🟠 HIGH
- **Ubicación:** [next.config.mjs](../../apps/web/next.config.mjs) — sin headers configurados
- **Impacto:**
  - Sin `Content-Security-Policy` → XSS puede cargar scripts externos
  - Sin `Permissions-Policy` → acceso a cámara/micrófono/geolocalización
  - Sin `X-Content-Type-Options` en frontend (solo el backend lo setea)
- **Probabilidad:** MEDIA — depende de existencia de XSS

---

### VULN-07: Sin Connection Pooling en PostgreSQL

- **Severidad:** 🟠 HIGH
- **Ubicación:** [settings.py](../../services/api/src/config/settings.py) DATABASES config
- **Código:**
  ```python
  DATABASES = {
    'default': {
      'ENGINE': 'django.db.backends.postgresql',
      ...
      # Sin CONN_MAX_AGE, sin pgbouncer, sin django-db-connection-pool
    }
  }
  ```
- **Impacto:** Cada request abre y cierra conexión. Bajo carga (100+ requests concurrentes), se agotan los 100 connections default de PostgreSQL → 503 errors.
- **Probabilidad:** ALTA cuando el sistema escale

---

### VULN-08: Employee Login — Rate Limit por UUID, No por IP

- **Severidad:** 🟡 MEDIUM
- **Ubicación:** [authentication.py](../../services/api/src/apps/accounts/authentication.py) EmployeeScopedThrottle
- **Código:**
  ```python
  def get_cache_key(self, request, view):
      employee = getattr(request, 'employee', None)
      if employee is not None:
          ident = str(employee.pk)
      else:
          ident = self.get_ident(request)  # IP fallback
  ```
- **Impacto:** En el endpoint de login (`/api/v1/auth/employee-login/`), el employee aún no está autenticado → siempre cae al fallback de IP. Un atacante puede probar 10 PINs/minuto por IP. Con rotación de IPs (proxies), el rate limit es inefectivo.
- **Probabilidad:** MEDIA — PINs de 4-8 dígitos son relativamente cortos
- **Explotación:** PIN de 4 dígitos = 10,000 combinaciones. A 10/min/IP con 100 IPs = 1000/min → PIN crackeado en ~10 minutos.

---

### VULN-09: WAF Solo Protege Admin Endpoints

- **Severidad:** 🟡 MEDIUM
- **Ubicación:** [waf.tf](../../infra/terraform/waf.tf)
- **Detalle:** El WAF tiene rate limiting específico solo para `/api/v1/platform-admin/auth/` (100 req/5min). El rate limit global (2000 req/5min/IP) aplica a todo, pero es muy permisivo para endpoints de auth.
- **Impacto:** Un atacante puede hacer 2000 requests cada 5 minutos al login de owners sin ser bloqueado por WAF.

---

### VULN-10: Frontend Sin Global Error Boundary

- **Severidad:** 🟡 MEDIUM
- **Ubicación:** [layout.tsx](../../apps/web/src/app/layout.tsx), [providers.tsx](../../apps/web/src/app/providers.tsx)
- **Impacto:** Un error de React no capturado muestra stack trace en producción (si no se configura error.tsx). Puede exponer rutas internas, nombres de componentes, state.
- **Probabilidad:** BAJA — pero ocurre

---

### VULN-11: EmployeeProfile.login_code_hash Sin Índice

- **Severidad:** 🟡 LOW
- **Ubicación:** [models.py](../../services/api/src/apps/accounts/models.py) EmployeeProfile
- **Detalle:** `login_code_hash` no tiene `db_index=True`. Sin embargo, el lookup se hace por `(business, employee_code)` que SÍ tiene índice, y luego `check_password` se hace en memoria. **No es un problema de performance**, pero el diseño es correcto.

---

## 3. 🛠️ PLAN DE REMEDIACIÓN

### Fase 1: URGENTE (1-3 días)

#### T1.1 — Rate Limiting en Auth Endpoints Públicos
- **Qué:** Crear throttle classes para login, register, forgot-password, reset-password
- **Dónde:** Backend — `services/api/src/apps/accounts/throttles.py` (nuevo)
- **Cómo:**

```python
# services/api/src/apps/accounts/throttles.py
from rest_framework.throttling import AnonRateThrottle

class LoginRateThrottle(AnonRateThrottle):
    """5 intentos/minuto por IP para login."""
    rate = '5/minute'

class RegisterRateThrottle(AnonRateThrottle):
    """3 intentos/minuto por IP para registro."""
    rate = '3/minute'

class ForgotPasswordRateThrottle(AnonRateThrottle):
    """3 intentos/minuto por IP para forgot-password."""
    rate = '3/minute'

class ResetPasswordRateThrottle(AnonRateThrottle):
    """5 intentos/minuto por IP para reset-password."""
    rate = '5/minute'

class VerifyEmailRateThrottle(AnonRateThrottle):
    """5 intentos/minuto por IP para verificación de email."""
    rate = '5/minute'

class RefreshTokenRateThrottle(AnonRateThrottle):
    """10 intentos/minuto por IP para refresh."""
    rate = '10/minute'
```

Luego agregar a cada view:
```python
class LoginView(APIView):
    throttle_classes = [LoginRateThrottle]
    ...
```

- **Impacto:** Bloquea brute-force y credential stuffing inmediatamente

#### T1.2 — Fix Enumeración de Usuarios en Register
- **Qué:** Siempre responder HTTP 201 sin revelar si el email existe
- **Dónde:** Backend — [views.py RegisterView](../../services/api/src/apps/accounts/views.py)
- **Cómo:**

```python
class RegisterView(APIView):
    throttle_classes = [RegisterRateThrottle]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email'].lower()
        password = serializer.validated_data['password']

        if User.objects.filter(email__iexact=email).exists():
            # Anti-enumeración: misma respuesta que éxito
            # No enviar email de verificación (ya existe)
            return Response({
                'status': 'created',
                'message': 'Revisa tu email para verificar la cuenta.',
            }, status=status.HTTP_201_CREATED)

        user = User.objects.create_user(username=email, email=email, password=password)
        profile, _ = AccountProfile.objects.get_or_create(user=user)
        token = profile.generate_verification_token()
        EmailService.send_verification_email(user, token)

        return Response({
            'status': 'created',
            'message': 'Revisa tu email para verificar la cuenta.',
        }, status=status.HTTP_201_CREATED)
```

- **Impacto:** Elimina enumeración de usuarios

#### T1.3 — Fix DEBUG Default
- **Qué:** Cambiar default de `DEBUG` a `False`
- **Dónde:** Backend — [settings.py](../../services/api/src/config/settings.py) línea ~25
- **Cómo:**
```python
DEBUG = os.getenv('DJANGO_DEBUG', 'False').lower() == 'true'
```
- **Impacto:** Si se olvidan de setear el env var en prod, el sistema es seguro por defecto

#### T1.4 — Rate Limiting Dimensional para Login de Owners
- **Qué:** Implementar rate limiting 3D (como el de admin) para el login de owners
- **Dónde:** Backend — reutilizar o adaptar `admin_rate_limiter.py`
- **Cómo:**

```python
# services/api/src/apps/accounts/auth_rate_limiter.py
# Clonar admin_rate_limiter.py con thresholds más permisivos:
# IP+email: 10 intentos, 15 min
# Email: 20 intentos, 30 min
# IP: 50 intentos, 10 min
# Reutilizar la misma estructura de check_rate_limit/record_failed_attempt/reset_on_success
```

Integrar en LoginView:
```python
class LoginView(APIView):
    throttle_classes = [LoginRateThrottle]

    def post(self, request):
        identifier = ...
        ip = _get_client_ip(request)
        
        # Check 3D rate limit
        rl_result = auth_rate_limiter.check_rate_limit(ip, identifier)
        if not rl_result.allowed:
            return Response(
                {'detail': 'Demasiados intentos. Intenta de nuevo más tarde.'},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
                headers={'Retry-After': str(rl_result.retry_after)},
            )
        
        user = authenticate(...)
        if user is None:
            auth_rate_limiter.record_failed_attempt(ip, identifier)
            return Response({'detail': 'Credenciales inválidas'}, status=400)
        
        auth_rate_limiter.reset_on_success(ip, identifier)
        ...
```

- **Impacto:** Protección dimensional contra credential stuffing + brute force

#### T1.5 — WAF: Rate Limit para Auth Endpoints Públicos
- **Qué:** Agregar regla WAF específica para `/api/v1/auth/`
- **Dónde:** Infra — [waf.tf](../../infra/terraform/waf.tf)
- **Cómo:**
```hcl
rule {
  name     = "auth-endpoints-rate-limit"
  priority = 5  # Before admin rule

  action {
    block {}
  }

  statement {
    rate_based_statement {
      limit              = 50  # 50 requests per 5 minutes per IP
      aggregate_key_type = "IP"

      scope_down_statement {
        byte_match_statement {
          search_string         = "/api/v1/auth/"
          positional_constraint = "STARTS_WITH"
          field_to_match {
            uri_path {}
          }
          text_transformation {
            priority = 0
            type     = "LOWERCASE"
          }
        }
      }
    }
  }

  visibility_config {
    sampled_requests_enabled   = true
    cloudwatch_metrics_enabled = true
    metric_name                = "mirubro-auth-rate-limit"
  }
}
```
- **Impacto:** Primera línea de defensa antes de que el request llegue al backend

---

### Fase 2: CORTO PLAZO (1-2 semanas)

#### T2.1 — Argon2 Password Hasher
- **Qué:** Agregar Argon2id como hasher principal
- **Dónde:** Backend — [settings.py](../../services/api/src/config/settings.py)
- **Cómo:**
```bash
pip install argon2-cffi
```
```python
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.Argon2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher',
]
```
Los passwords existentes se re-hashean automáticamente en el próximo login (Django lo hace transparente).
- **Impacto:** 500x mayor resistencia a ataques por GPU

#### T2.2 — Blacklist Refresh Tokens Tras Rotación
- **Qué:** Habilitar blacklist de refresh tokens
- **Dónde:** Backend — [settings.py](../../services/api/src/config/settings.py)
- **Cómo:**
```python
INSTALLED_APPS = [
    ...
    'rest_framework_simplejwt.token_blacklist',
]

SIMPLE_JWT = {
    ...
    'BLACKLIST_AFTER_ROTATION': True,
}
```
```bash
python manage.py migrate  # Crea la tabla de blacklist
```
Agregar tarea Celery para limpiar tokens expirados:
```python
CELERY_BEAT_SCHEDULE['flush-expired-tokens'] = {
    'task': 'accounts.flush_expired_tokens',
    'schedule': crontab(hour='3', minute='0'),  # Diario a las 3am
}
```
- **Impacto:** Un refresh token robado deja de funcionar cuando el usuario legítimo hace refresh

#### T2.3 — Security Headers en Next.js
- **Qué:** Agregar CSP y security headers en next.config.mjs
- **Dónde:** Frontend — [next.config.mjs](../../apps/web/next.config.mjs)
- **Cómo:**
```javascript
const nextConfig = {
  async headers() {
    return [
      {
        source: '/(.*)',
        headers: [
          { key: 'X-Content-Type-Options', value: 'nosniff' },
          { key: 'X-Frame-Options', value: 'DENY' },
          { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
          { key: 'Permissions-Policy', value: 'camera=(), microphone=(), geolocation=()' },
          {
            key: 'Content-Security-Policy',
            value: [
              "default-src 'self'",
              "script-src 'self' 'unsafe-inline' 'unsafe-eval'",  // Ajustar post-audit
              "style-src 'self' 'unsafe-inline'",
              `connect-src 'self' ${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}`,
              "img-src 'self' data: blob: https://via.placeholder.com https://images.unsplash.com",
              "font-src 'self'",
              "frame-ancestors 'none'",
            ].join('; '),
          },
        ],
      },
    ];
  },
  // ... rest of config
};
```
- **Impacto:** Mitiga XSS, clickjacking, data exfiltration

#### T2.4 — Connection Pooling PostgreSQL
- **Qué:** Agregar `CONN_MAX_AGE` y considerar PgBouncer
- **Dónde:** Backend — [settings.py](../../services/api/src/config/settings.py)
- **Cómo:**
```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('POSTGRES_DB', 'mirubro'),
        'USER': os.getenv('POSTGRES_USER', 'mirubro'),
        'PASSWORD': os.getenv('POSTGRES_PASSWORD', 'mirubro'),
        'HOST': os.getenv('POSTGRES_HOST', 'postgres'),
        'PORT': os.getenv('POSTGRES_PORT', '5432'),
        'CONN_MAX_AGE': int(os.getenv('DB_CONN_MAX_AGE', '600')),  # 10 min
        'CONN_HEALTH_CHECKS': True,  # Django 4.1+
    }
}
```
Para producción, agregar PgBouncer como sidecar:
```yaml
# docker-compose.yml
pgbouncer:
  image: edoburu/pgbouncer:latest
  environment:
    DATABASE_URL: postgres://mirubro:mirubro@postgres:5432/mirubro
    POOL_MODE: transaction
    MAX_CLIENT_CONN: 200
    DEFAULT_POOL_SIZE: 25
  ports:
    - '6432:6432'
```
- **Impacto:** Reduce conexiones a PostgreSQL de N (workers × requests) a 25 (pool size)

#### T2.5 — Employee Login Rate Limiting Dimensional
- **Qué:** Implementar rate limiting por IP + business_code + employee_code para PIN login
- **Dónde:** Backend — `employee_views.py`
- **Cómo:**
```python
# En employee_views.py, antes del authenticate:
EMPLOYEE_RL_PREFIX = 'emp_rl'

def _employee_rate_limit_key(ip, business_code, emp_code):
    combo = f"{ip}:{business_code}:{emp_code}"
    return f"{EMPLOYEE_RL_PREFIX}:{hashlib.sha256(combo.encode()).hexdigest()[:20]}"

# Limitar: 5 intentos por IP+business+employee en 15 minutos
key = _employee_rate_limit_key(ip, business_code, employee_code)
attempts = cache.get(key, 0)
if attempts >= 5:
    return Response({'error': 'Demasiados intentos.'}, status=429)

# En failure:
cache.set(key, attempts + 1, timeout=900)  # 15 min
```
- **Impacto:** Previene brute-force de PINs de 4 dígitos (10K combinaciones)

#### T2.6 — Frontend Error Boundary + Rate Limit UX
- **Qué:** Agregar global error boundary y manejar HTTP 429 en el cliente
- **Dónde:** Frontend — `apps/web/src/app/error.tsx` y `lib/api/client.ts`
- **Cómo:**

```typescript
// apps/web/src/app/error.tsx
'use client';
export default function GlobalError({ error, reset }: { error: Error; reset: () => void }) {
  return (
    <div className="flex min-h-screen items-center justify-center">
      <div className="text-center">
        <h2 className="text-xl font-semibold">Algo salió mal</h2>
        <button onClick={reset} className="mt-4 rounded bg-blue-600 px-4 py-2 text-white">
          Reintentar
        </button>
      </div>
    </div>
  );
}
```

```typescript
// En lib/api/client.ts — agregar manejo de 429
if (response.status === 429) {
  const retryAfter = response.headers.get('Retry-After');
  throw new ApiError(429, {
    detail: `Demasiados intentos. Intenta en ${retryAfter || '60'} segundos.`,
    retryAfter: parseInt(retryAfter || '60', 10),
  });
}
```
- **Impacto:** Mejor UX ante rate limiting, evita retries infinitos

---

### Fase 3: MEDIANO PLAZO (1-2 meses)

#### T3.1 — CAPTCHA Adaptativo
- **Qué:** Integrar hCaptcha (privacy-friendly) o Turnstile (Cloudflare) en login y registro
- **Dónde:** Frontend + Backend
- **Cómo:**
  - Frontend: Mostrar CAPTCHA solo después de N intentos fallidos (detectar 429 responses)
  - Backend: Nuevo campo `captcha_token` en LoginSerializer/RegisterSerializer
  - Validar server-side via API call a hCaptcha/Turnstile
  - Threshold: Activar CAPTCHA tras 3 intentos fallidos (tracked en Redis por IP)
- **Impacto:** Bloquea bots automatizados sin afectar UX normal

#### T3.2 — Observabilidad Completa
- **Qué:** Structured logging + métricas + alertas
- **Dónde:** Backend + Infra
- **Cómo:** Ver sección 6 (Métricas y Alertas)
- **Impacto:** Detectar ataques en tiempo real

#### T3.3 — Risk-Based Authentication
- **Qué:** Evaluar riesgo del login basado en IP, device fingerprint, hora, geolocalización
- **Dónde:** Backend — nuevo middleware
- **Cómo:**
  - Calcular risk score (0-100) basado en: nueva IP, nuevo user agent, hora inusual, geolocalización diferente
  - Score > 50 → pedir MFA
  - Score > 80 → bloquear + notificar email
  - Almacenar fingerprints en Redis (TTL 30 días)
- **Impacto:** Detecta account takeover incluso con credenciales válidas

#### T3.4 — Account lockout con notificación
- **Qué:** Tras N intentos fallidos, bloquear cuenta temporalmente y enviar email al usuario
- **Dónde:** Backend
- **Cómo:**
  - 10 intentos fallidos en 1 hora → bloquear cuenta 30 minutos
  - Enviar email: "Detectamos intentos de acceso sospechosos a tu cuenta"
  - Incluir link para desbloquear si es legítimo
  - No confundir con el rate limit por IP (este es por cuenta)
- **Impacto:** Protege cuentas individuales de credential stuffing

#### T3.5 — Redis Memory Policy Optimización
- **Qué:** Configurar `maxmemory-policy` y monitorear hot keys
- **Dónde:** Infra — ElastiCache parameter group
- **Cómo:**
```hcl
resource "aws_elasticache_parameter_group" "main" {
  name   = "mirubro-redis-params"
  family = "redis7"

  parameter {
    name  = "maxmemory-policy"
    value = "volatile-lru"  # Solo evicta keys con TTL
  }
}
```
- **Impacto:** Previene OOM en Redis, las rate limit keys sobreviven

---

## 4. 🧱 DISEÑO PROPUESTO — TARGET ARCHITECTURE

### Flujo de Login Seguro End-to-End

```
┌─────────────┐     ┌──────┐     ┌──────┐     ┌─────────┐     ┌──────────┐
│   Browser   │────▶│  WAF │────▶│  ALB │────▶│ Django  │────▶│ Postgres │
│  (Next.js)  │     │      │     │      │     │  + DRF  │     │          │
└─────────────┘     └──────┘     └──────┘     └─────────┘     └──────────┘
       │                │                           │
       │                │              ┌────────────┤
       │                │              │            │
       │                ▼              ▼            │
       │           ┌──────┐     ┌──────────┐       │
       │           │ CW   │     │  Redis   │       │
       │           │ Logs │     │ (cache)  │       │
       │           └──────┘     └──────────┘       │
       │                                           │
       ▼                                           ▼
  ┌─────────┐                               ┌──────────┐
  │ hCaptcha│                               │  Celery  │
  │ (abuse) │                               │ (emails) │
  └─────────┘                               └──────────┘
```

### Capas de Protección (Defense in Depth)

```
Capa 1: WAF  ──────────  Rate limit global + auth-specific (50 req/5min/IP)
                          Bot detection (AWS Bot Control - futuro)
                          Geo-blocking si necesario

Capa 2: ALB  ──────────  Request size limits (16KB body max para auth)
                          Connection timeouts (30s)
                          Slow POST protection

Capa 3: Django ─────────  DRF Throttle (per-view, per-IP)
                          3D Rate Limiter (IP + email + combo) via Redis
                          CAPTCHA validation (después de N fallos)
                          Argon2 password hashing
                          Timing attack mitigation
                          Anti-enumeration responses

Capa 4: Redis ─────────  Rate limit counters (TTL auto-cleanup)
                          MFA challenge tokens (5 min TTL)
                          OTP replay prevention (90s TTL)
                          Failed attempt counters per account

Capa 5: Postgres ──────  Indexed lookups (email, employee_code)
                          Connection pooling (PgBouncer)
                          Audit logs (all auth events)

Capa 6: Celery ────────  Async email delivery (non-blocking)
                          Token cleanup (daily)
                          Audit log archival (futuro)
```

### Flujo Ideal de Login con Protecciones

```
1. Request llega al WAF
   ├── Check: Rate limit global (2000/5min/IP) → block if exceeded
   ├── Check: Rate limit auth (50/5min/IP) → block if exceeded
   ├── Check: AWS Managed Rules → block bad inputs
   └── Pass → ALB

2. ALB forwards to Django
   ├── Check: Request body < 16KB → reject oversized
   └── Pass → View

3. LoginView receives request
   ├── Check: DRF Throttle (5/min/IP) → 429 if exceeded
   ├── Check: 3D Rate Limiter (Redis)
   │   ├── IP+email combo (10 attempts, 15 min) → 429 + Retry-After
   │   ├── Email global (20 attempts, 30 min) → 429 + Retry-After
   │   └── IP global (50 attempts, 10 min) → 429 + Retry-After
   ├── [If CAPTCHA threshold reached] Check: CAPTCHA token → 400 if invalid
   ├── Validate: authenticate(email, password) → Argon2 verify
   │   ├── SUCCESS:
   │   │   ├── Reset IP+email and email counters
   │   │   ├── Generate JWT (15 min access + 7 day refresh)
   │   │   ├── Set httpOnly+Secure+SameSite cookies
   │   │   ├── Audit log: LOGIN_SUCCESS
   │   │   └── Return 200 + cookies
   │   └── FAILURE:
   │       ├── Record failed attempt (all 3 dimensions)
   │       ├── If threshold breached → set cooldown
   │       ├── Add artificial delay (200-500ms random)
   │       ├── Audit log: LOGIN_FAILED
   │       └── Return 400 "Credenciales inválidas" (generic)
```

### Uso Correcto de Redis

```
Redis DB 0: Celery broker (task queue)
Redis DB 1: Django cache (rate limits, MFA tokens)

Keys structure:
  mirubro:auth_rl:ip:{ip}                    → int (attempt count)
  mirubro:auth_rl:em:{email_hash}            → int (attempt count)
  mirubro:auth_rl:ie:{ip}:{email_hash}       → int (attempt count)
  mirubro:auth_rl:*:cd                       → int (cooldown expiry timestamp)
  mirubro:admin_rl:*                         → int (admin rate limits)
  mirubro:emp_rl:{hash}                      → int (employee PIN attempts)
  mirubro:mfa_token:{user_id}               → str (challenge token, 5 min TTL)
  mirubro:mfa_used:{user_id}:{otp}          → bool (replay prevention, 90s TTL)
  mirubro:captcha_threshold:{ip}            → int (failed attempts before CAPTCHA)

TTL policy: ALL rate limit keys MUST have TTL (never persist indefinitely)
Memory policy: volatile-lru (evict keys with TTL first)
Max memory: 256MB (sufficient for 100K concurrent rate limit entries)
```

---

## 5. 📉 OPTIMIZACIÓN DE COSTOS

### Quick Wins (Implementación inmediata)

| Optimización | Ahorro estimado | Cómo |
|-------------|----------------|------|
| Rate limit en auth endpoints | 30-60% CPU en ataques | Evita procesar password hashing innecesario |
| `CONN_MAX_AGE=600` | 20-40% latencia DB | Reutiliza conexiones en vez de abrir/cerrar por request |
| WAF auth rate limit (50/5min) | Variable | Bloquea tráfico abusivo antes de que llegue a compute |
| `DEBUG=False` default | Evita leak → evita breach → evita costos de incidente | Un solo leak puede costar más que toda la infraestructura mensual |

### Cambios Estructurales

| Optimización | Ahorro estimado | Inversión |
|-------------|----------------|-----------|
| PgBouncer | 50% menos conexiones a RDS → menor tier possible | 2-4 horas setup |
| Argon2 con tuning | Mayor costo por hash PERO rate limit reduce volumen | 1 hora config |
| Redis `volatile-lru` | Evita upgrade de ElastiCache por crecimiento descontrolado | 30 min terraform |
| Celery: emails async | Reduce latencia de auth endpoints → menos compute time | Ya implementado parcialmente |

### Riesgos de Sobrecosto Actuales

1. **Sin rate limit en login** → Un ataque de credential stuffing genera costo de CPU por cada PBKDF2 hash (260K iteraciones). Con 1000 req/min, un t3.medium satura en minutos → auto-scaling crea instancias → **costo se multiplica sin generar valor**.

2. **Sin connection pooling** → Cada request abre conexión TCP a PostgreSQL. RDS cobra por IOPS y CPU. Conexiones innecesarias = IOPS innecesarios = **$$$**.

3. **Redis sin maxmemory** → Rate limit keys se acumulan. Si el set de keys activas supera la memoria del nodo → upgrade de ElastiCache de `cache.t4g.micro` ($12/mo) a `cache.t4g.small` ($24/mo) o más.

4. **Emails síncronos en auth** → `send_verification_email()` bloquea el request. Si SES/SMTP tarda, el worker queda ocupado más tiempo → más workers necesarios → más compute cost.

### Estimación de Ahorro por Fase

| Fase | Costo Actual (estimado) | Con fixes | Ahorro |
|------|------------------------|-----------|--------|
| Compute (ECS/EC2) | $150-300/mo | $100-200/mo | ~33% |
| RDS PostgreSQL | $50-100/mo | $40-80/mo | ~20% |
| ElastiCache Redis | $12-24/mo | $12/mo (sin upgrades) | Evita escalada |
| Data transfer | $20-50/mo | $15-30/mo | ~30% (menos tráfico basura) |

---

## 6. 📊 MÉTRICAS Y ALERTAS

### Qué Medir Sí o Sí

#### Auth Endpoints
| Métrica | Fuente | Umbral de Alerta |
|---------|--------|-------------------|
| `auth.login.count` | Django middleware/view | > 500/min = investigar |
| `auth.login.failure_rate` | Failed / Total | > 30% en 5 min = posible ataque |
| `auth.login.latency_p99` | Django timing | > 2s = DB o hashing issue |
| `auth.register.count` | View counter | > 50/min = spam/abuse |
| `auth.rate_limit.triggered` | Rate limiter | > 10/min = ataque activo |
| `auth.mfa.failure_count` | MFA view | > 20/hour = brute-force MFA |
| `auth.employee_login.failure_rate` | Employee view | > 50% en 10 min = PIN spray |

#### Infrastructure
| Métrica | Fuente | Umbral de Alerta |
|---------|--------|-------------------|
| `db.connections.active` | PostgreSQL | > 80% max_connections |
| `db.query.latency_p99` | pg_stat_statements | > 100ms para auth queries |
| `redis.memory.used_pct` | ElastiCache | > 75% = review keys |
| `redis.evictions` | ElastiCache | > 0 = memory pressure |
| `waf.blocked.count` | CloudWatch | > 100/min = DDoS |
| `celery.queue.length` | Celery/Redis | > 100 tasks = backlog |
| `cpu.utilization` | ECS/EC2 | > 70% sustained = scale |

### Señales de Ataque

| Señal | Indicador | Acción |
|-------|-----------|--------|
| Credential stuffing | Alto volumen de login failures desde múltiples IPs, mismas cuentas | WAF block IP range, activar CAPTCHA |
| Password spraying | Bajo volumen de failures por cuenta, pero muchas cuentas distintas | Rate limit por IP + alertar |
| Registration flood | > 30 registros/minuto | CAPTCHA obligatorio, review IPs |
| Token brute-force | Alto volumen a /reset-password/ o /verify-email/ | Rate limit + temporal block |
| Account takeover | Login exitoso desde IP/UA nunca visto + cambio de password inmediato | Notificar usuario, requerir re-auth |
| API scraping | Alto volumen a endpoints de datos con patrones de paginación | WAF + custom rate limit |

### Implementación Recomendada

```python
# services/api/src/apps/accounts/metrics.py
import logging
from django.core.cache import cache

logger = logging.getLogger('security.auth')

def log_auth_event(event_type: str, ip: str, email: str = '', success: bool = False, **extra):
    """Structured security log for auth events."""
    logger.info(
        'auth_event',
        extra={
            'event_type': event_type,  # login, register, forgot_password, etc.
            'ip': ip,
            'email_hash': hashlib.sha256(email.encode()).hexdigest()[:16] if email else '',
            'success': success,
            'timestamp': timezone.now().isoformat(),
            **extra,
        },
    )
```

### Dashboard Necesarios (CloudWatch / Grafana)

1. **Auth Overview**: Login success/failure rate, registro rate, rate limit triggers
2. **Attack Detection**: Failed login heatmap por IP, top IPs bloqueadas, WAF blocks
3. **Performance**: Auth endpoint latency p50/p95/p99, DB query time, Redis ops/sec
4. **Cost Impact**: CPU utilization correlated with auth traffic, DB connections, Redis memory

---

## 7. ✅ CHECKLIST DE IMPLEMENTACIÓN

### Fase 1 — URGENTE (1-3 días)

- [ ] **VULN-01** Crear `throttles.py` con throttle classes para todos los auth endpoints
- [ ] **VULN-01** Agregar `throttle_classes` a LoginView, RegisterView, ForgotPasswordView, ResetPasswordView, VerifyEmailView, RefreshView
- [ ] **VULN-02** Fix RegisterView para no revelar existencia de email
- [ ] **VULN-03** Cambiar `DEBUG` default a `False` en settings.py
- [ ] **T1.4** Implementar `auth_rate_limiter.py` (3D: IP + email + combo) para LoginView
- [ ] **T1.4** Integrar rate limiter en LoginView con Retry-After header
- [ ] **T1.5** Agregar regla WAF para `/api/v1/auth/` (50 req/5min/IP)
- [ ] Verificar que `DJANGO_DEBUG=False` en environment de producción
- [ ] Test: Verificar rate limiting funciona (curl loop)
- [ ] Test: Verificar anti-enumeración en register (misma respuesta)

### Fase 2 — CORTO PLAZO (1-2 semanas)

- [ ] **T2.1** Instalar `argon2-cffi`, configurar `PASSWORD_HASHERS` con Argon2 primero
- [ ] **T2.2** Habilitar `BLACKLIST_AFTER_ROTATION=True` en SIMPLE_JWT
- [ ] **T2.2** Agregar `rest_framework_simplejwt.token_blacklist` a INSTALLED_APPS
- [ ] **T2.2** Ejecutar migrations para tabla de blacklist
- [ ] **T2.2** Agregar tarea Celery para flush de tokens expirados
- [ ] **T2.3** Agregar security headers en `next.config.mjs` (CSP, X-Frame, Permissions-Policy)
- [ ] **T2.4** Configurar `CONN_MAX_AGE=600` en DATABASES
- [ ] **T2.4** Evaluar e implementar PgBouncer para producción
- [ ] **T2.5** Implementar rate limiting dimensional para employee login (IP + business + employee)
- [ ] **T2.6** Crear `error.tsx` global error boundary en Next.js
- [ ] **T2.6** Manejar HTTP 429 en `lib/api/client.ts`
- [ ] Test: Verificar que passwords existentes se re-hashean a Argon2 en login
- [ ] Test: Verificar que refresh token antiguo no funciona tras rotación
- [ ] Test: Verificar CSP no rompe funcionalidad existente

### Fase 3 — MEDIANO PLAZO (1-2 meses)

- [ ] **T3.1** Integrar CAPTCHA adaptativo (hCaptcha/Turnstile) en login y registro
- [ ] **T3.2** Implementar structured logging con `log_auth_event()`
- [ ] **T3.2** Configurar CloudWatch dashboards para auth metrics
- [ ] **T3.2** Crear alertas CloudWatch para umbrales de ataque
- [ ] **T3.3** Implementar risk-based authentication (fingerprint, geolocation, hora)
- [ ] **T3.4** Implementar account lockout con notificación email
- [ ] **T3.5** Configurar Redis `maxmemory-policy` como `volatile-lru` vía parameter group
- [ ] **T3.5** Definir `maxmemory` en ElastiCache (256MB mínimo)
- [ ] Implementar rate limit para `/api/v1/auth/resend-verification/` (3/hora por email)
- [ ] Audit log rotation/archival a S3 (Celery beat task)
- [ ] Penetration testing externo
- [ ] Revisar CORS_ALLOWED_ORIGINS en producción (no wildcard)

---

*Fin de la auditoría. Cada item es directamente convertible en un ticket de desarrollo, tarea de DevOps, o mejora de arquitectura.*
