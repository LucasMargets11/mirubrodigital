from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('business', '0006_subscription_service'),
        ('menu', '0003_publicmenuconfig'),
    ]

    operations = [
        migrations.CreateModel(
            name='MenuBrandingSettings',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('display_name', models.CharField(max_length=140)),
                ('logo_image', models.ImageField(blank=True, null=True, upload_to='menu/branding/logos/')),
                ('palette_primary', models.CharField(default='#4C1D95', max_length=7)),
                ('palette_secondary', models.CharField(default='#F97316', max_length=7)),
                ('palette_background', models.CharField(default='#0F172A', max_length=7)),
                ('palette_text', models.CharField(default='#F8FAFC', max_length=7)),
                ('font_heading', models.CharField(default='playfair_display', max_length=64)),
                ('font_body', models.CharField(default='inter', max_length=64)),
                ('font_scale_heading', models.DecimalField(decimal_places=2, default=1.25, max_digits=4)),
                ('font_scale_body', models.DecimalField(decimal_places=2, default=1.0, max_digits=4)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('business', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='menu_branding', to='business.business')),
            ],
        ),
    ]
