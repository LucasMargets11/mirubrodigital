import type { GenerateQrPosterPayload } from './types';

/**
 * Payload del diseño guardado — igual que GenerateQrPosterPayload pero sin File.
 * El backend almacena la imagen por separado; frontend recibe la URL.
 */
export type QrPosterDesignPayload = Omit<GenerateQrPosterPayload, 'background_image'>;

export interface QrPosterDesign {
    id: string;
    name: string;
    payload: QrPosterDesignPayload;
    background_image_url?: string | null;
    created_at: string;
    updated_at: string;
}

export interface QrPosterDesignListResponse {
    count: number;
    limit: number;
    results: QrPosterDesign[];
}

export interface SaveDesignInput {
    name: string;
    payload: QrPosterDesignPayload;
    background_image?: File | null;
}

export interface UpdateDesignInput {
    name?: string;
    payload?: QrPosterDesignPayload;
    background_image?: File | null;
}
