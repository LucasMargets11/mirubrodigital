from pathlib import Path
from datetime import timedelta
from decimal import Decimal
import os
import sys

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR.parent / '.env')

SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'unsafe-secret')
DEBUG = os.getenv('DJANGO_DEBUG', 'False').lower() == 'true'

if not DEBUG and SECRET_KEY == 'unsafe-secret':
    from django.core.exceptions import ImproperlyConfigured
    raise ImproperlyConfigured(
        'DJANGO_SECRET_KEY must be set in production. '
        'Generate one with: python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"'
    )

ALLOWED_HOSTS = [host.strip() for host in os.getenv('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1,mirubro-api').split(',') if host]

# Dynamically add the ngrok/tunnel host to ALLOWED_HOSTS and CORS so Django
# doesn't reject requests arriving through the tunnel in DEV.
_BASE_PUBLIC_URL = os.getenv('BASE_PUBLIC_URL', '').strip()
if _BASE_PUBLIC_URL and 'xxxx' not in _BASE_PUBLIC_URL.lower():
    from urllib.parse import urlparse as _urlparse
    _parsed = _urlparse(_BASE_PUBLIC_URL)
    _ngrok_host = _parsed.hostname  # e.g. 'abc123.ngrok-free.app'
    if _ngrok_host and _ngrok_host not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(_ngrok_host)

INSTALLED_APPS = [
  'django.contrib.admin',
  'django.contrib.auth',
  'django.contrib.contenttypes',
  'django.contrib.sessions',
  'django.contrib.messages',
  'django.contrib.staticfiles',
  'rest_framework',
  'rest_framework_simplejwt',
  'rest_framework_simplejwt.token_blacklist',
  'drf_spectacular',
  'corsheaders',
  'apps.accounts',
  'apps.business',
  'apps.catalog',
  'apps.inventory',
  'apps.invoices',
  'apps.sales',
  'apps.orders',
  'apps.customers',
  'apps.cash',
  'apps.reports',
  'apps.menu',
  'apps.merchant_payments',
  'apps.reviews',
  'apps.appointments',
  'apps.resto',
  'apps.billing',
  'apps.treasury',
  'apps.tax_backup',
  'apps.blog',
  'apps.printables',
  'apps.notifications',
  'apps.leads',
]

MIDDLEWARE = [
  'corsheaders.middleware.CorsMiddleware',
  'django.middleware.security.SecurityMiddleware',
  'config.middleware.CSPReportOnlyMiddleware',
  'django.contrib.sessions.middleware.SessionMiddleware',
  'django.middleware.common.CommonMiddleware',
  'django.middleware.csrf.CsrfViewMiddleware',
  'django.contrib.auth.middleware.AuthenticationMiddleware',
  'django.contrib.messages.middleware.MessageMiddleware',
  'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

# ── Authentication backends ──────────────────────────────────────────────────
# Custom backend supports login by email OR username (internal users).
AUTHENTICATION_BACKENDS = [
    'apps.accounts.auth_backends.UsernameOrEmailBackend',
]

TEMPLATES = [
  {
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'DIRS': [],
    'APP_DIRS': True,
    'OPTIONS': {
      'context_processors': [
        'django.template.context_processors.debug',
        'django.template.context_processors.request',
        'django.contrib.auth.context_processors.auth',
        'django.contrib.messages.context_processors.messages',
      ],
    },
  },
]

WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

DATABASES = {
  'default': {
    'ENGINE': 'django.db.backends.postgresql',
    'NAME': os.getenv('POSTGRES_DB', 'mirubro'),
    'USER': os.getenv('POSTGRES_USER', 'mirubro'),
    'PASSWORD': os.getenv('POSTGRES_PASSWORD', 'mirubro'),
    'HOST': os.getenv('POSTGRES_HOST', 'postgres'),
    'PORT': os.getenv('POSTGRES_PORT', '5432'),
    'CONN_MAX_AGE': int(os.getenv('CONN_MAX_AGE', '600')),
  }
}

PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.Argon2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2PasswordHasher',
]

AUTH_PASSWORD_VALIDATORS = [
  {
    'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
  },
  {
    'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
  },
  {
    'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
  },
  {
    'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
  },
]

LANGUAGE_CODE = 'es'
TIME_ZONE = 'America/Argentina/Buenos_Aires'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR.parent / 'staticfiles'
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR.parent / 'media'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ── S3 Public Media ───────────────────────────────────────────────────────────
# Active only when AWS_STORAGE_BUCKET_NAME is set (staging/prod on EC2 with
# an IAM instance role — no access keys embedded here).
# Without the variable the default FileSystemStorage stays in effect (local dev).
# Only menu images and business logos use this via common.storages.public_media_storage.
# Invoices, treasury, and tax_backup are NOT affected.
AWS_STORAGE_BUCKET_NAME = os.getenv('AWS_STORAGE_BUCKET_NAME', '')
if AWS_STORAGE_BUCKET_NAME:
    AWS_S3_REGION_NAME    = os.getenv('AWS_S3_REGION_NAME', 'sa-east-1')
    AWS_S3_FILE_OVERWRITE = False   # never clobber existing file by name
    AWS_DEFAULT_ACL       = None    # no per-object ACL; rely on bucket policy
    AWS_QUERYSTRING_AUTH  = False   # unsigned public URLs (no CloudFront needed)

