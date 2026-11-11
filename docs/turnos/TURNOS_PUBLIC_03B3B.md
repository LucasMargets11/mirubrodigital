# TURNOS PUBLIC 03B3B — onboarding mínimo post-compra

## Experiencia previa

Turnos ya tenía panel, servicios y categorías, horarios generales y por profesional, profesionales, configuración y tarjeta del link público. El retorno de 03B2 ya sondeaba el estado del checkout; en `active` llevaba al panel general. El retorno legacy a `/app/onboarding/checkout` no necesitaba cambios.

No se duplicaron pantallas, catálogo de servicios, generación de URL ni reglas de acceso.

## Decisión UX

El panel existente `/app/turnos` muestra una guía liviana a quienes pueden administrar Turnos. Se puede ocultar localmente y no redirige, bloquea ni cambia entitlements. El CTA del retorno activo lleva a `/app/turnos?onboarding=1`; la guía también permanece accesible desde el panel.

Los pasos esenciales son:

1. **Servicios:** al menos un servicio activo y reservable.
2. **Horarios:** una franja semanal que permita al menos un turno de un servicio activo.
3. **Link público:** página pública disponible.

El progreso es `n de 3 pasos esenciales completados`. Al completar los tres, se muestra “Tu agenda está lista para recibir reservas” y el CTA “Ver agenda”. Las configuraciones continúan visibles.

**Profesionales es opcional** y no entra en el progreso ni en el estado listo. Se muestra el número de profesionales activos y el texto “Podés agregar profesionales si necesitás agendas separadas.” Sin profesionales, un servicio usa el horario del negocio cuando el modelo lo permite.

## Estado y fuentes de datos

Se agregó `GET /api/v1/appointments/onboarding-status/`, read-only y protegido por los permisos existentes de Turnos. Devuelve los contadores/estados de servicios y profesionales, disponibilidad recurrente válida, disponibilidad del link público y `ready_to_receive_bookings`.

- Servicios: `AppointmentService` activos, la entidad que usa la reserva pública. La condición de reservable reutiliza la validación canónica de señas para no contar servicios legacy que el motor de reservas rechaza.
- Horarios: el helper de disponibilidad reutiliza la intersección del motor público entre horario del negocio y horario de profesionales elegibles, y exige que la franja admita la duración del servicio. Excepciones por fecha y turnos ocupados no eliminan la configuración semanal recurrente.
- Link: `public_booking_snapshot()`; en la UI se presenta la URL ya entregada en la sesión mediante la tarjeta existente, con sus acciones de ver y copiar.
- Listado y resumen respetan el acceso existente; la guía solo se monta con `manage_appointments`. No se guarda progreso derivado ni se agrega modelo/migración.

`ready_to_receive_bookings` requiere servicio activo y reservable, disponibilidad recurrente válida para al menos un servicio y link público disponible. No requiere profesionales.

## Archivos

- Backend: [availability.py](../../services/api/src/apps/appointments/services/availability.py) agrega la comprobación recurrente; [views.py](../../services/api/src/apps/appointments/views.py) y [urls.py](../../services/api/src/apps/appointments/urls.py) exponen el resumen protegido. La prueba focal está en [test_onboarding_status.py](../../services/api/src/apps/appointments/tests/test_onboarding_status.py).
- Frontend: [api.ts](../../apps/web/src/features/appointments/api.ts), [hooks.ts](../../apps/web/src/features/appointments/hooks.ts) y [types.ts](../../apps/web/src/features/appointments/types.ts) consumen el resumen; [appointments-onboarding-checklist.tsx](../../apps/web/src/app/app/turnos/appointments-onboarding-checklist.tsx) muestra la guía dentro de [page.tsx](../../apps/web/src/app/app/turnos/page.tsx).
- Link: [public-booking-link-card.tsx](../../apps/web/src/features/appointments/public-booking-link-card.tsx) conserva la tarjeta y agrega el destino de ancla para el paso.
- Return: en [page.tsx](../../apps/web/src/app/(marketing)/subscribe/return/page.tsx) solo cambia el CTA de `active`; polling, status endpoint, errores, expiración y flows legacy quedan intactos. Se actualiza su [prueba focal](../../apps/web/src/app/(marketing)/subscribe/return/__tests__/page.test.tsx).

