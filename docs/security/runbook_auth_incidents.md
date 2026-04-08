# Runbook: Incidentes de autenticación — MiRubro Digital

> Fase 2D · Última actualización: 2026-04-07

## Convenciones

- **Señal**: qué dispara la investigación (alerta, reporte de usuario, log review)
- **Causa probable**: hipótesis más comunes
- **Acciones**: pasos ordenados de diagnóstico y respuesta
- **Prevención**: mejoras para evitar recurrencia

---

## Incidente 1: Brute-force contra una cuenta

### Señal

- Alerta `LoginFailedHigh` (>50 auth.login.failed en 5 min)
- O reporte de usuario: "me bloquearon la cuenta"

### Causa probable

1. Atacante probando credenciales contra un email conocido
2. Credential stuffing con listas filtradas

### Acciones

1. **Identificar el target**

   ```
   fields email, ip, reason
   | filter event = 'auth.login.failed'
   | filter @timestamp > ago(30m)
   | stats count(*) as failures by email
   | sort failures desc
   | limit 10
   ```

2. **Verificar si el rate-limiter está actuando**

   ```
   fields email, ip
   | filter event = 'auth.ratelimit.triggered'
   | filter @timestamp > ago(30m)
   | stats count(*) as blocks by email, ip
   ```

   Si hay eventos `ratelimit.triggered` → el control **está funcionando**. El atacante está bloqueado después de N intentos.

3. **Bloquear IP en WAF** (si una IP domina)

   ```bash
   aws wafv2 update-ip-set \
     --name mirubro-blocked-ips \
     --scope REGIONAL \
     --addresses <IP>/32 \
     --id <ipset-id> --lock-token <token>
   ```

4. **Notificar al usuario** si es una cuenta real: "Detectamos intentos de acceso sospechosos. ¿Fuiste tú?"

5. **Forzar cambio de contraseña** si hay indicios de compromiso:

   > **Nota**: `changepassword` usa `USERNAME_FIELD` del modelo User (en este proyecto: `email`). Verificar que el entorno tenga acceso interactivo al container. En ECS, usar `aws ecs execute-command` en lugar de `docker compose exec`.

   ```bash
   docker compose exec api python manage.py changepassword <email>
   ```

6. **Verificar que el password NO fue comprometido** revisando si hubo un `login.success` desde la IP atacante.

### Prevención

- MFA habilitado para cuentas de alto privilegio (admin, owner)
- Monitorear listas de credentials en HaveIBeenPwned

---

## Incidente 2: Ataque automatizado / botnet

### Señal

- Alerta `RateLimitSustained` (>20 auth.ratelimit.triggered en 5 min)
- Múltiples IPs diferentes con rate-limit triggered

### Causa probable

1. Botnet en credential stuffing distribuido
2. Script automatizado rotando proxies

### Acciones

1. **Mapear las IPs involucradas**

   ```
   fields ip, email
   | filter event = 'auth.ratelimit.triggered'
   | filter @timestamp > ago(1h)
   | stats count(*) as blocks by ip
   | sort blocks desc
   | limit 50
   ```

2. **Verificar patrones**:
   - ¿Mismo email, distintas IPs? → targeting de una cuenta
   - ¿Distintos emails, misma IP? → enumeración de cuentas
   - ¿Distintos emails, distintas IPs? → botnet con lista de credenciales

3. **Si es enumeración** → la respuesta anti-enumeración ya protege (200 OK con mismo formato). Verificar que no hay leak en timing:

   ```
   fields email, ip
   | filter event = 'auth.login.failed'
   | filter reason = 'invalid_credentials'
   | stats count(*) as attempts by email
   | sort attempts desc
   ```

4. **Bloqueo masivo** — Si el ataque es distribuido (muchas IPs), considerar:
   - Rate-limit más agresivo a nivel WAF (AWS WAF rate-based rule)
   - CAPTCHA en login (temporal)
   - Geo-blocking si las IPs son de regiones no-target

5. **Escalar** si el volumen supera la capacidad del rate-limiter:
   - Habilitar AWS Shield Advanced
   - Contactar AWS Support

### Prevención

- Rate-limit a nivel WAF además de aplicación
- CAPTCHA inteligente (reCAPTCHA v3 o similar) como siguiente fase
- Monitoreo continuo de anomalías de volumen

---

## Incidente 3: Token replay (refresh token robado)

### Señal

- Alerta `RefreshFailedAnomaly` (>30 auth.refresh.failed en 5 min)
- O patrón: muchos `refresh.failed` desde una IP que no es la del último `login.success`

### Causa probable

1. Refresh token robado (XSS, network sniffing, malware)
2. Token ya rotado — el atacante tiene una copia vieja
3. Bug en frontend que envía tokens expirados repetidamente

### Acciones

