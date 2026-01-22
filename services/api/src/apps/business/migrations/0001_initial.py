from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

  initial = True

  dependencies = []

  operations = [
    migrations.CreateModel(
      name='Business',
      fields=[
        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
        ('name', models.CharField(max_length=255)),
        ('created_at', models.DateTimeField(auto_now_add=True)),
      ],
    ),
    migrations.CreateModel(
      name='Subscription',
      fields=[
        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
        ('plan', models.CharField(choices=[('starter', 'Starter'), ('pro', 'Pro')], default='starter', max_length=32)),
        ('status', models.CharField(choices=[('active', 'Active'), ('past_due', 'Past due'), ('canceled', 'Canceled')], default='active', max_length=32)),
        ('renews_at', models.DateTimeField(blank=True, null=True)),
        ('created_at', models.DateTimeField(auto_now_add=True)),
        ('updated_at', models.DateTimeField(auto_now=True)),
        ('business', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='subscription', to='business.business')),
      ],
    ),
  ]
