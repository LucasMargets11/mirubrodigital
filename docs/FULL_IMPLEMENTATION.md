# Documento de Implementación

## UX, SEO, Performance y Despliegue AWS para MiRubro

## 1. Propósito del documento

Este documento define la estrategia técnica y funcional para optimizar la experiencia de usuario de MiRubro en su landing pública y en la aplicación autenticada, asegurando:

* carga rápida y estable
* navegación profesional y fluida
* buena indexación orgánica
* uso correcto de cookies y consentimiento
* arquitectura preparada para escalar en AWS
* separación clara entre experiencia pública y privada
* una base sólida para desarrollar por fases sin perder contexto

También funciona como documento madre para coordinar decisiones entre frontend, backend, infraestructura y producto.

---

## 2. Objetivos principales

### 2.1 Objetivos de negocio

* generar una primera impresión profesional y confiable
* mejorar la conversión de visitas a registro, demo o contacto
* reforzar la percepción de producto SaaS serio
* permitir futuras campañas de adquisición sin degradar performance
* preparar una base escalable para nuevas verticales de MiRubro

### 2.2 Objetivos técnicos

* separar correctamente landing, app y API
* maximizar caché en contenido público
* evitar caché compartida en contenido autenticado
* mejorar SEO técnico desde la base del código
* implementar consentimiento de cookies de forma controlada
* reducir bundle y scripts innecesarios en la landing
* preparar el proyecto para operar con CloudFront, S3, ECS/Fargate y WAF
* medir experiencia real con observabilidad y monitoreo

---

## 3. Alcance

### Incluye

* arquitectura objetivo para dominios y subdominios
* definición de servicios AWS recomendados
* estrategia de caché por tipo de ruta
* estrategia SEO técnica
* estrategia de cookies y consentimiento
* preparación del código frontend para performance
* roadmap por fases
* checklist de implementación
* criterios de aceptación por fase

### No incluye en esta etapa

* redacción final de políticas legales
* contenido final de copy SEO de todas las páginas
* diseño visual final del banner de cookies
* configuración detallada de costos AWS
* migración de todos los assets existentes a producción

---

## 4. Contexto actual de MiRubro

MiRubro cuenta con una arquitectura moderna basada en frontend con Next.js App Router, backend Django, PostgreSQL, Redis y entorno productivo alineado con AWS/Terraform.

El sistema ya posee:

* landing pública y múltiples páginas de marketing
* blog público
* aplicación autenticada
* API separada
* assets públicos y privados
* autenticación basada en cookies/JWT
* módulos funcionales por vertical

Esto permite evolucionar sin rehacer el stack completo. La estrategia correcta es ordenar responsabilidades, separar el tráfico y optimizar la forma en que cada parte se sirve al usuario.

---

## 5. Principios rectores

1. **La landing pública y la app privada no deben comportarse igual.**
2. **Todo lo público debe estar pensado para caché, SEO y velocidad.**
3. **Todo lo autenticado debe priorizar seguridad, consistencia y aislamiento.**
4. **Los scripts de terceros no deben perjudicar la experiencia inicial.**
5. **Las decisiones de infraestructura deben estar reflejadas en el código.**
6. **La performance debe medirse con datos reales, no con suposiciones.**
7. **Cada fase debe dejar una mejora concreta y verificable.**

---

## 6. Arquitectura objetivo

### 6.1 Dominios propuestos

* `mirubro.com` → landing principal
* `www.mirubro.com` → redirección canónica a `mirubro.com`
* `app.mirubro.com` → aplicación autenticada
* `api.mirubro.com` → backend/API
* `assets.mirubro.com` → imágenes, recursos estáticos y media pública

### 6.2 Separación funcional

#### Experiencia pública

Incluye:

* home
* pricing
* landings de productos
* blog
* FAQ
* contacto
* páginas institucionales y legales

Objetivos:

* máxima fluidez
* excelente indexación
* caché eficiente
* JS mínimo
* carga optimizada de imágenes y scripts

#### Experiencia privada

Incluye:

* app autenticada
* backoffice
* dashboards
* onboarding privado
* módulos operativos

Objetivos:

* seguridad
* estabilidad
* no cachear HTML sensible
* mantener experiencia consistente y rápida

#### API

Incluye:

