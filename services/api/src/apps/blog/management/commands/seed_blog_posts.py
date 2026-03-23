"""
Seed the blog with the 14 original editorial posts and 9 categories.

Idempotent — skips any category/post whose slug already exists.

Usage:
    python manage.py seed_blog_posts
"""
from datetime import datetime, timezone

from django.core.management.base import BaseCommand

from apps.blog.models import BlogCategory, BlogPost

CATEGORIES = [
    {'slug': 'gestion', 'label': 'Gestión'},
    {'slug': 'inventario', 'label': 'Inventario'},
    {'slug': 'ventas', 'label': 'Ventas'},
    {'slug': 'caja', 'label': 'Caja'},
    {'slug': 'facturacion', 'label': 'Facturación'},
    {'slug': 'marketing', 'label': 'Marketing'},
    {'slug': 'menu-qr', 'label': 'Menú QR'},
    {'slug': 'resenas', 'label': 'Reseñas'},
    {'slug': 'gestion-comercial', 'label': 'Gestión Comercial'},
]

POSTS = [
    # ── Featured ──────────────────────────────────────────────────────────
    {
        'slug': 'como-digitalizar-tu-negocio-sin-complicaciones',
        'title': 'Cómo digitalizar tu negocio sin complicaciones',
        'excerpt': (
            'Descubre los pasos clave para llevar tu operación al siguiente nivel '
            'con tecnología que se adapta a cada etapa de tu negocio, sin necesidad '
            'de ser experto en sistemas.'
        ),
        'cover_image_url': 'https://images.unsplash.com/photo-1556761175-4b46a572b786?w=900&auto=format&fit=crop&q=70',
        'reading_time': '5 min',
        'date': '2026-02-20',
        'category_slug': 'gestion',
    },
    # ── Rich posts (Marzo 2026) ───────────────────────────────────────────
    {
        'slug': 'por-que-sumar-resenas-a-tu-menu-qr-online',
        'title': '¿Por qué sumar reseñas a tu menú QR online puede ayudarte a vender más?',
        'excerpt': (
            'Las reseñas no solo mejoran la confianza del cliente: también refuerzan '
            'la decisión de compra, elevan la percepción del local y ayudan a convertir '
            'visitas en ventas.'
        ),
        'cover_image_url': '/blog/blog-resenas-menu-qr-cover.svg',
        'reading_time': '6 min',
        'date': '2026-03-10',
        'category_slug': 'menu-qr',
        'meta_title': 'Reseñas en menú QR online: cómo funcionan y qué beneficios tienen',
        'meta_description': (
            'Descubrí cómo implementar reseñas en tu menú QR online, cómo funciona esta '
            'herramienta y por qué puede ayudarte a generar más confianza, visibilidad y '
            'conversiones.'
        ),
        'body_content': [
            {'type': 'h2', 'text': 'La confianza digital como factor de decisión'},
            {'type': 'p', 'text': 'Antes de elegir dónde comer o dónde pedir, la mayoría de las personas hace una búsqueda rápida. Mira fotos, lee comentarios, revisa si el local tiene reseñas recientes. Este comportamiento no es nuevo, pero con el auge del menú QR online se volvió parte del mismo momento de consumo: el cliente tiene el celular en la mano, ya está en tu local, y puede decidir en segundos si confiar en lo que ve.'},
            {'type': 'p', 'text': 'Integrar reseñas dentro del menú digital no es solo un detalle de diseño. Es una señal de transparencia que impacta directamente en cómo el cliente percibe tu negocio y en qué tan seguro se siente al hacer un pedido.'},
            {'type': 'h2', 'text': 'Qué significa integrar reseñas dentro del menú QR online'},
            {'type': 'p', 'text': 'No hablamos de un link externo a Google, ni de un banner genérico. La integración real de reseñas en el menú QR significa que, mientras el cliente navega tu carta digital, puede ver opiniones de otros clientes, puntajes por producto o categoría, y también dejar su propia reseña con un proceso sencillo y accesible desde el mismo dispositivo.'},
            {'type': 'p', 'text': 'En la práctica, esto convierte el menú en un ecosistema de confianza: el cliente no solo ve lo que ofrecés, sino también lo que otros piensan sobre eso. Es prueba social aplicada al punto exacto donde se toma la decisión.'},
            {'type': 'h2', 'text': 'Cómo funciona en la práctica dentro de Mirubro'},
            {'type': 'p', 'text': 'En Mirubro, las reseñas se integran directamente en el flujo del menú QR online. Al escanear el código, el cliente accede al menú digital de tu local y puede ver la puntuación general del negocio, las opiniones verificadas de otros clientes, y un acceso claro para dejar su propia reseña al final de su experiencia.'},
            {'type': 'p', 'text': 'El flujo está diseñado para ser simple: sin registro obligatorio, sin pasos innecesarios. La reseña se asocia al pedido o visita del cliente y queda visible para los próximos. Esto genera un ciclo virtuoso: más clientes satisfechos dejan reseñas, más nuevos clientes confían en tu local.'},
            {'type': 'h2', 'text': 'Beneficios concretos para tu negocio'},
            {'type': 'check', 'items': [
                'Más confianza al momento de pedir: el cliente decide en contexto, con información real de otros usuarios.',
                'Refuerzo de reputación online: acumulás reseñas verificables que elevan tu presencia digital.',
                'Mejor experiencia del cliente: el proceso de dejar feedback es simple y no interrumpe la experiencia.',
                'Prueba social en el punto de venta: la opinión positiva está visible justo cuando más influye.',
                'Mayor conversión en productos o servicios: los ítems más reseñados o mejor puntuados generan más pedidos.',
            ]},
            {'type': 'h2', 'text': 'Casos de uso: quién se beneficia más'},
            {'type': 'h3', 'text': 'Restaurantes y bares'},
            {'type': 'p', 'text': 'En un ambiente donde hay múltiples opciones en pocos metros cuadrados, las reseñas visibles en el menú QR pueden inclinar la balanza a tu favor. Un cliente nuevo que escanea el código y ve 4.8 estrellas con comentarios recientes tiene mucho menos fricción para hacer su primer pedido.'},
            {'type': 'h3', 'text': 'Cafeterías y take away'},
            {'type': 'p', 'text': 'En este tipo de negocios la velocidad del servicio es clave. Las reseñas integradas ayudan a validar la calidad sin que el cliente tenga que salir del menú a buscar referencias externas. El tiempo de decisión se reduce y la tasa de conversión mejora.'},
            {'type': 'h3', 'text': 'Negocios gastronómicos con delivery'},
            {'type': 'p', 'text': 'En el canal digital, donde no hay contacto visual ni interacción directa, la confianza se construye completamente a través de la reputación. Las reseñas en el menú QR son el equivalente digital de la boca en boca: el argumento más poderoso para que alguien elija pedirte a vos antes que a la competencia.'},
            {'type': 'h2', 'text': '¿Cuándo conviene activar las reseñas en tu menú QR?'},
            {'type': 'p', 'text': 'La respuesta simple es: desde el principio. Cuanto antes empieces a acumular reseñas reales, más sólido será tu historial de confianza. No esperes tener decenas de reseñas para lanzar la funcionalidad: el proceso de acumular opiniones es iterativo, y cada reseña suma.'},
            {'type': 'p', 'text': 'Si tu local ya tiene reseñas favorables en Google u otras plataformas, activar esta función dentro del menú QR es una extensión natural de esa reputación ya ganada. La llevas al mismo punto de consumo.'},
            {'type': 'cta', 'text': 'Activá tu menú QR online con reseñas y mostrá la confianza que ya genera tu local.', 'href': '/pricing', 'buttonLabel': 'Ver planes de Mirubro'},
            {'type': 'faq', 'items': [
                {'q': '¿Las reseñas del menú QR son verificadas o las puede escribir cualquiera?', 'a': 'En Mirubro las reseñas están asociadas a interacciones reales. Esto reduce el riesgo de comentarios falsos y le da más credibilidad a cada opinión visible en tu menú.'},
                {'q': '¿Puedo moderar las reseñas antes de que aparezcan públicamente?', 'a': 'Sí, la plataforma te permite gestionar las reseñas recibidas y definir cómo se muestran dentro del menú. Tenés control sobre el contenido que ven tus clientes.'},
                {'q': '¿Las reseñas del menú QR afectan mi posicionamiento en buscadores?', 'a': 'El contenido generado por usuarios (UGC) es valorado por los motores de búsqueda. Acumular reseñas verificables puede contribuir positivamente a tu presencia digital.'},
                {'q': '¿Qué pasa si recibo una reseña negativa?', 'a': 'Una reseña negativa bien gestionada puede ser más valiosa que ninguna. Te da la oportunidad de responder públicamente, mostrar profesionalismo y evidenciar que tu negocio escucha a sus clientes.'},
                {'q': '¿Necesito tener muchas reseñas para que la funcionalidad tenga impacto?', 'a': 'No. Incluso con pocas reseñas positivas, la señal de confianza ya está activa. El objetivo es empezar a acumular desde el primer día y crecer de forma orgánica.'},
            ]},
        ],
    },
    {
        'slug': 'propinas-digitales-como-funcionan-y-beneficios',
        'title': 'Propinas digitales: cómo funcionan y por qué pueden mejorar la experiencia de tu equipo',
        'excerpt': (
            'Las propinas digitales simplifican el aporte del cliente, modernizan el cobro y '
            'suman una alternativa cómoda para valorar la atención recibida.'
        ),
        'cover_image_url': '/blog/blog-propinas-digitales-cover.svg',
        'reading_time': '5 min',
        'date': '2026-03-06',
        'category_slug': 'menu-qr',
        'meta_title': 'Propinas digitales: funcionamiento, beneficios y experiencia para tu local',
        'meta_description': (
            'Conocé cómo funcionan las propinas digitales, qué ventajas ofrecen para clientes '
            'y equipos de trabajo, y por qué sumarlas puede mejorar la experiencia del servicio.'
        ),
        'body_content': [
            {'type': 'h2', 'text': 'El cambio en los hábitos de pago'},
            {'type': 'p', 'text': 'Cada vez más personas pagan con tarjeta, QR o billetera virtual. El efectivo se usa menos, y eso tiene un efecto colateral que muchos negocios gastronómicos notan: las propinas también cayeron. No porque los clientes no quieran dejarlas, sino porque ya no tienen billetes sueltos encima.'},
            {'type': 'p', 'text': 'Las propinas digitales resuelven exactamente ese problema. Permiten que el cliente agradezca la atención de forma rápida, clara y sin fricción, usando el mismo dispositivo con el que pagó o escaneó el menú.'},
            {'type': 'h2', 'text': 'Qué son las propinas digitales'},
            {'type': 'p', 'text': 'Una propina digital es el equivalente electrónico del billete que antes se dejaba sobre la mesa. En la práctica, es una opción que aparece dentro de la experiencia de pago o en el flujo del menú QR, donde el cliente puede elegir un porcentaje o monto fijo y confirmarlo con un toque. Sin efectivo, sin cambio, sin awkward moments de "te dejo algo?".'},
            {'type': 'h2', 'text': 'Cómo funciona el flujo dentro de Mirubro'},
            {'type': 'p', 'text': 'Dentro del ecosistema Mirubro, la propina digital aparece como un paso opcional dentro del cierre del pedido o del momento de pago. El flujo es deliberadamente simple:'},
            {'type': 'ul', 'items': [
                'El cliente termina de revisar su pedido o recibe el resumen del consumo.',
                'Aparece la pantalla de propina con opciones predefinidas (10%, 15%, 20%) y la posibilidad de ingresar un monto libre.',
                'Elige o ignora la opción y confirma.',
                'La propina queda registrada junto al pedido.',
            ]},
            {'type': 'p', 'text': 'El flujo no es invasivo ni obligatorio. No aparece como una pantalla difícil de saltar ni genera incomodidad. La decisión es completamente del cliente.'},
            {'type': 'h2', 'text': 'Beneficios para el cliente'},
            {'type': 'check', 'items': [
                'Facilidad: no requiere efectivo ni calcular cambio.',
                'Rapidez: el proceso toma segundos y no interrumpe la experiencia.',
                'Comodidad: puede elegir el monto que considera justo sin presión social.',
                'Modernidad: una experiencia alineada a su forma habitual de pagar.',
            ]},
            {'type': 'h2', 'text': 'Beneficios para el local y el equipo'},
            {'type': 'check', 'items': [
                'Experiencia más profesional: el proceso de propina está integrado y es invisible para el equipo.',
                'Menos fricción operativa: nadie tiene que preguntar ni manejar efectivo adicional.',
                'Valorización del servicio: el equipo recibe reconocimiento de forma directa y trazable.',
                'Registro histórico: las propinas quedan registradas, lo cual simplifica la distribución interna.',
                'Integración con la experiencia digital completa: suma coherencia al ecosistema del local.',
            ]},
            {'type': 'h2', 'text': 'En qué tipos de negocios tiene más sentido'},
            {'type': 'p', 'text': 'Las propinas digitales funcionan especialmente bien en negocios donde el servicio es parte del valor percibido: restaurantes, bares, cafeterías de autor, espacios de experiencia gastronómica. También en delivery y take away donde la interacción es breve pero el cliente valora la eficiencia y la calidad del producto.'},
            {'type': 'p', 'text': 'En cambio, en modelos de autoservicio total o en verdulerías y almacenes, puede no ser tan relevante. La clave es preguntarse: ¿hay un equipo humano cuyo servicio el cliente podría querer valorar?'},
            {'type': 'h2', 'text': 'Buenas prácticas para implementar propinas digitales'},
            {'type': 'ul', 'items': [
                'Hacé que la opción esté visible pero no intrusiva. El cliente tiene que sentir que elige, no que le imponen.',
                'Usá porcentajes razonables como opciones predeterminadas (10%, 15%, 20%).',
                'Permitís siempre la opción de omitirla sin penalización.',
                'Comunicale al equipo que las propinas quedan registradas: genera motivación.',
                'Revisá los datos periódicamente para entender cómo evoluciona el promedio.',
            ]},
            {'type': 'cta', 'text': 'Sumá propinas digitales a tu experiencia QR y ofrecé una atención más moderna de punta a punta.', 'href': '/pricing', 'buttonLabel': 'Ver planes de Mirubro'},
            {'type': 'faq', 'items': [
                {'q': '¿Las propinas digitales son obligatorias para el cliente?', 'a': 'No. La propina siempre es opcional y el cliente puede omitirla con un paso sencillo. El diseño está pensado para que no genere incomodidad.'},
                {'q': '¿Cómo se distribuyen las propinas entre el equipo?', 'a': 'Eso depende de la política interna de cada negocio. Mirubro registra las propinas de forma trazable, facilitando la distribución justa según los criterios que defina el local.'},
                {'q': '¿Necesito un sistema de pagos especial para activar propinas digitales?', 'a': 'Las propinas digitales se integran con el flujo de pago existente en tu configuración de Mirubro. No requieren infraestructura adicional.'},
                {'q': '¿Las propinas digitales aumentan el ingreso total del equipo?', 'a': 'En la mayoría de los casos sí. Al recuperar las propinas que antes se perdían por falta de efectivo, el equipo recibe un reconocimiento que de otra forma no hubiera llegado.'},
                {'q': '¿Se pueden activar propinas digitales sin tener carta online completa?', 'a': 'Consultá con el equipo de Mirubro las opciones de configuración disponibles para tu plan. Algunas funcionalidades pueden activarse de forma modular según tus necesidades.'},
            ]},
        ],
    },
    {
        'slug': 'como-usar-solo-el-qr-de-resenas-sin-carta-online',
        'title': 'Cómo usar solo el QR de reseñas sin implementar carta online',
        'excerpt': (
            'No hace falta tener menú QR online para aprovechar la reputación digital: '
            'podés usar un QR exclusivo para llevar a tus clientes directo a dejar una reseña.'
        ),
        'cover_image_url': '/blog/blog-qr-resenas-sin-carta-cover.svg',
        'reading_time': '5 min',
        'date': '2026-03-03',
        'category_slug': 'resenas',
        'meta_title': 'QR para reseñas sin carta online: cómo funciona y qué beneficios tiene',
        'meta_description': (
            'Descubrí cómo usar un QR que redirige directamente a dejar una reseña de tu '
            'local sin necesidad de implementar una carta online completa.'
        ),
        'body_content': [
            {'type': 'h2', 'text': 'Reputación digital sin necesidad de una carta online completa'},
            {'type': 'p', 'text': 'No todos los negocios están listos para digitalizar su carta. Cambiar los precios con frecuencia, tener una oferta muy variable, o simplemente no querer invertir tiempo en mantener un menú actualizado son razones válidas para no implementarlo todavía. Pero eso no significa que debas renunciar a construir presencia y reputación digital.'},
            {'type': 'p', 'text': 'Existe una alternativa más simple, más rápida y con menor costo de adopción: usar solo el QR de reseñas. Un código QR que, al ser escaneado, lleva directo al cliente al flujo para escribir una reseña de tu local. Sin carta, sin pedidos, sin setup complejo.'},
            {'type': 'h2', 'text': 'Qué es un QR exclusivo para reseñas'},
            {'type': 'p', 'text': 'Es un código QR que apunta a una URL específica de tu local dentro de Mirubro. Al escanearlo, el cliente no ve un menú ni una carta: se redirige automáticamente al formulario o flujo para dejar una reseña del negocio. El proceso es directo, sin pasos intermedios innecesarios.'},
            {'type': 'p', 'text': 'Este QR se puede imprimir en un sticker, una tarjeta de mesa, un volante, el visor de la caja o cualquier punto de contacto físico o digital con el cliente. Una vez impreso, funciona indefinidamente sin necesidad de mantenimiento.'},
            {'type': 'h2', 'text': 'Cómo funciona el flujo paso a paso'},
            {'type': 'ul', 'items': [
                'El cliente escanea el código QR con la cámara de su celular.',
                'Se abre automáticamente la URL configurada para tu local.',
                'El sistema redirige al cliente al flujo de reseña (sin pasar por el menú).',
                'El cliente califica y escribe su experiencia en segundos.',
                'La reseña queda registrada y visible en tu perfil de Mirubro.',
            ]},
            {'type': 'p', 'text': 'No requiere que el cliente descargue ninguna app ni cree una cuenta. El proceso está pensado para ser lo más simple posible y maximizar la tasa de participación.'},
            {'type': 'h2', 'text': 'Para qué tipo de negocios es ideal esta opción'},
            {'type': 'p', 'text': 'Esta modalidad es perfecta para negocios que quieren empezar a construir presencia digital sin comprometerse con la digitalización completa de su operación. En particular:'},
            {'type': 'check', 'items': [
                'Locales pequeños que no tienen recursos para mantener un menú actualizado.',
                'Cafeterías y bares con carta verbal o pizarra, sin necesidad de carte digital.',
                'Take away y comidas rápidas donde la experiencia es breve pero vale la pena valorarla.',
                'Servicios gastronómicos como catering o pastelería a pedido.',
                'Negocios que todavía están evaluando si vale la pena implementar carta digital completa.',
            ]},
            {'type': 'h2', 'text': 'Beneficios de usar solo el QR de reseñas'},
            {'type': 'check', 'items': [
                'Implementación en minutos: no necesitás configurar una carta ni cargar productos.',
                'Mejora de reputación online: acumulás reseñas verificables sin esfuerzo operativo.',
                'Más reseñas, más visibilidad: los buscadores valoran el volumen y frecuencia de reseñas.',
                'Bajo costo de adopción: es una de las formas más baratas de mejorar tu presencia digital.',
                'Primer paso hacia el ecosistema Mirubro: cuando estés listo para más, la plataforma ya te conoce.',
            ]},
            {'type': 'h2', 'text': 'Diferencia entre el QR de reseñas y el menú QR completo'},
            {'type': 'p', 'text': 'Son dos funcionalidades complementarias pero independientes. El menú QR completo te permite mostrar tu carta, recibir pedidos, integrar propinas y gestionar toda la experiencia digital del cliente. El QR de reseñas hace una sola cosa: llevar al cliente directo a dejar feedback.'},
            {'type': 'p', 'text': 'Ninguna es mejor que la otra en términos absolutos. La elección depende de en qué etapa está tu negocio y qué querés resolver primero. Para muchos locales, empezar por el QR de reseñas es la decisión más inteligente: bajo costo, impacto inmediato en reputación, y puerta de entrada natural a las demás funcionalidades.'},
            {'type': 'h2', 'text': 'Cuándo conviene empezar por esta opción'},
            {'type': 'p', 'text': 'Si tu local tiene clientes satisfechos pero pocas o ninguna reseña online, el QR de reseñas es la inversión con mejor ratio costo-beneficio que podés hacer hoy. No necesitás tiempo, no necesitás diseñador, no necesitás integrar sistemas. Solo necesitás imprimir el código y ponerlo en el contador.'},
            {'type': 'cta', 'text': 'Empezá por un QR de reseñas y mejorá tu reputación digital sin necesidad de implementar la carta online completa.', 'href': '/pricing', 'buttonLabel': 'Empezar con Mirubro'},
            {'type': 'faq', 'items': [
                {'q': '¿El QR de reseñas funciona aunque no tenga el menú QR activado?', 'a': 'Sí. Esta es exactamente la propuesta: podés usar solo el QR de reseñas sin necesidad de configurar ni mantener un menú digital. Son funcionalidades independientes.'},
                {'q': '¿El cliente necesita instalar una app para dejar la reseña?', 'a': 'No. El flujo funciona completamente desde el navegador del celular. Sin apps, sin registros obligatorios, sin pasos innecesarios.'},
                {'q': '¿Cuánto tiempo lleva configurar el QR de reseñas en Mirubro?', 'a': 'Una vez que tu negocio está registrado en la plataforma, generar y activar el QR de reseñas toma minutos. El code está disponible para descargar e imprimir de inmediato.'},
                {'q': '¿Las reseñas recopiladas con este QR aparecen en buscadores?', 'a': 'Las reseñas generadas quedan en tu perfil de Mirubro. Dependiendo de las integraciones de la plataforma, también pueden contribuir a tu presencia en resultados de búsqueda locales.'},
                {'q': '¿Puedo escalar más tarde al menú QR completo sin perder las reseñas acumuladas?', 'a': 'Sí. Todo lo que acumulás con el QR de reseñas queda asociado a tu negocio. Cuando actives funcionalidades adicionales, el historial de reputación ya construido se mantiene.'},
            ]},
        ],
    },
    {
        'slug': 'como-migrar-tu-inventario-a-gestion-comercial-importando-excel',
        'title': 'Cómo migrar tu inventario a Gestión Comercial importando tu Excel',
        'excerpt': (
            'Con la plantilla correcta, migrar tus productos a Gestión Comercial es más '
            'simple: descargás el ejemplo, completás tus datos y luego importás todo al sistema.'
        ),
        'cover_image_url': '/blog/blog-importar-excel-inventario-cover.svg',
        'reading_time': '7 min',
        'date': '2026-02-27',
        'category_slug': 'gestion-comercial',
        'meta_title': 'Importar inventario desde Excel a Gestión Comercial: guía paso a paso',
        'meta_description': (
            'Aprendé cómo migrar tus productos, categorías, precios y stock a Gestión '
            'Comercial descargando la plantilla Excel y luego importando tus datos de forma '
            'ordenada.'
        ),
        'body_content': [
            {'type': 'h2', 'text': 'Por qué ordenar el inventario antes de migrar'},
            {'type': 'p', 'text': 'Uno de los errores más comunes al empezar con un sistema de gestión es importar datos sucios: productos duplicados, precios desactualizados, categorías mezcladas o stocks incorrectos. Cuando eso pasa, el sistema refleja el caos que se quería resolver y la adopción fracasa.'},
            {'type': 'p', 'text': 'La migración desde Excel a Gestión Comercial es una oportunidad para hacer limpieza. Revisás lo que tenés, lo estructurás correctamente y cargás data de calidad desde el día uno. El resultado: un inventario confiable que tu equipo puede usar sin fricciones desde el primer login.'},
            {'type': 'h2', 'text': 'Qué datos podés importar'},
            {'type': 'p', 'text': 'La plantilla de importación de Mirubro cubre los datos esenciales para empezar a operar:'},
            {'type': 'check', 'items': [
                'Productos: nombre, descripción, código interno (SKU).',
                'Categorías: a qué grupo pertenece cada producto.',
                'Precios: precio de venta unitario.',
                'Stock inicial: cantidad disponible al momento de la carga.',
                'Variantes: en caso de productos con tallas, sabores u otras opciones.',
            ]},
            {'type': 'p', 'text': 'No es necesario completar todos los campos para empezar. Con nombre, categoría, precio y stock ya tenés lo suficiente para operar desde el primer día.'},
            {'type': 'h2', 'text': 'Guía paso a paso: cómo importar tu inventario'},
            {'type': 'h3', 'text': 'Paso 1: descargar la plantilla modelo'},
            {'type': 'p', 'text': 'Dentro de Gestión Comercial, en la sección de Inventario, encontrás la opción de importar productos. Desde ahí podés descargar la plantilla oficial en formato Excel (.xlsx). Esta plantilla tiene la estructura exacta que el sistema espera: columnas con nombres, tipos de dato y ejemplos de cómo completar cada campo.'},
            {'type': 'p', 'text': 'Nunca uses una plantilla genérica o armada a mano. Siempre trabajá desde la plantilla descargada del sistema para evitar errores de formato que puedan rechazar la importación.'},
            {'type': 'h3', 'text': 'Paso 2: revisar cómo está estructurada'},
            {'type': 'p', 'text': 'La plantilla tiene una fila de encabezado con el nombre de cada columna y filas de ejemplo con datos de muestra. Antes de completarla con tus datos reales, recorrela entera: entendé qué espera cada columna, qué valores son obligatorios y cuáles son opcionales. Los campos obligatorios están marcados en el encabezado.'},
            {'type': 'h3', 'text': 'Paso 3: completar la plantilla con tus datos reales'},
            {'type': 'p', 'text': 'Volcá tus productos en la plantilla siguiendo el formato indicado. Si ya tenés un Excel propio con tu inventario, es tan simple como copiar y pegar los datos en las columnas correspondientes. Prestá atención a los formatos: los precios van sin símbolo de moneda, los stocks son números enteros, y los nombres de categorías deben coincidir con las que definiste previamente en el sistema.'},
            {'type': 'ul', 'items': [
                'Nombres de producto: claros y consistentes, sin abreviaciones confusas.',
                'Categorías: definí las categorías primero en el sistema y usá exactamente esos nombres en la plantilla.',
                'Precios: número sin formato de moneda ni separadores de miles inconsistentes.',
                'Stock: cantidad real disponible en este momento, no una estimación.',
                'SKU/Código interno: si usás códigos propios, cargalos para facilitar búsquedas futuras.',
            ]},
            {'type': 'h3', 'text': 'Paso 4: validar formato y consistencia'},
            {'type': 'p', 'text': 'Antes de importar, hacé una revisión manual. Buscá duplicados, chequeá que no haya celdas vacías donde debería haber datos, y verificá que los nombres de categorías coincidan exactamente con los del sistema. Un error tipográfico en el nombre de una categoría puede generar inconsistencias que después son difíciles de corregir en bulk.'},
            {'type': 'h3', 'text': 'Paso 5: importar el archivo a Gestión Comercial'},
            {'type': 'p', 'text': 'Con la plantilla completa y revisada, volvé a la sección de importación en Gestión Comercial, subí el archivo y confirmá la operación. El sistema procesa el archivo, valida los datos y te muestra un resumen de lo que se va a cargar antes de confirmar definitivamente.'},
            {'type': 'h3', 'text': 'Paso 6: revisar resultados y corregir inconsistencias'},
            {'type': 'p', 'text': 'Una vez completada la importación, revisá el inventario cargado. Si el sistema detectó errores en alguna fila, te lo informa con detalle. Podés corregir esas filas en la plantilla y reimportarlas, o editarlas directamente en el sistema producto por producto.'},
            {'type': 'h2', 'text': 'Errores comunes a evitar'},
            {'type': 'ul', 'items': [
                'Importar con datos duplicados: revisá que no haya el mismo SKU cargado dos veces.',
                'Categorías sin crear primero: si la categoría no existe en el sistema, el producto puede quedar sin clasificar.',
                'Precios con formato incorrecto: evitá símbolos de moneda, espacios o comas como separadores de miles si el sistema espera punto.',
                'Stocks negativos o en cero cuando hay stock real: en un sistema de inventario, arrancar con stock incorrecto genera problemas desde el primer movimiento.',
                'No descargar la plantilla oficial: trabajar con una plantilla distinta a la del sistema casi siempre genera errores de importación.',
            ]},
            {'type': 'h2', 'text': 'Buenas prácticas antes de importar'},
            {'type': 'check', 'items': [
                'Hacé un conteo físico antes de cargar el stock inicial.',
                'Definí tu estructura de categorías antes de completar la plantilla.',
                'Probá con un lote pequeño (10-20 productos) antes de importar todo.',
                'Guardá la plantilla completada como respaldo antes de subirla.',
                'Coordiná la migración en un momento de baja operación del negocio.',
            ]},
            {'type': 'h2', 'text': 'Beneficios de migrar bien desde el inicio'},
            {'type': 'p', 'text': 'Un inventario bien cargado desde el día uno es la base de todo lo demás: reposiciones correctas, reportes confiables, menos errores en caja y una visión real de qué se vende y qué no. El tiempo invertido en la migración se recupera en la primera semana de operación.'},
            {'type': 'cta', 'text': 'Migrá tu inventario con una plantilla clara y empezá a operar en Gestión Comercial con datos ordenados desde el día uno.', 'href': '/pricing', 'buttonLabel': 'Ver Gestión Comercial'},
            {'type': 'faq', 'items': [
                {'q': '¿Hay un límite de productos que puedo importar en una sola vez?', 'a': 'Depende del plan contratado. Para volúmenes muy grandes se recomienda importar en lotes para facilitar la revisión de errores y el control del proceso.'},
                {'q': '¿Puedo importar y luego editar productos individualmente?', 'a': 'Sí. Después de la importación masiva podés editar cualquier producto directamente desde el panel de inventario, uno por uno o en edición múltiple según las funcionalidades disponibles.'},
                {'q': '¿Qué pasa si subo el mismo archivo dos veces?', 'a': 'El sistema detecta duplicados basándose en el código SKU o nombre del producto. Te avisará antes de confirmar si hay registros que ya existen en el inventario.'},
                {'q': '¿Puedo importar variantes de producto (tallas, sabores, etc.)?', 'a': 'Sí, la plantilla contempla variantes. Cada combinación de producto y variante puede cargarse como una fila separada con su propio stock y precio.'},
                {'q': '¿Es necesario vaciar el inventario antes de importar si ya tengo algunos productos cargados?', 'a': 'No necesariamente. Podés usar la importación para agregar nuevos productos sin afectar los existentes, siempre que los SKUs no se repitan. Si vas a reemplazar datos existentes, consultá con el equipo de soporte el procedimiento recomendado.'},
            ]},
        ],
    },
    # ── Legacy posts (sin bodyContent) ────────────────────────────────────
    {
        'slug': 'gestion-de-inventario-eficiente-para-pymes',
        'title': 'Gestión de inventario eficiente para PYMEs',
        'excerpt': (
            'Aprende a controlar tu stock en tiempo real y evita quiebres de inventario '
            'con procesos simples que escalan con tu equipo.'
        ),
        'cover_image_url': 'https://images.unsplash.com/photo-1553413077-190dd305871c?w=600&auto=format&fit=crop&q=70',
        'reading_time': '4 min',
        'date': '2026-02-14',
        'category_slug': 'inventario',
    },
    {
        'slug': 'menu-qr-como-aumentar-ventas-restaurante',
        'title': 'Menú QR: cómo aumentar ventas en tu restaurante',
        'excerpt': (
            'Un menú digital bien diseñado no solo mejora la experiencia del comensal, '
            'también acelera el servicio y reduce errores en las órdenes.'
        ),
        'cover_image_url': 'https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?w=600&auto=format&fit=crop&q=70',
        'reading_time': '3 min',
        'date': '2026-02-07',
        'category_slug': 'ventas',
    },
    {
        'slug': 'cierre-de-caja-sin-errores-guia-practica',
        'title': 'Cierre de caja sin errores: guía práctica',
        'excerpt': (
            'El cierre de caja es uno de los procesos más críticos del día. Te contamos '
            'las mejores prácticas para que sea rápido, exacto y auditable.'
        ),
        'cover_image_url': 'https://images.unsplash.com/photo-1554224155-6726b3ff858f?w=600&auto=format&fit=crop&q=70',
        'reading_time': '6 min',
        'date': '2026-01-28',
        'category_slug': 'caja',
    },
    {
        'slug': 'reportes-de-venta-que-datos-importan',
        'title': 'Reportes de ventas: ¿qué datos importan realmente?',
        'excerpt': (
            'No todos los números cuentan la misma historia. Descubre los KPIs de ventas '
            'que deberías revisar cada semana para tomar mejores decisiones.'
        ),
        'cover_image_url': 'https://images.unsplash.com/photo-1543286386-713bdd548da4?w=600&auto=format&fit=crop&q=70',
        'reading_time': '5 min',
        'date': '2026-01-15',
        'category_slug': 'ventas',
    },
    {
        'slug': 'fidelizacion-de-clientes-estrategias',
        'title': 'Fidelización de clientes: estrategias que funcionan',
        'excerpt': (
            'Retener a un cliente cuesta hasta 5 veces menos que conseguir uno nuevo. '
            'Aquí te mostramos cómo lograrlo con herramientas simples.'
        ),
        'cover_image_url': 'https://images.unsplash.com/photo-1521791136064-7986c2920216?w=600&auto=format&fit=crop&q=70',
        'reading_time': '4 min',
        'date': '2026-01-08',
        'category_slug': 'marketing',
    },
    {
        'slug': 'facturacion-electronica-primeros-pasos',
        'title': 'Facturación electrónica: primeros pasos',
        'excerpt': (
            'La transición a la factura electrónica puede parecer compleja, pero con el '
            'proceso correcto tu negocio puede estar listo en menos de una semana.'
        ),
        'cover_image_url': 'https://images.unsplash.com/photo-1450101499163-c8848c66ca85?w=600&auto=format&fit=crop&q=70',
        'reading_time': '7 min',
        'date': '2025-12-20',
        'category_slug': 'facturacion',
    },
]


