'use client'

import { ChangeEvent, FormEvent, MouseEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  ArrowDownRight,
  ArrowUpRight,
  BedDouble,
  CalendarDays,
  ChevronDown,
  Download,
  FileUp,
  Hotel,
  LayoutDashboard,
  LogOut,
  Menu,
  Network,
  Plus,
  Settings2,
  Sparkles,
  TrendingUp,
  Wallet,
  X,
} from 'lucide-react'
import { AppChatbot } from '@/components/app-chatbot'
import { useAuth } from '@/components/auth-provider'
import { ApiError, createWorkspace, fetchDashboard, fetchForecast, fetchGraph, fetchHistorical, fetchRooms, fetchSettings, fetchWorkspaces, generateForecast, setHotelId, updateProfile, uploadHistorical } from '@/lib/api'
import { compactMoney, formatDate, formatDelta, formatINR, formatPct, formatWhen, greeting, initials } from '@/lib/format'
import { parseReportFile } from '@/lib/parse-report'
import type { DashboardData, ForecastData, GraphData, HistoricalData, Hotel as HotelRecord, MonthRow, RoomRow, RoomsData, SettingsData } from '@/lib/types'

const MONTH_NAMES = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']

function uniqueRoomRows(rows: RoomRow[] = []) {
  const seen = new Map<string, RoomRow>()
  for (const row of rows) {
    const key = (row.name || row.id || '').trim().toLowerCase()
    if (key && !seen.has(key)) seen.set(key, row)
  }
  return [...seen.values()]
}

function monthTitle(row: MonthRow) {
  if (row.month && row.month >= 1 && row.month <= 12) return MONTH_NAMES[row.month - 1]
  const fromLabel = row.label?.split(' ')[0]
  return fromLabel || row.label || 'Month'
}

function yearTitle(row: MonthRow) {
  if (row.year) return String(row.year)
  const match = row.label?.match(/20\d{2}/)
  return match?.[0] || '—'
}

const nav = [
  ['Overview', LayoutDashboard],
  ['Historical', CalendarDays],
  ['Forecasts', TrendingUp],
  ['Graph explorer', Network],
  ['Rooms & rates', BedDouble],
  ['Settings', Settings2],
] as const

async function exportForecastExcel(rows: MonthRow[]) {
  const XLSX = await import('xlsx')
  const sheet = XLSX.utils.json_to_sheet(
    rows.map((row) => ({
      Month: row.label,
      Revenue: row.revenue,
      Expenses: row.expenses,
      'Net Profit': row.net_profit,
      Occupancy: row.occupancy,
    })),
  )
  const book = XLSX.utils.book_new()
  XLSX.utils.book_append_sheet(book, sheet, 'Forecast')
  XLSX.writeFile(book, 'staywise-forecast.xlsx')
}

function MetricCard({
  label,
  value,
  detail,
  trend,
  icon: Icon,
  positive = true,
}: {
  label: string
  value: string
  detail: string
  trend: string
  icon: typeof TrendingUp
  positive?: boolean
}) {
  return (
    <article className="metric-card">
      <div className="metric-head">
        <div className="metric-icon"><Icon size={17} /></div>
        <span className={`metric-trend ${positive ? 'positive' : 'negative'}`}>
          {positive ? <ArrowUpRight size={13} /> : <ArrowDownRight size={13} />}
          {trend}
        </span>
      </div>
      <p className="metric-label">{label}</p>
      <strong className="metric-value">{value}</strong>
      <span className="metric-detail">{detail}</span>
    </article>
  )
}

