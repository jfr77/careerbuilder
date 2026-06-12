// Pipeline — kanban across the 5 stages, cards color-coded by role type.
import { useCallback, useEffect, useRef, useState } from 'react'
import { api, downloadText } from '../api.js'
import { entriesToCsv, parseCsvFile } from '../csv.js'
import { Badge, Btn, Field, inputCls, Modal, PageHead, Spinner, useToast } from '../ui.jsx'

/* Highlight the search substring inside card text. */
function Hi({ text, q }) {
  if (!q || !text) return text || null
  const i = text.toLowerCase().indexOf(q.toLowerCase())
  if (i === -1) return text
  return (
    <>
      {text.slice(0, i)}
      <mark className="rounded-sm bg-amber-200/80 px-0.5">{text.slice(i, i + q.length)}</mark>
      {text.slice(i + q.length)}
    </>
  )
}

/* Search matches company, role, notes and contact name (when present). */
const cardHaystack = (e) =>
  `${e.company} ${e.role} ${e.notes || ''} ${e.contact_name || ''}`.toLowerCase()

const STAGES = [
  { id: 'researching', label: 'Researching' },
  { id: 'applied', label: 'Applied' },
  { id: 'in_progress', label: 'In Progress' },
  { id: 'offer', label: 'Offer' },
  { id: 'rejected', label: 'Rejected' },
]
const TYPES = ['fa', 'analytics', 'consulting', 'vc', 'other']
const TYPE_TONES = { fa: 'accent', analytics: 'sky', consulting: 'amber', vc: 'violet', other: 'neutral' }
const TYPE_BAR = { fa: '#0e8a64', analytics: '#0369a1', consulting: '#b45309', vc: '#6d28d9', other: '#9ca3af' }

/* Collapsible form/detail section. */
function Section({ title, defaultOpen = false, children }) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="rounded-xl border border-line">
      <button type="button"
        className="flex w-full items-center justify-between px-3 py-2 text-left"
        onClick={() => setOpen(!open)}>
        <span className="microlabel">{title}</span>
        <span className="text-xs text-neutral-400">{open ? '−' : '+'}</span>
      </button>
      {open && <div className="space-y-3 border-t border-line p-3">{children}</div>}
    </div>
  )
}

/* 1-5 excitement rating as clickable stars. */
function Stars({ value, onChange, size = 'text-base' }) {
  return (
    <span className={`inline-flex ${size} leading-none`}>
      {[1, 2, 3, 4, 5].map((n) => (
        <button key={n} type="button"
          className={n <= (value || 0) ? 'text-amber-500' : 'text-neutral-300'}
          onClick={onChange ? (e) => { e.stopPropagation(); onChange(n === value ? null : n) } : undefined}
          disabled={!onChange}>
          ★
        </button>
      ))}
    </span>
  )
}

const isDue = (e) => e.follow_up_date && e.follow_up_date <= new Date().toISOString().slice(0, 10)

const EMPTY_FORM = {
  company: '', role: '', type: 'other', stage: 'researching', link: '',
  start_date: '', end_date: '', deadline: '', notes: '',
  salary_range: '', source: '', cv_version: '', cover_letter_version: '',
  contact_name: '', contact_email: '', contact_role: '',
  referral: false, referral_name: '', follow_up_date: '', response_date: '',
  interviews: [], excitement: null,
}

