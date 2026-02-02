from rest_framework import serializers
from django.utils import timezone

from .models import Order, OrderItem


class KitchenItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = [
            'id',
            'name',
            'modifiers',
            'note',
            'quantity',
            'kitchen_status',
            'kitchen_started_at',
            'kitchen_ready_at',
            'kitchen_done_at',
        ]


class KitchenOrderSerializer(serializers.ModelSerializer):
    items = KitchenItemSerializer(many=True, read_only=True)
    table_name = serializers.CharField(read_only=True)
    channel_display = serializers.CharField(source='get_channel_display', read_only=True)
    elapsed_seconds = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            'id',
            'number',
            'channel',
            'channel_display',
            'table_name',
            'customer_name',
            'status',
            'opened_at',
            'items',
            'elapsed_seconds',
            'note',
        ]

    def get_elapsed_seconds(self, obj):
        if not obj.opened_at:
            return 0
        diff = timezone.now() - obj.opened_at
        return int(diff.total_seconds())
