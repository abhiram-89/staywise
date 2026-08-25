const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000'
const HOTEL_KEY = 'hbf_hotel_id'

export class ApiError extends Error {
  status: number
  constructor(message: string, status = 500) {
    super(message)
    this.status = status
  }
}

export const getHotelId = () => (typeof window !== 'undefined' ? localStorage.getItem(HOTEL_KEY) : null)
export const setHotelId = (id: string) => {
  if (typeof window !== 'undefined') localStorage.setItem(HOTEL_KEY, id)
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = typeof window !== 'undefined' ? localStorage.getItem('hbf_token') : null
  const hotelId = getHotelId()
  let res: Response
  try {
    res = await fetch(`${API_URL}${path}`, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(hotelId ? { 'X-Hotel-Id': hotelId } : {}),
        ...options.headers,
      },
    })
  } catch {
    throw new ApiError('Could not reach the server. Please check that the API is running.', 0)
  }

  const body = await res.json().catch(() => ({}))
  if (!res.ok) {
    const detail = body?.detail
    const message =
      typeof detail === 'string'
        ? detail
        : Array.isArray(detail)
          ? detail.map((item: { msg?: string }) => item.msg).filter(Boolean).join(' ')
          : res.status === 401
            ? 'Please sign in to continue.'
            : 'Something went wrong.'
    throw new ApiError(message, res.status)
  }
  return body as T
}

export const signup = (email: string, password: string, name: string) =>
  request<{ email: string; name?: string; message?: string }>('/api/auth/register', {
    method: 'POST',
    body: JSON.stringify({ email, password, name }),
  })

export const login = (email: string, password: string) =>
  request<{ access_token: string; token_type: string; name: string; email: string }>('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  })

export const fetchMe = () => request<{ email: string; name: string; hotel?: unknown; hotels?: import('./types').Hotel[]; hotel_id?: string }>('/api/auth/me')
export const updateProfile = (name: string) =>
  request<{ email: string; name: string }>('/api/auth/profile', {
    method: 'PATCH',
    body: JSON.stringify({ name }),
  })
export const fetchWorkspaces = () => request<import('./types').WorkspaceList>('/api/workspaces')
export const createWorkspace = (payload: { name: string; city?: string; rooms?: number }) =>
  request<{ hotel: import('./types').Hotel; hotels: import('./types').Hotel[] }>('/api/workspaces', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
export const fetchDashboard = () => request<import('./types').DashboardData>('/api/dashboard')
export const fetchHistorical = (params?: { start?: string; end?: string; category?: string }) => {
  const query = new URLSearchParams()
  if (params?.start) query.set('start', params.start)
  if (params?.end) query.set('end', params.end)
  if (params?.category) query.set('category', params.category)
  const suffix = query.toString() ? `?${query}` : ''
  return request<import('./types').HistoricalData>(`/api/historical${suffix}`)
}
export const uploadHistorical = (rows: Record<string, unknown>[]) =>
  request<import('./types').UploadResult>('/api/historical/upload', {
    method: 'POST',
    body: JSON.stringify({ rows }),
  })
export const fetchForecast = () => request<import('./types').ForecastData>('/api/forecast')
export const generateForecast = (months: number) =>
  request<import('./types').ForecastData>('/api/forecast/generate', {
    method: 'POST',
    body: JSON.stringify({ months }),
  })
export const fetchSettings = () => request<import('./types').SettingsData>('/api/settings')
export const fetchRooms = () => request<import('./types').RoomsData>('/api/rooms')
export const fetchGraph = () => request<import('./types').GraphData>('/api/graph')
export const sendChat = (message: string) =>
  request<{ reply: string }>('/api/chat', {
    method: 'POST',
    body: JSON.stringify({ message }),
  })