CORS_ALLOWED_ORIGINS = [
  origin.strip()
  for origin in os.getenv('CORS_ALLOWED_ORIGINS', 'http://localhost:3000').split(',')
  if origin
]

# Also allow the ngrok/tunnel origin so browser-to-API calls work when
# accessing the frontend through the tunnel in DEV.
# Gated behind DEBUG to prevent accidental CORS opening in production.
if DEBUG and _BASE_PUBLIC_URL and 'xxxx' not in _BASE_PUBLIC_URL.lower():
    # Strip trailing slash for CORS match
    _cors_origin = _BASE_PUBLIC_URL.rstrip('/')
    if _cors_origin not in CORS_ALLOWED_ORIGINS:
        CORS_ALLOWED_ORIGINS.append(_cors_origin)
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = ['authorization', 'content-type', 'x-requested-with', 'x-employee-token', 'x-business-id']

CSRF_TRUSTED_ORIGINS = [
  origin.strip()
  for origin in os.getenv('CSRF_TRUSTED_ORIGINS', 'http://localhost:3000').split(',')
  if origin.strip()
]

REST_FRAMEWORK = {
  'DEFAULT_AUTHENTICATION_CLASSES': [
    'apps.accounts.authentication.CookieJWTAuthentication',
    'rest_framework.authentication.SessionAuthentication',
  ],
  'DEFAULT_PERMISSION_CLASSES': [
    'rest_framework.permissions.IsAuthenticatedOrReadOnly',
  ],
  'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
  # NUM_PROXIES: tells DRF's get_ident() to count from the RIGHT of
  # X-Forwarded-For by this many positions, matching TRUSTED_PROXY_DEPTH.
  # Without this, DRF throttles use the leftmost (spoofable) XFF entry.
  'NUM_PROXIES': int(os.getenv('TRUSTED_PROXY_DEPTH', '1')),
  # Throttle rates for sensitive operative endpoints.
  # Throttle classes are applied per-view (not globally).
  'DEFAULT_THROTTLE_RATES': {
    'employee_login':      '10/minute',
    'employee_change_pin': '5/minute',
    # Public auth endpoints — each has a dedicated FailOpenAnonThrottle subclass.
    'auth_login':            '20/minute',
    'auth_register':         '5/minute',
    'auth_forgot_password':  '5/minute',
    'auth_reset_password':   '5/minute',
    'auth_verify_email':     '5/minute',
    'auth_refresh':          '30/minute',
    # Google OAuth
    'auth_google':           '10/minute',
  },
}

ACCESS_TOKEN_MINUTES = int(os.getenv('ACCESS_TOKEN_LIFETIME_MINUTES', '15'))
REFRESH_TOKEN_DAYS = int(os.getenv('REFRESH_TOKEN_LIFETIME_DAYS', '7'))

raw_cookie_domain = os.getenv('COOKIE_DOMAIN', '').strip()
if raw_cookie_domain.lower() in {'', 'localhost', '127.0.0.1'}:
  AUTH_COOKIE_DOMAIN = None
else:
  AUTH_COOKIE_DOMAIN = raw_cookie_domain
AUTH_COOKIE_SECURE = os.getenv('COOKIE_SECURE', str(not DEBUG)).lower() == 'true'
AUTH_COOKIE_SAMESITE = os.getenv('COOKIE_SAMESITE', 'Lax')
AUTH_COOKIE_PATH = '/'
AUTH_COOKIE_ACCESS_MAX_AGE = int(os.getenv('ACCESS_TOKEN_MAX_AGE_SECONDS', str(ACCESS_TOKEN_MINUTES * 60)))
AUTH_COOKIE_REFRESH_MAX_AGE = int(os.getenv('REFRESH_TOKEN_MAX_AGE_SECONDS', str(REFRESH_TOKEN_DAYS * 24 * 60 * 60)))

# ── Google OAuth ─────────────────────────────────────────────────────────────
GOOGLE_OAUTH_CLIENT_ID = os.getenv('GOOGLE_OAUTH_CLIENT_ID', '')

SIMPLE_JWT = {
  'ACCESS_TOKEN_LIFETIME': timedelta(minutes=ACCESS_TOKEN_MINUTES),
  'REFRESH_TOKEN_LIFETIME': timedelta(days=REFRESH_TOKEN_DAYS),
  'ROTATE_REFRESH_TOKENS': True,
  'BLACKLIST_AFTER_ROTATION': True,
  'ALGORITHM': 'HS256',
  'SIGNING_KEY': SECRET_KEY,
  'AUTH_HEADER_TYPES': ('Bearer',),
}

