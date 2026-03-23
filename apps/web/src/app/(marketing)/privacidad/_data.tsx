import type { LegalSection } from '@/components/legal/legal-page-layout';

/**
 * Fecha de última actualización de la Política de Privacidad.
 * Editá esta constante cada vez que se modifique el contenido.
 */
export const PRIVACY_LAST_UPDATED = '23 de marzo de 2026';

/**
 * Secciones de la Política de Privacidad.
 *
 * TODO interno (no visible al usuario):
 * - Completar razón social legal cuando esté confirmada
 * - Completar CUIT cuando esté disponible
 * - Completar domicilio legal/fiscal cuando se defina
 * - Revisar si se requiere DPO o representante de privacidad formal
 */
export const privacySections: LegalSection[] = [
    {
        id: 'responsable',
        title: 'Responsable del tratamiento',
        content: (
            <>
                <p>
                    Mi Rubro es la marca bajo la cual se ofrecen herramientas digitales
                    para comercios y locales. Para consultas vinculadas al tratamiento de
                    datos personales, podés escribir a{' '}
                    <a
                        href="mailto:mirubrodigital@gmail.com"
                        className="font-medium text-brand-600 underline underline-offset-2 hover:text-brand-500"
                    >
                        mirubrodigital@gmail.com
                    </a>
                    .
                </p>
            </>
        ),
    },
    {
        id: 'alcance',
        title: 'Alcance',
        content: (
            <p>
                Esta política aplica al uso del sitio web de Mi Rubro y a los servicios
                actualmente ofrecidos, incluyendo Gestión Comercial, Menú QR Online y QR
                para reseñas. También aplica a formularios de contacto, solicitudes de
                demo, comunicaciones comerciales y soporte.
            </p>
        ),
    },
    {
        id: 'datos-recopilados',
        title: 'Qué datos podemos recopilar',
        content: (
            <>
                <div>
                    <h3 className="mb-2 text-sm font-semibold uppercase tracking-wider text-slate-800">
                        Datos de identificación y contacto
                    </h3>
                    <ul className="list-disc space-y-1 pl-5 text-slate-600">
                        <li>Nombre y apellido</li>
                        <li>Nombre del comercio o local</li>
                        <li>Email</li>
                        <li>Teléfono</li>
                        <li>Cargo o rol</li>
                    </ul>
                </div>

                <div>
                    <h3 className="mb-2 text-sm font-semibold uppercase tracking-wider text-slate-800">
                        Datos comerciales y de cuenta
                    </h3>
                    <ul className="list-disc space-y-1 pl-5 text-slate-600">
                        <li>Información de registro</li>
                        <li>Plan o servicio consultado o contratado</li>
                        <li>Historial de altas, cambios o bajas</li>
                        <li>Comunicaciones con soporte o contacto comercial</li>
                    </ul>
                </div>

                <div>
                    <h3 className="mb-2 text-sm font-semibold uppercase tracking-wider text-slate-800">
                        Datos operativos del servicio
                    </h3>
                    <ul className="list-disc space-y-1 pl-5 text-slate-600">
                        <li>Configuración del comercio o local</li>
                        <li>Menúes, catálogos, sucursales, usuarios y permisos</li>
                        <li>Información cargada por el cliente en los módulos contratados</li>
                    </ul>
                </div>

                <div>
                    <h3 className="mb-2 text-sm font-semibold uppercase tracking-wider text-slate-800">
                        Datos técnicos
                    </h3>
                    <ul className="list-disc space-y-1 pl-5 text-slate-600">
                        <li>Dirección IP</li>
                        <li>Navegador</li>
                        <li>Sistema operativo</li>
                        <li>Dispositivo</li>
                        <li>Fecha, hora y páginas visitadas</li>
                        <li>Cookies y tecnologías similares</li>
                    </ul>
                </div>

                <div>
                    <h3 className="mb-2 text-sm font-semibold uppercase tracking-wider text-slate-800">
                        Datos de interacción mediante QR
                    </h3>
                    <p>
                        En algunos casos, cuando una persona accede a un menú QR o utiliza
                        un QR para reseñas, Mi Rubro puede registrar datos técnicos básicos
                        de navegación, métricas de uso o información estadística para mejorar
                        el servicio y medir su funcionamiento.
                    </p>
                </div>
            </>
        ),
    },
    {
        id: 'finalidades',
        title: 'Finalidades del tratamiento',
        content: (
            <ul className="list-disc space-y-1 pl-5">
                <li>Brindar, mantener y mejorar los servicios</li>
                <li>Crear y administrar cuentas</li>
                <li>Responder consultas, demos y pedidos comerciales</li>
                <li>Prestar soporte técnico y atención al cliente</li>
                <li>Gestionar cuestiones administrativas y comerciales</li>
                <li>
                    Enviar comunicaciones operativas, legales o comerciales, cuando
                    corresponda
                </li>
                <li>Prevenir fraude, accesos no autorizados y usos indebidos</li>
                <li>Generar métricas, reportes y análisis internos</li>
                <li>
                    Cumplir obligaciones legales o requerimientos de autoridad competente
                </li>
            </ul>
        ),
    },
    {
        id: 'base-legitimacion',
        title: 'Base de legitimación',
        content: (
            <p>
                Tratamos datos personales cuando ello es necesario para gestionar una
                relación precontractual o contractual, responder solicitudes realizadas
                por la persona usuaria, cumplir obligaciones legales, proteger la
                seguridad e integridad de la plataforma o, cuando corresponda, contar con
                consentimiento para determinadas finalidades.
            </p>
        ),
    },
    {
        id: 'datos-clientes',
        title: 'Datos provistos por clientes',
        content: (
            <p>
                Cuando un comercio o local utiliza Mi Rubro y carga datos dentro de la
                plataforma, ese cliente es responsable de contar con la legitimación
                necesaria para el tratamiento de esos datos frente a sus propios usuarios,
                clientes o contactos, cuando corresponda.
            </p>
        ),
    },
    {
        id: 'comparticion',
        title: 'Compartición de datos',
        content: (
            <p>
                Mi Rubro puede compartir datos con proveedores tecnológicos, servicios de
                hosting, almacenamiento, email, analítica, soporte, facturación o
                herramientas necesarias para la operación del servicio. También podrá
                compartir información cuando exista obligación legal o requerimiento válido
                de autoridad competente. Mi Rubro no vende datos personales.
            </p>
        ),
    },
    {
        id: 'terceros',
        title: 'Servicios de terceros',
        content: (
            <p>
                Algunas funcionalidades pueden redirigir o integrarse con servicios de
                terceros. Por ejemplo, un QR para reseñas puede dirigir a plataformas
                externas como Google u otros servicios similares. En esos casos, el
                tratamiento posterior de datos queda sujeto a las políticas y condiciones
                del tercero correspondiente.
            </p>
        ),
    },
    {
        id: 'conservacion',
        title: 'Conservación',
        content: (
            <p>
                Los datos personales se conservarán durante el tiempo necesario para
                cumplir las finalidades para las que fueron recopilados, sostener la
                relación comercial, responder reclamos, cumplir obligaciones legales,
                contractuales, contables o de seguridad y ejercer o defender derechos.
            </p>
        ),
    },
    {
        id: 'seguridad',
        title: 'Seguridad',
        content: (
            <p>
                Mi Rubro adopta medidas técnicas y organizativas razonables para proteger
                los datos personales contra acceso no autorizado, pérdida, alteración,
                divulgación o destrucción indebida. Sin embargo, ningún sistema puede
                garantizar seguridad absoluta.
            </p>
        ),
    },
    {
        id: 'derechos',
        title: 'Derechos de las personas titulares',
        content: (
            <>
                <p>
                    La persona titular de los datos puede ejercer sus derechos de acceso,
                    rectificación, actualización y supresión escribiendo a{' '}
                    <a
                        href="mailto:mirubrodigital@gmail.com"
                        className="font-medium text-brand-600 underline underline-offset-2 hover:text-brand-500"
                    >
                        mirubrodigital@gmail.com
                    </a>
                    .
                </p>
                <div className="rounded-lg border border-slate-200 bg-slate-50 px-5 py-4">
                    <p className="text-sm text-slate-600">
                        Si la respuesta no resulta satisfactoria, la persona titular podrá
                        acudir a la autoridad de control competente en materia de protección
                        de datos personales conforme a la normativa aplicable en Argentina.
                    </p>
                </div>
            </>
        ),
    },
    {
        id: 'cookies',
        title: 'Cookies',
        content: (
            <p>
                Mi Rubro puede utilizar cookies propias y de terceros para recordar
                preferencias, medir tráfico, analizar navegación y mejorar la experiencia
                del sitio. La persona usuaria puede configurar su navegador para rechazar
                o eliminar cookies, aunque eso podría afectar ciertas funcionalidades.
            </p>
        ),
    },
    {
        id: 'menores',
        title: 'Menores de edad',
        content: (
            <p>
                Los servicios de Mi Rubro están orientados a comercios, locales y personas
                mayores de edad. No se busca recopilar deliberadamente datos personales de
                menores sin la intervención o autorización válida de sus representantes,
                cuando corresponda.
            </p>
        ),
    },
    {
        id: 'cambios',
        title: 'Cambios a esta política',
        content: (
            <p>
                Mi Rubro podrá actualizar esta Política de Privacidad para reflejar
                cambios legales, técnicos, operativos o comerciales. La versión vigente
                será publicada en esta misma página indicando su fecha de última
                actualización.
            </p>
        ),
    },
    {
        id: 'contacto',
        title: 'Contacto',
        content: (
            <p>
                Para consultas sobre privacidad o tratamiento de datos personales,
                escribinos a:{' '}
                <a
                    href="mailto:mirubrodigital@gmail.com"
                    className="font-medium text-brand-600 underline underline-offset-2 hover:text-brand-500"
                >
                    mirubrodigital@gmail.com
                </a>
            </p>
        ),
    },
];
