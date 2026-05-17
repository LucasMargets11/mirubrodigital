import { useCallback, useEffect, useReducer } from 'react';

import {
    createQrPosterDesign,
    deleteQrPosterDesign,
    listQrPosterDesigns,
    updateQrPosterDesign,
} from './designs-api';
import type { QrPosterDesign, QrPosterDesignListResponse, SaveDesignInput, UpdateDesignInput } from './designs-types';

// ── State ─────────────────────────────────────────────────────────────────────

interface DesignsState {
    designs: QrPosterDesign[];
    limit: number;
    loading: boolean;
    saving: boolean;
    error: string | null;
}

type Action =
    | { type: 'FETCH_START' }
    | { type: 'FETCH_OK'; data: QrPosterDesignListResponse }
    | { type: 'FETCH_ERR'; message: string }
    | { type: 'SAVE_START' }
    | { type: 'SAVE_OK'; design: QrPosterDesign; mode: 'create' | 'update' }
    | { type: 'SAVE_ERR'; message: string }
    | { type: 'DELETE_OK'; id: string }
    | { type: 'CLEAR_ERROR' };

function reducer(state: DesignsState, action: Action): DesignsState {
    switch (action.type) {
        case 'FETCH_START':
            return { ...state, loading: true, error: null };
        case 'FETCH_OK':
            return {
                ...state,
                loading: false,
                designs: action.data.results,
                limit: action.data.limit,
            };
        case 'FETCH_ERR':
            return { ...state, loading: false, error: action.message };
        case 'SAVE_START':
            return { ...state, saving: true, error: null };
        case 'SAVE_OK': {
            const designs =
                action.mode === 'create'
                    ? [action.design, ...state.designs]
                    : state.designs.map((d) => (d.id === action.design.id ? action.design : d));
            return { ...state, saving: false, designs };
        }
        case 'SAVE_ERR':
            return { ...state, saving: false, error: action.message };
        case 'DELETE_OK':
            return {
                ...state,
                designs: state.designs.filter((d) => d.id !== action.id),
            };
        case 'CLEAR_ERROR':
            return { ...state, error: null };
        default:
            return state;
    }
}

const INITIAL: DesignsState = {
    designs: [],
    limit: 5,
    loading: true,
    saving: false,
    error: null,
};

// ── Hook ──────────────────────────────────────────────────────────────────────

export function useQrPosterDesigns() {
    const [state, dispatch] = useReducer(reducer, INITIAL);

    const load = useCallback(async () => {
        dispatch({ type: 'FETCH_START' });
        try {
            const data = await listQrPosterDesigns();
            dispatch({ type: 'FETCH_OK', data });
        } catch (err) {
            dispatch({
                type: 'FETCH_ERR',
                message: err instanceof Error ? err.message : 'No se pudo cargar los diseños.',
            });
        }
    }, []);

    useEffect(() => {
        void load();
    }, [load]);

    const saveDesign = useCallback(
        async (input: SaveDesignInput): Promise<QrPosterDesign | null> => {
            dispatch({ type: 'SAVE_START' });
            try {
                const design = await createQrPosterDesign(input);
                dispatch({ type: 'SAVE_OK', design, mode: 'create' });
                return design;
            } catch (err) {
                const errObj = err as Error & { code?: string };
                const message =
                    errObj.code === 'design_limit_reached'
                        ? 'Podés guardar hasta 5 diseños.'
                        : (errObj.message ?? 'No se pudo guardar el diseño.');
                dispatch({ type: 'SAVE_ERR', message });
                return null;
            }
        },
        [],
    );

    const updateDesign = useCallback(
        async (id: string, input: UpdateDesignInput): Promise<QrPosterDesign | null> => {
            dispatch({ type: 'SAVE_START' });
            try {
                const design = await updateQrPosterDesign(id, input);
                dispatch({ type: 'SAVE_OK', design, mode: 'update' });
                return design;
            } catch (err) {
                dispatch({
                    type: 'SAVE_ERR',
                    message: err instanceof Error ? err.message : 'No se pudo actualizar el diseño.',
                });
                return null;
            }
        },
        [],
    );

    const removeDesign = useCallback(async (id: string): Promise<boolean> => {
        try {
            await deleteQrPosterDesign(id);
            dispatch({ type: 'DELETE_OK', id });
            return true;
        } catch (err) {
            dispatch({
                type: 'SAVE_ERR',
                message: err instanceof Error ? err.message : 'No se pudo eliminar el diseño.',
            });
            return false;
        }
    }, []);

    const clearError = useCallback(() => dispatch({ type: 'CLEAR_ERROR' }), []);

    return {
        designs: state.designs,
        limit: state.limit,
        loading: state.loading,
        saving: state.saving,
        error: state.error,
        saveDesign,
        updateDesign,
        removeDesign,
        clearError,
        reload: load,
    };
}