SPECTACULAR_SETTINGS = {
  'TITLE': 'Mirubro API',
  'DESCRIPTION': 'API base para el SaaS multi-tenant',
  'VERSION': '1.0.0',
  'SERVE_INCLUDE_SCHEMA': False,
}

CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', os.getenv('REDIS_URL', 'redis://redis:6379/0'))
CELERY_RESULT_BACKEND = CELERY_BROKER_URL

# ── Cache (Redis / ElastiCache) ──────────────────────────────────────────────
# Used for admin rate limiting, MFA challenge tokens, OTP replay prevention.
# CACHE_REDIS_URL can point to Amazon ElastiCache (Redis or Valkey).
# Example: rediss://my-cluster.xxxxx.use1.cache.amazonaws.com:6379/0
# Use `rediss://` (double-s) for TLS, required by ElastiCache in-transit encryption.
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': os.getenv('CACHE_REDIS_URL', os.getenv('REDIS_URL', 'redis://redis:6379/1')),
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        },
        'KEY_PREFIX': 'mirubro',
        'TIMEOUT': 300,  # default 5 min
    },
}

# Periodic task schedule (requires celery-beat or django-celery-beat).
# expire_subscriptions runs every hour to enforce subscription lifecycle
# transitions (ACTIVE→PAST_DUE, PAST_DUE→SUSPENDED, TRIALING→SUSPENDED).
from celery.schedules import crontab  # noqa: E402
CELERY_BEAT_SCHEDULE = {
    'billing-expire-subscriptions': {
        'task': 'billing.expire_subscriptions',
        # Every hour at minute 0. Adjust frequency in high-churn environments.
        'schedule': crontab(minute='0'),
    },
    'billing-execute-scheduled-cancellations': {
        'task': 'billing.execute_scheduled_cancellations',
        # Every hour at minute 30. Runs after expire_subscriptions.
        'schedule': crontab(minute='30'),
    },
    'billing-expire-checkout-sessions': {
        'task': 'billing.expire_checkout_sessions',
        # Every 15 minutes.
        'schedule': crontab(minute='*/15'),
    },
    'blog-publish-scheduled': {
        'task': 'blog.publish_scheduled_posts',
        # Every 5 minutes — check for scheduled blog posts to publish.
        'schedule': crontab(minute='*/5'),
    },
    'jwt-flush-expired-tokens': {
        'task': 'accounts.flush_expired_tokens',
        # Daily at 03:00 — purge expired blacklisted tokens to prevent table bloat.
        'schedule': crontab(hour='3', minute='0'),
    },
    'reviews-send-weekly-digest': {
        'task': 'reviews.send_weekly_digest',
        # Mondays at 12:00 UTC (09:00 ART) — weekly feedback digest.
        'schedule': crontab(hour='12', minute='0', day_of_week='1'),
    },
    'billing-reconcile-promo-discounts': {
        'task': 'billing.reconcile_promotional_discounts',
        # Every hour at minute 45 — retry failed MP price restorations.
        'schedule': crontab(minute='45'),
    },
    'billing-retry-failed-webhooks': {
        'task': 'billing.retry_failed_webhooks',
        # Every 5 minutes — re-run FAILED MP webhook deliveries whose backoff
        # elapsed (per-row next_retry_at; see MP_WEBHOOK_RETRY_* below).
        'schedule': crontab(minute='*/5'),
    },
    'appointments-expire-holds': {
        'task': 'appointments.expire_holds',
        # Every 2 minutes — normalizes pending_payment → expired in DB. Slot
        # availability does NOT depend on it (occupying() ignores expired
        # holds dynamically), so a Beat outage only delays the stored status.
        'schedule': crontab(minute='*/2'),
    },
    'customers-dispatch-due-reminders': {
        'task': 'customers.dispatch_due_reminders',
        # Every minute — CustomerReminder pendiente con remind_at vencido →
        # BusinessNotification interna (una sola por recordatorio; idempotente
        # y seguro ante Beat duplicado). Un Beat caído solo demora el aviso.
        'schedule': crontab(),
    },
    'customers-retry-due-deliveries': {
        'task': 'customers.retry_due_deliveries',
        # Every minute — CustomerMessageDelivery (CUSTOMER 07D.2): reintentos
        # con next_retry_at vencido + pending con encolado perdido + processing
        # colgados → failed outcome_unknown. Hoy solo proveedores fake.
        'schedule': crontab(),
    },
    'leads-retry-due-takeover-commands': {
        'task': 'leads.retry_due_takeover_commands',
        # Every minute — TakeoverCommand (MIRUBRO TAKEOVER 05A): reintentos con
        # next_attempt_at vencido, kicks perdidos y envíos colgados (lease
        # vencido). No hace nada con AGENT_TAKEOVER_ENABLED=false.
        'schedule': crontab(),
    },
    'leads-retry-due-staff-messages': {
        'task': 'leads.retry_due_staff_messages',
        # Every minute — LeadStaffMessage (MIRUBRO HUMAN MESSAGES): mismo
        # barrido que takeover-commands, pero para mensajes de recepción hacia
        # el paciente. No hace nada con AGENT_TAKEOVER_ENABLED=false.
        'schedule': crontab(),
    },
}

