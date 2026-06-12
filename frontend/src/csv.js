// CSV import/export for the pipeline — maps common spreadsheet column names
// onto the application model so an Excel tracker migrates in one step.
// Export uses the exact field names, so export → re-import is lossless.
import Papa from 'papaparse'

export const EXPORT_FIELDS = [
  'company', 'role', 'type', 'stage', 'link', 'start_date', 'end_date',
  'deadline', 'reached_out', 'notes', 'salary_range', 'source', 'cv_version',
  'cover_letter_version', 'contact_name', 'contact_email', 'contact_role',
  'referral', 'referral_name', 'follow_up_date', 'response_date',
  'interviews', 'excitement',
]

// normalized header -> field. Exact field names map to themselves (lossless
// round trip); the rest covers what application spreadsheets typically use.
const HEADER_ALIASES = {
  employer: 'company', firma: 'company', unternehmen: 'company',
  position: 'role', jobtitle: 'role', title: 'role', job: 'role', rolle: 'role',
  status: 'stage',
  category: 'type',
  url: 'link', joblink: 'link', posting: 'link',
  startdate: 'start_date', start: 'start_date',
  enddate: 'end_date',
  duedate: 'deadline', due: 'deadline', bewerbungsfrist: 'deadline',
  comments: 'notes', bemerkung: 'notes', notizen: 'notes',
  salary: 'salary_range', salaryrange: 'salary_range', gehalt: 'salary_range',
  foundvia: 'source', wherefound: 'source', quelle: 'source',
  cv: 'cv_version', cvversion: 'cv_version', resume: 'cv_version',
  coverletter: 'cover_letter_version', coverletterversion: 'cover_letter_version',
  anschreiben: 'cover_letter_version',
  contact: 'contact_name', contactname: 'contact_name', recruiter: 'contact_name',
  ansprechpartner: 'contact_name',
  email: 'contact_email', contactemail: 'contact_email',
  contactrole: 'contact_role',
  referralname: 'referral_name',
  followup: 'follow_up_date', followupdate: 'follow_up_date',
  response: 'response_date', responsedate: 'response_date', heardback: 'response_date',
  rating: 'excitement', priority: 'excitement',
  reachedout: 'reached_out',
}
for (const f of EXPORT_FIELDS) HEADER_ALIASES[f.replaceAll('_', '')] = f

const STAGE_ALIASES = {
  applied: 'applied', bewerbung: 'applied', beworben: 'applied',
  interview: 'in_progress', interviewing: 'in_progress', inprogress: 'in_progress',
  phonescreen: 'in_progress', in_progress: 'in_progress',
  offer: 'offer', angebot: 'offer',
  rejected: 'rejected', declined: 'rejected', absage: 'rejected', no: 'rejected',
  researching: 'researching', wishlist: 'researching', toapply: 'researching',
  saved: 'researching', interested: 'researching',
}
const TYPES = ['fa', 'analytics', 'consulting', 'vc', 'other']

const norm = (h) => String(h || '').toLowerCase().replace(/[^a-z0-9]/g, '')

function parseDate(v) {
  const s = String(v || '').trim()
  if (!s) return null
  let m = s.match(/^(\d{4})-(\d{2})-(\d{2})/)            // ISO
  if (m) return `${m[1]}-${m[2]}-${m[3]}`
  m = s.match(/^(\d{1,2})\.(\d{1,2})\.(\d{4})$/)         // dd.mm.yyyy
  if (m) return `${m[3]}-${m[2].padStart(2, '0')}-${m[1].padStart(2, '0')}`
  m = s.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/)         // mm/dd/yyyy (US sheets)
  if (m) return `${m[3]}-${m[1].padStart(2, '0')}-${m[2].padStart(2, '0')}`
  return null
}

const parseBool = (v) =>
  ['true', 'yes', 'y', 'x', '1', 'ja'].includes(String(v || '').trim().toLowerCase())

/* One CSV row (header-keyed object) -> pipeline entry payload, or null when
   there's no company/role to anchor it. Unmapped, non-empty columns are
   preserved as "key: value" lines appended to notes — imports never drop data. */
export function rowToEntry(row) {
  const entry = {}
  const leftovers = []
  for (const [header, raw] of Object.entries(row)) {
    const value = String(raw ?? '').trim()
    if (!value) continue
    const field = HEADER_ALIASES[norm(header)]
    if (!field) {
      leftovers.push(`${header}: ${value}`)
      continue
    }
    if (field === 'stage') {
      entry.stage = STAGE_ALIASES[norm(value)] || 'researching'
    } else if (field === 'type') {
      entry.type = TYPES.includes(value.toLowerCase()) ? value.toLowerCase() : 'other'
    } else if (field === 'follow_up_date' || field === 'response_date') {
      const d = parseDate(value)
      if (d) entry[field] = d
      else leftovers.push(`${header}: ${value}`)
    } else if (field === 'referral' || field === 'reached_out') {
      entry[field] = parseBool(value)
    } else if (field === 'excitement') {
      const n = parseInt(value, 10)
      if (n >= 1 && n <= 5) entry.excitement = n
    } else if (field === 'interviews') {
      try { entry.interviews = JSON.parse(value) }
      catch { leftovers.push(`${header}: ${value}`) }
    } else {
      entry[field] = value
    }
  }
  if (!entry.company && !entry.role) return null
  entry.company = entry.company || '(unknown company)'
  entry.role = entry.role || '(unknown role)'
  if (leftovers.length) {
    entry.notes = [entry.notes, ...leftovers].filter(Boolean).join('\n')
  }
  return entry
}

export function parseCsvFile(file) {
  return new Promise((resolve, reject) => {
    Papa.parse(file, {
      header: true,
      skipEmptyLines: 'greedy',
      complete: (res) => resolve(res.data.map(rowToEntry).filter(Boolean)),
      error: reject,
    })
  })
}

export function entriesToCsv(entries) {
  const rows = entries.map((e) =>
    Object.fromEntries(EXPORT_FIELDS.map((f) => {
      let v = e[f]
      if (f === 'interviews') v = v?.length ? JSON.stringify(v) : ''
      if (v === true) v = 'true'
      if (v === false) v = 'false'
      return [f, v ?? '']
    })))
  return Papa.unparse(rows, { columns: EXPORT_FIELDS })
}