function EntryForm({ initial, onSave, onCancel, saving }) {
  const [form, setForm] = useState({
    ...EMPTY_FORM,
    ...Object.fromEntries(Object.entries(initial || {}).filter(([, v]) => v != null)),
  })
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })
  const setV = (k, v) => setForm((f) => ({ ...f, [k]: v }))

  const setInterview = (i, k, v) => setV('interviews',
    form.interviews.map((iv, n) => (n === i ? { ...iv, [k]: v } : iv)))

  const submit = () => {
    const out = { ...form }
    for (const k of Object.keys(out)) {
      if (out[k] === '') out[k] = null
    }
    out.interviews = form.interviews?.length ? form.interviews : null
    onSave(out)
  }

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-3">
        <Field label="Company"><input className={inputCls} value={form.company} onChange={set('company')} /></Field>
        <Field label="Role"><input className={inputCls} value={form.role} onChange={set('role')} /></Field>
        <Field label="Type">
          <select className={inputCls} value={form.type} onChange={set('type')}>
            {TYPES.map((t) => <option key={t}>{t}</option>)}
          </select>
        </Field>
        <Field label="Stage">
          <select className={inputCls} value={form.stage} onChange={set('stage')}>
            {STAGES.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
          </select>
        </Field>
      </div>

      <Section title="Details" defaultOpen>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Link"><input className={inputCls} value={form.link} onChange={set('link')} /></Field>
          <Field label="Salary range"><input className={inputCls} value={form.salary_range} onChange={set('salary_range')} placeholder="e.g. 2.200-2.600 €/month" /></Field>
          <Field label="Source (where found)">
            <select className={inputCls} value={form.source} onChange={set('source')}>
              <option value="">—</option>
              {['join', 'personio', 'linkedin', 'referral', 'other'].map((s) => <option key={s}>{s}</option>)}
            </select>
          </Field>
          <Field label="Excitement"><Stars value={form.excitement} onChange={(v) => setV('excitement', v)} /></Field>
        </div>
        <Field label="Notes"><textarea className={inputCls} rows={2} value={form.notes} onChange={set('notes')} /></Field>
      </Section>

      <Section title="Contact">
        <div className="grid grid-cols-2 gap-3">
          <Field label="Contact name"><input className={inputCls} value={form.contact_name} onChange={set('contact_name')} /></Field>
          <Field label="Contact email"><input className={inputCls} value={form.contact_email} onChange={set('contact_email')} /></Field>
          <Field label="Contact role"><input className={inputCls} value={form.contact_role} onChange={set('contact_role')} placeholder="e.g. recruiter, founder" /></Field>
          <Field label="Referral">
            <span className="flex items-center gap-2 pt-2 text-sm">
              <input type="checkbox" checked={!!form.referral} onChange={(e) => setV('referral', e.target.checked)} />
              <input className={inputCls} placeholder="referred by…" value={form.referral_name}
                onChange={set('referral_name')} disabled={!form.referral} />
            </span>
          </Field>
        </div>
      </Section>

      <Section title="Documents">
        <div className="grid grid-cols-2 gap-3">
          <Field label="CV version sent"><input className={inputCls} value={form.cv_version} onChange={set('cv_version')} placeholder="e.g. cv_2026_data.pdf" /></Field>
          <Field label="Cover letter version"><input className={inputCls} value={form.cover_letter_version} onChange={set('cover_letter_version')} /></Field>
        </div>
      </Section>

      <Section title="Interviews">
        {(form.interviews || []).map((iv, i) => (
          <div key={i} className="grid grid-cols-[60px_1fr_1fr_2fr_28px] items-center gap-2">
            <input className={inputCls + ' !px-2'} placeholder="round" value={iv.round ?? ''}
              onChange={(e) => setInterview(i, 'round', e.target.value)} />
            <input className={inputCls + ' !px-2'} placeholder="type (phone, case…)" value={iv.type ?? ''}
              onChange={(e) => setInterview(i, 'type', e.target.value)} />
            <input type="date" className={inputCls + ' !px-2'} value={iv.date ?? ''}
              onChange={(e) => setInterview(i, 'date', e.target.value)} />
            <input className={inputCls + ' !px-2'} placeholder="notes" value={iv.notes ?? ''}
              onChange={(e) => setInterview(i, 'notes', e.target.value)} />
            <button className="text-neutral-400 hover:text-red-600"
              onClick={() => setV('interviews', form.interviews.filter((_, n) => n !== i))}>✕</button>
          </div>
        ))}
        <Btn className="!px-2 !py-1 !text-xs"
          onClick={() => setV('interviews', [...(form.interviews || []), { round: String((form.interviews?.length || 0) + 1), type: '', date: '', notes: '' }])}>
          + Add interview
        </Btn>
      </Section>

      <Section title="Dates">
        <div className="grid grid-cols-2 gap-3">
          <Field label="Start date"><input className={inputCls} value={form.start_date} onChange={set('start_date')} placeholder="e.g. Oct 2026" /></Field>
          <Field label="End date"><input className={inputCls} value={form.end_date} onChange={set('end_date')} /></Field>
          <Field label="Application deadline"><input className={inputCls} value={form.deadline} onChange={set('deadline')} /></Field>
          <Field label="Follow up on"><input type="date" className={inputCls} value={form.follow_up_date} onChange={set('follow_up_date')} /></Field>
          <Field label="Response received"><input type="date" className={inputCls} value={form.response_date} onChange={set('response_date')} /></Field>
        </div>
      </Section>

      <div className="flex justify-end gap-2">
        <Btn onClick={onCancel}>Cancel</Btn>
        <Btn variant="primary" disabled={saving || !form.company.trim() || !form.role.trim()} onClick={submit}>
          Save
        </Btn>
      </div>
    </div>
  )
}

