from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('billing', '0024_appointments_commercial_v2'),
        ('business', '0027_alter_subscription_plan'),
    ]

    operations = [
        migrations.AlterField(
            model_name='subscriptionaddon',
            name='subscription',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.CASCADE,
                related_name='addons', to='business.subscription',
            ),
        ),
        migrations.AddField(
            model_name='subscriptionaddon',
            name='subscription_v2',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.CASCADE,
                related_name='addons', to='billing.subscriptionv2',
            ),
        ),
        migrations.AlterField(
            model_name='subscriptionaddon',
            name='code',
            field=models.CharField(
                max_length=64,
                choices=[
                    ('extra_branch', 'Sucursal Extra'), ('extra_seat', 'Usuario Extra'),
                    ('invoices_module', 'Módulo de Facturación'),
                    ('menu_qr_addon_reviews', 'Módulo Reseñas (Menú QR)'),
                    ('menu_qr_addon_tips', 'Módulo Propina (Menú QR)'),
                    ('appointments_automations', 'Automatizaciones Turnos'),
                    ('appointments_extra_professional', 'Profesional adicional Turnos'),
                ],
            ),
        ),
        migrations.AddConstraint(
            model_name='subscriptionaddon',
            constraint=models.CheckConstraint(
                check=(
                    models.Q(subscription__isnull=False, subscription_v2__isnull=True)
                    | models.Q(subscription__isnull=True, subscription_v2__isnull=False)
                ),
                name='subscriptionaddon_owner_xor',
            ),
        ),
        migrations.AddConstraint(
            model_name='subscriptionaddon',
            constraint=models.UniqueConstraint(
                fields=('subscription_v2', 'code'),
                condition=models.Q(subscription_v2__isnull=False),
                name='subscriptionaddon_v2_code_unique',
            ),
        ),
        migrations.AddConstraint(
            model_name='subscriptionaddon',
            constraint=models.CheckConstraint(
                check=~models.Q(code='appointments_automations') | models.Q(quantity__lte=1),
                name='subscriptionaddon_automations_qty',
            ),
        ),
    ]