class Command(BaseCommand):
    help = 'Seed 9 blog categories and 14 editorial posts (idempotent).'

    def handle(self, *args, **options):
        cat_created = 0
        cat_skipped = 0
        cat_map: dict[str, BlogCategory] = {}

        for cat_data in CATEGORIES:
            obj, created = BlogCategory.objects.get_or_create(
                slug=cat_data['slug'],
                defaults={'label': cat_data['label']},
            )
            cat_map[cat_data['slug']] = obj
            if created:
                cat_created += 1
            else:
                cat_skipped += 1

        self.stdout.write(
            f'Categories: {cat_created} created, {cat_skipped} already existed.'
        )

        post_created = 0
        post_skipped = 0

        for post_data in POSTS:
            if BlogPost.objects.filter(slug=post_data['slug']).exists():
                post_skipped += 1
                continue

            pub_date = datetime.strptime(post_data['date'], '%Y-%m-%d').replace(
                tzinfo=timezone.utc,
            )

            BlogPost.objects.create(
                title=post_data['title'],
                slug=post_data['slug'],
                excerpt=post_data['excerpt'],
                cover_image_url=post_data['cover_image_url'],
                reading_time=post_data['reading_time'],
                category=cat_map.get(post_data['category_slug']),
                body_content=post_data.get('body_content', []),
                meta_title=post_data.get('meta_title', ''),
                meta_description=post_data.get('meta_description', ''),
                source_label='MIRUBRO',
                status=BlogPost.Status.PUBLISHED,
                published_at=pub_date,
            )
            post_created += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'Posts: {post_created} created, {post_skipped} already existed.'
            )
        )