function MoneyChart({ rows, forecast = false }: { rows: MonthRow[]; forecast?: boolean }) {
  const areaRef = useRef<HTMLDivElement>(null)
  const [hover, setHover] = useState<number | null>(null)

  if (!rows.length) return <div className="empty-inline">No periods to chart yet.</div>
  const values = rows.flatMap((row) => [row.revenue, row.expenses || 0])
  const max = Math.max(...values, 1)
  const denom = Math.max(1, rows.length - 1)
  const points = rows.map((row, i) => ({
    x: (i * 100) / denom,
    yRev: 100 - ((Number(row.revenue) || 0) / max) * 92 - 4,
    yExp: 100 - ((Number(row.expenses) || 0) / max) * 92 - 4,
  }))
  const line = (key: 'yRev' | 'yExp') => points.map((point) => `${point.x},${point[key]}`).join(' ')
  const ticks = [max, max * 0.66, max * 0.33, 0]
  const labels = rows.length > 8
    ? rows.map((row, i) => (i % Math.ceil(rows.length / 8) === 0 ? row.label.replace(/ 20/, " '") : ''))
    : rows.map((row) => row.label.replace(/ 20/, " '"))

  const onMove = (event: MouseEvent<HTMLDivElement>) => {
    const el = areaRef.current
    if (!el) return
    const rect = el.getBoundingClientRect()
    const ratio = Math.max(0, Math.min(1, (event.clientX - rect.left) / Math.max(1, rect.width)))
    setHover(Math.round(ratio * (rows.length - 1)))
  }

  const active = hover == null ? null : rows[hover]
  const activePoint = hover == null ? null : points[hover]

  return (
    <div className="chart-wrap" aria-label="Revenue performance chart">
      <div className="chart-ylabels">
        {ticks.map((tick) => <span key={tick}>{compactMoney(tick)}</span>)}
      </div>
      <div
        className="chart-area"
        ref={areaRef}
        onMouseMove={onMove}
        onMouseLeave={() => setHover(null)}
      >
        <div className="chart-grid"><i /><i /><i /><i /></div>
        <div className="chart-plot">
          <svg viewBox="0 0 100 100" preserveAspectRatio="none" role="img" aria-label="Revenue chart">
            <polyline className="chart-line revenue" points={line('yRev')} fill="none" stroke="var(--teal)" />
            <polyline className={`chart-line expenses${forecast ? ' dashed' : ''}`} points={line('yExp')} fill="none" stroke="var(--coral)" />
          </svg>
          {points.map((point, i) => (
            <span key={`rev-${i}`} className={`chart-dot revenue ${hover === i ? 'active' : ''}`} style={{ left: `${point.x}%`, top: `${point.yRev}%` }} />
          ))}
          {points.map((point, i) => (
            <span key={`exp-${i}`} className={`chart-dot expenses ${hover === i ? 'active' : ''}`} style={{ left: `${point.x}%`, top: `${point.yExp}%` }} />
          ))}
          {active && activePoint && (
            <>
              <div className="chart-cursor" style={{ left: `${activePoint.x}%` }} />
              <div className={`chart-tooltip ${activePoint.x > 68 ? 'left' : ''}`} style={{ left: `${activePoint.x}%` }}>
                <span className="chart-tooltip-kicker">{yearTitle(active)} · {monthTitle(active)}</span>
                <p><i className="legend-dot actual" />Revenue <b>{formatINR(active.revenue)}</b></p>
                <p><i className="legend-dot forecast" />Expenses <b>{formatINR(active.expenses)}</b></p>
              </div>
            </>
          )}
        </div>
        <div className="chart-xlabels">{labels.map((label, i) => <span key={`${label}-${i}`}>{label}</span>)}</div>
      </div>
    </div>
  )
}

function ImportModal({
  onClose,
  onImported,
}: {
  onClose: () => void
  onImported: (message: string) => Promise<void>
}) {
  const input = useRef<HTMLInputElement>(null)
  const [error, setError] = useState('')
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)

  const parse = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    setName(file.name)
    setError('')
    setBusy(true)
    try {
      const rows = await parseReportFile(file)
      const result = await uploadHistorical(rows)
      await onImported(result.message || `Loaded ${result.count} months into CognoDB.`)
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not import this report.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="modal-backdrop" role="presentation" onClick={onClose}>
      <section className="import-modal" role="dialog" aria-modal="true" aria-labelledby="import-title" onClick={(e) => e.stopPropagation()}>
        <div className="modal-heading">
          <div>
            <span className="eyebrow">DATA INGESTION</span>
            <h2 id="import-title">Import hotel report</h2>
          <p>Upload Excel, CSV, or JSON. Overview, rooms, and forecasts refresh from this file.</p>
          </div>
          <button className="icon-button" onClick={onClose} aria-label="Close import dialog"><X size={18} /></button>
        </div>
        <button className="dropzone" onClick={() => input.current?.click()} disabled={busy}>
          <FileUp size={25} />
          <strong>{busy ? 'Uploading to CognoDB…' : name || 'Choose a report file'}</strong>
          <span>XLSX, CSV, or JSON · year, month, Room Revenue</span>
        </button>
        <input ref={input} hidden type="file" accept=".csv,.json,.xlsx,.xls,text/csv,application/json,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" onChange={parse} />
        {error && <p className="import-error">{error}</p>}
        <div className="modal-footer">
          <span>Need columns for year, month (or date), and revenue.</span>
          <button className="button-primary" onClick={() => input.current?.click()} disabled={busy}>
            {busy ? 'Uploading…' : 'Select file'}
          </button>
        </div>
      </section>
    </div>
  )
}

