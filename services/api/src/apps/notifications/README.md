# apps.notifications

## Propósito

App interna responsable de la trazabilidad y despacho de emails transaccionales de MiRubro Digital.

Centraliza el registro de cada intento de envío de email mediante el modelo `EmailDelivery`, permitiendo auditoría, reintentos y observabilidad de todos los emails salientes del sistema.

---

## Estado — Fase 1 (base) ✓

- [x] App Django creada y registrada en `INSTALLED_APPS`.
- [x] Settings formales de email/SES expuestos en `config/settings.py`.
- [x] Modelo `EmailDelivery` con ciclo de vida completo (queued → sending → sent / failed / bounced / complained).
- [x] Admin básico registrado.
- [x] Migración inicial creada.
- [x] Tests del modelo y settings.

## Estado — Fase 2 (providers + services + Celery + templates)

- [x] `providers/base.py` — `BaseEmailProvider` + `EmailSendResult` dataclass.
- [x] `providers/django_email.py` — `DjangoEmailProvider` (usa `EmailMultiAlternatives`).
- [x] `providers/amazon_ses.py` — `AmazonSESProvider` (boto3 SESv2, IAM Role, no access keys).
- [x] `services.py` — `get_email_provider`, `render_email_template`, `queue_transactional_email`, `send_transactional_email`, `send_queued_email_delivery`.
- [x] `tasks.py` — Celery task `notifications.send_email_delivery` (bind=True, max_retries=3).
- [x] `templates/emails/base.html` — base HTML con header, footer y soporte branding.
- [x] `templates/emails/generic.html` — template reutilizable con `title`, `message`, `action_url`, `action_label`.
- [x] Tests de providers, services y task.

### Fuera del alcance de Fase 2

- No se migraron flujos de email existentes en `accounts` ni en `reviews`.
- No se crearon templates específicos de verificación/reset.
- No se tocaron `billing`, `.env` ni configuración SMTP.
- No se conectó SNS para bounces/complaints.

---

## Proveedor de email

El proveedor definitivo de producción es **Amazon SES** via `boto3` / `SESv2 API` con **IAM Role** (sin access keys embebidas). No se usará SMTP en producción.

En desarrollo, `EMAIL_BACKEND` continúa usando el backend de consola de Django por defecto.

---

## Settings esperados

Todos son opcionales y tienen defaults seguros.

| Setting | Default | Descripción |
|---|---|---|
| `EMAIL_PROVIDER` | `django` | `django` o `amazon_ses`. Controla qué provider usar al despachar. |
| `AWS_SES_REGION` | `sa-east-1` | Región de Amazon SES. |
| `AWS_SES_CONFIGURATION_SET` | `""` | Configuration Set de SES para tracking de bounces/complaints. |
| `EMAIL_TRANSACTIONAL_ENABLED` | `True` | Habilita el envío de emails transaccionales. |
| `EMAIL_MARKETING_ENABLED` | `False` | Habilita el envío de emails de marketing (opt-in explícito). |
| `DEFAULT_FROM_EMAIL` | `MiRubro <notificaciones@mirubro.com>` | Remitente por defecto. |
| `SERVER_EMAIL` | igual a `DEFAULT_FROM_EMAIL` | Remitente para emails de error de Django. |
| `SUPPORT_EMAIL` | `mirubrodigital@gmail.com` | Email de soporte visible en comunicaciones al usuario. |
| `BILLING_EMAIL` | `mirubrodigital@gmail.com` | Email de facturación / cobranzas. |

Los settings heredados de SMTP (`EMAIL_BACKEND`, `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_USE_TLS`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`) se preservan intactos.

---

## Modelo EmailDelivery

Registra cada intento de envío de email. Campos clave:

- `id` — UUID primary key.
- `business` — FK nullable a `business.Business`.
- `user` — FK nullable a `AUTH_USER_MODEL`.
- `to_email`, `from_email`, `subject`, `template_key` — datos del mensaje.
- `html_body`, `text_body` — cuerpo renderizado (guardado para auditoría).
- `status` — `queued | sending | sent | failed | bounced | complained`.
- `provider` — `amazon_ses | django`.
- `provider_message_id` — ID de mensaje devuelto por SES.
- `error_message` — detalle del error si el envío falló.
- `metadata` — JSON libre para datos de contexto del template.
- `queued_at`, `sent_at`, `failed_at`, `created_at`, `updated_at` — timestamps de ciclo de vida.

### Métodos de ciclo de vida

```python
delivery.mark_sending()               # queued → sending
delivery.mark_sent(provider_message_id="...")  # sending → sent
delivery.mark_failed("error detail")  # → failed
```

---

## API de uso (services.py)

```python
from apps.notifications.services import queue_transactional_email, send_transactional_email

# Asíncrono (encola task Celery — recomendado en views/signals)
delivery = queue_transactional_email(
    to_email="usuario@example.com",
    subject="Bienvenido a MiRubro",
    template_key="welcome",           # busca emails/welcome.html, fallback a generic.html
    context={"title": "Hola!", "message": "Tu cuenta está lista."},
    business=business_instance,       # opcional
    user=user_instance,               # opcional
)

# Síncrono (útil en management commands o tests)
delivery = send_transactional_email(
    to_email="usuario@example.com",
    subject="Confirmación",
    template_key="generic",
    context={"title": "OK", "message": "Todo listo.", "action_url": "https://...", "action_label": "Ir"},
)
```

---

## Próximas fases

- **Fase 3**: Templates específicos (verificación de email, reset de contraseña).
- **Fase 4**: Migrar flujos de `accounts` (verificación, reset de contraseña).
- **Fase 5**: Migrar flujos de `reviews` (digest semanal).
- **Fase 6**: Conectar SNS para tracking de bounces/complaints → actualizar `EmailDelivery.status`.
