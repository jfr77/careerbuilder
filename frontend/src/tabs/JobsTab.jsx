// Discover — the shared scraped jobs pool, scored per profile.
// Scraper sources and constraints are fully user-defined (no hardcoded filters).
import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api.js'
import { Badge, Btn, FitRing, inputCls, Modal, PageHead, Spinner, useToast } from '../ui.jsx'

function ScraperSettingsModal({ onClose }) {
  const [lists, setLists] = useState(null)
  const [slug, setSlug] = useState('')
  const [source, setSource] = useState('join')
  const toast = useToast()

  const load = () => {
    api.get('/api/scrape/watchlist').then(setLists).catch((e) => toast(e.message))
  }
  useEffect(() => { load() }, [])

  const addSlug = async () => {
    if (!slug.trim()) return
    try {
      await api.post(`/api/scrape/watchlist/${source}`, { slug: slug.trim() })
      setSlug(''); load()
    } catch (e) { toast(e.message) }
  }
  const removeSlug = async (src, s) => {
    try { await api.del(`/api/scrape/watchlist/${src}/${encodeURIComponent(s)}`); load() }
    catch (e) { toast(e.message) }
  }

  return (
    <Modal title="Scraper settings" onClose={onClose} wide>
      {!lists ? <Spinner label="loading…" /> : (
        <div className="space-y-6">
          <section>
            <h3 className="microlabel mb-2">Company watchlists (global)</h3>
            <p className="mb-3 text-xs text-neutral-500">
              Scraping ingests <span className="font-semibold text-ink">every posting</span> from your
              watchlisted companies — narrowing down happens with the filters above the job list.
            </p>
            <div className="space-y-3">
              {['join', 'personio'].map((src) => (
                <div key={src} className="rounded-xl border border-line p-3">
                  <p className="mb-2 text-xs text-neutral-500">
                    <span className="font-semibold capitalize text-ink">{src}</span>
                    {src === 'join' ? ' — join.com/companies/<slug>' : ' — <slug>.jobs.personio.de'}
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {lists[src].length === 0 && <span className="text-xs text-neutral-400">no companies yet</span>}
                    {lists[src].map((s) => (
                      <span key={s} className="inline-flex items-center gap-1 rounded-md bg-black/5 px-2 py-1 text-xs font-medium">
                        {s}
                        <button className="opacity-50 hover:opacity-100" onClick={() => removeSlug(src, s)}>✕</button>
                      </span>
                    ))}
                  </div>
                </div>
              ))}
              <div className="flex gap-2">
                <select className={inputCls + ' w-32'} value={source} onChange={(e) => setSource(e.target.value)}>
                  <option value="join">join</option>
                  <option value="personio">personio</option>
                </select>
                <input className={inputCls} placeholder="company-slug" value={slug}
                  onChange={(e) => setSlug(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && addSlug()} />
                <Btn variant="primary" onClick={addSlug}>Add</Btn>
              </div>
            </div>
          </section>
        </div>
      )}
    </Modal>
  )
}

export default function JobsTab({ profile }) {
  const [jobs, setJobs] = useState([])
  const [loading, setLoading] = useState(true)
  const [scrape, setScrape] = useState(null)
  const [scoringAll, setScoringAll] = useState(false)
  const [scoringIds, setScoringIds] = useState(new Set())
  const [showSettings, setShowSettings] = useState(false)
  const [filters, setFilters] = useState({ source: '', company: '', employment: '', minFit: '', q: '' })
  const toast = useToast()
  const pollRef = useRef(null)

  const load = useCallback(async () => {
    setLoading(true)
    try { setJobs(await api.get(`/api/jobs?profile_id=${profile.id}`)) }
    catch (e) { toast(e.message) }
    finally { setLoading(false) }
  }, [profile.id])

  useEffect(() => { load() }, [load])
  useEffect(() => () => clearInterval(pollRef.current), [])

  const runScrapers = async () => {
    try {
      await api.post('/api/scrape/run')
    } catch (e) {
      if (e.status !== 409) { toast(e.message); return }
    }
    pollRef.current = setInterval(async () => {
      try {
        const st = await api.get('/api/scrape/status')
        setScrape(st)
        if (!st.running) {
          clearInterval(pollRef.current)
          setTimeout(() => setScrape(null), 8000)
          load()
          if (st.error) toast(`Scrape failed: ${st.error}`)
          else toast(`Scrape done — ${st.new_jobs} new job(s)`, 'info')
        }
      } catch { /* keep polling */ }
    }, 1500)
  }

  const scoreOne = async (jobId) => {
    setScoringIds((s) => new Set([...s, jobId]))
    try {
      const updated = await api.post(`/api/jobs/${jobId}/score?profile_id=${profile.id}`)
      setJobs((js) => js.map((j) => (j.id === jobId ? updated : j)))
    } catch (e) { toast(e.message) }
    finally { setScoringIds((s) => { const n = new Set(s); n.delete(jobId); return n }) }
  }

  const scoreAll = async () => {
    setScoringAll(true)
    try {
      let res
      do {
        res = await api.post(`/api/jobs/score-unscored?profile_id=${profile.id}&limit=10`)
        await load()
        if (res.errors?.length) toast(res.errors.join('; '))
      } while (res.remaining)
      toast('Scoring complete', 'info')
    } catch (e) { toast(e.message) }
    finally { setScoringAll(false) }
  }

  const addToPipeline = async (jobId) => {
    try {
      const r = await api.post(`/api/jobs/${jobId}/add-to-pipeline?profile_id=${profile.id}`)
      toast(`Added ${r.company} — ${r.role} to pipeline`, 'info')
    } catch (e) { toast(e.message) }
  }

  const unscored = jobs.filter((j) => j.fit_score == null).length
  const shown = jobs.filter((j) => {
    if (filters.source && j.source !== filters.source) return false
    if (filters.company && j.company !== filters.company) return false
    if (filters.employment && j.employment !== filters.employment) return false
    if (filters.minFit && (j.fit_score == null || j.fit_score < Number(filters.minFit))) return false
    if (filters.q) {
      const hay = `${j.title} ${j.company} ${j.location ?? ''} ${j.department ?? ''}`.toLowerCase()
      if (!hay.includes(filters.q.toLowerCase())) return false
    }
    return true
  })
  const companies = [...new Set(jobs.map((j) => j.company))].sort()
  const employments = [...new Set(jobs.map((j) => j.employment).filter(Boolean))].sort()

  return (
    <div>
      <PageHead title="Discover"
        sub={`${jobs.length} open postings from your sources · fit scores are ${profile.name}'s`}>
        <Btn onClick={() => setShowSettings(true)}>Scraper settings</Btn>
        <Btn onClick={scoreAll} disabled={scoringAll || unscored === 0}>
          {scoringAll ? <Spinner label="scoring…" /> : `Score new${unscored ? ` (${unscored})` : ''}`}
        </Btn>
        <Btn variant="accent" onClick={runScrapers} disabled={scrape?.running}>
          {scrape?.running ? 'Scraping…' : 'Run scrapers'}
        </Btn>
      </PageHead>

      {scrape && (
        <div className="card mb-4 p-4 text-xs">
          <div className="mb-1.5 flex items-center justify-between">
            <span className="font-semibold">
              Scraping {scrape.companies_done}/{scrape.companies_total || '…'} companies · {scrape.new_jobs} new
            </span>
            {scrape.running && <Spinner label="" />}
          </div>
          <div className="h-1.5 overflow-hidden rounded-full bg-line">
            <div className="h-full rounded-full bg-accent transition-all"
              style={{ width: `${scrape.companies_total ? (scrape.companies_done / scrape.companies_total) * 100 : 5}%` }} />
          </div>
          <div className="mt-2 max-h-20 overflow-y-auto font-mono text-neutral-400">
            {scrape.log.slice(-4).map((l, i) => <div key={i}>{l}</div>)}
          </div>
        </div>
      )}

      <div className="mb-5 flex flex-wrap gap-2">
        <input className={inputCls + ' max-w-xs flex-1'} placeholder="Search title, company, location…"
          value={filters.q} onChange={(e) => setFilters({ ...filters, q: e.target.value })} />
        <select className={inputCls + ' w-32'} value={filters.source} onChange={(e) => setFilters({ ...filters, source: e.target.value })}>
          <option value="">source</option>
          <option value="join">join</option>
          <option value="personio">personio</option>
          <option value="manual">manual</option>
        </select>
        <select className={inputCls + ' w-44'} value={filters.company} onChange={(e) => setFilters({ ...filters, company: e.target.value })}>
          <option value="">company</option>
          {companies.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
        <select className={inputCls + ' w-44'} value={filters.employment} onChange={(e) => setFilters({ ...filters, employment: e.target.value })}>
          <option value="">employment</option>
          {employments.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
        <select className={inputCls + ' w-28'} value={filters.minFit} onChange={(e) => setFilters({ ...filters, minFit: e.target.value })}>
          <option value="">min fit</option>
          {[5, 6, 7, 8, 9].map((n) => <option key={n} value={n}>≥ {n}</option>)}
        </select>
      </div>

      {loading ? <Spinner label="loading jobs…" /> : shown.length === 0 ? (
        <div className="card p-12 text-center">
          <p className="display text-lg text-neutral-400">
            {jobs.length === 0 ? 'The pool is empty' : 'Nothing matches these filters'}
          </p>
          <p className="mt-1 text-sm text-neutral-400">
            {jobs.length === 0
              ? 'Add companies in Scraper settings, then hit “Run scrapers”.'
              : 'Loosen a filter or two.'}
          </p>
        </div>
      ) : (
        <div className="space-y-2.5">
          {shown.map((j) => (
            <div key={j.id} className="card card-hover p-4">
              <div className="flex items-start gap-4">
                <FitRing score={j.fit_score} />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <a href={j.url} target="_blank" rel="noreferrer"
                      className="font-semibold hover:text-accent-deep hover:underline">{j.title}</a>
                    <Badge>{j.source}</Badge>
                    {j.employment && <Badge tone="accent">{j.employment}</Badge>}
                  </div>
                  <div className="mt-0.5 text-sm text-neutral-500">
                    {j.company}{j.location ? ` · ${j.location}` : ''}{j.department ? ` · ${j.department}` : ''}
                  </div>
                  {j.fit_note && <p className="mt-1.5 text-sm text-neutral-600">{j.fit_note}</p>}
                  {j.fit_breakdown && (
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {Object.entries(j.fit_breakdown).map(([k, v]) => (
                        <Badge key={k}>{k.replaceAll('_', ' ')} {v}</Badge>
                      ))}
                    </div>
                  )}
                </div>
                <div className="flex shrink-0 flex-col items-end gap-1.5">
                  <Btn variant="primary" onClick={() => addToPipeline(j.id)}>Add to pipeline</Btn>
                  <Btn variant="ghost" onClick={() => scoreOne(j.id)} disabled={scoringIds.has(j.id)}>
                    {scoringIds.has(j.id) ? 'scoring…' : j.fit_score == null ? 'Score' : 'Re-score'}
                  </Btn>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {showSettings && <ScraperSettingsModal onClose={() => { setShowSettings(false); load() }} />}
    </div>
  )
}
