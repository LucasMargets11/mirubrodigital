"""Configuración de la Recepcionista IA vista por su agente (PROD-03A).

La relación agente ↔ negocio tiene una sola fuente: el `AgentChannel` activo.
Por eso la configuración se resuelve con la MISMA regla del receiver
(`resolve_channel`): canal activo del `phone_number_id`, de esta instancia,
negocio operativo y `business_id` coincidente. Una instancia nunca obtiene la
configuración de un negocio que no atiende, aunque conozca su id.

Solo lectura y sin endpoint todavía (PROD-03B). No concede capacidades: la
agenda, el consumo IA y los permisos se siguen resolviendo por su cuenta.
"""
from __future__ import annotations

from ..models import AgentInstance, ReceptionistConfig
from .receiver import resolve_channel


def receptionist_config_for_agent(
    agent_instance: AgentInstance, *, phone_number_id: str, business_id: int,
) -> ReceptionistConfig | None:
    """Configuración del negocio atendido por este canal, o `None` si no hay.

    Errores de relación (canal ajeno/inactivo, negocio inactivo o distinto)
    son los del receiver: `channel_disabled`, `business_inactive`,
    `business_mismatch`.
    """
    channel = resolve_channel(agent_instance, {'phone_number_id': phone_number_id, 'business_id': business_id})
    return ReceptionistConfig.objects.filter(business_id=channel.business_id).first()
