export type Table = {
     id: string;
     code: string;
     name: string;
     capacity?: number;
     area?: string;
     notes?: string;
     is_enabled: boolean;
     is_paused: boolean;
};

export type TablePlacement = {
     id?: string;
     tableId: string;
     x: number;
     y: number;
     w?: number;
     h?: number;
     rotation?: number;
     zIndex?: number;
     tableCode?: string | null;
};

export type TablesLayout = {
     gridCols: number;
     gridRows: number;
     placements: TablePlacement[];
};

export type RestaurantTableState = 'FREE' | 'OCCUPIED' | 'PAUSED' | 'DISABLED';

export type TableGridPosition = {
      x: number;
      y: number;
      w: number;
      h: number;
};

export type TablePosition = {
      x: number;
      y: number;
      w: number;
      h: number;
      rotation?: number;
      z_index?: number;
      grid?: TableGridPosition;
};

export type RestaurantTableOrder = {
     id: string;
     number: number;
     status: string;
     status_label: string;
     total: string;
     updated_at: string | null;
};

export type RestaurantTableNode = {
     id: string;
     code: string;
     name: string;
     capacity?: number;
     area?: string;
     notes?: string;
     is_enabled: boolean;
     is_paused: boolean;
     position: TablePosition | null;
     active_order: RestaurantTableOrder | null;
     state: RestaurantTableState;
};

export type TablesGridDimensions = {
      gridCols: number;
      gridRows: number;
};

export type TablesMapStateResponse = {
      server_time: string;
      layout: TablesGridDimensions;
      tables: RestaurantTableNode[];
};

export type TableSelectionHandler = (tableId: string) => void;

export type TableConfiguration = {
     tables: Table[];
     layout: TablesLayout;
};

export type TableConfigurationPayload = TableConfiguration;
