import uuid

from django.db import models
from django.db.models import Q


class Customer(models.Model):
  class CustomerType(models.TextChoices):
    INDIVIDUAL = 'individual', 'Persona'
    COMPANY = 'company', 'Empresa'

  class DocumentType(models.TextChoices):
    DNI = 'dni', 'DNI'
    CUIT = 'cuit', 'CUIT'
    PASSPORT = 'passport', 'Pasaporte'
    OTHER = 'other', 'Otro'

  class TaxCondition(models.TextChoices):
    CONSUMER = 'consumer', 'Consumidor Final'
    REGISTERED = 'registered', 'Responsable Inscripto'
    MONOTAX = 'monotax', 'Monotributo'
    EXEMPT = 'exempt', 'Exento'
    OTHER = 'other', 'Otro'

  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
  business = models.ForeignKey('business.Business', related_name='customers', on_delete=models.CASCADE)
  name = models.CharField(max_length=255)
  type = models.CharField(max_length=16, choices=CustomerType.choices, default=CustomerType.INDIVIDUAL)
  doc_type = models.CharField(max_length=32, choices=DocumentType.choices, blank=True, default='')
  doc_number = models.CharField(max_length=64, blank=True, default='')
  tax_condition = models.CharField(max_length=32, choices=TaxCondition.choices, blank=True, default='')
  email = models.EmailField(blank=True)
  phone = models.CharField(max_length=64, blank=True)
  address_line = models.CharField(max_length=255, blank=True)
  city = models.CharField(max_length=128, blank=True)
  province = models.CharField(max_length=128, blank=True)
  postal_code = models.CharField(max_length=32, blank=True)
  country = models.CharField(max_length=64, blank=True)
  note = models.TextField(blank=True)
  tags = models.JSONField(default=list, blank=True)
  is_active = models.BooleanField(default=True)
  created_at = models.DateTimeField(auto_now_add=True)
  updated_at = models.DateTimeField(auto_now=True)

  class Meta:
    ordering = ['name']
    indexes = [
      models.Index(fields=['business', 'name']),
      models.Index(fields=['business', 'email']),
      models.Index(fields=['business', 'phone']),
      models.Index(fields=['business', 'doc_number']),
    ]
    constraints = [
      models.UniqueConstraint(
        fields=['business', 'doc_type', 'doc_number'],
        condition=Q(doc_type__gt='') & Q(doc_number__gt=''),
        name='customer_unique_document_per_business',
      )
    ]

  def __str__(self) -> str:
    return f"{self.name} ({self.business_id})"
