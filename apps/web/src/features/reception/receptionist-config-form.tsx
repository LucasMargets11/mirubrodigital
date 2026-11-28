"use client";

import { useEffect, useMemo, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Modal } from '@/components/ui/modal';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { ApiError } from '@/lib/api/client';

import { receptionistConfigAdapter, type ReceptionistConfigTarget } from './receptionist-config-api';
import {
    RECEPTIONIST_LIST_LIMITS,
    RECEPTIONIST_TEXT_LIMITS,
    type ReceptionistConfig,
    type ReceptionistConfigContent,
    type ReceptionistConfigField,
    type ReceptionistConfigResponse,
    type ReceptionistConfigStatus,
    type ReceptionistFaq,
    type ReceptionistService,
} from './types';

// ── Modelo del formulario (puro, exportado para tests) ──────────────────────

const CONTENT_FIELDS: ReceptionistConfigField[] = [
    'assistant_name', 'business_category', 'business_description', 'custom_instructions', 'tone',
    'language', 'welcome_message', 'operational_info', 'business_hours', 'services', 'reference_info',
    'faqs', 'handoff_rules',
];

export type ReceptionistTab = 'identity' | 'services' | 'faqs' | 'instructions';

const TABS: { id: ReceptionistTab; label: string }[] = [
    { id: 'identity', label: 'Identidad' },
    { id: 'services', label: 'Servicios' },
    { id: 'faqs', label: 'Preguntas frecuentes' },
    { id: 'instructions', label: 'Instrucciones' },
];

export const FIELD_LABELS: Record<string, string> = {
    assistant_name: 'Nombre del asistente',
    business_category: 'Rubro',
    business_description: 'Descripción del negocio',
    welcome_message: 'Mensaje de bienvenida',
    tone: 'Tono',
    language: 'Idioma',
    services: 'Servicios',
    faqs: 'Preguntas frecuentes',
    custom_instructions: 'Instrucciones adicionales',
    handoff_rules: 'Cuándo derivar a una persona',
    operational_info: 'Información operativa',
    business_hours: 'Horarios de atención',
    reference_info: 'Información de referencia',
    status: 'Estado',
    non_field_errors: 'Configuración',
};

const FIELD_TAB: Record<ReceptionistConfigField, ReceptionistTab> = {
    assistant_name: 'identity',
    business_category: 'identity',
    business_description: 'identity',
    welcome_message: 'identity',
    tone: 'identity',
    language: 'identity',
    services: 'services',
    faqs: 'faqs',
    custom_instructions: 'instructions',
    handoff_rules: 'instructions',
    operational_info: 'instructions',
    business_hours: 'instructions',
    reference_info: 'instructions',
};

export function tabOfField(field: string): ReceptionistTab | null {
    return (FIELD_TAB as Record<string, ReceptionistTab | undefined>)[field] ?? null;
}

/** Contenido normalizado: una descripción ausente equivale a vacía. */
export function contentOf(config: ReceptionistConfigContent): ReceptionistConfigContent {
    const content = {} as Record<string, unknown>;
    for (const field of CONTENT_FIELDS) content[field] = config[field];
    const normalized = content as ReceptionistConfigContent;
    normalized.services = (config.services ?? []).map((s) => ({ name: s.name, description: s.description ?? '' }));
    normalized.faqs = (config.faqs ?? []).map((f) => ({ question: f.question, answer: f.answer }));
    return normalized;
}

/** Solo los campos distintos del servidor; las listas se comparan por contenido. */
export function changedFields(
    server: ReceptionistConfigContent,
    draft: ReceptionistConfigContent,
): Partial<ReceptionistConfigContent> {
    const base = contentOf(server);
    const changes: Record<string, unknown> = {};
    for (const field of CONTENT_FIELDS) {
        if (JSON.stringify(base[field]) !== JSON.stringify(draft[field])) changes[field] = draft[field];
    }
    return changes as Partial<ReceptionistConfigContent>;
}

export type FieldErrors = Record<string, string>;

function payloadOf(error: unknown): Record<string, unknown> | null {
    if (error instanceof ApiError && error.payload && typeof error.payload === 'object') {
        return error.payload as Record<string, unknown>;
    }
    return null;
}

export function errorCode(error: unknown): string | null {
    const code = payloadOf(error)?.code;
    return typeof code === 'string' ? code : null;
}

