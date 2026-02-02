from pathlib import Path
from datetime import timedelta
from decimal import Decimal
import os

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR.parent / '.env')

SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'unsafe-secret')
DEBUG = os.getenv('DJANGO_DEBUG', 'True').lower() == 'true'
ALLOWED_HOSTS = [host.strip() for host in os.getenv('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1,mirubro-api').split(',') if host]

INSTALLED_APPS = [
  'django.contrib.admin',
  'django.contrib.auth',
  'django.contrib.contenttypes',
  'django.contrib.sessions',
  'django.contrib.messages',
  'django.contrib.staticfiles',
  'rest_framework',
  'rest_framework_simplejwt',
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
  'apps.resto',
  'apps.billing',
]

MIDDLEWARE = [
  'corsheaders.middleware.CorsMiddleware',
  'django.middleware.security.SecurityMiddleware',
  'django.contrib.sessions.middleware.SessionMiddleware',
  'django.middleware.common.CommonMiddleware',
  'django.middleware.csrf.CsrfViewMiddleware',
  'django.contrib.auth.middleware.AuthenticationMiddleware',
  'django.contrib.messages.middleware.MessageMiddleware',
  'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

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
  }
}

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
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR.parent / 'media'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

CORS_ALLOWED_ORIGINS = [
  origin.strip()
  for origin in os.getenv('CORS_ALLOWED_ORIGINS', 'http://localhost:3000').split(',')
  if origin
]
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = ['authorization', 'content-type', 'x-requested-with']

REST_FRAMEWORK = {
  'DEFAULT_AUTHENTICATION_CLASSES': [
    'apps.accounts.authentication.CookieJWTAuthentication',
    'rest_framework.authentication.SessionAuthentication',
  ],
  'DEFAULT_PERMISSION_CLASSES': [
    'rest_framework.permissions.IsAuthenticatedOrReadOnly',
  ],
  'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
}

ACCESS_TOKEN_MINUTES = int(os.getenv('ACCESS_TOKEN_LIFETIME_MINUTES', '15'))
REFRESH_TOKEN_DAYS = int(os.getenv('REFRESH_TOKEN_LIFETIME_DAYS', '7'))

raw_cookie_domain = os.getenv('COOKIE_DOMAIN', '').strip()
if raw_cookie_domain.lower() in {'', 'localhost', '127.0.0.1'}:
  AUTH_COOKIE_DOMAIN = None
else:
  AUTH_COOKIE_DOMAIN = raw_cookie_domain
AUTH_COOKIE_SECURE = os.getenv('COOKIE_SECURE', 'False').lower() == 'true'
AUTH_COOKIE_SAMESITE = os.getenv('COOKIE_SAMESITE', 'Lax')
AUTH_COOKIE_PATH = '/'
AUTH_COOKIE_ACCESS_MAX_AGE = int(os.getenv('ACCESS_TOKEN_MAX_AGE_SECONDS', str(ACCESS_TOKEN_MINUTES * 60)))
AUTH_COOKIE_REFRESH_MAX_AGE = int(os.getenv('REFRESH_TOKEN_MAX_AGE_SECONDS', str(REFRESH_TOKEN_DAYS * 24 * 60 * 60)))

SIMPLE_JWT = {
  'ACCESS_TOKEN_LIFETIME': timedelta(minutes=ACCESS_TOKEN_MINUTES),
  'REFRESH_TOKEN_LIFETIME': timedelta(days=REFRESH_TOKEN_DAYS),
  'ROTATE_REFRESH_TOKENS': True,
  'BLACKLIST_AFTER_ROTATION': False,
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

CELERY_BROKER_URL = os.getenv('REDIS_URL', 'redis://redis:6379/0')
CELERY_RESULT_BACKEND = CELERY_BROKER_URL

REPORTS_LOW_STOCK_THRESHOLD_DEFAULT = Decimal(os.getenv('REPORTS_LOW_STOCK_THRESHOLD_DEFAULT', '5'))
