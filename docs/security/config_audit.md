# Auditoría de configuración sensible — MiRubro Digital

> Fase 2D · Última actualización: 2026-04-07

## Resumen

Se auditaron todos los settings de seguridad en `services/api/src/config/settings.py`.
La base es el flag `_IS_PROD = not DEBUG`, que activa automáticamente los valores seguros cuando `DJANGO_DEBUG` no es `true`.

---

## 1. Django core

| Setting                      | Dev (DEBUG=True)    | Prod (DEBUG=False)         | Estado | Notas |
|------------------------------|---------------------|----------------------------|--------|-------|
| `DEBUG`                      | `True`              | `False`                    | ✅ OK  | Default `False`. Solo activo si `DJANGO_DEBUG=true` explícito. |
| `SECRET_KEY`                 | `'unsafe-secret'`   | Desde `DJANGO_SECRET_KEY`  | ⚠️ Revisar | El fallback `'unsafe-secret'` **nunca** debe usarse en prod. Agregar validación en startup (ver recomendación abajo). |
| `ALLOWED_HOSTS`              | `localhost,127.0.0.1,mirubro-api` | Desde `DJANGO_ALLOWED_HOSTS` | ✅ OK | Debe configurarse en prod con el dominio real. No usa `*`. |
| `SECURE_SSL_REDIRECT`        | `False`             | `True`                     | ✅ OK  | Fuerza HTTPS en prod. |
| `SECURE_HSTS_SECONDS`        | `0`                 | `31536000` (1 año)         | ✅ OK  | HSTS activo en prod con preload. |
| `SECURE_HSTS_INCLUDE_SUBDOMAINS` | `False`         | `True`                     | ✅ OK  | |
| `SECURE_HSTS_PRELOAD`        | `False`             | `True`                     | ✅ OK  | |
| `SECURE_PROXY_SSL_HEADER`    | `None`              | `('HTTP_X_FORWARDED_PROTO', 'https')` | ✅ OK | Necesario detrás de ALB. |
| `SECURE_CONTENT_TYPE_NOSNIFF`| `True`              | `True`                     | ✅ OK  | |
| `X_FRAME_OPTIONS`            | `DENY`              | `DENY`                     | ✅ OK  | Reforzado por CSP `frame-ancestors 'none'`. |

### Recomendación: validar SECRET_KEY en startup

Agregar al inicio de `settings.py` una validación que evite arrancar en prod con la key insegura:

```python
if not DEBUG and SECRET_KEY == 'unsafe-secret':
    raise ImproperlyConfigured(
        'DJANGO_SECRET_KEY must be set in production. '
        'Generate one with: python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"'
    )
```

**Estado: pendiente de implementar.** Riesgo bajo — en ECS la env var se inyecta desde Secrets Manager, pero la validación explícita es una buena defensa en profundidad.

---

## 2. Cookies de sesión y CSRF

| Setting                  | Dev                | Prod          | Estado | Notas |
|--------------------------|--------------------|---------------|--------|-------|
| `SESSION_COOKIE_SECURE`  | `False`            | `True`        | ✅ OK  | Solo se envía por HTTPS en prod. |
| `SESSION_COOKIE_HTTPONLY` | `True`            | `True`        | ✅ OK  | No accesible desde JS. |
| `SESSION_COOKIE_SAMESITE`| `Lax`              | `Lax`         | ✅ OK  | Protege contra CSRF en links externos. |
| `CSRF_COOKIE_SECURE`     | `False`            | `True`        | ✅ OK  | |
| `CSRF_COOKIE_HTTPONLY`    | `True`             | `True`        | ✅ OK  | |

---

## 3. Auth / JWT / cookies de autenticación

Las cookies JWT se configuran en las funciones `_set_auth_cookies()` y `_set_business_cookie()` de `views.py`:

| Cookie          | httpOnly | secure                   | sameSite                   | max_age              | path | Estado |
|-----------------|----------|--------------------------|----------------------------|----------------------|------|--------|
| `access_token`  | `True`   | `AUTH_COOKIE_SECURE`     | `AUTH_COOKIE_SAMESITE`     | 15 min (configurable)| `/`  | ✅ OK  |
| `refresh_token` | `True`   | `AUTH_COOKIE_SECURE`     | `AUTH_COOKIE_SAMESITE`     | 7 días (configurable)| `/`  | ✅ OK  |
| `mirubro_bid`   | `True`   | `AUTH_COOKIE_SECURE`     | `AUTH_COOKIE_SAMESITE`     | 30 días              | `/`  | ✅ OK  |

| Setting               | Dev               | Prod               | Estado | Notas |
|------------------------|-------------------|---------------------|--------|-------|
| `AUTH_COOKIE_SECURE`   | `False`           | `True` (env var)    | ✅ OK  | Debe setear `COOKIE_SECURE=true` en prod. |
| `AUTH_COOKIE_SAMESITE` | `Lax`             | `Lax` (env var)     | ✅ OK  | |
| `AUTH_COOKIE_DOMAIN`   | `None`            | Desde `COOKIE_DOMAIN` | ✅ OK | `None` para localhost, dominio real en prod. |