* endpoints autenticados
* endpoints públicos mínimos
* webhooks
* servicios internos

Objetivos:

* seguridad
* previsibilidad
* separación de tráfico
* observabilidad

---

## 7. Servicios AWS recomendados

### 7.1 Route 53

Se utilizará para:

* manejo de DNS
* alias records para CloudFront
* resolución de dominio raíz y subdominios

### 7.2 ACM

Se utilizará para:

* certificados TLS
* HTTPS en dominios públicos y privados

### 7.3 CloudFront

Será la capa principal de distribución global.

Se utilizará para:

* acelerar entrega de HTML, CSS, JS e imágenes
* cachear recursos públicos
* comprimir respuestas
* separar behaviors por path
* conectar con WAF
* mejorar TTFB y experiencia de primera carga

### 7.4 S3

Se utilizará para:

* assets públicos
* imágenes de landing
* capturas de producto
* OG images
* media estática compartida

### 7.5 ECS Fargate

Se utilizará para:

* ejecución del frontend Next.js
* ejecución del backend Django
* despliegue con contenedores sin administrar servidores

### 7.6 ALB

Se utilizará para:

* balancear tráfico hacia servicios dinámicos
* exponer origins a CloudFront
* health checks

### 7.7 WAF

Se utilizará para:

* proteger endpoints públicos
* aplicar rate limiting
* filtrar tráfico malicioso
* endurecer la exposición de landing y app

### 7.8 CloudWatch RUM

Se utilizará para:

* medir experiencia real del usuario
* errores de frontend
* tiempos de carga reales
* navegación por navegador/dispositivo

### 7.9 CloudWatch Synthetics

Se utilizará para:

* testear recorridos clave
* detectar degradaciones sin depender del tráfico real

---

## 8. Propuesta de despliegue

### 8.1 Capa pública

**CloudFront público** delante de:

* S3 para assets públicos
* Next.js marketing server para HTML marketing

Rutas típicas:

* `/`
* `/pricing`
* `/gestion`
* `/carta`
* `/resenas`
* `/blog/*`
* `/preguntas-frecuentes`
* `/contacto`

### 8.2 Capa privada

**CloudFront privado o distribución separada** delante de:

* app Next.js autenticada
* Django API

Rutas típicas:

* `/app/*`
* `/admin/*`
* `/api/*`

### 8.3 Capa de assets

**S3 + CloudFront** para:

* logos
* screenshots
* imágenes de marketing
* imágenes sociales
* media pública reutilizable

---

## 9. Estrategia de caché

## 9.1 Objetivo general

La caché debe servir para acelerar lo público sin comprometer seguridad ni mostrar datos incorrectos en contenido privado.

### 9.2 Reglas por tipo de contenido

#### Assets compilados versionados

Ejemplos:

* `/_next/static/*`
* JS/CSS con hash
* fuentes versionadas

Política:

* caché muy larga
* `public, max-age=31536000, immutable`

#### Imágenes públicas de marketing

Ejemplos:

* screenshots
* logos
* capturas de producto
* OG images estáticas

Política:

* caché alta
* `public, max-age=2592000, stale-while-revalidate=86400`

#### HTML de landing y blog

Política:

* ISR o revalidación controlada
* `public, s-maxage=300, stale-while-revalidate=3600`

#### HTML de app autenticada

Política:

* sin caché compartida
* `private, no-store`

#### Respuestas API autenticadas

Política:

* sin caché compartida
* `private, no-store`

### 9.3 Reglas clave

* no cachear páginas públicas variando por cookies innecesarias
* minimizar headers en la cache key
* ignorar query params de tracking si no alteran el contenido
* mantener separadas las respuestas públicas de las privadas

---

## 10. Estrategia SEO

## 10.1 Objetivo

Construir una base SEO técnica limpia y escalable para que MiRubro pueda posicionar sus productos y contenidos sin rehacer la estructura más adelante.

### 10.2 Requerimientos mínimos

* metadata por página
* titles únicos
* descriptions únicas
* canonical por ruta
* sitemap XML
* robots.txt
* Open Graph y Twitter cards
* JSON-LD en páginas clave
* noindex en páginas privadas, previews y entornos no públicos

### 10.3 Páginas prioritarias para SEO

