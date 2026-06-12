import { useCallback, useEffect, useState } from 'react'
import { api } from '../api.js'
import { Badge, Btn, inputCls, PageHead, Spinner, useToast } from '../ui.jsx'

const KIND_LABELS = { event: 'Event', career_fair: 'Career fair', certification: 'Certification', course: 'Course' }
const KIND_TONES = { event: 'accent', career_fair: 'sky', certification: 'amber', course: 'violet' }

export default function EventsTab({ profile }) {
  const [events, setEvents] = useState([])
  const [loading, setLoading] = useState(true)
  const [recommending, setRecommending] = useState(false)
  const [kind, setKind] = useState('')
  const [savedOnly, setSavedOnly] = useState(false)
  const toast = useToast()

  const load = useCallback(async () => {
    setLoading(true)
    try { setEvents(await api.get(`/api/events?profile_id=${profile.id}`)) }
    catch (e) { toast(e.message) }
    finally { setLoading(false) }
  }, [profile.id])
  useEffect(() => { load() }, [load])

  const recommend = async () => {
    setRecommending(true)
    try {
      const items = await api.post(`/api/events/recommend?profile_id=${profile.id}`)
      toast(`Got ${items.length} AI suggestions — review them below`, 'info')
      load()
    } catch (e) { toast(e.message) }
    finally { setRecommending(false) }
  }

  const setSaved = async (ev, saved) => {
    try {
      await api.post(`/api/events/${ev.id}/save?profile_id=${profile.id}`, { saved })
      setEvents((es) => es.map((e) => (e.id === ev.id ? { ...e, saved } : e)))
    } catch (e) { toast(e.message) }
  }

  const shown = events.filter((e) => {
    if (kind && e.kind !== kind) return false
    if (savedOnly && !e.saved) return false
    return true
  })

  return (
    <div>
      <PageHead title="Events & Certifications"
        sub={`Fairs, meetups, certs and courses — saves are ${profile.name}'s`}>
        <select className={inputCls + ' w-40'} value={kind} onChange={(e) => setKind(e.target.value)}>
          <option value="">all kinds</option>
          {Object.entries(KIND_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <label className="flex items-center gap-1.5 text-sm text-neutral-600">
          <input type="checkbox" checked={savedOnly} onChange={(e) => setSavedOnly(e.target.checked)} />
          saved only
        </label>
        <Btn variant="accent" onClick={recommend} disabled={recommending}>
          {recommending ? <Spinner label="asking the AI…" /> : '✦ Get recommendations'}
        </Btn>
      </PageHead>

      {loading ? <Spinner label="loading events…" /> : (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          {shown.length === 0 && (
            <div className="card col-span-full p-12 text-center">
              <p className="display text-lg text-neutral-400">Nothing here</p>
              <p className="mt-1 text-sm text-neutral-400">Adjust filters or get AI recommendations.</p>
            </div>
          )}
          {shown.map((e) => (
            <div key={e.id} className="card card-hover flex flex-col p-4">
              <div className="mb-1 flex items-start justify-between gap-2">
                <Badge tone={KIND_TONES[e.kind]}>{KIND_LABELS[e.kind]}</Badge>
                {e.source === 'llm' && <Badge tone="amber">AI — verify</Badge>}
              </div>
              {e.url
                ? <a href={e.url} target="_blank" rel="noreferrer" className="display font-semibold leading-snug hover:text-accent-deep hover:underline">{e.title}</a>
                : <span className="display font-semibold leading-snug">{e.title}</span>}
              <div className="mt-1 text-sm text-neutral-500">
                {[e.provider, e.location, e.date, e.cost].filter(Boolean).join(' · ')}
              </div>
              {e.relevance_note && <p className="mt-2 text-sm text-neutral-600">{e.relevance_note}</p>}
              <div className="mt-auto pt-3">
                {e.saved
                  ? <Btn onClick={() => setSaved(e, false)}>Saved ✓</Btn>
                  : <Btn variant="primary" onClick={() => setSaved(e, true)}>Save</Btn>}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
