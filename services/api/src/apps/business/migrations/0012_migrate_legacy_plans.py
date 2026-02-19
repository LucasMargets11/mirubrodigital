# Migration para migrar planes legacy a nuevos planes

from django.db import migrations


def migrate_legacy_plans(apps, schema_editor):
    """
    Migra los planes legacy a los nuevos:
    - STARTER -> START
    - PRO -> PRO (sin cambios en nombre)
    - PLUS -> BUSINESS
    """
    Subscription = apps.get_model('business', 'Subscription')
    
    # Mapeo de planes legacy a nuevos
    plan_mapping = {
        'starter': 'start',
        'plus': 'business',
        # 'pro' permanece igual
    }
    
    for old_plan, new_plan in plan_mapping.items():
        subscriptions = Subscription.objects.filter(plan=old_plan)
        count = subscriptions.count()
        if count > 0:
            subscriptions.update(plan=new_plan)
            print(f"Migrated {count} subscriptions from '{old_plan}' to '{new_plan}'")
    
    # Ajustar límites por defecto según el plan
    # START: max_branches=1, max_seats=2
    Subscription.objects.filter(plan='start').update(
        max_branches=1,
        max_seats=2
    )
    
    # PRO: max_branches=1, max_seats=10
    Subscription.objects.filter(plan='pro').update(
        max_branches=1,
        max_seats=10
    )
    
    # BUSINESS: max_branches=5, max_seats=20
    Subscription.objects.filter(plan='business').update(
        max_branches=5,
        max_seats=20
    )
    
    # ENTERPRISE: max_branches=999, max_seats=100
    Subscription.objects.filter(plan='enterprise').update(
        max_branches=999,
        max_seats=100
    )
    
    print("Plan migration completed successfully")


def reverse_migration(apps, schema_editor):
    """
    Reversión: volver los planes nuevos a legacy
    """
    Subscription = apps.get_model('business', 'Subscription')
    
    reverse_mapping = {
        'start': 'starter',
        'business': 'plus',
    }
    
    for new_plan, old_plan in reverse_mapping.items():
        subscriptions = Subscription.objects.filter(plan=new_plan)
        subscriptions.update(plan=old_plan)


class Migration(migrations.Migration):

    dependencies = [
        ('business', '0011_subscription_plans_addons'),
    ]

    operations = [
        migrations.RunPython(migrate_legacy_plans, reverse_migration),
    ]