* home
* pricing
* gestión comercial
* carta QR
* QR de reseñas
* FAQ
* blog
* nosotros

### 10.4 Estructura recomendada

Crear una capa centralizada de SEO para evitar metadata repetida o inconsistente.

Ejemplo conceptual:

* `src/lib/seo/defaultMetadata.ts`
* `src/lib/seo/buildMetadata.ts`
* `app/robots.ts`
* `app/sitemap.ts`

---

## 11. Estrategia de cookies y consentimiento

## 11.1 Enfoque general

La landing debe poder funcionar perfectamente aunque el usuario rechace todas las cookies no esenciales.

### 11.2 Categorías sugeridas

#### Cookies estrictamente necesarias

Incluyen:

* autenticación
* seguridad
* preferencias esenciales
* recordatorio de consentimiento

Estas pueden estar activas por defecto.

#### Cookies analíticas

Incluyen:

* analítica de comportamiento
* medición de tráfico
* mapas de calor y herramientas similares

Estas deben requerir consentimiento.

#### Cookies de marketing

Incluyen:

* remarketing
* pixel publicitario
* audiencias
* campañas pagas

Estas deben requerir consentimiento.

### 11.3 Requisitos funcionales

* banner visible y claro
* opción de aceptar
* opción de rechazar
* opción de personalizar
* posibilidad de cambiar preferencias luego
* scripts no esenciales bloqueados hasta consentimiento

### 11.4 Estrategia inicial sugerida

Fase inicial:

* lanzar solo con cookies estrictamente necesarias
* no cargar GA4, Meta Pixel ni herramientas similares hasta tener el sistema de consentimiento listo

---

## 12. Requerimientos de frontend

## 12.1 Separación de layouts

Crear separación explícita entre:

* `app/(marketing)`
* `app/(private)`

Objetivo:

* que el layout de marketing no cargue providers, lógica ni dependencias de la app autenticada

## 12.2 Componentes y scripts

* usar `next/script` para terceros
* retrasar scripts no críticos
* evitar scripts inline improvisados
* bloquear terceros detrás de consentimiento

## 12.3 Imágenes

* usar `next/image` en la landing
* optimizar tamaños
* definir imágenes críticas para LCP
* migrar recursos pesados a assets públicos via S3

## 12.4 Navegación

* usar prefetch en enlaces estratégicos
* mantener CTAs principales con navegación instantánea
* revisar transiciones y estados de carga

## 12.5 Bundle y render

* mantener marketing con JS mínimo
* usar Server Components cuando sea posible
* evitar importar librerías pesadas en páginas públicas
* usar ISR o SSG en páginas aptas

---

## 13. Requerimientos de infraestructura

### 13.1 DNS y certificados

* definir dominio raíz y subdominios
* emitir certificados necesarios
* configurar redirecciones canónicas

### 13.2 CloudFront

* definir behaviors por path
* habilitar compresión
* revisar TTLs
* definir policies de caché
* limitar forwarding innecesario de cookies y query strings

### 13.3 S3

* crear bucket para assets públicos
* definir estructura de carpetas
* versionar assets cuando aplique

### 13.4 Contenedores

* definir servicios separados para frontend público, frontend privado si hiciera falta, y API
* health checks
* variables de entorno claras

### 13.5 Seguridad

* asociar WAF
* rate limits
* headers de seguridad
* control de acceso a recursos internos

---

## 14. Observabilidad y medición

## 14.1 Qué medir

* performance real del usuario
* tiempos de carga de home, pricing y login
* errores JS
* abandonos en formularios o CTAs
* pasos críticos del funnel

### 14.2 Herramientas

* CloudWatch RUM
* CloudWatch Synthetics
* logs de aplicación
* métricas de ALB/CloudFront

### 14.3 Recorridos sintéticos sugeridos

* home → pricing
* home → entrar
* pricing → CTA principal
* entrar → login exitoso
* home móvil → CTA producto

---

## 15. Roadmap de implementación por fases

## Fase 0 — Diseño técnico y documentación

### Objetivo

Definir reglas, responsabilidades y decisiones de base.

### Tareas

* mapear rutas públicas y privadas
* definir política de caché por ruta
* definir política de consentimiento
* definir matriz SEO
* definir estrategia de dominios
* consolidar este documento como fuente de verdad