# CUSTOMER 07D.2 — entregas externas al Customer (apps.customers.deliveries).
# Máximo 3 intentos; espera tras el intento N = BACKOFF[N-1] (1 min, 5 min; el
# tercero ya no reintenta). Solo existen proveedores fake (sin network): el
# modo simula success | retryable_failure | permanent_failure para QA.
CUSTOMER_DELIVERY_MAX_ATTEMPTS = int(os.getenv('CUSTOMER_DELIVERY_MAX_ATTEMPTS', '3'))
CUSTOMER_DELIVERY_RETRY_BACKOFF_SECONDS = (60, 300, 1800)
CUSTOMER_DELIVERY_PROCESSING_LEASE_SECONDS = 600
CUSTOMER_DELIVERY_FAKE_MODE = os.getenv('CUSTOMER_DELIVERY_FAKE_MODE', 'success')
# CUSTOMER 07D.3A — proveedor de email: 'fake' (default, sin network) | 'ses'.
# SES real SOLO con opt-in explícito; no se autodetecta por credenciales.
# Reusa AWS_SES_REGION / AWS_SES_CONFIGURATION_SET (abajo) y la cadena normal
# de credenciales de boto3 (IAM role en EC2/ECS). Remitente: AWS_SES_FROM_EMAIL
# (identidad verificada; default = dirección de DEFAULT_FROM_EMAIL) y
# AWS_SES_FROM_NAME (default = nombre de DEFAULT_FROM_EMAIL).
CUSTOMER_DELIVERY_PROVIDER_EMAIL = os.getenv('CUSTOMER_DELIVERY_PROVIDER_EMAIL', 'fake').strip().lower()
# CUSTOMER 07D.4A — guard: la suite de tests SIEMPRE usa el fake, aunque el
# .env/entorno del contenedor diga 'ses' (los tests de SES lo piden explícito
# con override_settings y un cliente boto3 mockeado).
if len(sys.argv) > 1 and sys.argv[1] == 'test':
    CUSTOMER_DELIVERY_PROVIDER_EMAIL = 'fake'
# CUSTOMER 07D.4A — recordatorio automático vencido → email al cliente (si el
# Business lo activó). Si preparar el Delivery falla tras el aviso interno, el
# barrido de avisos lo reintenta mientras el aviso tenga menos de N minutos.
CUSTOMER_REMINDER_DELIVERY_RECOVERY_MINUTES = int(os.getenv('CUSTOMER_REMINDER_DELIVERY_RECOVERY_MINUTES', '60'))
AWS_SES_FROM_EMAIL = os.getenv('AWS_SES_FROM_EMAIL', '').strip()
AWS_SES_FROM_NAME = os.getenv('AWS_SES_FROM_NAME', '').strip()

REPORTS_LOW_STOCK_THRESHOLD_DEFAULT = Decimal(os.getenv('REPORTS_LOW_STOCK_THRESHOLD_DEFAULT', '5'))

MP_ACCESS_TOKEN = os.getenv('MP_ACCESS_TOKEN')
MP_WEBHOOK_SECRET = os.getenv('MP_WEBHOOK_SECRET')

# Webhook delivery retry policy (Slice 5B.4 — apps.billing.webhook_lifecycle).
# Backoff after the Nth failed attempt = BASE * 2**(N-1), capped at
# MAX_BACKOFF. Defaults: 5m, 10m, 20m, 40m, 80m, 160m, 320m → DEAD_LETTER on
# the 8th failure (~10.5h of retries). The Beat sweep runs every 5 minutes.
MP_WEBHOOK_RETRY_MAX_ATTEMPTS = int(os.getenv('MP_WEBHOOK_RETRY_MAX_ATTEMPTS', '8'))
MP_WEBHOOK_RETRY_BASE_SECONDS = int(os.getenv('MP_WEBHOOK_RETRY_BASE_SECONDS', '300'))
MP_WEBHOOK_RETRY_MAX_BACKOFF_SECONDS = int(os.getenv('MP_WEBHOOK_RETRY_MAX_BACKOFF_SECONDS', str(6 * 3600)))
# A PROCESSING delivery older than this is assumed crashed and re-claimable.
MP_WEBHOOK_PROCESSING_LEASE_SECONDS = int(os.getenv('MP_WEBHOOK_PROCESSING_LEASE_SECONDS', '900'))
MP_BASE_URL = os.getenv('MP_BASE_URL', 'https://api.mercadopago.com')

# Mercado Pago OAuth per-business (Fase 2 — QR Menu tips)
MP_CLIENT_ID = os.getenv('MP_CLIENT_ID', '')
MP_CLIENT_SECRET = os.getenv('MP_CLIENT_SECRET', '')
MP_REDIRECT_URI = os.getenv('MP_REDIRECT_URI', '')

