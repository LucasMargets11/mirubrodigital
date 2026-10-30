from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('billing', '0023_webhookdelivery_retry_lifecycle'),
    ]

    operations = [
        migrations.AddField(
            model_name='subscriptionv2',
            name='usage_tier',
            field=models.CharField(
                blank=True, null=True, max_length=16,
                choices=[('ai_300', 'IA 300'), ('ai_1500', 'IA 1500'),
                         ('ai_3000', 'IA 3000'), ('custom', 'Custom')],
            ),
        ),
        migrations.AddField(
            model_name='pendingsubscriptionchange',
            name='subscription_v2',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name='pending_changes', to='billing.subscriptionv2',
            ),
        ),
        migrations.AddField(
            model_name='pendingsubscriptionchange',
            name='target_usage_tier',
            field=models.CharField(
                blank=True, null=True, max_length=16,
                choices=[('ai_300', 'IA 300'), ('ai_1500', 'IA 1500'),
                         ('ai_3000', 'IA 3000'), ('custom', 'Custom')],
            ),
        ),
        migrations.AlterField(
            model_name='pendingsubscriptionchange',
            name='config_snapshot',
            field=models.JSONField(
                default=dict,
                help_text='Legacy configuration or Turnos {addons: {code: 0|1}, quantities: {code: integer}}',
            ),
        ),
        migrations.AlterField(
            model_name='pendingsubscriptionchange',
            name='total_amount',
            field=models.IntegerField(
                blank=True, null=True, help_text='Total amount in ARS pesos (integer)',
            ),
        ),
    ]
