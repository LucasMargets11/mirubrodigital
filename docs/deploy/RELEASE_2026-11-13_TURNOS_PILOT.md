# Release 2026-11-13 — Turnos para el primer cliente

Tag: `release-2026-11-13-turnos-pilot` (rama `develop`). Bot: `agenterecep`
`e8b70fb` en `develop` (no se despliega en este corte).

## Destino

| | |
|---|---|
| Dominio | `https://www.mirubro.com` (apex `mirubro.com` → 301 a www) |
| Host | `18.230.251.156` (AWS sa-east-1), nginx 1.28 delante de los contenedores |
| API | mismo dominio, `/api/v1/` (no hay `api.mirubro.com`) |
| Compose | `infra/docker-compose.yml` del checkout del servidor; `.env` en `services/api/.env` y `apps/web/.env` (no versionados) |
| Versión en producción al 2026-11-13 | anterior a Turnos: `/api/v1/leads/` y `/app/turnos` responden 404. Se asume `master` (`4c7ebfe`); confirmarlo con `git rev-parse HEAD` en el servidor (paso 0). |

La infraestructura Terraform/ECS de `infra/terraform` está documentada pero no
es la que sirve producción.

## Qué entra

Todo Turnos (agenda, servicios, profesionales, pagos MP del negocio, link
público), Clientes (notas, recordatorios, entregas), Leads + receptor del
agente + toma de chat, ciclo de vida de webhooks de billing, stock por
ubicación, alta de Turnos desde el panel admin. Flags del agente apagados.

Ajustes de este release sobre `e383ac5`:

- `.gitattributes`: `*.sh` con LF (el checkout de Windows rompía `set -e`).
- `requirements.txt`: `celery==5.6.3`, `kombu==5.6.2` (5.7.0 tira el worker al arrancar).
- `docker-entrypoint.sh`: `manage.py` en la ruta correcta; modos `migrate`,
  `precheck`, `postcheck`. `migrate` corre con `AI_USAGE_METERING_ENABLED=false`
  para ese proceso y después ejecuta los checks de base con el entorno real.
- `infra/docker-compose.yml`: la API migra al arrancar a través del entrypoint.
- Alta admin: los planes Turnos sembrados (inactivos, no a la venta) se pueden
  otorgar como acceso bonificado desde `/admin/clientes/nuevo`. El checkout
  público sigue cerrado (`appointments.is_active=false`).

## Migraciones (desde `master`)

| App | Migraciones | Nota |
|---|---|---|
| accounts | 0034 | |
| appointments | 0001–0015 | tablas nuevas |
| billing | 0022–0027 | **0023 requiere ventana** (writers viejos fallan) |
| business | 0025–0028 | |
| customers | 0005–0014 | aditivas |
| inventory | 0009–0012 | **0010/0011 corte coordinado** (`docs/STOCK_LOCATIONS_PR2_CUTOVER.md`) |
| leads | 0001–0010 | tablas nuevas |
| menu | 0014 | solo estado (MercadoPagoConnection pasa a merchant_payments) |
| merchant_payments | 0001–0002 | **0002 cifra tokens MP: exige `MP_TOKEN_ENCRYPTION_KEY`** |
| notifications | 0002–0005 | |

Probado sobre base vacía con la imagen del release: todas aplican, post-check
sin errores, también con la medición encendida.

## Variables nuevas en `services/api/.env`

Obligatoria antes de migrar:

```
MP_TOKEN_ENCRYPTION_KEY=<Fernet nueva; guardarla fuera del servidor también>
```

Generar: `docker compose run --rm --no-deps api python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.

Dejar explícitas (default seguro):

```
AGENT_INTEGRATION_ENABLED=false
AGENT_TAKEOVER_ENABLED=false
AI_USAGE_METERING_ENABLED=false
AI_USAGE_BILLING_PROVIDER=disabled
CUSTOMER_DELIVERY_PROVIDER_EMAIL=fake
```

`AGENT_SECRET_ENCRYPTION_KEY` se carga recién al conectar el bot.

## Procedimiento (en el servidor, desde la raíz del checkout)

```bash
# 0. Registrar la versión actual (reversión)
cd <checkout>
git rev-parse HEAD | tee ~/pre-release-2026-11-13.sha
docker compose -f infra/docker-compose.yml images | tee ~/pre-release-2026-11-13.images
cp services/api/.env ~/pre-release-2026-11-13.api.env
cp apps/web/.env ~/pre-release-2026-11-13.web.env
docker compose -f infra/docker-compose.yml exec -T api python manage.py showmigrations --plan | grep '\[X\]' | tail -n 400 > ~/pre-release-2026-11-13.migrations
for s in api web celery-worker celery-beat; do docker tag infra-$s:latest infra-$s:pre-2026-11-13; done

# 1. Código y configuración
git fetch origin --tags
git checkout release-2026-11-13-turnos-pilot
#   editar services/api/.env (bloque de arriba)

# 2. Imágenes ANTES del corte (servicios viejos siguen atendiendo)
docker compose -f infra/docker-compose.yml build api web celery-worker celery-beat
docker compose -f infra/docker-compose.yml run --rm --no-deps api precheck    # sin errores

