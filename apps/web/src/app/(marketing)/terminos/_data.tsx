import Link from 'next/link';
import type { LegalSection } from '@/components/legal/legal-page-layout';

/**
 * Fecha de última actualización de los Términos y Condiciones.
 * Editá esta constante cada vez que se modifique el contenido.
 */
export const TERMS_LAST_UPDATED = '23 de marzo de 2026';

/**
 * Secciones de los Términos y Condiciones.
 *
 * TODO interno (no visible al usuario):
 * - Completar razón social legal cuando esté confirmada
 * - Completar CUIT cuando esté disponible
 * - Completar domicilio legal/fiscal cuando se defina
 * - Definir política comercial exacta (moneda, IVA, facturación, renovación)
 * - Definir política de baja/reintegros si aplica
 * - Si se habilita contratación online directa para consumidores:
 *   · Revisar implementación de botón de arrepentimiento
 *   · Revisar publicación de contratos de adhesión
 *   · Revisar baja online si corresponde
 */
export const termsSections: LegalSection[] = [
    {
        id: 'quienes-somos',
        title: 'Quiénes somos',
        content: (
            <p>
                Mi Rubro ofrece herramientas digitales para comercios y locales.
                Actualmente, sus servicios se enfocan en Gestión Comercial, Menú QR
                Online y QR para reseñas.
            </p>
        ),
    },
    {
        id: 'aceptacion',
        title: 'Aceptación y capacidad',
        content: (
            <p>
                El uso de los servicios requiere capacidad legal para contratar. Si actuás
                en representación de un comercio, empresa o local, declarás contar con
                facultades suficientes para obligarlo conforme a estos términos.
            </p>
        ),
    },
    {
        id: 'registro',
        title: 'Registro y cuenta',
        content: (
            <p>
                Para acceder a determinados servicios puede ser necesario crear una cuenta
                y proporcionar información actualizada, completa y veraz. La persona
                usuaria es responsable de mantener la confidencialidad de sus credenciales,
                restringir accesos no autorizados y notificar cualquier uso indebido de la
                cuenta.
            </p>
        ),
    },
    {
        id: 'descripcion-servicio',
        title: 'Descripción general del servicio',
        content: (
            <>
                <p>
                    Mi Rubro puede incluir, según el servicio o plan contratado,
                    herramientas de administración y gestión comercial, publicación de
                    menúes o catálogos accesibles por QR, herramientas para facilitar el
                    acceso a canales de reseñas y funcionalidades complementarias de
                    configuración, soporte o analítica básica.
                </p>
                <div className="rounded-lg border border-slate-200 bg-slate-50 px-5 py-4">
                    <p className="text-sm text-slate-600">
                        No todas las funcionalidades se encuentran necesariamente
                        disponibles en todos los planes, etapas del producto o
                        implementaciones.
                    </p>
                </div>
            </>
        ),
    },
    {
        id: 'uso-permitido',
        title: 'Uso permitido',
        content: (
            <ul className="list-disc space-y-1 pl-5">
                <li>Usar el servicio conforme a la ley y a estos términos</li>
                <li>No utilizarlo con fines ilícitos, fraudulentos o engañosos</li>
                <li>No cargar contenidos que infrinjan derechos de terceros</li>
                <li>
                    No intentar acceder sin autorización a sistemas, cuentas o datos
                </li>
                <li>
                    No interferir con la seguridad, estabilidad o integridad de la
                    plataforma
                </li>
                <li>
                    No usar la plataforma para spam o automatizaciones abusivas no
                    autorizadas
                </li>
            </ul>
        ),
    },
    {
        id: 'contenido-cliente',
        title: 'Contenido y datos cargados por el cliente',
        content: (
            <>
                <p>
                    El cliente conserva la titularidad sobre los contenidos, datos,
                    imágenes, textos, menúes, descripciones y demás materiales que cargue
                    en la plataforma. El cliente declara que cuenta con los derechos,
                    autorizaciones y bases necesarias para utilizar, publicar y tratar esos
                    contenidos y datos.
                </p>
                <p>
                    Mi Rubro podrá suspender o remover contenido cuando exista
                    incumplimiento legal, reclamo de terceros, riesgo operativo o violación
                    de estos términos.
                </p>
            </>
        ),
    },
    {
        id: 'planes-precios',
        title: 'Planes, precios y facturación',
        content: (
            <>
                <p>
                    Los precios, planes, alcances, promociones y condiciones comerciales se
                    informarán en el sitio, propuesta comercial o proceso de contratación
                    correspondiente. Salvo indicación expresa en contrario, la falta de pago
                    podrá generar suspensión o limitación del servicio.
                </p>
                {/*
                 * TODO interno (no visible al usuario):
                 * Bloque preparado para futura expansión cuando se definan
                 * política comercial, suscripciones y cobranzas.
                 * Agregar: moneda, IVA, facturación automática, reintegros,
                 * renovación automática cuando estén definidos.
                 */}
            </>
        ),
    },
    {
        id: 'cancelacion',
        title: 'Cancelación y baja',
        content: (
            <p>
                La cancelación o baja de un servicio deberá solicitarse por los canales
                habilitados por Mi Rubro. La cancelación no elimina automáticamente
                obligaciones de pago ya devengadas ni importes pendientes por períodos ya
                utilizados o comprometidos comercialmente.
            </p>
        ),
    },
    {
        id: 'suspension',
        title: 'Suspensión o terminación por incumplimiento',
        content: (
            <p>
                Mi Rubro podrá suspender temporalmente o terminar el acceso al servicio
                cuando existan incumplimientos de estos términos, mora en el pago, uso
                abusivo o riesgoso de la plataforma, requerimientos legales o amenazas a la
                seguridad o integridad del servicio.
            </p>
        ),
    },
    {
        id: 'disponibilidad',
        title: 'Disponibilidad y soporte',
        content: (
            <p>
                Mi Rubro realizará esfuerzos razonables para mantener la disponibilidad del
                servicio, pero no garantiza funcionamiento ininterrumpido ni libre de
                errores. Podrán existir interrupciones por mantenimiento, actualizaciones,
                incidencias técnicas, integraciones de terceros, fuerza mayor o causas
                ajenas al control del servicio.
            </p>
        ),
    },
    {
        id: 'integraciones',
        title: 'Integraciones y terceros',
        content: (
            <p>
                Determinadas funciones pueden depender de servicios de terceros. Mi Rubro
                no garantiza la disponibilidad permanente ni las políticas comerciales,
                técnicas o de privacidad de esos terceros. Cuando un módulo redirija a
                servicios externos para reseñas u otras funciones, el uso posterior quedará
                sujeto a las condiciones del tercero respectivo.
            </p>
        ),
    },
    {
        id: 'propiedad-intelectual',
        title: 'Propiedad intelectual',
        content: (
            <>
                <p>
                    Todos los derechos sobre el sitio, software, diseño, marca, identidad
                    visual, logos, textos, interfaces y desarrollos vinculados a Mi Rubro
                    pertenecen a sus titulares o licenciantes correspondientes. El uso del
                    servicio no implica cesión ni transferencia de derechos de propiedad
                    intelectual, salvo autorización expresa por escrito.
                </p>
                <p className="text-sm text-slate-500">
                    La plataforma fue desarrollada por Estudio VIZION.
                </p>
            </>
        ),
    },
    {
        id: 'limitacion-responsabilidad',
        title: 'Limitación de responsabilidad',
        content: (
            <p>
                En la medida permitida por la normativa aplicable, Mi Rubro no será
                responsable por daños indirectos, incidentales, pérdida de oportunidades
                comerciales, fallas de conectividad, hosting o servicios de terceros, ni
                por contenidos cargados por clientes o terceros. Nada de lo previsto en
                estos términos limita derechos irrenunciables que pudieran corresponder
                bajo normativa aplicable.
            </p>
        ),
    },
    {
        id: 'proteccion-datos',
        title: 'Protección de datos',
        content: (
            <p>
                El tratamiento de datos personales se rige además por la{' '}
                <Link
                    href={'/privacidad' as never}
                    className="font-medium text-brand-600 underline underline-offset-2 hover:text-brand-500"
                >
                    Política de Privacidad
                </Link>{' '}
                vigente, que integra estos términos en lo pertinente.
            </p>
        ),
    },
    {
        id: 'modificaciones',
        title: 'Modificaciones',
        content: (
            <p>
                Mi Rubro podrá actualizar estos términos por cambios legales, técnicos,
                operativos o comerciales. La versión vigente será publicada en el sitio con
                su fecha de última actualización.
            </p>
        ),
    },
    {
        id: 'contacto',
        title: 'Contacto',
        content: (
            <p>
                Para consultas legales, comerciales o contractuales, escribinos a:{' '}
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
