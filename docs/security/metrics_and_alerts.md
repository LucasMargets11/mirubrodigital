# Métricas y alertas de seguridad — MiRubro Digital

> Fase 2D · Última actualización: 2026-04-07

## 1. Métricas derivables desde logs

Todos los eventos son emitidos por el logger `apps.accounts.security` a través del módulo `security_events.py`. En producción los logs salen en formato JSON estructurado (`python-json-logger`), con los campos:

| Campo     | Tipo   | Descripción                          |
|-----------|--------|--------------------------------------|
| timestamp | string | ISO-8601 con timezone                |
| level     | string | INFO / WARNING                       |
| logger    | string | `apps.accounts.security`             |
| message   | string | `{event} {outcome}`                  |
| event     | string | Nombre canónico de la métrica        |
| outcome   | string | `success` / `failed` / `blocked`     |
| user_id   | int    | ID del usuario (cuando aplica)       |
| email     | string | Identificador (nunca la contraseña)  |
| ip        | string | IP real del cliente (post-proxy)     |
| reason    | string | Motivo del fallo (cuando aplica)     |

### Eventos disponibles

| Evento                      | Nivel   | Significado                                    |
|-----------------------------|---------|------------------------------------------------|
| `auth.login.success`        | INFO    | Login exitoso (credenciales + rate-limit OK)   |
| `auth.login.failed`         | WARNING | Credenciales inválidas o usuario inactivo      |
| `auth.logout.success`       | INFO    | Logout con token blacklisteado                 |
| `auth.refresh.success`      | INFO    | Rotación de refresh token exitosa              |
| `auth.refresh.failed`       | WARNING | Refresh rechazado (expirado, replay, inválido) |
| `auth.ratelimit.triggered`  | WARNING | 3D rate-limiter bloqueó el intento             |

---

## 2. Queries de ejemplo — CloudWatch Logs Insights

### 2.1 Resumen general de eventos auth (últimos 30 min)

```
fields @timestamp, event, outcome, ip, user_id
| filter logger = 'apps.accounts.security'
| sort @timestamp desc
| limit 200
```

### 2.2 Conteo por tipo de evento

```
fields event
| filter logger = 'apps.accounts.security'
| stats count(*) as total by event
| sort total desc
```

### 2.3 Top IPs con login fallido

```
fields ip
| filter event = 'auth.login.failed'
| stats count(*) as failures by ip
| sort failures desc
| limit 20
```

### 2.4 Tasa de rate-limit por IP

```
fields ip, email, reason
| filter event = 'auth.ratelimit.triggered'
| stats count(*) as blocks by ip
| sort blocks desc
| limit 10
```

### 2.5 Refresh rechazados — posible replay

```
fields @timestamp, ip, reason
| filter event = 'auth.refresh.failed'
| stats count(*) as failures by ip, reason
| sort failures desc
```

### 2.6 Logins exitosos por usuario (auditoría)

```
fields @timestamp, user_id, email, ip
| filter event = 'auth.login.success'
| sort @timestamp desc
| limit 100
```

---

## 3. Alertas sugeridas

### 3.1 Brute-force: login_failed alto

| Parámetro      | Valor                                         |
|----------------|-----------------------------------------------|
| Métrica        | `auth.login.failed`                           |
| Umbral         | > 50 en 5 min                                 |
| Indica         | Posible ataque de fuerza bruta                |
| Acción         | Ver Top IPs (query 2.3), verificar rate-limiter, revisar si una IP domina. Considerar bloqueo WAF. |

**CloudWatch Metric Filter:**

```
{ $.event = "auth.login.failed" }
```

Alarm: `LoginFailedHigh` → threshold 50 / period 300s → SNS topic `mirubro-security-alerts`.

---

### 3.2 Rate-limit sostenido

| Parámetro      | Valor                                                   |
|----------------|---------------------------------------------------------|
| Métrica        | `auth.ratelimit.triggered`                              |
| Umbral         | > 20 en 5 min                                           |
| Indica         | Ataque automatizado persistente o botnet                |
| Acción         | Revisar IPs (query 2.4). Si es una sola IP → bloqueo WAF. Si son múltiples → evaluar captcha o cooldown más agresivo. |

**CloudWatch Metric Filter:**

```
{ $.event = "auth.ratelimit.triggered" }
```

Alarm: `RateLimitSustained` → threshold 20 / period 300s.

---

### 3.3 Refresh anómalo

| Parámetro      | Valor                                               |
|----------------|-----------------------------------------------------|
| Métrica        | `auth.refresh.failed`                               |
| Umbral         | > 30 en 5 min                                       |
| Indica         | Tokens robados en replay, o client-side bug masivo  |
| Acción         | Si una IP domina → posible session hijack. Si muchas IPs → posible token leak o bug en frontend. |

**CloudWatch Metric Filter:**

```
{ $.event = "auth.refresh.failed" }
```

Alarm: `RefreshFailedAnomaly` → threshold 30 / period 300s.

---

### 3.4 Errores 5xx en auth endpoints

| Parámetro      | Valor                                           |
|----------------|-------------------------------------------------|
| Métrica        | HTTP 5xx en `/api/v1/auth/*`                    |
| Umbral         | > 5 en 5 min                                    |
| Indica         | Bug en auth, DB down, Redis down                |
| Acción         | Revisar logs de `django.request`, verificar conectividad PostgreSQL y Redis. |

> **Requisito**: esta alerta depende de **request logs estructurados** (Django `django.request` logger en formato JSON) o de **ALB access logs** habilitados en S3. El campo `status` solo está disponible si alguna de estas fuentes está activa. Verificar la configuración antes de crear el metric filter.

**Filtro (ALB access logs o Django request log):**

```
fields @timestamp, status
| filter @message like /\/api\/v1\/auth\//
| filter status >= 500
| stats count(*) as errors
```

Alarm: `Auth5xxErrors` → threshold 5 / period 300s.

---

## 4. Implementación en CloudWatch

### Paso 1: Metric Filters

Crear un metric filter por cada evento en el log group del servicio API (ECS task logs):

```bash
aws logs put-metric-filter \
  --log-group-name /ecs/mirubro-api \
  --filter-name AuthLoginFailed \
  --filter-pattern '{ $.event = "auth.login.failed" }' \
  --metric-transformations \
    metricName=AuthLoginFailed,metricNamespace=MiRubro/Security,metricValue=1
```

Repetir para cada evento (`auth.ratelimit.triggered`, `auth.refresh.failed`, etc.).

### Paso 2: Alarms

```bash
aws cloudwatch put-metric-alarm \
  --alarm-name LoginFailedHigh \
  --namespace MiRubro/Security \
  --metric-name AuthLoginFailed \
  --statistic Sum \
  --period 300 \
  --threshold 50 \
  --comparison-operator GreaterThanThreshold \
  --evaluation-periods 1 \
  --alarm-actions arn:aws:sns:us-east-1:ACCOUNT:mirubro-security-alerts
```

### Paso 3: SNS

Configurar el topic `mirubro-security-alerts` con suscriptores (email, Slack webhook, PagerDuty).

---

## 5. Resumen de alertas

| Alerta              | Evento                     | Umbral      | Severidad |
|---------------------|----------------------------|-------------|-----------|
| LoginFailedHigh     | auth.login.failed          | >50 / 5min  | HIGH      |
| RateLimitSustained  | auth.ratelimit.triggered   | >20 / 5min  | HIGH      |
| RefreshFailedAnomaly| auth.refresh.failed        | >30 / 5min  | MEDIUM    |
| Auth5xxErrors       | HTTP 5xx en /auth/*        | >5 / 5min   | CRITICAL  |