function ClientModal({
  onClose,
  onCreated,
}: {
  onClose: () => void
  onCreated: (hotel: HotelRecord, hotels: HotelRecord[]) => Promise<void>
}) {
  const [name, setName] = useState('')
  const [city, setCity] = useState('')
  const [rooms, setRooms] = useState('80')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    const nextName = name.trim()
    if (nextName.length < 2) {
      setError('Enter a client or property name.')
      return
    }
    setBusy(true)
    setError('')
    try {
      const result = await createWorkspace({
        name: nextName,
        city: city.trim(),
        rooms: Number(rooms) || 0,
      })
      await onCreated(result.hotel, result.hotels)
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not add this client.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="modal-backdrop" role="presentation" onClick={onClose}>
      <section className="import-modal" role="dialog" aria-modal="true" aria-labelledby="client-title" onClick={(e) => e.stopPropagation()}>
        <div className="modal-heading">
          <div>
            <span className="eyebrow">WORKSPACE</span>
            <h2 id="client-title">Add a client</h2>
            <p>Create a new hotel property. Import a report after switching to it.</p>
          </div>
          <button className="icon-button" onClick={onClose} aria-label="Close add client dialog"><X size={18} /></button>
        </div>
        <form onSubmit={submit}>
          <label className="control-label">Property name
            <input value={name} onChange={(e) => setName(e.target.value)} required minLength={2} placeholder="Grand Metropolitan Plaza" />
          </label>
          <label className="control-label">City
            <input value={city} onChange={(e) => setCity(e.target.value)} placeholder="Hyderabad" />
          </label>
          <label className="control-label">Room count
            <input type="number" min={0} max={5000} value={rooms} onChange={(e) => setRooms(e.target.value)} />
          </label>
          {error && <p className="import-error">{error}</p>}
          <div className="modal-footer">
            <span>Each client keeps its own history and forecasts.</span>
            <button className="button-primary" disabled={busy}>{busy ? 'Adding…' : 'Add client'}</button>
          </div>
        </form>
      </section>
    </div>
  )
}

