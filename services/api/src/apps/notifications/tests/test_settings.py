from django.conf import settings
from django.test import SimpleTestCase


class EmailSettingsTest(SimpleTestCase):
    def test_email_provider_setting_exists(self):
        self.assertTrue(hasattr(settings, "EMAIL_PROVIDER"))
        self.assertIn(
            settings.EMAIL_PROVIDER,
            ("django", "amazon_ses"),
            msg="EMAIL_PROVIDER must be 'django' or 'amazon_ses'",
        )

    def test_email_provider_default_is_django(self):
        # When no env var is set the default is 'django'
        self.assertEqual(settings.EMAIL_PROVIDER, "django")

    def test_aws_ses_region_setting_exists(self):
        self.assertTrue(hasattr(settings, "AWS_SES_REGION"))
        self.assertIsInstance(settings.AWS_SES_REGION, str)
        self.assertNotEqual(settings.AWS_SES_REGION, "")

    def test_aws_ses_region_default(self):
        self.assertEqual(settings.AWS_SES_REGION, "sa-east-1")

    def test_aws_ses_configuration_set_setting_exists(self):
        self.assertTrue(hasattr(settings, "AWS_SES_CONFIGURATION_SET"))
        self.assertIsInstance(settings.AWS_SES_CONFIGURATION_SET, str)

    def test_email_transactional_enabled_default_true(self):
        self.assertTrue(hasattr(settings, "EMAIL_TRANSACTIONAL_ENABLED"))
        self.assertIs(settings.EMAIL_TRANSACTIONAL_ENABLED, True)

    def test_email_marketing_enabled_default_false(self):
        self.assertTrue(hasattr(settings, "EMAIL_MARKETING_ENABLED"))
        self.assertIs(settings.EMAIL_MARKETING_ENABLED, False)

    def test_default_from_email_uses_mirubro_domain(self):
        self.assertIn("mirubro.com", settings.DEFAULT_FROM_EMAIL)
        self.assertNotIn("no-reply@mirubro.com", settings.DEFAULT_FROM_EMAIL)

    def test_support_email_setting_exists(self):
        self.assertTrue(hasattr(settings, "SUPPORT_EMAIL"))
        self.assertIsInstance(settings.SUPPORT_EMAIL, str)
        self.assertIn("@", settings.SUPPORT_EMAIL)

    def test_billing_email_setting_exists(self):
        self.assertTrue(hasattr(settings, "BILLING_EMAIL"))
        self.assertIsInstance(settings.BILLING_EMAIL, str)
        self.assertIn("@", settings.BILLING_EMAIL)

    def test_server_email_setting_exists(self):
        self.assertTrue(hasattr(settings, "SERVER_EMAIL"))
        self.assertIsInstance(settings.SERVER_EMAIL, str)

    def test_legacy_email_backend_preserved(self):
        self.assertTrue(hasattr(settings, "EMAIL_BACKEND"))

    def test_legacy_email_host_preserved(self):
        self.assertTrue(hasattr(settings, "EMAIL_HOST"))

    def test_legacy_email_port_preserved(self):
        self.assertTrue(hasattr(settings, "EMAIL_PORT"))

    def test_legacy_email_use_tls_preserved(self):
        self.assertTrue(hasattr(settings, "EMAIL_USE_TLS"))

    def test_legacy_email_host_user_preserved(self):
        self.assertTrue(hasattr(settings, "EMAIL_HOST_USER"))

    def test_legacy_email_host_password_preserved(self):
        self.assertTrue(hasattr(settings, "EMAIL_HOST_PASSWORD"))