# Fernet key for encrypting merchants' own MP OAuth tokens at rest
# (MercadoPagoConnection.access_token / refresh_token). REQUIRED in
# production. Dedicated key, separate from MFA_ENCRYPTION_KEY, so rotating
# or compromising one never affects the other.
# Generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
#
# Production (AWS): store in AWS Secrets Manager and inject via ECS task
# definition secretsRef or a startup script that calls:
#   aws secretsmanager get-secret-value --secret-id mirubro/mp-token-encryption-key
# Never commit this value to source control.
MP_TOKEN_ENCRYPTION_KEY = os.getenv('MP_TOKEN_ENCRYPTION_KEY', '')

# Fernet key for encrypting the agent-integration HMAC secrets at rest
# (apps.leads AgentCredential.encrypted_secret, AGENT 02A). Dedicated key,
# separate from MP_TOKEN_ENCRYPTION_KEY and MFA_ENCRYPTION_KEY. Without it,
# provisioning/verifying agent credentials fails closed (never plaintext).
# Generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
AGENT_SECRET_ENCRYPTION_KEY = os.getenv('AGENT_SECRET_ENCRYPTION_KEY', '')

# AGENT 02B: habilita el receiver PUT /api/v1/integrations/agent/leads/<uuid>/.
# Default false: apagado responde 503. Encendido sin AGENT_SECRET_ENCRYPTION_KEY
# válida → error de system check leads.E001/E002 (falla `check`/`migrate`).
AGENT_INTEGRATION_ENABLED = os.getenv('AGENT_INTEGRATION_ENABLED', 'False').lower() == 'true'

# MIRUBRO TAKEOVER 05A: comandos humanos MiRubro → Agent (pausar/reanudar el bot
# de una conversación). Dirección y credencial PROPIAS, separadas de la del
# receiver (nunca reutilizar AGENT_SECRET_ENCRYPTION_KEY ni la credencial del
# agente). El secreto vive solo en env: no se persiste ni se loguea.
# Default false: la acción humana responde 503 y no se envía nada. En true,
# base URL / key id / secret inválidos → system check leads.E003–E006.
AGENT_TAKEOVER_ENABLED = os.getenv('AGENT_TAKEOVER_ENABLED', 'False').lower() == 'true'
AGENT_TAKEOVER_BASE_URL = os.getenv('AGENT_TAKEOVER_BASE_URL', '').strip()
AGENT_TAKEOVER_KEY_ID = os.getenv('AGENT_TAKEOVER_KEY_ID', '').strip()
AGENT_TAKEOVER_SECRET = os.getenv('AGENT_TAKEOVER_SECRET', '')
AGENT_TAKEOVER_TIMEOUT_SECONDS = 10
# Espera tras el intento N = BACKOFF[N-1] (el último valor se repite). Después
# de MAX_ATTEMPTS intentos fallidos transitorios el comando queda failed.
AGENT_TAKEOVER_RETRY_BACKOFF_SECONDS = (30, 60, 120, 240, 480, 900)
AGENT_TAKEOVER_MAX_ATTEMPTS = int(os.getenv('AGENT_TAKEOVER_MAX_ATTEMPTS', '10'))
# Un intento `delivering` sin resultado después de esto se vuelve a enviar
# (el agente es idempotente por versión/event_id).
AGENT_TAKEOVER_DELIVERY_LEASE_SECONDS = 60

# Public frontend URL (used in QR menu URLs and back_urls for MP checkout)
FRONTEND_URL = os.getenv('FRONTEND_URL', 'http://localhost:3000')
PUBLIC_MENU_BASE_URL = os.getenv('PUBLIC_MENU_BASE_URL', FRONTEND_URL)

# ── Email ─────────────────────────────────────────────────────────────────────
# In development: EMAIL_BACKEND defaults to console so no SMTP is needed.
# In production: set EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
# and populate the EMAIL_HOST_* vars.
EMAIL_BACKEND = os.getenv(
    'EMAIL_BACKEND',
    'django.core.mail.backends.console.EmailBackend',
)
EMAIL_HOST        = os.getenv('EMAIL_HOST', 'smtp.sendgrid.net')
EMAIL_PORT        = int(os.getenv('EMAIL_PORT', '587'))
EMAIL_USE_TLS     = os.getenv('EMAIL_USE_TLS', 'True').lower() == 'true'
EMAIL_HOST_USER   = os.getenv('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL = os.getenv(
    'DEFAULT_FROM_EMAIL',
    'MiRubro <notificaciones@mirubro.com>',
)
SERVER_EMAIL = os.getenv('SERVER_EMAIL', DEFAULT_FROM_EMAIL)
SUPPORT_EMAIL = os.getenv('SUPPORT_EMAIL', 'mirubrodigital@gmail.com')
BILLING_EMAIL = os.getenv('BILLING_EMAIL', 'mirubrodigital@gmail.com')
OPERATIONS_EMAIL = os.getenv('OPERATIONS_EMAIL', 'mirubrodigital@gmail.com')
ADMIN_EMAIL = os.getenv('ADMIN_EMAIL', 'mirubrodigital@gmail.com')
ADMIN_FRONTEND_URL = os.getenv('ADMIN_FRONTEND_URL', 'http://localhost:3000/admin')