/** `validation_error.fields` (`{campo: [mensajes]}`) → un mensaje por campo. */
export function fieldErrorsFrom(error: unknown): FieldErrors {
    const fields = payloadOf(error)?.fields;
    if (!fields || typeof fields !== 'object' || Array.isArray(fields)) return {};
    const result: FieldErrors = {};
    for (const [field, value] of Object.entries(fields as Record<string, unknown>)) {
        const text = Array.isArray(value) ? value.filter((v) => typeof v === 'string').join(' ') : String(value ?? '');
        if (text) result[field] = text;
    }
    return result;
}

// Textos que dependen de quién edita: el comercio o Platform Admin.
const COPY = {
    business: {
        forbiddenRead: 'Tu rol o tu plan de Recepcionista IA no permiten administrar el agente.',
        forbiddenWrite: 'Tu rol o tu plan no permiten editar la configuración del agente.',
        empty: 'Tu agente todavía no tiene configuración',
    },
    platform_admin: {
        forbiddenRead: 'Tu rol de Platform Admin no permite ver ni editar la configuración de Recepcionista IA.',
        forbiddenWrite: 'Tu rol de Platform Admin no permite editar la configuración de Recepcionista IA.',
        empty: 'Este cliente todavía no tiene configuración',
    },
} as const;

function writeErrorMessage(error: unknown, kind: ReceptionistConfigTarget['kind']): string {
    if (error instanceof ApiError && error.status === 403) {
        return COPY[kind].forbiddenWrite;
    }
    const detail = payloadOf(error)?.detail;
    return typeof detail === 'string' && detail ? detail : 'No pudimos guardar la configuración. Intentá nuevamente.';
}

// ── Cambios sin guardar ────────────────────────────────────────────────────

export const UNSAVED_CHANGES_MESSAGE = 'Tenés cambios sin guardar en la configuración del agente. ¿Salir igual?';

/** Avisa antes de cerrar/recargar y antes de seguir un link interno con cambios pendientes. */
function useUnsavedChangesGuard(active: boolean) {
    useEffect(() => {
        if (!active) return undefined;
        const onBeforeUnload = (event: BeforeUnloadEvent) => {
            event.preventDefault();
            event.returnValue = '';
        };
        const onClick = (event: MouseEvent) => {
            if (event.defaultPrevented || event.button !== 0) return;
            if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
            const anchor = (event.target as Element | null)?.closest?.('a[href]');
            if (!anchor || anchor.getAttribute('target') === '_blank') return;
            if (!window.confirm(UNSAVED_CHANGES_MESSAGE)) {
                event.preventDefault();
                event.stopPropagation();
            }
        };
        window.addEventListener('beforeunload', onBeforeUnload);
        document.addEventListener('click', onClick, true);
        return () => {
            window.removeEventListener('beforeunload', onBeforeUnload);
            document.removeEventListener('click', onClick, true);
        };
    }, [active]);
}

// ── Estilos (mismos que el resto de /app) ──────────────────────────────────

const CARD = 'space-y-4 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm';
const PRIMARY =
    'rounded-lg bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50';
const SECONDARY =
    'rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50';
const INPUT =
    'mt-1 w-full rounded-2xl border px-4 py-2 text-sm text-slate-900 focus:border-slate-900 focus:outline-none disabled:bg-slate-50 disabled:text-slate-500';

function inputClass(error?: string) {
    return `${INPUT} ${error ? 'border-rose-300' : 'border-slate-200'}`;
}

// ── Lectura compartida ─────────────────────────────────────────────────────

/**
 * Query de la configuración para un target. El formulario y quien lo monta
 * (p. ej. la tarjeta de Platform Admin, que se oculta ante 404
 * `client_not_found`) comparten la misma key: una sola lectura.
 */
export function useReceptionistConfig(target: ReceptionistConfigTarget) {
    const { kind, businessId } = target;
    const adapter = useMemo(
        () => receptionistConfigAdapter({ kind, businessId } as ReceptionistConfigTarget),
        [kind, businessId],
    );
    const query = useQuery({
        queryKey: adapter.key,
        queryFn: adapter.get,
        // Sin reintentos (403/404 son estados reales) ni recargas al volver a la
        // pestaña: el servidor solo se relee de forma explícita. Sin
        // `retryOnMount`: un segundo observador (el formulario dentro de la
        // tarjeta admin) no debe volver a pedir un error ya resuelto.
        retry: false,
        retryOnMount: false,
        refetchOnWindowFocus: false,
        staleTime: Infinity,
    });
    return { adapter, query };
}

