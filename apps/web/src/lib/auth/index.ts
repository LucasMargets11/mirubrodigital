import { serverApiFetch } from '@/lib/api/server';

import type { Session } from './types';

export async function getSession(): Promise<Session | null> {
  try {
    return await serverApiFetch<Session>('/api/v1/auth/me/');
  } catch (error) {
    return null;
  }
}

export type { Session };