# ── Notifications / SES settings ─────────────────────────────────────────────
EMAIL_PROVIDER = os.getenv('EMAIL_PROVIDER', 'django').strip().lower()

AWS_SES_REGION = os.getenv('AWS_SES_REGION', 'sa-east-1')
AWS_SES_CONFIGURATION_SET = os.getenv('AWS_SES_CONFIGURATION_SET', '')

EMAIL_TRANSACTIONAL_ENABLED = os.getenv('EMAIL_TRANSACTIONAL_ENABLED', 'true').lower() == 'true'
EMAIL_MARKETING_ENABLED = os.getenv('EMAIL_MARKETING_ENABLED', 'false').lower() == 'true'

# How long email-verification and password-reset tokens remain valid.
EMAIL_VERIFICATION_TOKEN_HOURS = int(os.getenv('EMAIL_VERIFICATION_TOKEN_HOURS', '48'))
PASSWORD_RESET_TOKEN_HOURS = int(os.getenv('PASSWORD_RESET_TOKEN_HOURS', '2'))

# BASE_PUBLIC_URL: externally reachable URL of the *API* server.
# Used to build the MP notification_url (webhook callback).
# In DEV: set to your ngrok/cloudflared HTTPS URL.
# In prod: set to your real domain (e.g. https://api.example.com).
# If not set, falls back to PUBLIC_MENU_BASE_URL then FRONTEND_URL.
BASE_PUBLIC_URL = os.getenv('BASE_PUBLIC_URL', '') or None

# ── Rollout feature flags ─────────────────────────────────────────────────────
# Platform-level switches for incremental feature rollout.
# Default: all False — new behaviours are opt-in at deploy time.
# Consumed by apps.accounts.rollout._RolloutFlags.is_enabled().
ROLLOUT_FLAGS = {
    # Steer new registrations through the 7-step onboarding funnel.
    'new_onboarding_enabled': os.getenv('ROLLOUT_NEW_ONBOARDING', 'false').lower() == 'true',
    # Enable v2 owner management endpoints (change_role, suspend_member, remove_member).
    'owner_user_management_v2_enabled': os.getenv('ROLLOUT_OWNER_MGMT_V2', 'false').lower() == 'true',
    # Block suspended AccountProfiles at the HasBusinessMembership permission gate.
    'subscription_status_enforcement_enabled': os.getenv('ROLLOUT_SUBSCRIPTION_ENFORCEMENT', 'false').lower() == 'true',
    # Require email_verified=True before commercial activation (billing checkout/subscribe).
    # Safe to enable for new envs; existing users were backfilled as email_verified=True.
    'email_verification_enforcement_enabled': os.getenv('ROLLOUT_EMAIL_VERIFICATION', 'false').lower() == 'true',
}

# ── Logging ──────────────────────────────────────────────────────────────────
# Structured staging-friendly logging.  All billing / runtime / webhook events
# are emitted at INFO level.  Set DJANGO_LOG_LEVEL=DEBUG in .env for verbose output.
_LOG_LEVEL = os.getenv('DJANGO_LOG_LEVEL', 'INFO').upper()

# In production (DEBUG=False), emit JSON-structured logs so they can be parsed
# by CloudWatch / ELK / any log aggregator.  In dev, keep the human-readable
# format so developers can read the console output.
_LOG_FORMAT = os.getenv('LOG_FORMAT', 'json' if not DEBUG else 'text').lower()

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{asctime}] [{levelname}] [{name}] {message}',
            'style': '{',
            'datefmt': '%Y-%m-%d %H:%M:%S',
        },
        'json': {
            '()': 'pythonjsonlogger.json.JsonFormatter',
            'format': '%(asctime)s %(levelname)s %(name)s %(message)s',
            'datefmt': '%Y-%m-%dT%H:%M:%S%z',
            'rename_fields': {
                'asctime': 'timestamp',
                'levelname': 'level',
                'name': 'logger',
            },
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'json' if _LOG_FORMAT == 'json' else 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': _LOG_LEVEL,
    },
    'loggers': {
        # Security / auth events — always INFO so auth telemetry is captured.
        'apps.accounts.security': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        # Billing subsystems — always INFO in staging so key events are visible
        'apps.billing': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'apps.billing.tasks': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'apps.billing.runtime': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'apps.billing.enforcement': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        # Reviews subsystem — always INFO so operational events are visible.
        'apps.reviews': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        # Celery internals
        'celery': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'celery.task': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        # Django request log (access log equivalent)
        'django.request': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
    },
}

