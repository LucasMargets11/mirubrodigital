from django.conf import settings
from django.db import models
from django.utils import timezone
from apps.business.models import Business

class Plan(models.Model):
    code = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=128)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    interval = models.CharField(max_length=32)  # monthly, yearly
    features_json = models.JSONField(default=dict)
    mp_preapproval_plan_id = models.CharField(max_length=128, null=True, blank=True)

    def __str__(self):
        return f"{self.name} ({self.code})"

class SubscriptionIntent(models.Model):
    STATUS_CHOICES = [
        ('created', 'Created'),
        ('redirected', 'Redirected'),
        ('confirmed', 'Confirmed'),
        ('failed', 'Failed'),
    ]
    tenant = models.ForeignKey(Business, on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    plan_code = models.CharField(max_length=64)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default='created')
    mp_init_point = models.URLField(max_length=500, null=True, blank=True)
    mp_preapproval_id = models.CharField(max_length=128, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)

class PaymentEvent(models.Model):
    provider = models.CharField(max_length=32)
    event_id = models.CharField(max_length=128, unique=True)
    resource_id = models.CharField(max_length=128)
    payload_json = models.JSONField()
    processed_at = models.DateTimeField(auto_now_add=True)


class Module(models.Model):
    VERTICAL_CHOICES = [
        ('commercial', 'Commercial'),
        ('restaurant', 'Restaurant'),
        ('both', 'Both'),
        ('menu_qr', 'Menu QR'),
    ]
    CATEGORY_CHOICES = [
        ('operation', 'Operation'),
        ('admin', 'Admin'),
        ('insights', 'Insights'),
    ]

    code = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=128)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=32, choices=CATEGORY_CHOICES)
    vertical = models.CharField(max_length=32, choices=VERTICAL_CHOICES)
    
    price_monthly = models.IntegerField(help_text="Price in cents")
    price_yearly = models.IntegerField(help_text="Price in cents", null=True, blank=True)
    
    is_core = models.BooleanField(default=False)
    requires = models.ManyToManyField('self', blank=True, symmetrical=False)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} ({self.code})"

class Bundle(models.Model):
    VERTICAL_CHOICES = [
        ('commercial', 'Commercial'),
        ('restaurant', 'Restaurant'),
        ('menu_qr', 'Menu QR'),
    ]
    PRICING_MODE_CHOICES = [
        ('fixed_price', 'Fixed Price'),
        ('discount_percent', 'Discount Percent'),
    ]

    code = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=128)
    description = models.TextField(blank=True)
    vertical = models.CharField(max_length=32, choices=VERTICAL_CHOICES)
    badge = models.CharField(max_length=64, blank=True, null=True)
    
    modules = models.ManyToManyField(Module, related_name='bundles')
    
    pricing_mode = models.CharField(max_length=32, choices=PRICING_MODE_CHOICES)
    fixed_price_monthly = models.IntegerField(null=True, blank=True, help_text="Override price in cents")
    fixed_price_yearly = models.IntegerField(null=True, blank=True, help_text="Override price in cents")
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    
    is_default_recommended = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name

class Promotion(models.Model):
    TARGET_TYPE_CHOICES = [
        ('bundle', 'Bundle'),
        ('module', 'Module'),
    ]

    code = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=128)
    applies_to = models.CharField(max_length=32, choices=TARGET_TYPE_CHOICES)
    
    # We use FKs for integrity, serializer can handle code logic
    target_bundle = models.ForeignKey(Bundle, null=True, blank=True, on_delete=models.CASCADE)
    target_module = models.ForeignKey(Module, null=True, blank=True, on_delete=models.CASCADE)
    
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    fixed_override_price = models.IntegerField(null=True, blank=True)
    
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    def is_valid(self):
        now = timezone.now()
        if not self.is_active:
            return False
        if self.starts_at and now < self.starts_at:
            return False
        if self.ends_at and now > self.ends_at:
            return False
        return True

class Subscription(models.Model):
    PLAN_TYPE_CHOICES = [
        ('bundle', 'Bundle'),
        ('custom', 'Custom'),
    ]
    BILLING_PERIOD_CHOICES = [
        ('monthly', 'Monthly'),
        ('yearly', 'Yearly'),
    ]
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('trial', 'Trial'),
        ('past_due', 'Past Due'),
        ('canceled', 'Canceled'),
    ]

    business = models.OneToOneField(Business, related_name='billing_subscription', on_delete=models.CASCADE)
    
    plan_type = models.CharField(max_length=32, choices=PLAN_TYPE_CHOICES)
    bundle = models.ForeignKey(Bundle, null=True, blank=True, on_delete=models.SET_NULL)
    selected_modules = models.ManyToManyField(Module, blank=True)
    
    billing_period = models.CharField(max_length=32, choices=BILLING_PERIOD_CHOICES)
    currency = models.CharField(max_length=3, default='ARS')
    
    price_snapshot = models.JSONField(default=dict, help_text="Snapshot of pricing at the time of subscription")
    
    plan = models.ForeignKey(Plan, null=True, blank=True, on_delete=models.SET_NULL)
    mp_preapproval_id = models.CharField(max_length=128, null=True, blank=True)
    next_billing_date = models.DateTimeField(null=True, blank=True)
    current_period_end = models.DateTimeField(null=True, blank=True)

    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default='active')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.business} - {self.plan_type}"
