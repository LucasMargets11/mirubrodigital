# Auditoría de login con Google — MiRubro

**Fecha:** 9 de mayo de 2026  
**Autor:** Auditoría técnica — senior backend engineer  
**Alcance:** Solo lectura del código. No se modificó nada.

---

## 1. Resumen ejecutivo

**Un usuario secundario creado por el owner con un Gmail puede ingresar directamente con "Ingresar con Google". Funciona hoy, sin ningún cambio adicional.**

El flujo de `GoogleAuthView` tiene implementado explícitamente el escenario de vinculación por email: si existe un `User` con ese email pero sin `google_sub`, el sistema lo vincula automáticamente en el primer login con Google, respeta su `Membership` y `role` existentes, y emite JWT válido para el negocio del owner.

La implementación es segura en los aspectos críticos: valida firma, audience, issuer y `email_verified` vía la librería oficial de Google.

---

## 2. Flujo actual de Google login

**Endpoint:** `POST /api/v1/auth/google/`  
**Archivo:** `services/api/src/apps/accounts/views.py` — `GoogleAuthView`  
**Throttle:** `GoogleAuthThrottle` — 10/minute por IP

### Pasos detallados

**1. Recibe el credential (ID token)**  
El frontend envía `{ "credential": "<Google ID token>" }` obtenido desde el botón de Google.

**2. Valida el token con Google**  
Llama a `GoogleOAuthService.verify_token(credential)`, que usa `google.oauth2.id_token.verify_oauth2_token()` de la librería oficial de Google.  
Valida internamente:
- Firma RS256 contra las claves públicas de Google (JWKS)
- Expiración del token
- `audience` → debe coincidir con `GOOGLE_OAUTH_CLIENT_ID` (configurado en settings)
- `issuer` → debe ser `accounts.google.com` o `https://accounts.google.com`

Si falla cualquier validación → 400 con "Token de Google inválido o expirado."

**3. Verifica `email_verified`**  
Revisa explícitamente que `payload.email_verified == True`.  
Si Google devuelve `email_verified=false` → 400 con "El email de Google no está verificado."

**4. Busca usuario por `google_sub` (Paso 1 de lookup)**  
Hace `AccountProfile.objects.get(google_sub=payload.sub)` — índice único.  
Si encuentra → usuario identificado, pasa al check de `is_active`.

**5. Busca usuario por email y vincula `google_sub` (Paso 2 de lookup)**  
Si no encontró por `google_sub`:  
```python
user = User.objects.get(email__iexact=payload.email)
profile.google_sub = payload.sub  # vincula
profile.email_verified = True     # marca verificado si no lo estaba
profile.save(...)
```
Lookup es case-insensitive. Vinculación es automática, sin confirmación adicional.

**6. Crea usuario nuevo si no existe (Paso 3)**  
Si tampoco encontró por email:  
- Crea `User` con `set_unusable_password()` (sin contraseña)
- `auth_provider='google'`, `google_sub=payload.sub`, `email_verified=True`
- `account_mode` queda en default `owner_managed` (potencial issue para nuevos registros directos)
- Marca `is_new_user=True`

**7. Verifica `is_active`**  
Si `user.is_active == False` → 403 "Cuenta suspendida."

**8. Resuelve membership y emite JWT**  
Llama a `_ensure_membership(user)`:
- Si el usuario ya tiene Membership → devuelve la primera encontrada (su membership existente en el negocio del owner)
- Si no tiene ninguna → crea un negocio nuevo en estado `onboarding` (aplica solo a nuevos registros vía Google, no a secundarios)

Emite JWT (access + refresh) como cookies httpOnly. Establece cookie de business context.

**9. Loguea el evento**  
Emite `security_events.login_success(user_id, email, ip)` → log estructurado `auth.login.success`.  
**No genera `AccessAuditLog` en base de datos** para logins con Google (ver sección 4).

---

## 3. Comportamiento por escenario