export default function HotelDashboard() {
  const { user, token, ready, signOut, updateName } = useAuth()
  const [active, setActive] = useState<(typeof nav)[number][0]>('Overview')
  const [mobileNav, setMobileNav] = useState(false)
  const [range, setRange] = useState('12 months')
  const [importOpen, setImportOpen] = useState(false)
  const [clientOpen, setClientOpen] = useState(false)
  const [workspaceOpen, setWorkspaceOpen] = useState(false)
  const workspaceRef = useRef<HTMLDivElement>(null)
  const [profileHover, setProfileHover] = useState(false)
  const [profilePinned, setProfilePinned] = useState(false)
  const profileRef = useRef<HTMLDivElement>(null)
  const [loading, setLoading] = useState(true)
  const [forecastBusy, setForecastBusy] = useState(false)
  const [horizon, setHorizon] = useState(6)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [dashboard, setDashboard] = useState<DashboardData | null>(null)
  const [historical, setHistorical] = useState<HistoricalData | null>(null)
  const [forecast, setForecast] = useState<ForecastData | null>(null)
  const [settings, setSettings] = useState<SettingsData | null>(null)
  const [roomsData, setRoomsData] = useState<RoomsData | null>(null)
  const [graphData, setGraphData] = useState<GraphData | null>(null)
  const [hotels, setHotels] = useState<HotelRecord[]>([])
  const [graphNode, setGraphNode] = useState('hotel')
  const [roomFilter, setRoomFilter] = useState('All rooms')
  const [histStart, setHistStart] = useState('')
  const [histEnd, setHistEnd] = useState('')
  const [histCategory, setHistCategory] = useState('All')
  const [page, setPage] = useState(1)
  const [nameDraft, setNameDraft] = useState('')
  const [savingName, setSavingName] = useState(false)

  const loadAll = useCallback(async () => {
    if (!token) return
    setLoading(true)
    setError('')
    try {
      const [dash, hist, fc, set, rooms, graph, workspaces] = await Promise.all([
        fetchDashboard(),
        fetchHistorical(),
        fetchForecast(),
        fetchSettings(),
        fetchRooms(),
        fetchGraph(),
        fetchWorkspaces(),
      ])
      setDashboard(dash)
      setHistorical(hist)
      setForecast(fc)
      setSettings(set)
      setRoomsData(rooms)
      setGraphData(graph)
      setHotels(workspaces.hotels || set.hotels || [])
      if (set.hotel_id) setHotelId(set.hotel_id)
      setGraphNode('hotel')
      setHistCategory('All')
      setPage(1)
    } catch (err) {
      if (err instanceof ApiError && (err.status === 401 || err.status === 403)) {
        signOut()
        return
      }
      setError(err instanceof Error ? err.message : 'Could not load workspace data.')
    } finally {
      setLoading(false)
    }
  }, [token, signOut])

  useEffect(() => {
    if (ready && token) void loadAll()
  }, [ready, token, loadAll])

  useEffect(() => {
    setNameDraft(user?.name || '')
  }, [user?.name])

  useEffect(() => {
    if (!workspaceOpen) return undefined
    const onClick = (event: Event) => {
      if (workspaceRef.current && !workspaceRef.current.contains(event.target as Node)) {
        setWorkspaceOpen(false)
      }
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [workspaceOpen])

  useEffect(() => {
    if (!profilePinned) return undefined
    const onClick = (event: Event) => {
      if (profileRef.current && !profileRef.current.contains(event.target as Node)) {
        setProfilePinned(false)
        setProfileHover(false)
      }
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [profilePinned])

  const filterHistorical = async () => {
    setLoading(true)
    setError('')
    try {
      const hist = await fetchHistorical({
        start: histStart || undefined,
        end: histEnd || undefined,
        category: histCategory,
      })
      setHistorical(hist)
      setPage(1)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not filter historical rows.')
    } finally {
      setLoading(false)
    }
  }

  const onImported = async (message: string) => {
    setNotice(message)
    await loadAll()
    setActive('Overview')
  }

  const switchHotel = async (id?: string) => {
    if (!id) return
    setHotelId(id)
    setWorkspaceOpen(false)
    await loadAll()
  }

  const onClientCreated = async (hotel: HotelRecord, nextHotels: HotelRecord[]) => {
    setHotels(nextHotels)
    if (hotel.id) setHotelId(hotel.id)
    setNotice(`${hotel.name || 'Client'} added. Import a report to populate this workspace.`)
    await loadAll()
  }

  const saveName = async () => {
    const next = nameDraft.trim()
    if (next.length < 2 || next === user?.name) return
    setSavingName(true)
    setError('')
    try {
      const data = await updateProfile(next)
      updateName(data.name)
      setNotice('Username updated.')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not update your username.')
    } finally {
      setSavingName(false)
    }
  }

  const runForecast = async () => {
    setForecastBusy(true)
    setError('')
    try {
      setForecast(await generateForecast(horizon))
      setNotice(`Forecast generated for the next ${horizon} months.`)
      setActive('Forecasts')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not generate a forecast.')
    } finally {
      setForecastBusy(false)
    }
  }

  const hotel = settings?.hotel
  const firstName = user?.name?.split(' ')[0] || 'there'
  const kpis = dashboard?.kpis
  const histRows = historical?.rows || []
  const forecastRows = forecast?.rows || []
  const empty = !loading && (!dashboard || dashboard.empty)
  const hotelName = hotel?.name || 'Your workspace'
  const rooms = empty ? 0 : hotel?.rooms || 0
  const roomRows = useMemo(
    () => uniqueRoomRows(roomsData?.rows || []).filter((row) => (
      roomFilter === 'All rooms' || row.demand === roomFilter.replace(' demand', '')
    )),
    [roomsData, roomFilter],
  )
  const trend = useMemo(() => {
    const rows = dashboard?.trend || []
    if (range === '90 days') return rows.slice(-3)
    if (range === '6 months') return rows.slice(-6)
    return rows
  }, [dashboard, range])
  const pageSize = 8
  const pageCount = Math.max(1, Math.ceil(histRows.length / pageSize))
  const slice = histRows.slice((page - 1) * pageSize, page * pageSize)
  const go = (name: (typeof nav)[number][0]) => {
    setActive(name)
    setMobileNav(false)
  }

  const overview = empty ? (
    <section className="panel empty-panel">
      <div className="insight-orb"><FileUp size={20} /></div>
      <span className="eyebrow">NO HISTORY YET</span>
      <h2>Import a hotel report to populate this workspace.</h2>
      <p>Upload Excel or CSV with year, month, and Room Revenue. Charts, rooms, and forecasts stay empty until that file is imported.</p>
      <button className="button-primary" onClick={() => setImportOpen(true)}><FileUp size={15} />Import report</button>
    </section>
  ) : (
    <>
      <section className="metrics-grid">
        <MetricCard label="Total revenue" value={formatINR(kpis?.revenue)} detail={dashboard?.period || 'this period'} trend={formatDelta(kpis?.revenue_delta)} icon={TrendingUp} positive={(kpis?.revenue_delta || 0) >= 0} />
        <MetricCard label="Total expenses" value={formatINR(kpis?.expenses)} detail="operating costs" trend={formatDelta(kpis?.expenses_delta)} icon={Wallet} positive={(kpis?.expenses_delta || 0) <= 0} />
        <MetricCard label="Net profit" value={formatINR(kpis?.net_profit)} detail="after expenses" trend={formatDelta(kpis?.profit_delta)} icon={ArrowUpRight} positive={(kpis?.profit_delta || 0) >= 0} />
        <MetricCard label="Occupancy rate" value={formatPct(kpis?.occupancy)} detail="average" trend={formatDelta(kpis?.occupancy_delta)} icon={Hotel} positive={(kpis?.occupancy_delta || 0) >= 0} />
      </section>
      <section className="main-grid">
        <article className="panel performance-panel">
          <div className="panel-heading">
            <div>
              <h2>Revenue vs expenses</h2>
              <p>Live P&L from your imported history · {dashboard?.period}</p>
            </div>
            <div className="select-wrap">
              <CalendarDays size={14} />
              <select value={range} onChange={(e) => setRange(e.target.value)} aria-label="Chart time range">
                <option>12 months</option>
                <option>6 months</option>
                <option>90 days</option>
              </select>
              <ChevronDown size={14} />
            </div>
          </div>
          <div className="legend">
            <span><i className="legend-dot actual" />Revenue</span>
            <span><i className="legend-dot forecast" />Expenses</span>
          </div>
          <MoneyChart rows={trend} />
        </article>
        <article className="panel insight-panel">
          <div className="insight-orb"><Sparkles size={20} /></div>
          <span className="eyebrow">FORECAST INSIGHT</span>
          <h2>{forecastRows.length ? 'Latest forecast is ready.' : 'Generate a forecast from this file.'}</h2>
          <p>
            {forecast?.insights?.[0] || 'Imported booking and P&L history is now in CognoDB. Run a forecast to project the next planning window.'}
          </p>
          <button className="text-button" onClick={() => (forecastRows.length ? go('Forecasts') : void runForecast())}>
            {forecastRows.length ? 'View forecast details' : 'Run forecast'} <ArrowUpRight size={15} />
          </button>
          <div className="insight-foot">
            <span>{forecastRows.length ? 'Horizon' : 'History loaded'}</span>
            <strong>{forecastRows.length ? `${forecastRows.length} mo` : `${histRows.length} periods`}</strong>
            <div className="confidence"><i style={{ width: forecastRows.length ? '87%' : '40%' }} /></div>
          </div>
        </article>
      </section>
      <section className="bottom-grid">
        <article className="panel">
          <div className="panel-heading">
            <div>
              <h2>Expense breakdown</h2>
              <p>Latest month department mix</p>
            </div>
          </div>
          <div className="entity-list">
            {(dashboard?.breakdown || []).map((item) => (
              <div className="entity-row" key={item.id}>
                <div className="entity-icon" style={{ background: `${item.color}22`, color: item.color }} />
                <div>
                  <strong>{item.name}</strong>
                  <span>{formatINR(item.amount)}</span>
                </div>
                <span className="entity-status">{formatPct(item.percent, 0)}</span>
              </div>
            ))}
          </div>
        </article>
        <article className="panel activity-panel">
          <div className="panel-heading">
            <div>
              <h2>Data activity</h2>
              <p>What this workspace is using now</p>
            </div>
          </div>
          <div className="activity-list">
            <div className="activity">
              <div className="activity-avatar teal-bg">{initials(user?.name)}</div>
              <p><strong>You</strong> are signed in as <b>{user?.email}</b><small>Active session</small></p>
            </div>
            <div className="activity">
              <div className="activity-avatar coral-bg">IM</div>
              <p><strong>Import</strong> loaded <b>{histRows.length} report periods</b><small>{dashboard?.as_of ? `As of ${dashboard.as_of}` : 'Waiting for import'}</small></p>
            </div>
            <div className="activity">
              <div className="activity-avatar sand-bg">FC</div>
              <p><strong>Forecast engine</strong> {forecastRows.length ? <>has <b>{forecastRows.length} projected months</b></> : 'has not been run yet'}<small>{forecast?.created_at ? formatWhen(forecast.created_at) : 'Generate from Forecasts'}</small></p>
            </div>
          </div>
        </article>
      </section>
    </>
  )

  const historicalView = (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">IMPORTED HISTORY</span>
          <h1>Historical data</h1>
          <p className="subheading">This table is the live imported dataset used by Overview and Forecasts.</p>
        </div>
        <button className="button-primary" onClick={() => setImportOpen(true)}><FileUp size={15} />Import report</button>
      </div>
      <section className="panel table-panel">
        <div className="table-toolbar wrap-toolbar">
          <label className="control-label compact-field">Start
            <input type="date" value={histStart} onChange={(e) => setHistStart(e.target.value)} />
          </label>
          <label className="control-label compact-field">End
            <input type="date" value={histEnd} onChange={(e) => setHistEnd(e.target.value)} />
          </label>
          <label className="control-label compact-field">Category
            <select className="full-select compact" value={histCategory} onChange={(e) => setHistCategory(e.target.value)}>
              {(historical?.categories || ['All']).map((item) => <option key={item}>{item}</option>)}
            </select>
          </label>
          <button className="button-secondary" onClick={() => void filterHistorical()} disabled={loading}>Filter</button>
        </div>
        {!histRows.length ? (
          <div className="empty-inline">No historical rows yet. Import a report to see them here.</div>
        ) : (
          <>
            <div className="data-table">
              <div className="table-row table-head hist-head">
                <span>Date</span><span>Revenue</span><span>Expenses</span><span>Net profit</span><span>Occupancy</span>
              </div>
              {slice.map((row) => (
                <div className="table-row hist-row" key={row.id}>
                  <strong>{formatDate(row.date, row.label)}</strong>
                  <span>{formatINR(row.revenue)}</span>
                  <span>{formatINR(row.expenses)}</span>
                  <b className={row.net_profit >= 0 ? 'positive' : 'negative'}>{formatINR(row.net_profit)}</b>
                  <span>{formatPct(row.occupancy)}</span>
                </div>
              ))}
            </div>
            <div className="pager">
              <span>Showing {(page - 1) * pageSize + 1}–{Math.min(page * pageSize, histRows.length)} of {histRows.length}</span>
              <div className="pager-buttons">
                <button className="button-secondary" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Previous</button>
                <button className="button-secondary" disabled={page >= pageCount} onClick={() => setPage((p) => p + 1)}>Next</button>
              </div>
            </div>
          </>
        )}
      </section>
    </>
  )

  const forecastsView = (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">PLANNING STUDIO</span>
          <h1>Forecast scenarios</h1>
          <p className="subheading">Generated from the historical file you imported.</p>
        </div>
        <div className="heading-actions">
          <label className="control-label compact-field">Horizon
            <select className="full-select compact" value={horizon} onChange={(e) => setHorizon(Number(e.target.value))} disabled={forecastBusy}>
              <option value={3}>Next 3 months</option>
              <option value={6}>Next 6 months</option>
              <option value={12}>Next 12 months</option>
            </select>
          </label>
          <button className="button-secondary" onClick={() => void exportForecastExcel(forecastRows)} disabled={!forecastRows.length}>
            <Download size={15} />Export Excel
          </button>
          <button className="button-primary" onClick={() => void runForecast()} disabled={forecastBusy || empty}>
            <Sparkles size={15} />{forecastBusy ? 'Generating…' : 'Run forecast'}
          </button>
        </div>
      </div>
      {!forecastRows.length ? (
        <section className="panel empty-panel">
          <h2>No forecast yet</h2>
          <p>Import history first, then generate a 3, 6, or 12 month projection.</p>
        </section>
      ) : (
        <>
          <section className="main-grid">
            <article className="panel performance-panel">
              <div className="panel-heading">
                <div>
                  <h2>Projected revenue</h2>
                  <p>{forecastRows.length} months · {forecast?.created_at ? formatWhen(forecast.created_at) : 'just generated'}</p>
                </div>
              </div>
              <div className="legend">
                <span><i className="legend-dot actual" />Forecasted revenue</span>
                <span><i className="legend-dot forecast" />Forecasted expenses</span>
              </div>
              <MoneyChart rows={forecastRows} forecast />
            </article>
            <article className="panel">
              <h2>Key insights</h2>
              <div className="insight-list">
                {(forecast?.insights || []).map((note) => (
                  <p key={note}>{note}</p>
                ))}
              </div>
              <div className="forecast-total">
                <span>Projected revenue</span>
                <strong>{formatINR(forecastRows.reduce((sum, row) => sum + (row.revenue || 0), 0))}</strong>
              </div>
            </article>
          </section>
          <section className="panel table-panel">
            <div className="data-table">
              <div className="table-row table-head hist-head">
                <span>Month</span><span>Revenue</span><span>Expenses</span><span>Net profit</span><span>Occupancy</span>
              </div>
              {forecastRows.map((row) => (
                <div className="table-row hist-row" key={row.id}>
                  <strong>{row.label}</strong>
                  <span>{formatINR(row.revenue)}</span>
                  <span>{formatINR(row.expenses)}</span>
                  <b className="positive">{formatINR(row.net_profit)}</b>
                  <span>{formatPct(row.occupancy)}</span>
                </div>
              ))}
            </div>
          </section>
        </>
      )}
    </>
  )

  const graphView = (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">RELATIONSHIP MAP</span>
          <h1>Graph explorer</h1>
          <p className="subheading">Hotel, imported months, rooms, departments, and forecast runs currently linked together.</p>
        </div>
        <button className="button-secondary" onClick={() => setImportOpen(true)}><FileUp size={15} />Import source</button>
      </div>
      <section className="graph-panel panel">
        <div className="graph-canvas">
          {(graphData?.nodes || []).map((node) => (
            <button
              key={node.id}
              className={`graph-node node-${node.type} ${graphNode === node.id ? 'selected' : ''}`}
              onClick={() => setGraphNode(node.id)}
            >
              <strong>{node.label}</strong>
              <span>{empty && node.type !== 'hotel' && node.type !== 'city' ? 'Waiting for import' : node.detail}</span>
            </button>
          ))}
          <div className="graph-lines" />
        </div>
        <div className="graph-side">
          <span className="eyebrow">SELECTED ENTITY</span>
          <h2>{(graphData?.nodes || []).find((node) => node.id === graphNode)?.label || hotelName}</h2>
          <p className="subheading">{(graphData?.nodes || []).find((node) => node.id === graphNode)?.detail || 'Select a node to inspect its links.'}</p>
          <div className="entity-stats">
            <span><strong>{empty ? '—' : histRows.length}</strong> imported months</span>
            <span><strong>{empty ? '—' : uniqueRoomRows(roomsData?.rows).length}</strong> room types</span>
            <span><strong>{empty ? '—' : forecastRows.length}</strong> forecast months</span>
          </div>
          <div className="graph-rels">
            {(graphData?.edges || []).filter((edge) => edge.from === graphNode || edge.to === graphNode).map((edge) => (
              <span key={`${edge.from}-${edge.rel}-${edge.to}`}>{edge.rel}</span>
            ))}
          </div>
        </div>
      </section>
    </>
  )

  const roomsView = (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">INVENTORY MANAGEMENT</span>
          <h1>Rooms & rates</h1>
          <p className="subheading">{empty ? 'Import a report to calculate availability, rates, and demand.' : `Availability and pricing from the latest imported month${roomsData?.as_of ? ` · ${roomsData.as_of}` : ''}.`}</p>
        </div>
      </div>
      <section className="panel table-panel">
        <div className="table-toolbar">
          <h2>Room inventory <span className="muted-count">{empty ? 'No imported file yet' : `${roomRows.length} types · ${rooms || 0} total rooms`}</span></h2>
          <select value={roomFilter} onChange={(e) => setRoomFilter(e.target.value)} className="full-select compact">
            <option>All rooms</option>
            <option>High demand</option>
            <option>Medium demand</option>
            <option>Low demand</option>
          </select>
        </div>
        {empty || !uniqueRoomRows(roomsData?.rows || []).length ? (
          <div className="empty-inline">No room performance yet. Import history to populate rates and demand.</div>
        ) : !roomRows.length ? (
          <div className="empty-inline">No room types match this demand filter.</div>
        ) : (
          <div className="room-grid">
            {roomRows.map((row) => (
              <article className="room-card" key={row.id || row.name}>
                <div className="room-card-top">
                  <strong>{row.name}</strong>
                  <span className={`demand ${row.demand.toLowerCase()}`}>{row.demand}</span>
                </div>
                <div className="room-card-stats">
                  <div>
                    <span>Availability</span>
                    <b>{row.rooms ? `${row.rooms} rooms` : '—'}</b>
                  </div>
                  <div>
                    <span>Rate / night</span>
                    <b>{row.base_rate ? formatINR(row.base_rate) : '—'}</b>
                  </div>
                  <div>
                    <span>Latest revenue</span>
                    <b>{row.revenue ? formatINR(row.revenue) : '—'}</b>
                  </div>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>
    </>
  )

  const settingsView = (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">WORKSPACE ADMIN</span>
          <h1>Settings</h1>
          <p className="subheading">Account and property details for this workspace.</p>
        </div>
      </div>
      <section className="settings-grid">
        <article className="panel">
          <h2>Signed in as</h2>
          <label className="control-label">Username
            <input value={nameDraft} onChange={(e) => setNameDraft(e.target.value)} minLength={2} autoComplete="name" />
          </label>
          <label className="control-label">Email<input value={user?.email || ''} readOnly /></label>
          <div className="settings-actions">
            <button className="button-primary" onClick={() => void saveName()} disabled={savingName || nameDraft.trim().length < 2 || nameDraft.trim() === (user?.name || '')}>
              {savingName ? 'Saving…' : 'Save username'}
            </button>
            <button className="button-secondary" onClick={signOut}><LogOut size={15} />Sign out</button>
          </div>
        </article>
        <article className="panel">
          <h2>Data connection</h2>
          <p className="subheading">{hotelName}{hotel?.city ? ` · ${hotel.city}` : ''}{rooms ? ` · ${rooms} rooms` : ''}</p>
          <div className="connection-status">
            <i className="sync-dot" />
            <div>
              <strong>{empty ? 'Waiting for import' : 'Workspace connected'}</strong>
              <span>{empty ? 'Upload a report to create monthly snapshots' : `Last period ${dashboard?.as_of}`}</span>
            </div>
          </div>
          <button className="button-secondary" onClick={() => setImportOpen(true)}><FileUp size={15} />Import report</button>
        </article>
      </section>
    </>
  )

  const content =
    active === 'Overview' ? overview
      : active === 'Historical' ? historicalView
        : active === 'Forecasts' ? forecastsView
          : active === 'Graph explorer' ? graphView
            : active === 'Rooms & rates' ? roomsView
              : settingsView

  if (!token) return null

  return (
    <div className="app-shell">
      <aside className={`sidebar ${mobileNav ? 'open' : ''}`}>
        <div className="brand">
          <div className="brand-mark"><Hotel size={19} /></div>
          <span>staywise</span>
          <button className="icon-button close-nav" onClick={() => setMobileNav(false)} aria-label="Close navigation"><X size={18} /></button>
        </div>
        <div className="workspace-wrap" ref={workspaceRef}>
          <button className={`workspace ${workspaceOpen ? 'open' : ''}`} onClick={() => setWorkspaceOpen((value) => !value)} aria-expanded={workspaceOpen} aria-haspopup="listbox">
            <div className="hotel-avatar">{initials(hotelName, 'HT')}</div>
            <div>
              <span className="eyebrow">WORKSPACE</span>
              <strong>{hotelName}</strong>
            </div>
            <ChevronDown size={15} />
          </button>
          {workspaceOpen && (
            <div className="workspace-menu" role="listbox" aria-label="Clients">
              {(hotels.length ? hotels : [{ id: hotel?.id, name: hotelName, city: hotel?.city, rooms }]).map((item) => (
                <button
                  key={item.id || item.name}
                  className={`workspace-option ${item.id && hotel?.id === item.id ? 'selected' : ''}`}
                  onClick={() => void switchHotel(item.id)}
                >
                  <strong>{item.name || 'Workspace'}</strong>
                  <span>{[item.city, item.rooms ? `${item.rooms} rooms` : ''].filter(Boolean).join(' · ') || 'Client'}</span>
                </button>
              ))}
              <button className="workspace-option add" onClick={() => { setWorkspaceOpen(false); setClientOpen(true) }}>
                <Plus size={14} /> Add new client
              </button>
            </div>
          )}
        </div>
        <nav aria-label="Main navigation">
          <span className="nav-label">Manage</span>
          {nav.slice(0, 5).map(([name, Icon]) => (
            <button key={name} className={`nav-item ${active === name ? 'selected' : ''}`} onClick={() => go(name)}>
              <Icon size={17} /><span>{name}</span>
            </button>
          ))}
          <span className="nav-label nav-label-settings">Workspace</span>
          <button className={`nav-item ${active === 'Settings' ? 'selected' : ''}`} onClick={() => go('Settings')}>
            <Settings2 size={17} /><span>Settings</span>
          </button>
        </nav>
        <div className="sidebar-bottom logout-only">
          <button className="icon-button logout-button" onClick={signOut} aria-label="Sign out"><LogOut size={18} /></button>
        </div>
      </aside>
      <div className="main-column">
        <header className="topbar">
          <button className="icon-button menu-button" onClick={() => setMobileNav(true)} aria-label="Open navigation"><Menu size={20} /></button>
          <div className="breadcrumbs"><span>Workspace</span><b>/</b><strong>{active}</strong></div>
          <div
            className="profile-menu"
            ref={profileRef}
            onMouseEnter={() => setProfileHover(true)}
            onMouseLeave={() => setProfileHover(false)}
          >
            <button
              className="profile"
              onClick={() => setProfilePinned((value) => !value)}
              aria-label="Account details"
              aria-expanded={profileHover || profilePinned}
            >
              {initials(user?.name)}
            </button>
            {(profileHover || profilePinned) && (
              <div className="profile-card" role="dialog" aria-label="Account details">
                <div className="profile-card-avatar">{initials(user?.name)}</div>
                <strong>{user?.name || 'Signed in'}</strong>
                <span>{user?.email || '—'}</span>
                <p>{hotelName}{hotel?.city ? ` · ${hotel.city}` : ''}</p>
                <button className="text-button" onClick={() => { setProfilePinned(false); go('Settings') }}>
                  Open settings
                </button>
              </div>
            )}
          </div>
        </header>
        <main className="content">
          {active === 'Overview' && (
            <div className="page-heading">
              <div>
                <h1>{greeting()}, {firstName} <span className="wave">✦</span></h1>
                <p className="subheading">{empty ? 'Import a report to see live performance.' : `Here's how ${hotelName} is performing from your imported file, ${firstName}.`}</p>
              </div>
              <div className="heading-actions">
                <button className="button-secondary" onClick={() => setImportOpen(true)}><FileUp size={15} />Import report</button>
                <button className="button-primary" onClick={() => void runForecast()} disabled={forecastBusy || empty}>
                  <Sparkles size={15} />{forecastBusy ? 'Generating…' : 'Run forecast'}
                </button>
              </div>
            </div>
          )}
          {notice && <div className="notice-banner">{notice}<button onClick={() => setNotice('')} aria-label="Dismiss"><X size={14} /></button></div>}
          {error && <div className="error-banner">{error}</div>}
          {loading ? (
            <section className="metrics-grid">
              {[1, 2, 3, 4].map((i) => <article key={i} className="metric-card skeleton" />)}
            </section>
          ) : content}
        </main>
        <footer className="footer">
          <span>© {new Date().getFullYear()} staywise</span>
        </footer>
      </div>
      {importOpen && <ImportModal onClose={() => setImportOpen(false)} onImported={onImported} />}
      {clientOpen && <ClientModal onClose={() => setClientOpen(false)} onCreated={onClientCreated} />}
      <AppChatbot />
    </div>
  )
}