# ── Security hardening ───────────────────────────────────────────────────────
# In production, set these via environment variables.
# In development, they default to permissive values.

_IS_PROD = not DEBUG

# Cookie security (applies to Django session cookie if session middleware is active)
SESSION_COOKIE_SECURE = os.getenv('SESSION_COOKIE_SECURE', str(_IS_PROD)).lower() == 'true'
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = os.getenv('SESSION_COOKIE_SAMESITE', 'Lax')

CSRF_COOKIE_SECURE = os.getenv('CSRF_COOKIE_SECURE', str(_IS_PROD)).lower() == 'true'
CSRF_COOKIE_HTTPONLY = True

# HTTPS enforcement (only in production)
SECURE_SSL_REDIRECT = os.getenv('SECURE_SSL_REDIRECT', str(_IS_PROD)).lower() == 'true'
SECURE_HSTS_SECONDS = int(os.getenv('SECURE_HSTS_SECONDS', '31536000' if _IS_PROD else '0'))
SECURE_HSTS_INCLUDE_SUBDOMAINS = os.getenv('SECURE_HSTS_INCLUDE_SUBDOMAINS', str(_IS_PROD)).lower() == 'true'
SECURE_HSTS_PRELOAD = os.getenv('SECURE_HSTS_PRELOAD', 'false').lower() == 'true'
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https') if _IS_PROD else None

X_FRAME_OPTIONS = 'DENY'
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = os.getenv('SECURE_REFERRER_POLICY', 'strict-origin-when-cross-origin')

# Number of trusted proxies in front of Django (ALB=1, CloudFront+ALB=2).
# Used to extract the real client IP from X-Forwarded-For.
TRUSTED_PROXY_DEPTH = int(os.getenv('TRUSTED_PROXY_DEPTH', '1'))

# ── Admin login rate limiting ────────────────────────────────────────────────
# All values configurable via env to allow tuning without redeploy.

ADMIN_LOGIN_IP_EMAIL_MAX_ATTEMPTS    = int(os.getenv('ADMIN_LOGIN_IP_EMAIL_MAX_ATTEMPTS', '5'))
ADMIN_LOGIN_IP_EMAIL_WINDOW_SECONDS  = int(os.getenv('ADMIN_LOGIN_IP_EMAIL_WINDOW_SECONDS', str(15 * 60)))
ADMIN_LOGIN_IP_EMAIL_COOLDOWN_SECONDS = int(os.getenv('ADMIN_LOGIN_IP_EMAIL_COOLDOWN_SECONDS', str(15 * 60)))

ADMIN_LOGIN_EMAIL_MAX_ATTEMPTS       = int(os.getenv('ADMIN_LOGIN_EMAIL_MAX_ATTEMPTS', '10'))
ADMIN_LOGIN_EMAIL_WINDOW_SECONDS     = int(os.getenv('ADMIN_LOGIN_EMAIL_WINDOW_SECONDS', str(30 * 60)))
ADMIN_LOGIN_EMAIL_COOLDOWN_SECONDS   = int(os.getenv('ADMIN_LOGIN_EMAIL_COOLDOWN_SECONDS', str(30 * 60)))

ADMIN_LOGIN_IP_MAX_ATTEMPTS          = int(os.getenv('ADMIN_LOGIN_IP_MAX_ATTEMPTS', '20'))
ADMIN_LOGIN_IP_WINDOW_SECONDS        = int(os.getenv('ADMIN_LOGIN_IP_WINDOW_SECONDS', str(10 * 60)))
ADMIN_LOGIN_IP_COOLDOWN_SECONDS      = int(os.getenv('ADMIN_LOGIN_IP_COOLDOWN_SECONDS', str(10 * 60)))

# Anti-enumeration: minimum artificial delay (seconds) for failed login responses.
ADMIN_LOGIN_FAILURE_DELAY_SECONDS    = float(os.getenv('ADMIN_LOGIN_FAILURE_DELAY_SECONDS', '0.5'))

# ── MFA (TOTP) ──────────────────────────────────────────────────────────────
# Fernet key for encrypting TOTP secrets at rest. REQUIRED in production.
# Generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
#
# Production (AWS): store in AWS Secrets Manager and inject via ECS task
# definition secretsRef or a startup script that calls:
#   aws secretsmanager get-secret-value --secret-id mirubro/mfa-encryption-key
# Never commit this value to source control.
MFA_ENCRYPTION_KEY = os.getenv('MFA_ENCRYPTION_KEY', '')

# OTP verification limits
MFA_OTP_MAX_ATTEMPTS   = int(os.getenv('MFA_OTP_MAX_ATTEMPTS', '5'))
MFA_OTP_LOCKOUT_SECONDS = int(os.getenv('MFA_OTP_LOCKOUT_SECONDS', str(15 * 60)))
MFA_CHALLENGE_TTL_SECONDS = int(os.getenv('MFA_CHALLENGE_TTL_SECONDS', str(5 * 60)))