### Entregables

* documento validado
* checklist base
* matriz de rutas

### Criterio de cierre

No quedan decisiones ambiguas sobre qué es público, qué es privado, qué se indexa y qué se cachea.

---

## Fase 1 — Refactor de estructura frontend

### Objetivo

Separar correctamente marketing y app.

### Tareas

* crear layouts separados
* extraer providers pesados del layout público
* centralizar metadata
* crear robots y sitemap
* ordenar imágenes y componentes de marketing

### Entregables

* estructura de carpetas limpia
* capa SEO inicial
* marketing layout liviano

### Criterio de cierre

La landing no depende de lógica privada ni carga bundle innecesario.

---

## Fase 2 — Consentimiento y control de scripts

### Objetivo

Implementar un sistema profesional de cookies y consentimiento.

### Tareas

* crear ConsentProvider
* crear banner y modal de preferencias
* bloquear scripts no esenciales por defecto
* documentar categorías de cookies
* definir eventos de analítica

### Entregables

* banner funcional
* preferencias persistentes
* scripts condicionados por consentimiento

### Criterio de cierre

El sitio funciona completo aunque el usuario rechace todo lo no esencial.

---

## Fase 3 — Infraestructura pública AWS

### Objetivo

Acelerar landing y assets con CDN y caché correcta.

### Tareas

* preparar S3 para assets públicos
* configurar CloudFront público
* configurar Route 53
* emitir certificados
* definir behaviors
* activar compresión
* asociar WAF base

### Entregables

* dominio funcionando por CDN
* assets públicos distribuidos por CloudFront
* headers de caché correctos

### Criterio de cierre

La landing pública responde rápido, con caché eficiente y sin errores de routing.

---

## Fase 4 — Infraestructura privada AWS

### Objetivo

Servir app y API de forma segura y predecible.

### Tareas

* desplegar servicios dinámicos en ECS/Fargate
* configurar ALB
* exponer app y API detrás de CloudFront o capas separadas
* revisar cookies de sesión
* revisar headers de seguridad
* revisar no-cache en contenido privado

### Entregables

* app y API productivas en arquitectura estable
* control de caché privado validado

### Criterio de cierre

No existe riesgo de caché compartida de contenido autenticado.

---

## Fase 5 — Observabilidad y optimización fina

### Objetivo

Medir experiencia real y optimizar sobre evidencia.

### Tareas

* activar RUM
* activar recorridos sintéticos
* revisar páginas de mayor impacto
* optimizar LCP, CLS e INP
* ajustar prefetch y cargas diferidas

### Entregables

* dashboard de experiencia real
* panel de recorridos críticos
* backlog de mejoras concretas

### Criterio de cierre

Existe visibilidad real sobre la calidad de experiencia y degradaciones.

---

## Fase 6 — SEO y crecimiento

### Objetivo

Escalar posicionamiento y adquisición orgánica.

### Tareas

* optimizar landings por vertical
* implementar schema en páginas clave
* fortalecer enlazado interno
* generar contenido de blog con estructura SEO consistente
* revisar canibalización y noindex

### Entregables

* arquitectura SEO sólida
* páginas prioritarias optimizadas

### Criterio de cierre

MiRubro cuenta con una base técnica SEO estable y escalable.

---

## 16. Checklist técnico resumido

### Frontend

* [ ] separar layouts marketing y private
* [ ] mover providers fuera del layout público
* [ ] implementar metadata por ruta
* [ ] crear robots.ts
* [ ] crear sitemap.ts
* [ ] usar next/image en la landing
* [ ] revisar scripts de terceros
* [ ] implementar ConsentProvider
* [ ] revisar prefetch de CTAs
* [ ] evitar imports pesados en marketing

### Infraestructura

* [ ] definir subdominios
* [ ] emitir certificados ACM
* [ ] configurar Route 53
* [ ] crear bucket S3 de assets
* [ ] configurar CloudFront público
* [ ] configurar CloudFront/app privado
* [ ] definir WAF base
* [ ] revisar ALB y Fargate

### SEO

* [ ] titles únicos
* [ ] descriptions únicas
* [ ] canonical por página
* [ ] Open Graph por página clave
* [ ] sitemap funcional
* [ ] robots funcional
* [ ] noindex en privados/previews