## Responsive

Validación autenticada de `/app/turnos?onboarding=1` con tres owners reales en PostgreSQL desechable, membresías owner y suscripciones V2 `active`, provider `manual`. La sesión confirmó `manage_appointments=true`, `source=v2` y `access_allowed=true`. No se interceptaron respuestas ni se simularon permisos en el navegador.

Se usó Chromium integrado sobre una **build de producción local**, API Docker, PostgreSQL 16 y Redis exclusivos. Web/API expuestos únicamente en loopback (`3103`/`8103`); bases sin puertos publicados, red interna para datos y red de ingreso de validación para la API. Sin archivos `.env` del repositorio, tokens MP ni workers. No es un deploy.

La emulación se calibró contra `window.innerWidth` y `document.documentElement.clientWidth`, no contra el tamaño físico del panel de VS Code. Se comprobaron los cinco anchos CSS exactos en **cada uno de los tres estados: 15 combinaciones**.

Medidas `scrollWidth / clientWidth`, en px; los resultados fueron idénticos entre incompleto, parcial y ready:

| Ancho CSS | Documento | Checklist | Card del link público | Overflow horizontal |
| --- | --- | --- | --- | --- |
| 320 | 320 / 320 | 270 / 270 | 270 / 270 | No |
| 375 | 375 / 375 | 325 / 325 | 325 / 325 | No |
| 768 | 768 / 768 | 462 / 462 | 462 / 462 | No |
| 1024 | 1024 / 1024 | 718 / 718 | 718 / 718 | No |
| 1440 | 1440 / 1440 | 1134 / 1134 | 1134 / 1134 | No |

En las 15 combinaciones se cumplió `scrollWidth <= clientWidth` tanto para documento como para checklist. Las mediciones adicionales de `li`, párrafos, links y botones no encontraron contenido horizontal desbordado; ningún control quedó fuera de los límites del checklist. La URL pública larga del fixture se parte dentro de la card.

**Bug real encontrado y corregido:** a 768 px, la barra lateral dejaba 462 px al checklist y `sm:flex-row` comprimía los textos de las cards (hasta 0–10 px disponibles) frente a los CTAs sin contracción. Se cambió únicamente a `xl:flex-row xl:items-center` en las cards esenciales y opcional. Se conservan una columna estrecha y dos desde `sm`; dentro de cada card, texto y CTA quedan apilados hasta `xl`. Se repitió la matriz completa sobre la build corregida, sin superposición ni cortes problemáticos.

La inspección visual y las capturas del navegador verificaron checklist visible, texto/progreso legibles, profesionales marcado **(opcional)** y link/card sin romper el layout. A 320 px todos los controles de la guía tienen nombre, `tabIndex=0` y dimensiones positivas; los cuatro CTAs de pasos miden 212 px de ancho. Se comprobó navegación real por teclado:

- Servicios → `/app/turnos/servicios`, encabezado “Servicios”.
- Horarios → `/app/turnos/horarios`, encabezado “Horarios”.
- Profesionales → `/app/turnos/profesionales`, encabezado “Profesionales”.
- Link → `/app/turnos?onboarding=1#public-booking-link`.
- Ver agenda → `/app/turnos/turnos`.
- Ocultar elimina solo la guía; en estado incompleto el acceso “Ver turnos” continúa visible y navega a la agenda. No se exige completar pasos para usar el panel.
- “Copiar enlace” devuelve “Enlace copiado”; “Abrir página” conserva la URL local canónica `/t/<slug>`.

## Estados funcionales visuales

| Estado real | Servicios | Horarios | Link | Progreso visible | Mensaje |
| --- | --- | --- | --- | --- | --- |
| Incompleto | Pendiente | Pendiente | Pendiente | 0 de 3, 0% | Completá los pasos esenciales |
| Parcial | Listo | Pendiente | Listo | 2 de 3, 67% | Completá los pasos esenciales |
| Ready | Listo | Listo | Listo | 3 de 3, 100% | Tu agenda está lista para recibir reservas. |