/** 404 de dominio de Platform Admin: el cliente no tiene Recepcionista IA aplicable. */
/** PROD-09C3: estado de la atención automática según la configuración leída. */
export type AttentionState = 'enabled' | 'paused' | 'unknown';

export function attentionStateOf(config: ReceptionistConfig | null | undefined): AttentionState {
    const value = config?.automatic_attention_enabled;
    if (value === true) return 'enabled';
    if (value === false) return 'paused';
    return 'unknown';
}

export const ATTENTION_LABELS: Record<AttentionState, { label: string; className: string }> = {
    enabled: { label: 'Habilitada', className: 'bg-emerald-100 text-emerald-700' },
    paused: { label: 'Pausada', className: 'bg-amber-100 text-amber-800' },
    unknown: { label: 'Estado desconocido', className: 'bg-slate-100 text-slate-600' },
};

export function isClientWithoutReception(error: unknown): boolean {
    return error instanceof ApiError && error.status === 404 && errorCode(error) === 'client_not_found';
}

// ── Formulario ─────────────────────────────────────────────────────────────

type Props = {
    target: ReceptionistConfigTarget;
    /** Negocio sobre el que se edita, visible siempre. */
    businessName: string;
    canEdit: boolean;
};

/**
 * PROD-08B — Configuración individual de Recepcionista IA (contrato PROD-03B),
 * compartida por el comercio y Platform Admin vía `target`. Cada negocio monta
 * una instancia nueva (`key`): nunca hereda estado, cambios ni caché de otro.
 */
export function ReceptionistConfigForm(props: Props) {
    return <ReceptionistConfigFormInner key={`${props.target.kind}:${props.target.businessId}`} {...props} />;
}

type Pending = 'create' | 'save' | 'status' | null;
type Notice = { tone: 'success' | 'error'; text: string } | null;