function Card({ entry, onMove, onUpdate, onDelete, onGenerateDoc, onEdit, highlight }) {
  const [open, setOpen] = useState(false)
  const idx = STAGES.findIndex((s) => s.id === entry.stage)
  const docCount = Object.values(entry.documents || {}).reduce((n, arr) => n + (arr?.length || 0), 0)
  return (
    <div className="card card-hover overflow-hidden text-sm"
      style={{ borderLeft: `3px solid ${TYPE_BAR[entry.type]}` }}>
      <div className="cursor-pointer p-3" onClick={() => setOpen(!open)}>
        <div className="flex items-center justify-between gap-2">
          <span className="display truncate font-semibold"><Hi text={entry.company} q={highlight} /></span>
          <Badge tone={TYPE_TONES[entry.type]}>{entry.type}</Badge>
        </div>
        <div className="truncate text-neutral-600"><Hi text={entry.role} q={highlight} /></div>
        <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-neutral-400">
          {entry.excitement && <Stars value={entry.excitement} size="text-xs" />}
          {isDue(entry) && <Badge tone="red">follow up due</Badge>}
          {entry.deadline && <span className="font-medium text-amber-600">due {entry.deadline}</span>}
          {entry.reached_out && <span className="text-accent-deep">reached out ✓</span>}
          {docCount > 0 && <span>{docCount} doc{docCount > 1 ? 's' : ''}</span>}
        </div>
      </div>
      {open && (
        <div className="space-y-2 border-t border-line bg-paper/40 p-3">
          {entry.link && (
            <a className="block truncate text-xs text-accent-deep hover:underline" href={entry.link} target="_blank" rel="noreferrer">{entry.link}</a>
          )}
          {entry.notes && <p className="whitespace-pre-wrap text-xs text-neutral-600"><Hi text={entry.notes} q={highlight} /></p>}
          <div className="space-y-0.5 text-xs text-neutral-500">
            {entry.salary_range && <div>salary: {entry.salary_range}</div>}
            {entry.source && <div>found via: {entry.source}</div>}
            {entry.contact_name && (
              <div>
                contact: <Hi text={entry.contact_name} q={highlight} />
                {entry.contact_role ? ` (${entry.contact_role})` : ''}
                {entry.contact_email ? ` · ${entry.contact_email}` : ''}
              </div>
            )}
            {entry.referral && <div>referral{entry.referral_name ? `: ${entry.referral_name}` : ' ✓'}</div>}
            {(entry.cv_version || entry.cover_letter_version) && (
              <div>sent: {[entry.cv_version, entry.cover_letter_version].filter(Boolean).join(' + ')}</div>
            )}
            {entry.follow_up_date && <div className={isDue(entry) ? 'font-medium text-red-600' : ''}>follow up {entry.follow_up_date}</div>}
            {entry.response_date && <div>response {entry.response_date}</div>}
            {(entry.interviews || []).map((iv, i) => (
              <div key={i}>interview {iv.round || i + 1}{iv.type ? ` (${iv.type})` : ''}{iv.date ? ` ${iv.date}` : ''}{iv.notes ? ` — ${iv.notes}` : ''}</div>
            ))}
          </div>
          <label className="flex items-center gap-1.5 text-xs text-neutral-600">
            <input type="checkbox" checked={entry.reached_out}
              onChange={(e) => onUpdate(entry.id, { reached_out: e.target.checked })} />
            reached out
          </label>
          <div className="flex flex-wrap gap-1">
            {idx > 0 && <Btn className="!px-2 !py-1 !text-xs" onClick={() => onMove(entry, -1)}>← {STAGES[idx - 1].label}</Btn>}
            {idx < STAGES.length - 1 && <Btn className="!px-2 !py-1 !text-xs" onClick={() => onMove(entry, 1)}>{STAGES[idx + 1].label} →</Btn>}
          </div>
          <div className="flex flex-wrap gap-1">
            <Btn className="!px-2 !py-1 !text-xs" onClick={() => onGenerateDoc({ kind: 'cover_letter', pipelineId: entry.id })}>✦ Cover letter</Btn>
            <Btn className="!px-2 !py-1 !text-xs" onClick={() => onGenerateDoc({ kind: 'cv', pipelineId: entry.id })}>✦ Tailor CV</Btn>
            <Btn className="!px-2 !py-1 !text-xs" onClick={() => onEdit(entry)}>Edit</Btn>
            <Btn variant="danger" className="!px-2 !py-1 !text-xs" onClick={() => onDelete(entry)}>Delete</Btn>
          </div>
        </div>
      )}
    </div>
  )
}