El fixture incompleto tiene suscripción válida pero carece de servicios, horarios y slug; el link responde a la regla real `missing_slug`. El parcial tiene servicio activo y slug, sin horarios. Ready tiene servicio de 30 minutos, horario general de lunes 09:00–12:00 y slug, **sin profesionales**. No se usaron mocks del estado.

Ready se verificó primero con cero profesionales y luego agregando uno activo sin asignarlo al servicio: el texto cambió a “1 activos”, pero el progreso siguió **3/3** y `ready_to_receive_bookings=true`. Profesionales no entra en el denominador ni impide estar listo.

## Return activo

Se persistió un `AppointmentsCheckout` de prueba en `active`, ligado al owner y a su suscripción V2 manual. La navegación real a `/subscribe/return?appointments_checkout_id=...` mostró “Tu plan de Turnos está activo.” y el botón **Configurar Turnos**.

El status endpoint real devolvió HTTP 200, `status=active`, `subscription_status=active`, `can_retry=false`. La activación del botón navegó a **`/app/turnos?onboarding=1`** y mostró el checklist autenticado. No se modificaron polling, endpoint, reconciliación ni backend de 03B2; el fixture no usa IDs, tokens ni llamadas de provider.

## Prettier: todos los archivos frontend del slice

Se ejecutó `prettier --check` sobre los nueve archivos de esta tabla. Resultado global: **exit 1 por cinco archivos existentes**, no un PASS global.

| Archivo | Resultado | Líneas añadidas/modificadas por 03B3B |
| --- | --- | --- |
| [appointments-onboarding-checklist.tsx](../../apps/web/src/app/app/turnos/appointments-onboarding-checklist.tsx) | PASS | Archivo nuevo completo, incluida la corrección responsive |
| [appointments-onboarding-checklist.test.tsx](../../apps/web/src/app/app/turnos/__tests__/appointments-onboarding-checklist.test.tsx) | PASS | Archivo nuevo completo |
| [page.tsx del panel](../../apps/web/src/app/app/turnos/page.tsx) | WARN preexistente | 7, 18, 46–47: conformes |
| [api.ts](../../apps/web/src/features/appointments/api.ts) | WARN preexistente | 10, 34–37: conformes |
| [hooks.ts](../../apps/web/src/features/appointments/hooks.ts) | WARN preexistente | 20, 57, 62–68: conformes |
| [types.ts](../../apps/web/src/features/appointments/types.ts) | WARN preexistente | 157–166: conformes |
| [public-booking-link-card.tsx](../../apps/web/src/features/appointments/public-booking-link-card.tsx) | WARN preexistente | 68: conforme |
| [page.tsx del return](../../apps/web/src/app/(marketing)/subscribe/return/page.tsx) | PASS | CTA activo: destino y texto |
| [page.test.tsx del return](../../apps/web/src/app/(marketing)/subscribe/return/__tests__/page.test.tsx) | PASS | Expectativa del CTA activo |

Se corrigió solamente la indentación de las adiciones del slice en los cinco archivos existentes. La API de Prettier generó una versión formateada en memoria con la configuración del repositorio; se comparó línea por línea con el archivo actual y con `git show HEAD:<archivo>`. Los cinco archivos ya fallaban en `HEAD`. **Todas las líneas con diferencias de formato residuales son idénticas a HEAD; ninguna línea añadida/modificada por 03B3B introduce el fallo.** El retorno tiene trabajo previo de 03B2, por lo que su diff completo contra HEAD no se atribuye a este slice; ambos archivos de return pasan completos.

Líneas actuales exactas con diferencias residuales (incluyen indentación y expresiones que Prettier partiría; no se reformatearon):