### JWT

| Setting                     | Valor             | Estado | Notas |
|-----------------------------|--------------------|--------|-------|
| `ACCESS_TOKEN_LIFETIME`     | 15 min             | ✅ OK  | Configurable. |
| `REFRESH_TOKEN_LIFETIME`    | 7 días             | ✅ OK  | Configurable. |
| `ROTATE_REFRESH_TOKENS`     | `True`             | ✅ OK  | Cada refresh emite un token nuevo. |
| `BLACKLIST_AFTER_ROTATION`  | `True`             | ✅ OK  | Fase 2A: revoca token viejo. |
| `ALGORITHM`                 | `HS256`            | ✅ OK  | Simétrico con SECRET_KEY. |
| `SIGNING_KEY`               | `SECRET_KEY`       | ✅ OK  | Compartido con Django. |

---

## 4. CORS

| Setting                | Valor                                     | Estado | Notas |
|------------------------|-------------------------------------------|--------|-------|
| `CORS_ALLOWED_ORIGINS` | Desde `CORS_ALLOWED_ORIGINS` env var      | ✅ OK  | Lista explícita, no usa `*`. Default: `http://localhost:3000`. |
| `CORS_ALLOW_CREDENTIALS` | `True`                                  | ✅ OK  | Necesario para cookies cross-origin. |
| `CORS_ALLOW_HEADERS`  | Lista explícita                            | ✅ OK  | Solo headers necesarios. |

**Mecanismo ngrok/tunnel**: se agrega dinámicamente `BASE_PUBLIC_URL` a CORS si está configurado y no contiene `'xxxx'`. Esto es para desarrollo, no debería estar activo en prod.

### Recomendación

Verificar que `BASE_PUBLIC_URL` no esté configurado en las env vars de producción. Si lo está, asegurar que apunte al dominio real del API y no a un tunnel.

---

## 5. Password hashing

| Setting           | Valor                                    | Estado |
|-------------------|------------------------------------------|--------|
| `PASSWORD_HASHERS[0]` | `Argon2PasswordHasher`               | ✅ OK  |
| `PASSWORD_HASHERS[1]` | `PBKDF2PasswordHasher` (fallback)    | ✅ OK  |

Fase 2B implementada. Rehash transparente verificado.

---

## 6. Miscelánea

| Setting                | Valor     | Estado | Notas |
|------------------------|-----------|--------|-------|
| `TRUSTED_PROXY_DEPTH`  | `1`       | ✅ OK  | Ajustar a `2` si CloudFront + ALB. Configurable por env. |
| `CONN_MAX_AGE`         | `600`     | ✅ OK  | Reutiliza conexiones PG. Configurable por env. |
| `MFA_ENCRYPTION_KEY`   | Desde env | ✅ OK  | Fernet key. Vacío en dev (MFA deshabilitado). Obligatorio en prod. |

---

## 7. Variables de entorno — separación dev / staging / prod

### Obligatorias en producción

| Variable                | Motivo                                          |
|-------------------------|-------------------------------------------------|
| `DJANGO_SECRET_KEY`     | Clave criptográfica. No usar el default.        |
| `DJANGO_DEBUG=False`    | Default correcto, pero verificar que no sea `true`. |
| `DJANGO_ALLOWED_HOSTS`  | Dominio(s) real(es) del API.                    |
| `COOKIE_SECURE=true`    | Cookies solo por HTTPS.                         |
| `COOKIE_DOMAIN`         | Dominio para compartir cookies frontend↔API.    |
| `CORS_ALLOWED_ORIGINS`  | URL(s) del frontend en prod.                    |
| `POSTGRES_PASSWORD`     | Password de base de datos.                      |
| `MFA_ENCRYPTION_KEY`    | Fernet key para TOTP secrets.                   |
| `NEXT_PUBLIC_API_URL`   | URL del API para CSP connect-src en frontend.   |

### Solo para desarrollo (no deben estar en prod)

| Variable             | Motivo                          |
|----------------------|---------------------------------|
| `DJANGO_DEBUG=true`  | Sería un riesgo grave en prod.  |
| `BASE_PUBLIC_URL`    | Tunnel URL para dev.            |

---

## 8. Hallazgos y estado final

| # | Hallazgo | Severidad | Estado |
|---|----------|-----------|--------|
| 1 | `SECRET_KEY` tiene fallback inseguro sin validación en startup | Media | ⚠️ Pendiente (defensa en profundidad) |
| 2 | `BASE_PUBLIC_URL` podría quedar configurado en prod accidentalmente | Baja | ⚠️ Verificar en deploy |
| 3 | Todos los demás settings de seguridad son correctos | — | ✅ OK |

**Conclusión**: la configuración de seguridad está bien estructurada y sigue el patrón correcto de defaults seguros en prod. Los dos hallazgos son de riesgo bajo/medio y tienen mitigaciones claras.
