from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('business', '0022_alter_businessbranding_logo_horizontal_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='BusinessOnboardingProgress',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('product_type', models.CharField(
                    choices=[('gestion', 'Gestión Comercial'), ('menu_qr', 'Menú QR'), ('qr_reviews', 'QR de Reseñas')],
                    default='gestion',
                    max_length=32,
                )),
                ('version', models.CharField(default='v1', max_length=8)),
                ('current_step', models.CharField(blank=True, default='', max_length=64)),
                ('skipped_steps', models.JSONField(default=list)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('dismissed_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('business', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='onboarding_progress',
                    to='business.business',
                )),
            ],
            options={
                'verbose_name': 'Business Onboarding Progress',
                'verbose_name_plural': 'Business Onboarding Progress',
            },
        ),
        migrations.AddConstraint(
            model_name='businessonboardingprogress',
            constraint=models.UniqueConstraint(
                fields=('business', 'product_type', 'version'),
                name='uq_onboarding_progress',
            ),
        ),
        migrations.AddIndex(
            model_name='businessonboardingprogress',
            index=models.Index(fields=['business', 'product_type'], name='onboarding_biz_type_idx'),
        ),
    ]