- [page.tsx del panel](../../apps/web/src/app/app/turnos/page.tsx): `11, 13–15, 17, 20–27, 29–44, 48, 50–60, 62–64`.
- [api.ts](../../apps/web/src/features/appointments/api.ts): `4–9, 11–22, 26–33, 42–47, 51, 54–55, 59, 64–70, 74, 77–78, 82, 87–92, 96, 99–100, 104, 110–113, 117, 120–121, 125, 131–134, 138, 141–142, 146, 152–155, 157–163, 169, 173–180, 184, 188, 192, 198, 202, 208, 211–212, 218, 222, 225–226`.
- [hooks.ts](../../apps/web/src/features/appointments/hooks.ts): `4–19, 21–36, 40–49, 70–75, 79–85, 89–97, 101–107, 112–117, 121–128, 132–140, 144–151, 156–161, 165–171, 175–182, 186–192, 197–202, 206–212, 216–223, 227–233, 238–243, 247–253, 257–264, 268–274, 280–281, 283–287, 293–297, 301–302, 304–308, 312–318, 322–329, 333–339, 347–351, 355–359, 367–371, 375–379, 387–391, 395–399`.
- [types.ts](../../apps/web/src/features/appointments/types.ts): `4–11, 15–16, 20–23, 29–40, 44–52, 56–61, 65–66, 70–79, 83–89, 97–103, 107–114, 118–121, 125–133, 137–142, 148–149, 153–156, 172–177, 180–185, 190–197, 201–205, 213–218, 222–249, 253–266, 270, 275–279, 285–287, 291–292, 296–303, 307–309, 313–319, 325–330, 338–345, 348–353, 357–376, 385–390, 394–399, 406–410, 415–416, 424–425, 434–437`.
- [public-booking-link-card.tsx](../../apps/web/src/features/appointments/public-booking-link-card.tsx): `8–10, 14–16, 25–33, 37, 41–43, 45–47, 49–53, 55–64, 66–67, 69–79, 81–121`.

## Checks finales

| Check repetido | Resultado |
| --- | --- |
| `python manage.py test apps.appointments.tests.test_onboarding_status --noinput` | 7/7 PASS, PostgreSQL 16 desechable |
| `python manage.py check` | PASS, 0 issues |
| `python manage.py makemigrations --check --dry-run` | PASS, `No changes detected` |
| Vitest: checklist + return | 14/14 PASS (4 + 10), repetido después del fix |
| `tsc --noEmit` | PASS |
| ESLint sobre los nueve archivos frontend de la tabla | PASS |
| Prettier sobre los nueve archivos | 4 PASS; 5 WARN preexistentes con atribución exacta arriba |
| Auditoría de formato de líneas añadidas/modificadas | PASS, cero diferencias residuales del slice |
| Build de producción Next/Turbopack | PASS, TypeScript y 147 páginas generadas |
| `git diff --check` focal | PASS |

La build se ejecutó en una copia temporal sin `.env`, con dependencias ya instaladas mediante junctions y URLs locales. Solo el config temporal fijó raíz de Turbopack y directorio de salida para aislar artefactos; no se deshabilitaron checks. Los hashes SHA-256 de los **nueve archivos frontend** coincidieron con los del workspace. Intentos previos del harness con Webpack/junction entre discos fallaron; se resolvió el entorno de validación usando Turbopack y la misma resolución de dependencias del monorepo, sin cambios de código ajenos ni instalaciones.

El proceso web, los tres contenedores, sus volúmenes desechables y ambas redes de validación se retiraron al terminar. No quedaron listeners de validación ni se intervino infraestructura compartida.

## Invariantes

- `appointments.is_active` permanece `false`; no se activó checkout público ni el producto.
- Sin cambios del slice a Mercado Pago, precios, planes, seats, entitlements, webhooks, S8 o IA onboarding. El trabajo previo de otros slices presente en el worktree no se revirtió ni se amplió.
- Sin migraciones nuevas, dependencias nuevas, automatizaciones nuevas ni persistencia del progreso. Manifests, lockfiles y catálogo generado sin diff.
- La inactividad del producto restringe su venta pública, **no invalida el acceso de negocios ya suscriptos**. El fixture V2 activo tuvo link público disponible y estado ready real sin cambiar `is_active`. Se corrige así la afirmación anterior de este informe que asociaba incorrectamente catálogo inactivo con link siempre indisponible.
- Sin provider real, producción ni deploy. No se avanzó al siguiente slice.

TURNOS PUBLIC 03B3B — CLOSED
