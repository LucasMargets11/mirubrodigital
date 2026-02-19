# Generated migration file

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('business', '0010_alter_businessbillingprofile_options_and_more'),
    ]

    operations = [
        # 1. Agregar nuevos choices al plan
        migrations.AlterField(
            model_name='subscription',
            name='plan',
            field=models.CharField(
                max_length=32,
                choices=[
                    ('start', 'Start'),
                    ('pro', 'Pro'),
                    ('business', 'Business'),
                    ('enterprise', 'Enterprise'),
                    ('menu_qr', 'Menú QR'),
                    ('starter', 'Starter (Legacy)'),
                    ('plus', 'Plus (Legacy)'),
                ],
                default='start'
            ),
        ),
        
        # 2. Actualizar help text de max_branches y max_seats
        migrations.AlterField(
            model_name='subscription',
            name='max_branches',
            field=models.PositiveIntegerField(
                default=1,
                help_text='Sucursales incluidas en el plan base'
            ),
        ),
        migrations.AlterField(
            model_name='subscription',
            name='max_seats',
            field=models.PositiveIntegerField(
                default=2,
                help_text='Usuarios incluidos en el plan base'
            ),
        ),
        
        # 3. Crear tabla SubscriptionAddon
        migrations.CreateModel(
            name='SubscriptionAddon',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(
                    max_length=64,
                    choices=[
                        ('extra_branch', 'Sucursal Extra'),
                        ('extra_seat', 'Usuario Extra'),
                        ('invoices_module', 'Módulo de Facturación'),
                    ]
                )),
                ('quantity', models.PositiveIntegerField(default=1, help_text='Cantidad de unidades (ej: 2 sucursales extra)')),
                ('is_active', models.BooleanField(default=True)),
                ('activated_at', models.DateTimeField(auto_now_add=True)),
                ('deactivated_at', models.DateTimeField(null=True, blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('subscription', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='addons',
                    to='business.subscription'
                )),
            ],
            options={
                'verbose_name': 'Subscription Add-on',
                'verbose_name_plural': 'Subscription Add-ons',
                'unique_together': {('subscription', 'code')},
            },
        ),
    ]
