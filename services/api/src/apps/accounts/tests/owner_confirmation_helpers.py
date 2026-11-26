"""PROD-02F4 test helpers: explicitly confirm reusing an existing owner account."""
from apps.accounts.admin_client_provisioning_service import ExistingOwnerRequiresConfirmationError

CONFIRMATION_CODE = 'existing_owner_requires_confirmation'


def call_confirming_owner(provision, **kwargs):
    """Service level: answer the confirmation prompt with its own bound token."""
    try:
        return provision(**kwargs)
    except ExistingOwnerRequiresConfirmationError as exc:
        return provision(
            **kwargs, attach_existing_owner=True, owner_confirmation_token=exc.confirmation_token,
        )


def post_confirming_owner(client, url, payload):
    """HTTP level: the admin confirms the account the 409 prompt identified."""
    response = client.post(url, payload, format='json')
    if response.status_code == 409 and response.data.get('code') == CONFIRMATION_CODE:
        response = client.post(url, {
            **payload,
            'attach_existing_owner': True,
            'owner_confirmation_token': response.data['confirmation']['token'],
        }, format='json')
    return response
