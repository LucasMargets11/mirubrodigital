from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

  initial = True

  dependencies = [
    migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ('business', '0001_initial'),
  ]

  operations = [
    migrations.CreateModel(
      name='Membership',
      fields=[
        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
        ('role', models.CharField(choices=[('owner', 'Owner'), ('admin', 'Admin'), ('analyst', 'Analyst')], default='owner', max_length=24)),
        ('created_at', models.DateTimeField(auto_now_add=True)),
        ('business', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='memberships', to='business.business')),
        ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='memberships', to=settings.AUTH_USER_MODEL)),
      ],
      options={
        'unique_together': {('user', 'business')},
      },
    ),
  ]
