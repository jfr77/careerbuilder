// Pipeline — kanban across the 5 stages, cards color-coded by role type.
import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api.js'
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

function EntryForm({ initial, onSave, onCancel, saving }) {
  const [form, setForm] = useState({
    company: '', role: '', type: 'other', stage: 'researching', link: '',
    start_date: '', end_date: '', deadline: '', notes: '', ...Object.fromEntries(
      Object.entries(initial || {}).filter(([, v]) => v != null)),
  })
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })
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
        <Field label="Start date"><input className={inputCls} value={form.start_date} onChange={set('start_date')} placeholder="e.g. Oct 2026" /></Field>
        <Field label="End date"><input className={inputCls} value={form.end_date} onChange={set('end_date')} /></Field>
        <Field label="Deadline"><input className={inputCls} value={form.deadline} onChange={set('deadline')} /></Field>
        <Field label="Link"><input className={inputCls} value={form.link} onChange={set('link')} /></Field>
      </div>
      <Field label="Notes"><textarea className={inputCls} rows={2} value={form.notes} onChange={set('notes')} /></Field>
      <div className="flex justify-end gap-2">
        <Btn onClick={onCancel}>Cancel</Btn>
        <Btn variant="primary" disabled={saving || !form.company.trim() || !form.role.trim()}
          onClick={() => onSave({ ...form,
            link: form.link || null, start_date: form.start_date || null,
            end_date: form.end_date || null, deadline: form.deadline || null, notes: form.notes || null })}>
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
        <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-neutral-400">
          {entry.start_date && <span>start {entry.start_date}</span>}
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
          {entry.notes && <p className="text-xs text-neutral-600"><Hi text={entry.notes} q={highlight} /></p>}
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

  return (
    <div>
      <PageHead title="Pipeline" sub={`${entries.length} applications · ${profile.name}`}>
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
