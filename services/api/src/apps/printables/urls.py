from django.urls import path

from .views import GeneratePDFView

app_name = 'printables'

urlpatterns = [
    path('generate-pdf/', GeneratePDFView.as_view(), name='generate-pdf'),
]