# MFA bootstrap: first platform staff user can complete login without MFA
# to complete initial TOTP enrollment. Disable in production once enrolled.
MFA_BOOTSTRAP_ENABLED = os.getenv('MFA_BOOTSTRAP_ENABLED', 'true').lower() == 'true'

# ── IP allowlist for platform admin (optional) ───────────────────────────────
# Comma-separated list of IPs or CIDR ranges. Empty = disabled (all IPs allowed).
ADMIN_IP_ALLOWLIST = [
    ip.strip()
    for ip in os.getenv('ADMIN_IP_ALLOWLIST', '').split(',')
    if ip.strip()
]

# ── DRF throttle scopes for admin auth (secondary defense) ──────────────────
REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'].update({
    'admin_auth': os.getenv('ADMIN_AUTH_THROTTLE_RATE', '30/minute'),
    'admin_mfa': os.getenv('ADMIN_MFA_THROTTLE_RATE', '10/minute'),
})

# ── DRF throttle scopes for public auth endpoints ───────────────────────────
REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'].update({
    'auth_login':          os.getenv('AUTH_LOGIN_THROTTLE_RATE', '15/minute'),
    'auth_register':       os.getenv('AUTH_REGISTER_THROTTLE_RATE', '5/minute'),
    'auth_forgot_password': os.getenv('AUTH_FORGOT_PASSWORD_THROTTLE_RATE', '5/minute'),
    'auth_reset_password':  os.getenv('AUTH_RESET_PASSWORD_THROTTLE_RATE', '5/minute'),
    'auth_verify_email':    os.getenv('AUTH_VERIFY_EMAIL_THROTTLE_RATE', '5/minute'),
    'auth_refresh':         os.getenv('AUTH_REFRESH_THROTTLE_RATE', '30/minute'),
    # Public-facing endpoints (menu, reviews, tips)
    'public_menu':          os.getenv('PUBLIC_MENU_THROTTLE_RATE', '120/minute'),
    'public_reviews':       os.getenv('PUBLIC_REVIEWS_THROTTLE_RATE', '60/minute'),
    'public_tips':          os.getenv('PUBLIC_TIPS_THROTTLE_RATE', '60/minute'),
    'public_appointments':  os.getenv('PUBLIC_APPOINTMENTS_THROTTLE_RATE', '120/minute'),
    # POST de reserva pública (Slice 4B): más restrictivo que la lectura, mismo criterio que auth_register.
    'public_appointments_booking': os.getenv('PUBLIC_APPOINTMENTS_BOOKING_THROTTLE_RATE', '20/minute'),
    # POST de checkout de seña (Slice 6A): cada request exitoso puede crear una Preference en MP.
    'public_appointments_checkout': os.getenv('PUBLIC_APPOINTMENTS_CHECKOUT_THROTTLE_RATE', '10/minute'),
    # AGENT 02B: requests firmadas por AgentInstance (no por IP).
    'agent_leads_sync': os.getenv('AGENT_LEADS_SYNC_THROTTLE_RATE', '600/minute'),
})

# ── Owner/public login 3D rate limiting ──────────────────────────────────────
# All values configurable via env to allow tuning without redeploy.

AUTH_LOGIN_IP_IDENT_MAX_ATTEMPTS    = int(os.getenv('AUTH_LOGIN_IP_IDENT_MAX_ATTEMPTS', '10'))
AUTH_LOGIN_IP_IDENT_WINDOW_SECONDS  = int(os.getenv('AUTH_LOGIN_IP_IDENT_WINDOW_SECONDS', str(15 * 60)))
AUTH_LOGIN_IP_IDENT_COOLDOWN_SECONDS = int(os.getenv('AUTH_LOGIN_IP_IDENT_COOLDOWN_SECONDS', str(15 * 60)))

AUTH_LOGIN_IDENT_MAX_ATTEMPTS       = int(os.getenv('AUTH_LOGIN_IDENT_MAX_ATTEMPTS', '20'))
AUTH_LOGIN_IDENT_WINDOW_SECONDS     = int(os.getenv('AUTH_LOGIN_IDENT_WINDOW_SECONDS', str(30 * 60)))
AUTH_LOGIN_IDENT_COOLDOWN_SECONDS   = int(os.getenv('AUTH_LOGIN_IDENT_COOLDOWN_SECONDS', str(30 * 60)))

AUTH_LOGIN_IP_MAX_ATTEMPTS          = int(os.getenv('AUTH_LOGIN_IP_MAX_ATTEMPTS', '50'))
AUTH_LOGIN_IP_WINDOW_SECONDS        = int(os.getenv('AUTH_LOGIN_IP_WINDOW_SECONDS', str(10 * 60)))
AUTH_LOGIN_IP_COOLDOWN_SECONDS      = int(os.getenv('AUTH_LOGIN_IP_COOLDOWN_SECONDS', str(10 * 60)))

