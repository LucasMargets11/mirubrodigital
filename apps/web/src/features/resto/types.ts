export type RestaurantOperationDefaultPosMode = 'quick_sale' | 'kitchen_order';

export type RestaurantOperationSettings = {
  tables_enabled: boolean;
  kitchen_enabled: boolean;
  counter_orders_enabled: boolean;
  pos_quick_sale_enabled: boolean;
  allow_pickup_orders: boolean;
  allow_dine_in_orders: boolean;
  allow_delivery_orders: boolean;
  default_pos_mode: RestaurantOperationDefaultPosMode;
};

export const DEFAULT_RESTAURANT_OPERATION_SETTINGS: RestaurantOperationSettings = {
  tables_enabled: true,
  kitchen_enabled: true,
  counter_orders_enabled: true,
  pos_quick_sale_enabled: true,
  allow_pickup_orders: true,
  allow_dine_in_orders: true,
  allow_delivery_orders: false,
  default_pos_mode: 'quick_sale',
};