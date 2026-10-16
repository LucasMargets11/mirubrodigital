"""Django admin de apps.leads: el ciphertext nunca se muestra ni se edita (AGENT 02A)."""
from __future__ import annotations

from django.contrib import admin
from django.test import RequestFactory, SimpleTestCase

from apps.leads.models import AgentChannel, AgentCredential, AgentInstance, Lead


class LeadsAdminTests(SimpleTestCase):
    def test_models_registered(self):
        for model in (AgentInstance, AgentCredential, AgentChannel, Lead):
            self.assertTrue(admin.site.is_registered(model), model.__name__)

    def test_credential_admin_hides_secret_and_is_read_only(self):
        model_admin = admin.site._registry[AgentCredential]
        request = RequestFactory().get('/')
        self.assertNotIn('encrypted_secret', model_admin.get_fields(request))
        self.assertNotIn('encrypted_secret', model_admin.list_display)
        self.assertNotIn('encrypted_secret', model_admin.search_fields)
        self.assertFalse(model_admin.has_add_permission(request))
        self.assertFalse(model_admin.has_change_permission(request))

    def test_instance_external_id_read_only_on_change(self):
        model_admin = admin.site._registry[AgentInstance]
        request = RequestFactory().get('/')
        self.assertIn('external_id', model_admin.get_readonly_fields(request, AgentInstance(external_id='abc')))
        self.assertNotIn('external_id', model_admin.get_readonly_fields(request, None))
