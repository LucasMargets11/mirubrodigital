"use client";

import { createContext, useContext, type ReactNode } from 'react';

import { TURNOS_LEADS_CONTEXT, type LeadsRouteContext } from './leads-routes';

/** PROD-02G2: contexto de producto del CRM de Leads (ver `leads-routes.ts`). Default: Turnos. */
const LeadsContext = createContext<LeadsRouteContext>(TURNOS_LEADS_CONTEXT);

export function LeadsContextProvider({ value, children }: { value: LeadsRouteContext; children: ReactNode }) {
    return <LeadsContext.Provider value={value}>{children}</LeadsContext.Provider>;
}

export function useLeadsContext(): LeadsRouteContext {
    return useContext(LeadsContext);
}