### Observabilidad

* [ ] activar RUM
* [ ] activar Synthetics
* [ ] definir eventos clave
* [ ] crear panel de métricas

---

## 17. Riesgos y errores a evitar

* mezclar cookies de sesión con caché pública
* reenviar demasiadas cookies a CloudFront
* cargar analytics o pixels antes del consentimiento
* mantener el layout público contaminado con lógica privada
* dejar páginas públicas sin metadata consistente
* depender de HTML totalmente dinámico para todo marketing
* usar la misma política de caché para landing y app
* optimizar sin observabilidad real

---

## 18. Decisiones iniciales recomendadas

1. Separar públicamente `mirubro.com` y `app.mirubro.com`.
2. Usar CloudFront como capa frontal principal.
3. Usar S3 para assets públicos de marketing.
4. Mantener app y API con políticas de no-cache compartido.
5. Implementar consentimiento antes de cargar analytics no esenciales.
6. Hacer SEO técnico desde la estructura del código.
7. Medir experiencia con RUM antes de optimizar fino.

---

## 19. Próximos pasos inmediatos

1. Validar este documento como base.
2. Crear la matriz exacta de rutas de MiRubro con:

   * tipo de ruta
   * política de caché
   * SEO/indexación
   * cookies requeridas
3. Comenzar Fase 1 sobre el código del frontend.
4. Definir el backlog técnico de implementación por tareas.
5. Ejecutar fase por fase con validación al cierre.

---

## 20. Estado del documento

Versión inicial de implementación. Documento abierto a iteración a medida que se definan detalles del código, Terraform, despliegue y medición.

---

## 21. Fase 1 — Prompt de análisis previo a la implementación

### Objetivo del análisis

Antes de modificar código, se debe realizar un análisis técnico del frontend actual de MiRubro para identificar:

* cómo está organizada hoy la estructura de rutas y layouts
* qué partes públicas y privadas están mezcladas
* qué providers, scripts o dependencias se cargan de más en la landing
* qué metadata SEO ya existe y qué falta
* qué assets e imágenes deben optimizarse
* qué rutas pueden quedar listas para caché pública y cuáles no

La idea es evitar implementar a ciegas. Primero se diagnostica, luego se propone la refactorización y recién después se ejecuta.

### Resultado esperado del análisis

El análisis debe producir un informe concreto con:

1. mapa actual de layouts y rutas
2. rutas públicas de marketing identificadas
3. rutas privadas/autenticadas identificadas
4. providers y wrappers globales actualmente cargados en el layout principal
5. scripts de terceros detectados
6. metadata actual existente por página
7. archivos candidatos a separación en `app/(marketing)` y `app/(private)`
8. riesgos técnicos de la refactorización
9. propuesta de estructura objetivo
10. backlog técnico priorizado para implementación

### Qué revisar en el código

#### Estructura App Router

* `src/app/`
* layouts globales
* route groups existentes
* páginas públicas actuales
* páginas autenticadas actuales
* páginas admin
* endpoints especiales como sitemap, robots o metadata si ya existen

#### Navegación y shells

* layout principal
* navbar pública
* sidebar/app shell
* wrappers globales
* providers de auth, query, theme, toasts, analytics o session

#### SEO actual

* uso de `metadata`
* uso de `generateMetadata`
* titles y descriptions existentes
* canonical
* Open Graph
* `robots.ts`
* `sitemap.ts`
* páginas sin metadata o con metadata repetida

#### Performance estructural

* componentes pesados cargados en la landing
* imports globales innecesarios
* librerías que viajan al bundle público sin aportar valor
* uso actual de `next/image`
* scripts de terceros y estrategia de carga
* componentes client innecesarios en marketing

#### Riesgo de mezcla público/privado

* providers o middlewares innecesarios en marketing
* lectura de cookies/headers en páginas públicas
* dependencias compartidas que vuelven dinámicas páginas que podrían ser estáticas
* layout compartido entre marketing y app

### Entregable mínimo del análisis

El análisis debe devolver un documento o respuesta estructurada con estos apartados:

#### A. Diagnóstico actual

Resumen técnico de cómo está organizado hoy el frontend.

#### B. Hallazgos

Lista de problemas encontrados, por ejemplo:

* layout público contaminado con lógica privada
* falta de metadata centralizada
* ausencia de `robots.ts` o `sitemap.ts`
* imágenes no optimizadas
* providers innecesarios a nivel raíz

#### C. Propuesta de refactor

Cómo debería quedar la estructura objetivo.

#### D. Plan de implementación

Tareas concretas ordenadas por prioridad.

#### E. Riesgos y validaciones

Qué puede romperse y qué probar al terminar.

---

## 22. Prompt sugerido para pedir el análisis de Fase 1

```text
Necesito que hagas primero un análisis técnico del frontend actual de MiRubro antes de implementar cambios.

Contexto:
- Proyecto MiRubro
- Frontend en Next.js App Router
- Existe una landing pública, páginas de marketing, blog y una app autenticada
- El objetivo de esta fase es separar correctamente la experiencia pública y privada para mejorar performance, SEO, caché futura y orden estructural
- Todavía no quiero que implementes código
- Primero quiero diagnóstico, propuesta de estructura y backlog técnico

Quiero que revises el frontend actual y me entregues un análisis estructurado con:
1. mapa actual de `src/app` y layouts
2. identificación de rutas públicas, privadas y admin
3. providers, wrappers o shells globales actualmente montados en el layout raíz
4. scripts de terceros o integraciones que afecten la landing
5. estado actual de SEO técnico: metadata, generateMetadata, robots, sitemap, canonical, Open Graph
6. uso actual de `next/image` y manejo de assets en páginas públicas
7. componentes o dependencias pesadas que estén cargándose innecesariamente en marketing
8. riesgos de que marketing y app compartan layout o lógica
9. propuesta de estructura objetivo para separar `app/(marketing)` y `app/(private)`
10. backlog técnico priorizado para implementar la Fase 1

Formato de respuesta esperado:
- Diagnóstico actual
- Hallazgos
- Riesgos
- Propuesta de estructura objetivo
- Backlog técnico priorizado
- Recomendaciones previas a implementar

Importante:
- No implementes cambios todavía
- No hagas suposiciones vagas: basate en el código real
- Marcá explícitamente qué archivos habría que tocar después
- Indicá qué validaciones habría que hacer antes de pasar a implementación
```

---

## 23. Prompt sugerido para implementación de Fase 1, una vez aprobado el análisis

```text
Ahora sí, con base en el análisis aprobado, implementá la Fase 1 del frontend de MiRubro.

Objetivo:
Separar correctamente la estructura pública y privada del frontend para mejorar orden, performance y base SEO.

Implementaciones esperadas:
1. separar la estructura en route groups para marketing y private si corresponde
2. dejar el layout público lo más liviano posible
3. extraer providers, wrappers o lógica privada fuera del layout de marketing
4. preparar una capa SEO base reutilizable
5. crear `app/robots.ts` si no existe
6. crear `app/sitemap.ts` si no existe
7. dejar metadata base consistente en páginas públicas clave
8. no romper rutas existentes ni navegación actual
9. mantener el comportamiento funcional actual salvo refactor estructural necesario
10. documentar qué cambios se hicieron y qué quedó preparado para la Fase 2

Condiciones:
- priorizar cambios pequeños, claros y seguros
- no mezclar esta fase con consentimiento de cookies todavía
- no introducir herramientas nuevas sin necesidad
- no tocar infraestructura AWS en esta fase
- si encontrás algo riesgoso, dejalo documentado y aplicá la opción más segura

Quiero como salida:
- resumen de cambios implementados
- archivos modificados
- decisiones técnicas tomadas
- validaciones/manual checks recomendados
- próximos pasos sugeridos para Fase 2
```

---

## 24. Criterio de avance entre análisis e implementación

No se debe pasar a implementación de Fase 1 hasta que el análisis previo confirme:

* qué layouts están mezclando lógica pública y privada
* qué rutas deben vivir en marketing y cuáles en private
* qué providers deben moverse
* qué metadata ya existe y qué falta
* qué archivos exactos se van a modificar
* qué riesgos de regresión pueden aparecer

---

## 25. Próximo paso operativo

El próximo paso es ejecutar el prompt de análisis de Fase 1 sobre el frontend actual de MiRubro y usar su resultado para definir el plan exacto de refactor antes de escribir código.