| Escenario | Resultado actual | Riesgo | Recomendación |
|---|---|---|---|
| User existe con mismo email y **sin** `google_sub` | ✅ Login exitoso. Se vincula `google_sub` automáticamente. Se respeta su Membership/role existente | Bajo — requiere que Google confirme email ownership | Documentar. Es el flujo esperado para secundarios. |
| User existe con mismo email y **con** `google_sub` | ✅ Login por `google_sub` (lookup rápido por índice único). Sin vinculación adicional | Ninguno | OK. |
| User **no existe** en la base | ⚠️ Se crea un usuario nuevo con negocio propio en `onboarding`. `account_mode=owner_managed` | Medio — si era un email institucional podría crear cuenta duplicada sin membresía real | Evaluar si debería requerir invitación previa para evitar cuentas huérfanas. |
| User está **inactivo** (`is_active=False`) | ✅ Rechazado con 403 "Cuenta suspendida" | Ninguno | OK. |
| User existe pero **no tiene membership** | ⚠️ `_ensure_membership` crea un negocio nuevo en `onboarding` para ese usuario | Potencial confusión — el secundario aparece con su propio negocio vacío | Considerar devolver 403 si no tiene membership en el contexto esperado. |
| User tiene **rol secundario** en un negocio | ✅ `_ensure_membership` devuelve su Membership existente. JWT incluye contexto del negocio correcto. | Ninguno | OK. Funciona correctamente. |
| Email de Google **no verificado** | ✅ Rechazado en paso 3 con 400 "El email de Google no está verificado" | Ninguno | OK. |
| Email de Google con **case distinto** (ej. `Lucas@gmail.com` vs `lucas@gmail.com`) | ✅ Lookup es `email__iexact` — case-insensitive | Ninguno | OK. |
| Usuario tiene **`account_mode=owner_managed`** | ✅ Login permitido. `account_mode` NO restringe login vía Google | Ninguno — `account_mode` controla self-service de contraseña, no el login | OK por diseño. |

---

## 4. Seguridad

### ✅ Validaciones implementadas correctamente

| Control | Estado | Detalle |
|---|---|---|
| Firma del token (RS256) | ✅ Validado | Via `id_token.verify_oauth2_token()` de Google |
| `audience` / `client_id` | ✅ Validado | Comparado contra `GOOGLE_OAUTH_CLIENT_ID` en settings |
| `issuer` | ✅ Validado | La librería de Google valida `accounts.google.com` automáticamente |
| `email_verified` | ✅ Verificado | Bloquea si Google devuelve `false` |
| Expiración del token | ✅ Validado | Manejado por la librería de Google |
| `is_active` del usuario | ✅ Verificado | 403 si el usuario está desactivado |
| `google_sub` almacenado | ✅ Sí, vinculado en primer login | Índice único en base de datos |
| Throttle | ✅ 10/minute por IP | `GoogleAuthThrottle` |

### ⚠️ Gaps encontrados

**1. Sin `AccessAuditLog` para logins con Google**  
Los logins regulares no tienen `AccessAuditLog` tampoco, solo `security_events` (log estructurado). Pero el evento de vinculación (`google_sub` linked por primera vez) también solo queda en logger INFO sin registro en base de datos. No se puede auditar retroactivamente qué usuarios fueron vinculados a Google.

**2. Vinculación automática sin notificación**  
Cuando un usuario existente hace su primer login con Google, se le vincula `google_sub` sin que reciba ningún aviso (email de seguridad). Si alguien tomara control de una cuenta de Gmail con el mismo email, podría vincularse sin que el usuario lo sepa.

**3. Nuevo usuario sin membership real**  
Si alguien con un email Gmail que nunca fue registrado en el sistema hace login con Google → se crea una cuenta nueva con negocio vacío en `onboarding`. No hay forma actual de distinguir este caso de un usuario secundario que "se olvidó" de que fue invitado.

**4. `account_mode=owner_managed` para nuevos usuarios Google**  
Cuando se crea un usuario nuevo via Google (paso 3), el `account_mode` queda en `owner_managed` (default del modelo). Esto significa que no puede hacer self-reset de contraseña, lo cual es correcto (no tiene contraseña), pero puede generar confusión en otros flujos que revisan `account_mode`.

### ✅ Account takeover: riesgo bajo

El escenario de account takeover requeriría:
1. El atacante controla una cuenta de Google con el mismo email
2. Google devuelve `email_verified=true` para esa cuenta

