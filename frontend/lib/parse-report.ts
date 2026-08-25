type Row = Record<string, unknown>

const splitCsvLine = (line: string) => {
  const cells: string[] = []
  let current = ''
  let quoted = false
  for (let i = 0; i < line.length; i += 1) {
    const char = line[i]
    if (char === '"') {
      if (quoted && line[i + 1] === '"') {
        current += '"'
        i += 1
      } else {
        quoted = !quoted
      }
    } else if (char === ',' && !quoted) {
      cells.push(current.trim())
      current = ''
    } else {
      current += char
    }
  }
  cells.push(current.trim())
  return cells
}

const parseCsv = (text: string): Row[] => {
  const lines = text.split(/\r?\n/).filter((line) => line.trim())
  if (!lines.length) return []
  const headers = splitCsvLine(lines[0]).map((header) => header.replace(/^"|"$/g, ''))
  return lines.slice(1).map((line) => {
    const values = splitCsvLine(line)
    const row: Row = {}
    headers.forEach((header, index) => {
      row[header] = values[index] ?? ''
    })
    return row
  })
}

const unwrapJson = (raw: unknown): Row[] => {
  if (Array.isArray(raw)) return raw.filter((item) => item && typeof item === 'object') as Row[]
  if (raw && typeof raw === 'object') {
    const maybe = raw as { rows?: unknown; data?: unknown }
    if (Array.isArray(maybe.rows)) return maybe.rows as Row[]
    if (Array.isArray(maybe.data)) return maybe.data as Row[]
  }
  return []
}

export async function parseReportFile(file: File): Promise<Row[]> {
  const name = file.name.toLowerCase()
  if (name.endsWith('.json')) {
    const parsed = JSON.parse(await file.text())
    const rows = unwrapJson(parsed)
    if (!rows.length) throw new Error('No data rows found in the JSON file.')
    return rows
  }
  if (name.endsWith('.csv')) {
    const rows = parseCsv(await file.text())
    if (!rows.length) throw new Error('No data rows found in the CSV file.')
    return rows
  }
  if (name.endsWith('.xlsx') || name.endsWith('.xls')) {
    const XLSX = await import('xlsx')
    const workbook = XLSX.read(await file.arrayBuffer(), { type: 'array' })
    const sheet = workbook.Sheets[workbook.SheetNames[0]]
    const rows = XLSX.utils.sheet_to_json<Row>(sheet)
    if (!rows.length) throw new Error('No data rows found in the Excel file.')
    return rows
  }
  throw new Error('Upload a .xlsx, .csv, or .json file.')
}