# 3. Backup verificado (con la versión vieja todavía arriba)
#    Si POSTGRES_HOST=postgres (contenedor del compose):
docker compose -f infra/docker-compose.yml exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > ~/mirubro-2026-11-13-pre.dump
#    Si POSTGRES_HOST apunta a RDS: además snapshot manual en la consola RDS, y
#    docker run --rm --env-file services/api/.env postgres:16-alpine sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -h "$POSTGRES_HOST" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > ~/mirubro-2026-11-13-pre.dump
ls -lh ~/mirubro-2026-11-13-pre.dump
docker run --rm -i postgres:16-alpine pg_restore --list < ~/mirubro-2026-11-13-pre.dump | grep -c 'TABLE DATA'   # > 0, sin error
#    Copiar el dump fuera del servidor (S3 o equipo del operador).

# 4. Corte: drenar escritores (MP reintenta webhooks mientras tanto)
docker compose -f infra/docker-compose.yml stop celery-beat
docker compose -f infra/docker-compose.yml stop celery-worker     # termina las tareas en curso
docker compose -f infra/docker-compose.yml stop api web
#    Sin otros procesos que escriban inventario (comandos manuales, cron).

# 5. Migrar una sola vez con la imagen nueva
docker compose -f infra/docker-compose.yml run --rm --no-deps api migrate
docker compose -f infra/docker-compose.yml run --rm --no-deps api python manage.py showmigrations billing inventory leads appointments merchant_payments | grep -c '\[ \]'   # 0
docker compose -f infra/docker-compose.yml run --rm --no-deps api python manage.py shell -c "
from django.db.models import Count, F
from apps.inventory.models import ProductStock, StockLocation
print('stock sin ubicación:', ProductStock.objects.filter(location__isnull=True).count())
print('stock con ubicación de otro negocio:', ProductStock.objects.exclude(location__business_id=F('business_id')).count())
print('negocios con >1 principal:', StockLocation.objects.filter(is_primary=True, is_active=True).values('business').annotate(n=Count('id')).filter(n__gt=1).count())
print('filas ProductStock:', ProductStock.objects.count())
"
#    Comparar 'filas ProductStock' con el conteo previo del backup:
#    docker run --rm -i postgres:16-alpine pg_restore -f - -a -t inventory_productstock < ~/mirubro-2026-11-13-pre.dump | grep -c -v -E '^(--|SET|SELECT|COPY|\\\.|$)'

# 6. Catálogo Turnos (inactivo, no a la venta) para el alta desde el panel
docker compose -f infra/docker-compose.yml run --rm --no-deps api python manage.py seed_appointments_catalog

# 7. Levantar todo con la misma versión, en orden
docker compose -f infra/docker-compose.yml up -d api
curl -fsS https://www.mirubro.com/api/v1/health/       # {"status":"ok",...database ok, redis ok}
docker compose -f infra/docker-compose.yml up -d web
docker compose -f infra/docker-compose.yml up -d celery-worker
docker compose -f infra/docker-compose.yml up -d celery-beat
```

## Verificación

```bash
C="docker compose -f infra/docker-compose.yml"
$C ps                                                          # 4 servicios Up, una sola celery-beat
$C images | grep -E 'api|web|celery'                           # mismas imágenes recién construidas
curl -fsS -o /dev/null -w '%{http_code}\n' https://www.mirubro.com/            # 200
curl -fsS -o /dev/null -w '%{http_code}\n' https://www.mirubro.com/api/health  # 200 (web) — si nginx lo enruta
curl -s  -o /dev/null -w '%{http_code}\n' https://www.mirubro.com/api/v1/leads/   # 401 (antes 404)
$C exec celery-worker celery -A config inspect ping            # 1 node online
$C exec celery-worker celery -A config inspect registered | grep -c -E 'appointments\.|leads\.|customers\.'
$C logs --since 5m celery-beat | grep -c 'Sending due task'    # > 0
$C logs --since 5m celery-worker | grep -E 'retry sweep skipped|ERROR' | head   # vacío
docker ps --format '{{.Names}}' | grep -c beat                 # 1
$C run --rm --no-deps api postcheck
```

En el navegador (usuario staff de plataforma): `/admin/clientes`,
`/admin/clientes/nuevo` muestra "Turnos" con planes Turnos y Turnos Pro.
Con un negocio existente: login, `/app` del servicio que usa, POS/stock
(un producto con stock muestra la misma cantidad que antes), ventas/pedidos,
Menú QR público (`/r/<slug>/`), reseñas QR, facturación (estado de la
suscripción).

## Reversión

- Hasta el paso 4 (antes de migrar): `git checkout $(cat ~/pre-release-2026-11-13.sha)`
  y `docker compose up -d` con las imágenes `:pre-2026-11-13` retaggeadas a `latest`.
- Después de migrar: el esquema nuevo **no** es compatible con el código viejo
  (billing.0023, inventory.0011). Revertir = detener todo y restaurar el dump:
  `pg_restore --clean --if-exists -d <db>` desde `~/mirubro-2026-11-13-pre.dump`,
  luego código e imágenes previas. Se pierde lo escrito después del corte.
- Revertir migraciones por separado no es la vía recomendada: `inventory` no
  vuelve atrás si ya hay stock en dos ubicaciones; `merchant_payments` < 0002
  deja tokens MP en texto plano.

## Pendiente fuera de este corte

- Bot: desplegar `agenterecep` `develop` (`e8b70fb`) con credenciales; ver
  `docs/turnos/LEADS_HANDOFF_RECEPCION.md`.
- Activar `AGENT_INTEGRATION_ENABLED` y `provision_agent` solo después.