export default function PipelineTab({ profile, onGenerateDoc }) {
  const [entries, setEntries] = useState([])
  const [loading, setLoading] = useState(true)
  const [showAdd, setShowAdd] = useState(false)
  const [editing, setEditing] = useState(null)
  const [pasteOpen, setPasteOpen] = useState(false)
  const [pasteText, setPasteText] = useState('')
  const [extracting, setExtracting] = useState(false)
  const [extracted, setExtracted] = useState(null)
  const [saving, setSaving] = useState(false)
  const [search, setSearch] = useState('')        // raw input
  const [query, setQuery] = useState('')          // debounced, drives matching
  const searchRef = useRef(null)
  const toast = useToast()

  // ~200ms debounce keeps typing instant even with hundreds of cards
  useEffect(() => {
    const t = setTimeout(() => setQuery(search.trim()), 200)
    return () => clearTimeout(t)
  }, [search])

  const load = useCallback(async () => {
    setLoading(true)
    try { setEntries(await api.get(`/api/pipeline?profile_id=${profile.id}`)) }
    catch (e) { toast(e.message) }
    finally { setLoading(false) }
  }, [profile.id])
  useEffect(() => { load() }, [load])

  const create = async (form) => {
    setSaving(true)
    try {
      await api.post(`/api/pipeline?profile_id=${profile.id}`, form)
      setShowAdd(false); setExtracted(null); setPasteOpen(false); setPasteText('')
      load()
    } catch (e) { toast(e.message) }
    finally { setSaving(false) }
  }

  const update = async (id, patch) => {
    try {
      const updated = await api.patch(`/api/pipeline/${id}`, patch)
      setEntries((es) => es.map((e) => (e.id === id ? updated : e)))
    } catch (e) { toast(e.message) }
  }

  const move = (entry, dir) => {
    const idx = STAGES.findIndex((s) => s.id === entry.stage)
    const next = STAGES[idx + dir]
    if (next) update(entry.id, { stage: next.id })
  }

  const remove = async (entry) => {
    if (!confirm(`Delete ${entry.company} — ${entry.role}?`)) return
    try { await api.del(`/api/pipeline/${entry.id}`); load() }
    catch (e) { toast(e.message) }
  }

  const extract = async () => {
    setExtracting(true)
    try {
      const data = await api.post('/api/pipeline/extract', { text: pasteText })
      setExtracted({ ...data, stage: 'researching' })
    } catch (e) { toast(e.message) }
    finally { setExtracting(false) }
  }

  const importCsv = async (file) => {
    if (!file) return
    try {
      const rows = await parseCsvFile(file)
      if (rows.length === 0) { toast('No importable rows found (need at least a company or role column)'); return }
      const res = await api.post(`/api/pipeline/import?profile_id=${profile.id}`, { entries: rows })
      toast(`Imported ${res.created} application(s)`, 'info')
      load()
    } catch (e) { toast(`Import failed: ${e.message}`) }
  }

  const exportCsv = () => {
    downloadText('pipeline.csv', entriesToCsv(entries))
  }

  const dueCount = entries.filter(isDue).length

  return (
    <div>
      <PageHead title="Pipeline" sub={`${entries.length} applications · ${profile.name}`}>
        {dueCount > 0 && (
          <span className="rounded-lg bg-red-50 px-2.5 py-1.5 text-xs font-semibold text-red-700">
            {dueCount} follow-up{dueCount > 1 ? 's' : ''} due today
          </span>
        )}
        <label className="cursor-pointer">
          <span className="inline-block rounded-lg border border-line bg-white px-3.5 py-2 text-sm font-medium transition-colors hover:border-neutral-400">
            Import CSV
          </span>
          <input type="file" accept=".csv,text/csv" className="hidden"
            onChange={(e) => { importCsv(e.target.files?.[0]); e.target.value = '' }} />
        </label>
        <Btn onClick={exportCsv} disabled={entries.length === 0}>Export CSV</Btn>
        <Btn onClick={() => setPasteOpen(true)}>Paste posting…</Btn>
        <Btn variant="primary" onClick={() => setShowAdd(true)}>+ Add entry</Btn>
      </PageHead>

      <div className="relative mb-4 max-w-md">
        <input ref={searchRef} className={inputCls + ' pr-9'}
          placeholder="Search applications… (company, role, notes, contact)"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Escape') { setSearch(''); setQuery('') } }} />
        {search && (
          <button
            className="absolute right-2.5 top-1/2 -translate-y-1/2 text-neutral-400 hover:text-ink"
            onClick={() => { setSearch(''); setQuery(''); searchRef.current?.focus() }}>
            ✕
          </button>
        )}
      </div>

      {loading ? <Spinner label="loading pipeline…" /> : (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3 xl:grid-cols-5">
          {STAGES.map((stage) => {
            const col = entries.filter((e) => e.stage === stage.id)
            const matching = query ? col.filter((e) => cardHaystack(e).includes(query.toLowerCase())) : col
            return (
              <div key={stage.id} className="rounded-2xl bg-black/[0.035] p-2">
                <div className="mb-2 flex items-center justify-between px-1.5 pt-1">
                  <h3 className="microlabel">{stage.label}</h3>
                  <span className="rounded-md bg-white px-1.5 text-xs font-semibold text-neutral-500">
                    {query ? `${matching.length}/${col.length}` : col.length}
                  </span>
                </div>
                <div className="space-y-2">
                  {matching.map((e) => (
                    <Card key={e.id} entry={e} onMove={move} onUpdate={update}
                      onDelete={remove} onGenerateDoc={onGenerateDoc} onEdit={setEditing}
                      highlight={query} />
                  ))}
                </div>
              </div>
            )
          })}
        </div>
      )}

      {showAdd && (
        <Modal title="Add pipeline entry" onClose={() => setShowAdd(false)} wide>
          <EntryForm onSave={create} onCancel={() => setShowAdd(false)} saving={saving} />
        </Modal>
      )}
      {editing && (
        <Modal title={`Edit ${editing.company}`} onClose={() => setEditing(null)} wide>
          <EntryForm initial={editing} saving={saving} onCancel={() => setEditing(null)}
            onSave={async (form) => { await update(editing.id, form); setEditing(null) }} />
        </Modal>
      )}
      {pasteOpen && (
        <Modal title="Paste a job posting" onClose={() => { setPasteOpen(false); setExtracted(null) }} wide>
          {!extracted ? (
            <div className="space-y-3">
              <p className="text-sm text-neutral-500">
                Paste the raw posting text and/or URL — the AI extracts company, role, type and dates
                into an editable form before anything is saved.
              </p>
              <textarea className={inputCls} rows={10} value={pasteText}
                onChange={(e) => setPasteText(e.target.value)}
                placeholder="Paste job posting text or URL here…" />
              <div className="flex justify-end">
                <Btn variant="accent" onClick={extract} disabled={extracting || pasteText.trim().length < 10}>
                  {extracting ? <Spinner label="extracting…" /> : 'Extract fields'}
                </Btn>
              </div>
            </div>
          ) : (
            <EntryForm initial={extracted} onSave={create} saving={saving}
              onCancel={() => setExtracted(null)} />
          )}
        </Modal>
      )}
    </div>
  )
}
