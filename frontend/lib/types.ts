export type Hotel = {
  id?: string
  name?: string
  rooms?: number
  star_rating?: number
  city?: string
}

export type User = {
  email: string
  name: string
}

export type MonthRow = {
  id: string
  label: string
  year?: number
  month?: number
  date?: string
  revenue: number
  expenses: number
  net_profit: number
  occupancy: number
  adr?: number
}

export type DashboardData = {
  empty: boolean
  as_of?: string
  period?: string
  months_used?: number
  kpis?: {
    revenue: number
    revenue_delta: number
    expenses: number
    expenses_delta: number
    net_profit: number
    profit_delta: number
    occupancy: number
    occupancy_delta: number
  }
  trend: MonthRow[]
  breakdown: { id: string; name: string; color: string; amount: number; percent: number }[]
}

export type HistoricalData = {
  rows: MonthRow[]
  categories: string[]
  count: number
}

export type ForecastData = {
  empty: boolean
  rows: MonthRow[]
  insights: string[]
  created_at?: string
}

export type SettingsData = {
  user: User
  hotel: Hotel | null
  hotels?: Hotel[]
  hotel_id?: string
}

export type RoomRow = {
  id: string
  name: string
  base_rate: number
  rooms: number
  revenue: number
  demand: string
}

export type RoomsData = {
  empty: boolean
  hotel: Hotel
  as_of?: string
  occupancy: number
  rows: RoomRow[]
}

export type GraphNode = {
  id: string
  type: string
  label: string
  detail: string
}

export type GraphData = {
  empty: boolean
  nodes: GraphNode[]
  edges: { from: string; to: string; rel: string }[]
  hotel: Hotel
  months: number
  as_of?: string
}

export type UploadResult = {
  status: string
  count: number
  from?: string
  to?: string
  message: string
}

export type WorkspaceList = {
  hotels: Hotel[]
}
