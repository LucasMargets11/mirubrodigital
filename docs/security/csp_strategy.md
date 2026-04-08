# Estrategia CSP — MiRubro Digital

> Fase 2D · Última actualización: 2026-04-07

## 1. Estado actual

CSP está implementada en modo **report-only** en dos capas:

| Capa      | Archivo                                | Header                                    |
|-----------|----------------------------------------|-------------------------------------------|
| Django    | `services/api/src/config/middleware.py` | `Content-Security-Policy-Report-Only`     |
| Next.js   | `apps/web/src/middleware.ts`           | `Content-Security-Policy-Report-Only`     |

**No se bloquea nada.** Las violaciones solo aparecen en la consola del navegador.

---

## 2. Política actual explicada

### Django (API / Admin / DRF browsable)

```
default-src 'self';
script-src 'self' 'unsafe-inline';
style-src 'self' 'unsafe-inline';
img-src 'self' data:;
font-src 'self' data:;
connect-src 'self';
frame-ancestors 'none';
base-uri 'self';
form-action 'self'
```

### Next.js (Frontend)

```
default-src 'self';
script-src 'self' 'unsafe-inline' ['unsafe-eval' solo en dev];
style-src 'self' 'unsafe-inline';
img-src 'self' data: https://via.placeholder.com https://images.unsplash.com;
font-src 'self' data:;
connect-src 'self' [localhost:8000 en dev | NEXT_PUBLIC_API_URL en prod];
frame-ancestors 'none';
base-uri 'self';
form-action 'self'
```

### Por qué `'unsafe-inline'`

- **script-src**: Next.js inyecta `<script>` inline para hidratación y chunk loading. Sin un sistema de nonces per-request, `'unsafe-inline'` es necesario.
- **style-src**: Algunos componentes React, animaciones y estilos dinámicos (`style=` attributes) pueden requerir inline styles. Se debe auditar cuáles son realmente necesarios antes de endurecer `style-src` y remover `'unsafe-inline'`.

### Por qué `'unsafe-eval'` solo en dev

- Next.js Fast Refresh (hot-reload) usa `eval()` para inyectar módulos actualizados en el browser.
- En producción, el bundle está pre-compilado y no usa `eval()`. Por eso `'unsafe-eval'` solo aplica cuando `NODE_ENV=development`.

### Cómo funciona `connect-src` por entorno

```typescript
// middleware.ts
const apiOrigin = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
const connectSrc = isDev
    ? "connect-src 'self' http://localhost:8000 http://api:8000"
    : `connect-src 'self' ${apiOrigin}`;
```

- **Dev**: permite `localhost:8000` (browser directo) y `api:8000` (Docker internal).
- **Prod**: solo `'self'` + la URL real del API (`NEXT_PUBLIC_API_URL`). Ningún host de desarrollo queda expuesto.

---

## 3. Cómo observar violaciones

### 3.1 DevTools → Console

Las violaciones CSP report-only aparecen como warnings:

```
[Report Only] Refused to execute inline script because it violates the
following Content-Security-Policy directive: "script-src 'self'". Either
the 'unsafe-inline' keyword, a hash, or a nonce is required to enable inline execution.
```

### 3.2 DevTools → Network → filtrar por `csp-report`

Si se agrega `report-uri` o `report-to` en el futuro, las violaciones se enviarán como requests POST a un endpoint de recolección.

### 3.3 Qué buscar

| Tipo de violación        | ¿Esperada? | Acción                                        |
|--------------------------|------------|-----------------------------------------------|
| inline script blocked    | Sí         | Esperada hasta que implementemos nonces       |
| inline style blocked     | Sí         | Esperada por Tailwind/React                   |
| eval blocked             | Solo dev   | Si aparece en prod → investigar               |
| connect a host unknown   | No         | **Peligrosa** — posible XSS exfiltrando datos |
| frame-ancestors violated | No         | Alguien intenta embeber la app (clickjacking) |
| img-src externo unknown  | Quizás     | Evaluar si es CDN legítimo o inyección        |

---

## 4. Plan de endurecimiento

### Fase 1: Observar (actual)

- [x] CSP report-only activa en Django y Next.js
- [x] `'unsafe-eval'` limitada a dev
- [x] `connect-src` env-aware
- [x] `frame-ancestors 'none'`
- [ ] Monitorear violaciones en DevTools durante 2+ semanas

### Fase 2: Limpiar violaciones conocidas

| Tarea                              | Esfuerzo | Impacto |
|------------------------------------|----------|---------|
| Implementar nonces para scripts    | Alto     | Permite remover `'unsafe-inline'` de script-src |
| Migrar estilos inline a clases CSS | Medio    | Permite remover `'unsafe-inline'` de style-src  |
| Auditar img-src externos            | Bajo     | Acotar lista de dominios permitidos              |

#### Nonces en Next.js

Next.js 13+ soporta CSP nonces via `next/headers`:

```typescript
// Generar nonce per-request en middleware
const nonce = Buffer.from(crypto.randomUUID()).toString('base64');
// Inyectar en CSP: script-src 'nonce-{nonce}'
// Pasar al layout via header o cookie
```

Esto es un cambio de arquitectura no-trivial. Evaluar para una fase futura.

### Fase 3: Enforce parcial

Una vez que no haya violaciones críticas:

1. Cambiar `Content-Security-Policy-Report-Only` → `Content-Security-Policy` en Django primero (menor superficie de HTML).
2. Mantener report-only en Next.js hasta validar nonces.

### Fase 4: Enforce completo

- CSP enforce en ambas capas
- `'unsafe-inline'` reemplazado por nonces
- `'unsafe-eval'` eliminado por completo

---

## 5. Checklist antes de activar enforce

- [ ] **0 violaciones críticas** en report-only durante 2 semanas mínimo
- [ ] **Frontend estable**: todas las funcionalidades probadas sin errores de CSP
- [ ] **`connect-src` correcto**: `NEXT_PUBLIC_API_URL` configurada en prod
- [ ] **img-src cerrado**: solo dominios conocidos (placeholder.com, unsplash si se usa)
- [ ] **No hay scripts de terceros** no contemplados (analytics, chat widgets, etc.)
- [ ] **Tests pasan**: 72/72 security tests sin regressions
- [ ] **Rollback plan**: poder volver a report-only cambiando el header en middleware

### Cómo activar enforce (cuando esté listo)

**Django** — `config/middleware.py`:
```python
# Cambiar esta línea:
response['Content-Security-Policy-Report-Only'] = _CSP_POLICY
# Por:
response['Content-Security-Policy'] = _CSP_POLICY
```

**Next.js** — `middleware.ts`:
```typescript
// Cambiar esta línea:
response.headers.set('Content-Security-Policy-Report-Only', CSP_DIRECTIVES);
// Por:
response.headers.set('Content-Security-Policy', CSP_DIRECTIVES);
```

### Rollback inmediato

Revertir el nombre del header a `Content-Security-Policy-Report-Only`. No requiere ningún otro cambio.