function ReceptionistConfigFormInner({ target, businessName, canEdit }: Props) {
    const { adapter, query } = useReceptionistConfig(target);
    const queryClient = useQueryClient();
    const copy = COPY[target.kind];

    const [edits, setEdits] = useState<Partial<ReceptionistConfigContent>>({});
    const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
    const [notice, setNotice] = useState<Notice>(null);
    const [conflictVersion, setConflictVersion] = useState<number | null | undefined>(undefined);
    const [pending, setPending] = useState<Pending>(null);
    const [confirmDraft, setConfirmDraft] = useState(false);
    const [tab, setTab] = useState<ReceptionistTab>('identity');

    const config = query.data?.config ?? null;
    const draft = useMemo(() => (config ? { ...contentOf(config), ...edits } : null), [config, edits]);
    const changes = useMemo(() => (config && draft ? changedFields(config, draft) : {}), [config, draft]);
    const dirty = Object.keys(changes).length > 0;
    const inConflict = conflictVersion !== undefined;
    const locked = !canEdit || pending !== null;

    useUnsavedChangesGuard(dirty);

    // PROD-09C3: la query es compartida (p. ej. con el interruptor de atención
    // automática de Platform Admin). Si el CONTENIDO del servidor cambia
    // mientras hay cambios sin guardar y no es una escritura propia, se entra
    // en conflicto: nunca se adopta en silencio otra versión para guardar
    // encima. Un cambio solo de versión/atención automática no toca el
    // contenido sobre el que se calculan los cambios y no es conflicto.
    const contentKey = config ? JSON.stringify(contentOf(config)) : null;
    const baseContentKey = useRef(contentKey);
    useEffect(() => {
        if (contentKey === baseContentKey.current) return;
        const previous = baseContentKey.current;
        baseContentKey.current = contentKey;
        if (previous !== null && dirty && pending === null && !inConflict) {
            setConflictVersion(config?.version ?? null);
            setNotice(null);
        }
        // Solo reacciona a cambios del contenido del servidor.
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [contentKey]);

    const storeConfig = (response: ReceptionistConfigResponse) => {
        queryClient.setQueryData(adapter.key, response);
    };

    const update = <K extends ReceptionistConfigField>(field: K, value: ReceptionistConfigContent[K]) => {
        setEdits((previous) => ({ ...previous, [field]: value }));
        setFieldErrors((previous) => {
            if (!(field in previous)) return previous;
            const next = { ...previous };
            delete next[field];
            return next;
        });
        setNotice((previous) => (previous?.tone === 'success' ? null : previous));
    };

    const handleWriteError = async (error: unknown) => {
        const code = errorCode(error);
        if (code === 'version_conflict') {
            // Nunca se reintenta ni se fusiona: el usuario decide cuándo releer.
            const current = payloadOf(error)?.current_version;
            setConflictVersion(typeof current === 'number' ? current : null);
            setNotice(null);
            return;
        }
        if (code === 'validation_error') {
            setFieldErrors(fieldErrorsFrom(error));
            setNotice({ tone: 'error', text: 'Revisá los campos marcados. No se guardó ningún cambio.' });
            return;
        }
        if (code === 'receptionist_config_not_found') {
            setNotice({ tone: 'error', text: 'La configuración ya no existe. Actualizamos la pantalla.' });
            await query.refetch();
            return;
        }
        setNotice({ tone: 'error', text: writeErrorMessage(error, target.kind) });
    };

    const handleCreate = async () => {
        setPending('create');
        setNotice(null);
        try {
            storeConfig(await adapter.create());
        } catch (error) {
            if (errorCode(error) === 'receptionist_config_exists') {
                setNotice({ tone: 'error', text: 'El negocio ya tenía una configuración. Cargamos la actual.' });
                await query.refetch();
            } else {
                setNotice({ tone: 'error', text: writeErrorMessage(error, target.kind) });
            }
        } finally {
            setPending(null);
        }
    };

    const handleSave = async () => {
        if (!config || !dirty || inConflict) return;
        setPending('save');
        setNotice(null);
        try {
            storeConfig(await adapter.patch({ ...changes, expected_version: config.version }));
            setEdits({});
            setFieldErrors({});
            setNotice({ tone: 'success', text: 'Cambios guardados.' });
        } catch (error) {
            await handleWriteError(error);
        } finally {
            setPending(null);
        }
    };

    const handleStatus = async (status: ReceptionistConfigStatus) => {
        if (!config || dirty || inConflict) return;
        setConfirmDraft(false);
        setPending('status');
        setNotice(null);
        try {
            storeConfig(await adapter.patch({ status, expected_version: config.version }));
            setFieldErrors({});
            setNotice({
                tone: 'success',
                text: status === 'ready' ? 'Configuración marcada como lista.' : 'La configuración volvió a borrador.',
            });
        } catch (error) {
            await handleWriteError(error);
        } finally {
            setPending(null);
        }
    };

    const handleLoadCurrent = async () => {
        setEdits({});
        setFieldErrors({});
        setConflictVersion(undefined);
        setNotice(null);
        await query.refetch();
    };

    const businessLine = (
        <p className="text-sm text-slate-500">
            Negocio: <span className="font-medium text-slate-800">{businessName}</span>
        </p>
    );

    if (query.isLoading) {
        return (
            <section aria-busy="true" className={CARD}>
                {businessLine}
                <p className="text-sm text-slate-500">Cargando configuración…</p>
            </section>
        );
    }

    if (query.isError || !query.data) {
        const forbidden = query.error instanceof ApiError && query.error.status === 403;
        return (
            <section role="status" className={CARD}>
                {businessLine}
                <h2 className="text-sm font-semibold text-slate-800">
                    {forbidden ? 'Sin acceso a la configuración del agente' : 'No pudimos cargar la configuración'}
                </h2>
                <p className="text-sm text-slate-500">
                    {forbidden ? copy.forbiddenRead : 'Intentá nuevamente en unos minutos.'}
                </p>
                {!forbidden ? (
                    <button type="button" className={SECONDARY} onClick={() => query.refetch()}>
                        Reintentar
                    </button>
                ) : null}
            </section>
        );
    }

    if (!config || !draft) {
        return (
            <section className={CARD}>
                {businessLine}
                <h2 className="text-sm font-semibold text-slate-800">{copy.empty}</h2>
                <p className="text-sm text-slate-500">
                    Se crea vacía, como borrador. El agente no la usa hasta que la completes y la marques como lista.
                </p>
                {notice ? <NoticeLine notice={notice} /> : null}
                {canEdit ? (
                    <button type="button" className={PRIMARY} disabled={pending !== null} onClick={handleCreate}>
                        {pending === 'create' ? 'Creando…' : 'Crear borrador'}
                    </button>
                ) : null}
            </section>
        );
    }

    const errorEntries = Object.entries(fieldErrors);
    const tabErrors = (id: ReceptionistTab) => errorEntries.filter(([field]) => tabOfField(field) === id).length;
    const isReady = config.status === 'ready';
    const missing = config.missing_for_ready ?? [];

    return (
        <div className="space-y-4">
            <section aria-labelledby="receptionist-status-title" className={CARD}>
                <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="space-y-1">
                        {businessLine}
                        <div className="flex items-center gap-2">
                            <h2 id="receptionist-status-title" className="text-sm font-semibold text-slate-800">Estado</h2>
                            <span
                                className={
                                    isReady
                                        ? 'rounded-full bg-emerald-50 px-2.5 py-0.5 text-xs font-semibold text-emerald-700'
                                        : 'rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-semibold text-slate-600'
                                }
                            >
                                {isReady ? 'Configuración lista' : 'Borrador'}
                            </span>
                        </div>
                    </div>
                    {canEdit ? (
                        isReady ? (
                            <button
                                type="button"
                                className={SECONDARY}
                                disabled={locked || dirty || inConflict}
                                onClick={() => setConfirmDraft(true)}
                            >
                                Volver a borrador
                            </button>
                        ) : (
                            <button
                                type="button"
                                className={PRIMARY}
                                disabled={locked || dirty || inConflict || missing.length > 0}
                                onClick={() => handleStatus('ready')}
                            >
                                Marcar como lista
                            </button>
                        )
                    ) : null}
                </div>
                <p className="text-xs text-slate-500">
                    «Configuración lista» indica que el contenido está completo. No significa que el agente esté
                    conectado ni atendiendo por WhatsApp.
                </p>
                {target.kind === 'business' ? <AttentionLine config={config} /> : null}
                {!isReady && missing.length > 0 ? (
                    <p className="text-sm text-amber-800">
                        Para marcarla como lista falta: {missing.map((field) => FIELD_LABELS[field] ?? field).join(', ')}.
                    </p>
                ) : null}
                {canEdit && dirty ? (
                    <p className="text-xs text-slate-500">Guardá los cambios antes de cambiar el estado.</p>
                ) : null}
                {fieldErrors.status ? <p className="text-sm text-rose-600">{fieldErrors.status}</p> : null}
            </section>

            {inConflict ? (
                <Alert variant="destructive">
                    <AlertTitle>Otra persona guardó cambios en esta configuración</AlertTitle>
                    <AlertDescription>
                        <p>
                            Tus cambios siguen en pantalla y no se guardaron. Copiá lo que necesites y cargá la versión
                            actual{typeof conflictVersion === 'number' ? ` (versión ${conflictVersion})` : ''} para seguir
                            editando.
                        </p>
                        <button type="button" className={`${SECONDARY} mt-2`} onClick={handleLoadCurrent}>
                            Cargar la versión actual
                        </button>
                    </AlertDescription>
                </Alert>
            ) : null}

            {notice ? <NoticeLine notice={notice} /> : null}

            {errorEntries.length > 0 ? (
                <ul aria-label="Errores de validación" className="space-y-1 rounded-2xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">
                    {errorEntries.map(([field, message]) => {
                        const fieldTab = tabOfField(field);
                        return (
                            <li key={field}>
                                {fieldTab ? (
                                    <button type="button" className="text-left underline" onClick={() => setTab(fieldTab)}>
                                        {FIELD_LABELS[field] ?? field}: {message}
                                    </button>
                                ) : (
                                    <span>
                                        {FIELD_LABELS[field] ?? field}: {message}
                                    </span>
                                )}
                            </li>
                        );
                    })}
                </ul>
            ) : null}

            <section className={CARD}>
                <Tabs defaultValue="identity" value={tab} onValueChange={(value) => setTab(value as ReceptionistTab)}>
                    <TabsList className="max-w-full overflow-x-auto">
                        {TABS.map(({ id, label }) => {
                            const count = tabErrors(id);
                            return (
                                <TabsTrigger key={id} value={id}>
                                    {label}
                                    {count > 0 ? (
                                        <span className="ml-1.5 inline-flex h-2 w-2 rounded-full bg-rose-500">
                                            <span className="sr-only"> (con errores)</span>
                                        </span>
                                    ) : null}
                                </TabsTrigger>
                            );
                        })}
                    </TabsList>

                    <TabsContent value="identity" className="mt-4 space-y-4">
                        <div className="grid gap-4 sm:grid-cols-2">
                            <TextField field="assistant_name" value={draft.assistant_name} required disabled={locked} error={fieldErrors.assistant_name} onChange={update} />
                            <TextField field="business_category" value={draft.business_category} required disabled={locked} error={fieldErrors.business_category} onChange={update} />
                        </div>
                        <TextField field="business_description" value={draft.business_description} multiline required disabled={locked} error={fieldErrors.business_description} onChange={update} />
                        <TextField field="welcome_message" value={draft.welcome_message} multiline required disabled={locked} error={fieldErrors.welcome_message} onChange={update} />
                        <div className="grid gap-4 sm:grid-cols-2">
                            <label className="text-sm font-semibold text-slate-700">
                                {FIELD_LABELS.tone}
                                <select
                                    className={inputClass(fieldErrors.tone)}
                                    value={draft.tone}
                                    disabled={locked}
                                    onChange={(event) => update('tone', event.target.value as ReceptionistConfigContent['tone'])}
                                >
                                    <option value="warm">Cercano</option>
                                    <option value="professional">Profesional</option>
                                    <option value="formal">Formal</option>
                                </select>
                                <FieldError message={fieldErrors.tone} />
                            </label>
                            <label className="text-sm font-semibold text-slate-700">
                                {FIELD_LABELS.language}
                                <select
                                    className={inputClass(fieldErrors.language)}
                                    value={draft.language}
                                    disabled={locked}
                                    onChange={(event) => update('language', event.target.value as ReceptionistConfigContent['language'])}
                                >
                                    <option value="es-AR">Español (Argentina)</option>
                                    <option value="es">Español neutro</option>
                                </select>
                                <FieldError message={fieldErrors.language} />
                            </label>
                        </div>
                    </TabsContent>

                    <TabsContent value="services" className="mt-4 space-y-3">
                        <ServicesRows
                            items={draft.services}
                            disabled={locked}
                            error={fieldErrors.services}
                            onChange={(items) => update('services', items)}
                        />
                    </TabsContent>

                    <TabsContent value="faqs" className="mt-4 space-y-3">
                        <FaqRows items={draft.faqs} disabled={locked} error={fieldErrors.faqs} onChange={(items) => update('faqs', items)} />
                    </TabsContent>

                    <TabsContent value="instructions" className="mt-4 space-y-4">
                        <TextField field="custom_instructions" value={draft.custom_instructions} multiline disabled={locked} error={fieldErrors.custom_instructions} onChange={update} />
                        <TextField field="handoff_rules" value={draft.handoff_rules} multiline disabled={locked} error={fieldErrors.handoff_rules} onChange={update} />
                        <TextField field="operational_info" value={draft.operational_info} multiline disabled={locked} error={fieldErrors.operational_info} onChange={update} />
                        <TextField
                            field="business_hours"
                            value={draft.business_hours}
                            multiline
                            hint="Opcional. Si lo dejás vacío, el agente no informa horarios."
                            disabled={locked}
                            error={fieldErrors.business_hours}
                            onChange={update}
                        />
                        <TextField field="reference_info" value={draft.reference_info} multiline disabled={locked} error={fieldErrors.reference_info} onChange={update} />
                    </TabsContent>
                </Tabs>

                {canEdit ? (
                    <div className="flex flex-wrap items-center gap-2 border-t border-slate-100 pt-4">
                        <button type="button" className={PRIMARY} disabled={locked || !dirty || inConflict} onClick={handleSave}>
                            {pending === 'save' ? 'Guardando…' : 'Guardar cambios'}
                        </button>
                        <button
                            type="button"
                            className={SECONDARY}
                            disabled={locked || !dirty}
                            onClick={() => {
                                setEdits({});
                                setFieldErrors({});
                                setNotice(null);
                            }}
                        >
                            Descartar cambios
                        </button>
                        {dirty ? <span className="text-xs text-amber-700">Cambios sin guardar</span> : null}
                    </div>
                ) : (
                    <p className="text-xs text-slate-500">Solo lectura.</p>
                )}
            </section>

            <Modal
                open={confirmDraft}
                title="¿Volver a borrador?"
                eyebrow={null}
                onClose={() => setConfirmDraft(false)}
                footer={
                    <div className="flex justify-end gap-2">
                        <button type="button" className={SECONDARY} onClick={() => setConfirmDraft(false)}>
                            Cancelar
                        </button>
                        <button type="button" className={PRIMARY} onClick={() => handleStatus('draft')}>
                            Volver a borrador
                        </button>
                    </div>
                }
            >
                <p className="text-sm text-slate-600">
                    Volver a borrador también pausa la atención automática de este negocio: las consultas nuevas pasan
                    al equipo. Marcarla otra vez como lista no la reactiva;{' '}
                    {target.kind === 'platform_admin'
                        ? 'hay que volver a habilitarla en «Preparación del agente».'
                        : 'la reactiva el equipo de Mi Rubro.'}
                </p>
            </Modal>
        </div>
    );
}

// ── Piezas locales ─────────────────────────────────────────────────────────

/** PROD-09C3 — Comercio: estado de solo lectura de la atención automática. */
function AttentionLine({ config }: { config: ReceptionistConfig }) {
    const state = attentionStateOf(config);
    const badge = ATTENTION_LABELS[state];
    return (
        <div className="space-y-1 border-t border-slate-100 pt-3">
            <div className="flex items-center gap-2">
                <h3 className="text-sm font-semibold text-slate-800">Atención automática</h3>
                <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${badge.className}`}>{badge.label}</span>
            </div>
            <p className="text-xs text-slate-500">
                {state === 'unknown'
                    ? 'No pudimos verificar el estado de la atención automática.'
                    : 'La habilita o la pausa el equipo de Mi Rubro.'}{' '}
                Volver a borrador también la pausa; volver a marcarla como lista no la reactiva. Habilitada no
                significa que el agente esté conectado ni respondiendo.
            </p>
        </div>
    );
}

function NoticeLine({ notice }: { notice: NonNullable<Notice> }) {
    return (
        <p role={notice.tone === 'error' ? 'alert' : 'status'} className={notice.tone === 'error' ? 'text-sm text-rose-600' : 'text-sm text-emerald-700'}>
            {notice.text}
        </p>
    );
}

function FieldError({ message }: { message?: string }) {
    return message ? <span className="mt-1 block text-xs font-normal text-rose-600">{message}</span> : null;
}

function Counter({ length, max }: { length: number; max: number }) {
    return (
        <span className="text-xs font-normal text-slate-400">
            {length}/{max}
        </span>
    );
}

type TextFieldName = keyof typeof RECEPTIONIST_TEXT_LIMITS;

function TextField({
    field,
    value,
    multiline = false,
    required = false,
    hint,
    disabled,
    error,
    onChange,
}: {
    field: TextFieldName;
    value: string;
    multiline?: boolean;
    required?: boolean;
    hint?: string;
    disabled: boolean;
    error?: string;
    onChange: (field: TextFieldName, value: string) => void;
}) {
    const max = RECEPTIONIST_TEXT_LIMITS[field];
    const id = `receptionist-${field}`;
    const common = {
        id,
        value,
        maxLength: max,
        disabled,
        'aria-invalid': error ? true : undefined,
        className: inputClass(error),
    };
    return (
        <div className="text-sm font-semibold text-slate-700">
            <div className="flex items-baseline justify-between gap-2">
                <label htmlFor={id}>
                    {FIELD_LABELS[field]}
                    {required ? <span className="text-slate-400"> (requerido para «lista»)</span> : null}
                </label>
                <Counter length={value.length} max={max} />
            </div>
            {multiline ? (
                <textarea {...common} rows={field === 'business_hours' ? 3 : 4} onChange={(event) => onChange(field, event.target.value)} />
            ) : (
                <input {...common} type="text" onChange={(event) => onChange(field, event.target.value)} />
            )}
            {hint ? <span className="mt-1 block text-xs font-normal text-slate-500">{hint}</span> : null}
            <FieldError message={error} />
        </div>
    );
}

function ServicesRows({
    items,
    disabled,
    error,
    onChange,
}: {
    items: ReceptionistService[];
    disabled: boolean;
    error?: string;
    onChange: (items: ReceptionistService[]) => void;
}) {
    const limits = RECEPTIONIST_LIST_LIMITS.services;
    const set = (index: number, patch: Partial<ReceptionistService>) =>
        onChange(items.map((item, i) => (i === index ? { ...item, ...patch } : item)));
    return (
        <>
            <p className="text-sm text-slate-500">
                Lo que tu negocio ofrece. Se necesita al menos uno para marcar la configuración como lista. ({items.length}/
                {limits.maxItems})
            </p>
            {items.map((item, index) => (
                <fieldset key={index} className="space-y-2 rounded-xl border border-slate-100 p-3">
                    <legend className="sr-only">Servicio {index + 1}</legend>
                    <label className="block text-sm font-semibold text-slate-700">
                        Nombre del servicio {index + 1}
                        <input
                            type="text"
                            className={inputClass()}
                            value={item.name}
                            maxLength={limits.name}
                            disabled={disabled}
                            onChange={(event) => set(index, { name: event.target.value })}
                        />
                    </label>
                    <label className="block text-sm font-semibold text-slate-700">
                        Descripción del servicio {index + 1}
                        <textarea
                            className={inputClass()}
                            rows={2}
                            value={item.description ?? ''}
                            maxLength={limits.description}
                            disabled={disabled}
                            onChange={(event) => set(index, { description: event.target.value })}
                        />
                    </label>
                    <button
                        type="button"
                        className="text-xs font-medium text-rose-600 hover:underline disabled:opacity-50"
                        disabled={disabled}
                        onClick={() => onChange(items.filter((_, i) => i !== index))}
                    >
                        Quitar servicio {index + 1}
                    </button>
                </fieldset>
            ))}
            <FieldError message={error} />
            <button
                type="button"
                className={SECONDARY}
                disabled={disabled || items.length >= limits.maxItems}
                onClick={() => onChange([...items, { name: '', description: '' }])}
            >
                Agregar servicio
            </button>
        </>
    );
}

function FaqRows({
    items,
    disabled,
    error,
    onChange,
}: {
    items: ReceptionistFaq[];
    disabled: boolean;
    error?: string;
    onChange: (items: ReceptionistFaq[]) => void;
}) {
    const limits = RECEPTIONIST_LIST_LIMITS.faqs;
    const set = (index: number, patch: Partial<ReceptionistFaq>) =>
        onChange(items.map((item, i) => (i === index ? { ...item, ...patch } : item)));
    return (
        <>
            <p className="text-sm text-slate-500">
                Preguntas que tus clientes hacen seguido, con su respuesta. ({items.length}/{limits.maxItems})
            </p>
            {items.map((item, index) => (
                <fieldset key={index} className="space-y-2 rounded-xl border border-slate-100 p-3">
                    <legend className="sr-only">Pregunta {index + 1}</legend>
                    <label className="block text-sm font-semibold text-slate-700">
                        Pregunta {index + 1}
                        <input
                            type="text"
                            className={inputClass()}
                            value={item.question}
                            maxLength={limits.question}
                            disabled={disabled}
                            onChange={(event) => set(index, { question: event.target.value })}
                        />
                    </label>
                    <label className="block text-sm font-semibold text-slate-700">
                        Respuesta {index + 1}
                        <textarea
                            className={inputClass()}
                            rows={2}
                            value={item.answer}
                            maxLength={limits.answer}
                            disabled={disabled}
                            onChange={(event) => set(index, { answer: event.target.value })}
                        />
                    </label>
                    <button
                        type="button"
                        className="text-xs font-medium text-rose-600 hover:underline disabled:opacity-50"
                        disabled={disabled}
                        onClick={() => onChange(items.filter((_, i) => i !== index))}
                    >
                        Quitar pregunta {index + 1}
                    </button>
                </fieldset>
            ))}
            <FieldError message={error} />
            <button
                type="button"
                className={SECONDARY}
                disabled={disabled || items.length >= limits.maxItems}
                onClick={() => onChange([...items, { question: '', answer: '' }])}
            >
                Agregar pregunta
            </button>
        </>
    );
}