1. **Determinar si es bug o ataque**

   ```
   fields ip, reason, @timestamp
   | filter event = 'auth.refresh.failed'
   | filter @timestamp > ago(30m)
   | stats count(*) as failures by ip, reason
   | sort failures desc
   ```

   - `reason = 'token_expired'` desde muchas IPs → probablemente bug en frontend
   - `reason = 'token_invalid'` o `'token_blacklisted'` desde IP nueva → posible replay

2. **Si es replay**: identificar el user_id afectado y su último login legítimo

   ```
   fields user_id, ip, @timestamp
   | filter event = 'auth.login.success'
   | filter user_id = <USER_ID>
   | sort @timestamp desc
   | limit 5
   ```

3. **Revocar todas las sesiones del usuario** (flush tokens):

   ```bash
   docker compose exec api python manage.py shell -c "
   from apps.accounts.models import User
   from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken
   user = User.objects.get(id=<USER_ID>)
   tokens = OutstandingToken.objects.filter(user=user)
   for t in tokens:
       BlacklistedToken.objects.get_or_create(token=t)
   print(f'Blacklisted {tokens.count()} tokens for user {user.email}')
   "
   ```

4. **Forzar re-login**: el usuario no podrá refrescar y será redirigido al login.

5. **Contactar al usuario**: informar que se cerró su sesión por actividad sospechosa y solicitar cambio de contraseña.

6. **Investigar vector**: si fue XSS → revisar CSP violations y logs del frontend. Si fue network → verificar que cookies tienen `Secure` flag.

### Prevención

- MFA reduce el impacto de tokens robados (el atacante no puede re-autenticarse)
- Evaluar token binding (vincular refresh token a fingerprint del cliente)
- CSP enforce para prevenir XSS

---

## Incidente 4: Anomalía en sesiones (session hijacking)

### Señal

- Reporte de usuario: "alguien más está usando mi cuenta"
- O detección proactiva: `login.success` seguido de actividad desde otra IP/región

### Causa probable

1. Credenciales comprometidas (password reutilizado, phishing)
2. Session hijack vía token robado (ver Incidente 3)
3. Cuenta compartida intencionalmente (falsa alarma)

### Acciones

1. **Auditar actividad reciente del usuario**

   ```
   fields event, outcome, ip, @timestamp
   | filter logger = 'apps.accounts.security'
   | filter user_id = <USER_ID>
   | sort @timestamp desc
   | limit 50
   ```

2. **Listar IPs únicas**

   ```
   fields ip
   | filter user_id = <USER_ID>
   | filter event in ['auth.login.success', 'auth.refresh.success']
   | stats count(*) by ip
   ```

3. **Si hay IPs sospechosas**: revocar todas las sesiones (ver Incidente 3, paso 3).

4. **Forzar cambio de contraseña**:

   > **Nota**: `changepassword` usa `USERNAME_FIELD` del modelo User (en este proyecto: `email`). En ECS, usar `aws ecs execute-command` en lugar de `docker compose exec`.

   ```bash
   docker compose exec api python manage.py changepassword <email>
   ```

5. **Verificar si el password estaba en una breach conocida** (si se implementa check contra HaveIBeenPwned).

6. **Bloquear IP del atacante** en WAF si es identificable.

### Prevención

- MFA (reduce impacto de password comprometido)
- Notificaciones de login desde nueva IP/dispositivo
- Password policy + check contra breaches conocidas

---

## Comandos útiles de referencia

### Blacklistear todos los tokens de un usuario

```bash
docker compose exec api python manage.py shell -c "
from apps.accounts.models import User
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken
user = User.objects.get(email='<email>')
tokens = OutstandingToken.objects.filter(user=user)
for t in tokens:
    BlacklistedToken.objects.get_or_create(token=t)
print(f'Revoked {tokens.count()} tokens')
"
```

### Limpiar tokens expirados (también en celery beat diario)

```bash
docker compose exec api python manage.py flushexpiredtokens
```

### Verificar que Argon2 está activo

```bash
docker compose exec api python manage.py shell -c "
from django.contrib.auth.hashers import get_hasher
h = get_hasher('default')
print(h.algorithm)  # debe ser 'argon2'
"
```

### Verificar health de Redis (rate-limiter depende de esto)

```bash
docker compose exec redis redis-cli ping
# Esperado: PONG
```

### Verificar conexión a PostgreSQL

> **Nota**: `dbshell` requiere que el cliente de base de datos (`psql`) esté instalado en el container. Si no está disponible, usar la alternativa con Django ORM:
> ```bash
> docker compose exec api python manage.py shell -c "from django.db import connection; cursor = connection.cursor(); cursor.execute('SELECT 1'); print(cursor.fetchone())"
> ```

```bash
docker compose exec api python manage.py dbshell -c "SELECT 1;"
```