Esto equivale a que el atacante ya controla el email objetivo — si controla el Gmail, el takeover de MiRubro es un efecto secundario esperado. **No hay riesgo de takeover sin control previo del email.**

---

## 5. Impacto en usuarios secundarios

**Respuesta directa:**

> ¿El owner puede crear un admin secundario con `lucasmargets@gmail.com` y ese usuario entrar simplemente con "Ingresar con Google"?

**✅ Sí. Funciona hoy, sin ningún cambio.**

Flujo concreto:

1. Owner crea usuario via `InternalUserService.create_internal_user(email='lucasmargets@gmail.com', role='admin', ...)`
2. Se crea `User` + `AccountProfile` (con `email_verified=True`, `account_mode='owner_managed'`) + `Membership` activa en el negocio del owner
3. El usuario abre la app, hace clic en "Ingresar con Google" con su cuenta `lucasmargets@gmail.com`
4. Google verifica y devuelve payload con `email_verified=true`, `sub=...`
5. `GoogleAuthView`:
   - `google_sub` lookup → no encontrado (primer login)
   - `email__iexact='lucasmargets@gmail.com'` → **encontrado**
   - Vincula `google_sub` automáticamente
   - `_ensure_membership(user)` → devuelve su Membership en el negocio del owner
6. Se emiten JWT cookies. El usuario queda logueado como admin del negocio correcto.

**El role, el business context y los permisos se respetan íntegramente.**

---

## 6. Recomendación técnica

El flujo actual es correcto para el caso de uso principal. El flujo ideal que se debería documentar (y ya funciona):

```
Owner crea usuario secundario con email Gmail
         ↓
Usuario abre app → hace clic en "Ingresar con Google"
         ↓
Google confirma email_verified=true
         ↓
Backend: email__iexact lookup → User encontrado
         ↓
Backend: vincula google_sub (primera vez)
         ↓
Backend: _ensure_membership → Membership existente del negocio del owner
         ↓
JWT emitido con business context correcto → Login exitoso
```

**Mejoras opcionales (no bloqueantes):**

1. **Email de seguridad al vincular Google por primera vez**: Cuando el sistema ejecuta el paso 2 (vinculación por email sin `google_sub` previo), enviar un email de seguridad al usuario: "Tu cuenta fue vinculada a Google. Si no fuiste vos, contactá soporte." Esto cierra el gap de notificación identificado.

2. **`AccessAuditLog` para GOOGLE_LINKED**: Registrar en base de datos cuando un `google_sub` es vinculado por primera vez a un usuario existente. Util para soporte y auditoría.

3. **`account_mode` para nuevos usuarios Google**: Nuevos usuarios que se registran directamente via Google (sin invitación previa del owner) deberían tener `account_mode='personal'` para que puedan usar self-service de contraseña en el futuro.

---

## 7. Próximo PR recomendado

**Opción A — Solo email informativo al usuario secundario, porque Google login ya funciona por email.**

Esta es la opción correcta para el contexto actual. El login ya funciona. La vinculación ya ocurre. Lo que falta es:

- Email de seguridad cuando `google_sub` es vinculado por primera vez a un usuario existente  
  (equivalente a PR-4 pero para vinculación OAuth, no para cambio de contraseña)
- El email diría: "Tu cuenta de MiRubro fue vinculada a Google. Si no fuiste vos, contactá soporte."

**No es necesario implementar vinculación — ya existe y funciona.**

**Opción B** (implementar vinculación segura) — **No aplica**. Ya está implementada.

**Opción C** (ambas) — No corresponde. El PR debería ser solo el email de aviso de vinculación.

---

## 8. Checklist

- [x] Se revisó backend Google login (`GoogleAuthView`, `GoogleOAuthService`)
- [x] Se revisó si existe `google_sub` (campo en `AccountProfile`, unique index)
- [x] Se revisó validación de `email_verified` (paso explícito en la view)
- [x] Se revisó creación/vinculación de usuario (3 pasos: sub lookup → email lookup+link → create)
- [x] Se revisó memberships/roles (`_ensure_membership` devuelve Membership existente)
- [x] Se revisó riesgo de account takeover (bajo — requiere control del email en Google)
- [x] No se modificó código
