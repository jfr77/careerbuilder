// Discover — the shared scraped jobs pool, scored per profile.
// Ingestion is unrestricted; all narrowing happens here at query time:
// structured filter chips, a natural-language prompt, and saved filters
// all feed the same GET /api/jobs query.
import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api.js'
import { Badge, Btn, FitRing, inputCls, Modal, PageHead, Spinner, useToast } from '../ui.jsx'

const FILTER_LABELS = {
  q: 'keyword', location: 'location', employment_type: 'type', source: 'source',
  company: 'company', language: 'language', posted_after: 'posted after',
  status: 'status', remote: 'remote',
}

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

/* Active-filter chips: every set key is one removable chip. */
function FilterChips({ filters, onRemove }) {
  const entries = Object.entries(filters).filter(([, v]) => v !== '' && v != null && v !== false)
  if (entries.length === 0) return null
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {entries.map(([k, v]) => (
        <span key={k} className="inline-flex items-center gap-1 rounded-md bg-accent-soft px-2 py-1 text-xs font-medium text-accent-deep">
          <span className="opacity-60">{FILTER_LABELS[k] || k}:</span> {v === true ? 'yes' : String(v)}
          <button className="opacity-50 hover:opacity-100" onClick={() => onRemove(k)}>✕</button>
        </span>
      ))}
    </div>
  )
}

