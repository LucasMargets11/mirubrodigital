# Generated migration for BusinessBillingProfile and BusinessBranding models

from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('business', '0007_alter_business_default_service_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='BusinessBillingProfile',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('legal_name', models.CharField(blank=True, help_text='Razón social completa', max_length=255)),
                ('tax_id_type', models.CharField(
                    blank=True,
                    choices=[
                        ('CUIT', 'CUIT'),
                        ('CUIL', 'CUIL'),
                        ('CDI', 'CDI'),
                        ('DNI', 'DNI'),
                        ('passport', 'Pasaporte'),
                    ],
                    help_text='Tipo de identificación fiscal',
                    max_length=20,
                )),
                ('tax_id', models.CharField(blank=True, help_text='Número de identificación fiscal (CUIT/CUIL/etc.)', max_length=50)),
                ('vat_condition', models.CharField(
                    blank=True,
                    choices=[
                        ('RI', 'Responsable Inscripto'),
                        ('M', 'Monotributista'),
                        ('E', 'Exento'),
                        ('NI', 'No Inscripto'),
                        ('CF', 'Consumidor Final'),
                    ],
                    help_text='Condición ante el IVA',
                    max_length=20,
                )),
                ('legal_address', models.TextField(blank=True, help_text='Domicilio legal/fiscal completo')),
                ('commercial_address', models.TextField(blank=True, help_text='Domicilio comercial si difiere del legal')),
                ('city', models.CharField(blank=True, max_length=100)),
                ('state_province', models.CharField(blank=True, max_length=100)),
                ('postal_code', models.CharField(blank=True, max_length=20)),
                ('country', models.CharField(default='Argentina', max_length=100)),
                ('phone', models.CharField(blank=True, max_length=50)),
                ('email', models.EmailField(blank=True, max_length=254)),
                ('website', models.URLField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('business', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='billing_profile',
                    to='business.business'
                )),
            ],
            options={
                'db_table': 'business_billing_profile',
            },
        ),
        migrations.CreateModel(
            name='BusinessBranding',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('logo_horizontal', models.ImageField(blank=True, help_text='Logo horizontal para facturas y PDFs', null=True, upload_to='business/%Y/%m/')),
                ('logo_square', models.ImageField(blank=True, help_text='Logo cuadrado para menú QR y apps', null=True, upload_to='business/%Y/%m/')),
                ('accent_color', models.CharField(
                    blank=True,
                    default='#000000',
                    help_text='Color corporativo en formato hex (#RRGGBB)',
                    max_length=7,
                )),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('business', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='branding',
                    to='business.business'
                )),
            ],
            options={
                'db_table': 'business_branding',
            },
        ),
    ]