export default function JobsTab({ profile }) {
  const [data, setData] = useState({ results: [], total: 0, page: 1, page_size: 50 })
  const [loading, setLoading] = useState(true)
  const [scrape, setScrape] = useState(null)
  const [scoringAll, setScoringAll] = useState(false)
  const [scoringIds, setScoringIds] = useState(new Set())
  const [showSettings, setShowSettings] = useState(false)
  const [filters, setFilters] = useState({})
  const [sort, setSort] = useState('newest')
  const [minFit, setMinFit] = useState('')
  const [facets, setFacets] = useState(null)
  const [prompt, setPrompt] = useState('')
  const [parsing, setParsing] = useState(false)
  const [saved, setSaved] = useState([])
  const toast = useToast()
  const pollRef = useRef(null)
  const debounceRef = useRef(null)
  const fetchSeq = useRef(0)

  const queryString = (f, page = 1) => {
    const params = new URLSearchParams({ profile_id: profile.id, sort, page })
    Object.entries(f).forEach(([k, v]) => {
      if (v !== '' && v != null && v !== false) params.set(k, v)
    })
    return params.toString()
  }

  const load = useCallback(async (f = filters, page = 1, append = false) => {
    const seq = ++fetchSeq.current
    if (!append) setLoading(true)
    try {
      const res = await api.get(`/api/jobs?${queryString(f, page)}`)
      if (seq !== fetchSeq.current) return // stale response
      setData((d) => append ? { ...res, results: [...d.results, ...res.results] } : res)
    } catch (e) { toast(e.message) }
    finally { if (seq === fetchSeq.current) setLoading(false) }
  }, [profile.id, sort]) // eslint-disable-line react-hooks/exhaustive-deps

  const loadMeta = useCallback(() => {
    api.get('/api/jobs/facets').then(setFacets).catch(() => {})
    api.get('/api/filters').then(setSaved).catch(() => {})
  }, [])

  // debounced refetch whenever filters/sort change
  useEffect(() => {
    clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => load(filters, 1), 250)
    return () => clearTimeout(debounceRef.current)
  }, [filters, sort, load])
  useEffect(() => { loadMeta() }, [loadMeta])
  useEffect(() => () => clearInterval(pollRef.current), [])

  const setF = (k, v) => setFilters((f) => {
    const n = { ...f }
    if (v === '' || v == null || v === false) delete n[k]
    else n[k] = v
    return n
  })

  const runPrompt = async () => {
    if (prompt.trim().length < 3) return
    setParsing(true)
    try {
      const res = await api.post(`/api/jobs/prompt-filter?profile_id=${profile.id}`, { prompt })
      setFilters(res.filter)        // chips become editable state…
      setData(res)                  // …and the results are already here
      setLoading(false)
    } catch (e) { toast(e.message) }
    finally { setParsing(false) }
  }

  const saveCurrentFilter = async () => {
    const name = window.prompt('Name this filter (e.g. "my FA search"):')
    if (!name?.trim()) return
    try {
      await api.post('/api/filters', { name: name.trim(), filter: filters })
      loadMeta()
      toast(`Saved filter “${name.trim()}”`, 'info')
    } catch (e) { toast(e.message) }
  }

  const deleteSavedFilter = async (id) => {
    try { await api.del(`/api/filters/${id}`); loadMeta() }
    catch (e) { toast(e.message) }
  }

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
          load(); loadMeta()
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
      setData((d) => ({ ...d, results: d.results.map((j) => (j.id === jobId ? updated : j)) }))
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

  const jobs = data.results
  const shown = minFit
    ? jobs.filter((j) => j.fit_score != null && j.fit_score >= Number(minFit))
    : jobs
  const unscored = jobs.filter((j) => j.fit_score == null).length
  const hasMore = jobs.length < data.total

  return (
    <div>
      <PageHead title="Discover"
        sub={`${data.total} matching postings · fit scores are ${profile.name}'s`}>
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

      {/* ------------------------------------------------ filter bar */}
      <div className="mb-5 space-y-2.5">
        <div className="flex gap-2">
          <input className={inputCls + ' flex-1'}
            placeholder="Describe what you're looking for… (e.g. FA or strategy internships in Munich, posted in the last 2 weeks)"
            value={prompt} onChange={(e) => setPrompt(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && runPrompt()} />
          <Btn variant="accent" onClick={runPrompt} disabled={parsing || prompt.trim().length < 3}>
            {parsing ? <Spinner label="" /> : '✦ Filter'}
          </Btn>
        </div>

        <div className="flex flex-wrap gap-2">
          <input className={inputCls + ' max-w-44 flex-1'} placeholder="keyword…"
            value={filters.q || ''} onChange={(e) => setF('q', e.target.value)} />
          <input className={inputCls + ' w-32'} placeholder="location…"
            value={filters.location || ''} onChange={(e) => setF('location', e.target.value)} />
          <select className={inputCls + ' w-36'} value={filters.employment_type || ''}
            onChange={(e) => setF('employment_type', e.target.value)}>
            <option value="">type</option>
            {(facets?.employment_types || []).map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
          <select className={inputCls + ' w-40'} value={filters.company || ''}
            onChange={(e) => setF('company', e.target.value)}>
            <option value="">company</option>
            {(facets?.companies || []).map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
          <select className={inputCls + ' w-28'} value={filters.source || ''}
            onChange={(e) => setF('source', e.target.value)}>
            <option value="">source</option>
            {(facets?.sources || []).map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
          <select className={inputCls + ' w-24'} value={filters.language || ''}
            onChange={(e) => setF('language', e.target.value)}>
            <option value="">lang</option>
            <option value="de">de</option>
            <option value="en">en</option>
          </select>
          <input type="date" className={inputCls + ' w-40'} title="posted after"
            value={filters.posted_after || ''} onChange={(e) => setF('posted_after', e.target.value)} />
          <select className={inputCls + ' w-28'} value={filters.status || 'open'}
            onChange={(e) => setF('status', e.target.value === 'open' ? '' : e.target.value)}>
            <option value="open">open</option>
            <option value="closed">closed</option>
            <option value="all">all</option>
          </select>
          <select className={inputCls + ' w-28'} value={minFit} onChange={(e) => setMinFit(e.target.value)}>
            <option value="">min fit</option>
            {[5, 6, 7, 8, 9].map((n) => <option key={n} value={n}>≥ {n}</option>)}
          </select>
          <select className={inputCls + ' w-28'} value={sort} onChange={(e) => setSort(e.target.value)}>
            <option value="newest">newest</option>
            <option value="fit">best fit</option>
          </select>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <FilterChips filters={filters} onRemove={(k) => setF(k, '')} />
          {Object.keys(filters).length > 0 && (
            <>
              <button className="text-xs text-neutral-400 underline hover:text-ink"
                onClick={() => setFilters({})}>clear all</button>
              <button className="text-xs text-accent-deep underline hover:opacity-70"
                onClick={saveCurrentFilter}>save filter…</button>
            </>
          )}
          {saved.length > 0 && (
            <span className="ml-auto flex flex-wrap items-center gap-1.5 text-xs text-neutral-500">
              saved:
              {saved.map((s) => (
                <span key={s.id} className="inline-flex items-center gap-1 rounded-md bg-black/5 px-2 py-1 font-medium">
                  <button className="hover:text-accent-deep" onClick={() => setFilters(s.filter)}>{s.name}</button>
                  <button className="opacity-40 hover:opacity-100" onClick={() => deleteSavedFilter(s.id)}>✕</button>
                </span>
              ))}
            </span>
          )}
        </div>
      </div>

      {loading ? <Spinner label="loading jobs…" /> : shown.length === 0 ? (
        <div className="card p-12 text-center">
          <p className="display text-lg text-neutral-400">
            {data.total === 0 && Object.keys(filters).length === 0
              ? 'The pool is empty' : 'Nothing matches these filters'}
          </p>
          <p className="mt-1 text-sm text-neutral-400">
            {data.total === 0 && Object.keys(filters).length === 0
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
                    {j.language && <Badge tone="sky">{j.language}</Badge>}
                    {j.remote && <Badge tone="violet">remote</Badge>}
                    {j.closed_at && <Badge tone="red">closed</Badge>}
                  </div>
                  <div className="mt-0.5 text-sm text-neutral-500">
                    {j.company}{j.location ? ` · ${j.location}` : ''}{j.department ? ` · ${j.department}` : ''}
                    {j.posted_date ? ` · posted ${j.posted_date}` : ''}
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
          {hasMore && (
            <div className="pt-2 text-center">
              <Btn onClick={() => load(filters, data.page + 1, true)}>
                Load more ({jobs.length}/{data.total})
              </Btn>
            </div>
          )}
        </div>
      )}

      {showSettings && <ScraperSettingsModal onClose={() => { setShowSettings(false); load(); loadMeta() }} />}
    </div>
  )
}
