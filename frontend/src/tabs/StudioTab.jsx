// Studio — the AI document workspace: templates, cover letters, tailored CVs,
// interview prep. Controls on the left, generated output on the right canvas.
import { useEffect, useState } from 'react'
import { api, downloadText } from '../api.js'
import { Badge, Btn, Field, inputCls, Modal, PageHead, Spinner, useToast } from '../ui.jsx'

const TOOLS = [
  { id: 'templates', title: 'Templates', desc: 'Library with placeholders + AI drafting' },
  { id: 'cover', title: 'Cover letter', desc: 'Drafts a one-pager from your profile + the role' },
  { id: 'cv', title: 'CV tailor', desc: 'Reorders & rephrases your master CV — never invents' },
  { id: 'trainer', title: 'Interview prep', desc: 'Likely questions, concepts, questions to ask' },
]

const TEMPLATE_TYPES = ['cover_letter', 'cv_section', 'outreach']

function TemplateEditorModal({ initial, onClose, onSaved }) {
  const [form, setForm] = useState({
    name: '', type: 'cover_letter', language: 'en', body: '', ...(initial || {}),
  })
  const [saving, setSaving] = useState(false)
  const toast = useToast()
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })

  const save = async () => {
    setSaving(true)
    try {
      const payload = { name: form.name, type: form.type, language: form.language, body: form.body }
      const saved = form.id
        ? await api.patch(`/api/templates/${form.id}`, payload)
        : await api.post('/api/templates', payload)
      onSaved(saved)
      onClose()
    } catch (e) { toast(e.message) }
    finally { setSaving(false) }
  }

  return (
    <Modal title={form.id ? `Edit ${form.name}` : 'New template'} onClose={onClose} wide>
      <div className="space-y-3">
        <div className="grid grid-cols-3 gap-3">
          <Field label="Name"><input className={inputCls} value={form.name} onChange={set('name')} /></Field>
          <Field label="Type">
            <select className={inputCls} value={form.type} onChange={set('type')}>
              {TEMPLATE_TYPES.map((t) => <option key={t}>{t}</option>)}
            </select>
          </Field>
          <Field label="Language">
            <select className={inputCls} value={form.language} onChange={set('language')}>
              <option value="de">de</option><option value="en">en</option>
            </select>
          </Field>
        </div>
        <Field label="Body" hint="Placeholders: {{company}} {{role}} {{hiring_manager}} {{source}} {{my_name}} — [square brackets] mark spots the AI should write.">
          <textarea className={inputCls + ' min-h-[300px] font-mono !text-xs'}
            value={form.body} onChange={set('body')} />
        </Field>
        <div className="flex justify-end gap-2">
          <Btn onClick={onClose}>Cancel</Btn>
          <Btn variant="primary" onClick={save} disabled={saving || !form.name.trim() || !form.body.trim()}>Save</Btn>
        </div>
      </div>
    </Modal>
  )
}

const TONES = [
  { id: 'formal_de', label: 'Formal · DE' },
  { id: 'formal_en', label: 'Formal · EN' },
  { id: 'startup', label: 'Startup-direct' },
]

function EntryPicker({ pipeline, value, onChange, allowNone }) {
  return (
    <Field label="Pipeline entry">
      <select className={inputCls} value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">{allowNone ? '— none (paste / industry below) —' : '— pick an application —'}</option>
        {pipeline.map((p) => <option key={p.id} value={p.id}>{p.company} — {p.role}</option>)}
      </select>
    </Field>
  )
}

function OutputCanvas({ children, empty }) {
  return (
    <div className="card min-h-[420px] p-6">
      {children || (
        <div className="grid h-full min-h-[360px] place-items-center text-center">
          <div>
            <p className="display text-lg font-medium text-neutral-300">{empty}</p>
          </div>
        </div>
      )}
    </div>
  )
}

export default function StudioTab({ profile, docRequest, onDocRequestHandled }) {
  const [tool, setTool] = useState('templates')
  const [pipeline, setPipeline] = useState([])
  const [pipelineId, setPipelineId] = useState('')
  const [pasted, setPasted] = useState('')
  const [tone, setTone] = useState('formal_en')
  const [industry, setIndustry] = useState('')
  const [busy, setBusy] = useState(false)
  const [draft, setDraft] = useState('')           // cover letter text
  const [cvResult, setCvResult] = useState(null)   // {tailored, diff}
  const [cvView, setCvView] = useState('diff')
  const [brief, setBrief] = useState(null)         // trainer JSON
  // templates tool
  const [templates, setTemplates] = useState([])
  const [templateId, setTemplateId] = useState('')
  const [tplOut, setTplOut] = useState(null)       // {text, unresolved, template_name}
  const [tplEditor, setTplEditor] = useState(null) // null | {} (new) | template (edit)
  const toast = useToast()

  const loadTemplates = () =>
    api.get('/api/templates').then(setTemplates).catch(() => {})

  useEffect(() => {
    setPipeline([]); setPipelineId(''); setDraft(''); setCvResult(null); setBrief(null); setTplOut(null)
    api.get(`/api/pipeline?profile_id=${profile.id}`).then(setPipeline).catch(() => {})
    loadTemplates()
  }, [profile.id])

  // jump-in from a pipeline card
  useEffect(() => {
    if (docRequest) {
      setTool(docRequest.kind === 'cv' ? 'cv' : 'cover')
      setPipelineId(String(docRequest.pipelineId))
      onDocRequestHandled()
    }
  }, [docRequest])

  const entry = pipeline.find((p) => p.id === Number(pipelineId))
  const template = templates.find((t) => t.id === Number(templateId))

  const fillTemplate = async () => {
    setBusy(true)
    try {
      setTplOut(await api.post(`/api/templates/${templateId}/render?profile_id=${profile.id}`, {
        pipeline_id: pipelineId ? Number(pipelineId) : null,
      }))
    } catch (e) { toast(e.message) }
    finally { setBusy(false) }
  }

  const draftTemplateWithAI = async () => {
    setBusy(true)
    try {
      setTplOut(await api.post(`/api/templates/${templateId}/draft?profile_id=${profile.id}`, {
        pipeline_id: pipelineId ? Number(pipelineId) : null,
        pasted_posting: pasted.trim() || null,
      }))
    } catch (e) { toast(e.message) }
    finally { setBusy(false) }
  }

  const saveTplDraft = async () => {
    const title = `${tplOut.template_name} — ${entry?.company} (${new Date().toISOString().slice(0, 10)})`
    try {
      await api.post('/api/documents/save', {
        pipeline_id: Number(pipelineId),
        doc_type: template?.type === 'cv_section' ? 'cv' : 'cover_letter',
        title,
        content: tplOut.text,
        meta: { template_id: tplOut.template_id, template_name: tplOut.template_name },
      })
      if (template?.type !== 'cv_section') {
        await api.patch(`/api/pipeline/${pipelineId}`, { cover_letter_version: title })
      }
      toast(`Saved to ${entry?.company} as document version`, 'info')
    } catch (e) { toast(e.message) }
  }

  const deleteTemplate = async () => {
    if (!template || template.is_builtin) return
    if (!confirm(`Delete template "${template.name}"?`)) return
    try {
      await api.del(`/api/templates/${template.id}`)
      setTemplateId(''); setTplOut(null); loadTemplates()
    } catch (e) { toast(e.message) }
  }

  const duplicateTemplate = async () => {
    try {
      const copy = await api.post(`/api/templates/${templateId}/duplicate`)
      await loadTemplates()
      setTemplateId(String(copy.id))
      toast(`Duplicated as “${copy.name}” — now editable`, 'info')
    } catch (e) { toast(e.message) }
  }

  const generate = async () => {
    setBusy(true)
    try {
      if (tool === 'cover') {
        const res = await api.post(`/api/documents/cover-letter?profile_id=${profile.id}`, {
          pipeline_id: pipelineId ? Number(pipelineId) : null,
          pasted_posting: pasted.trim() || null, tone,
        })
        setDraft(res.draft)
      } else if (tool === 'cv') {
        setCvResult(await api.post(`/api/documents/cv-tailor?profile_id=${profile.id}`, {
          pipeline_id: pipelineId ? Number(pipelineId) : null,
          pasted_posting: pasted.trim() || null,
        }))
        setCvView('diff')
      } else {
        const res = await api.post(`/api/documents/trainer?profile_id=${profile.id}`, {
          pipeline_id: pipelineId ? Number(pipelineId) : null,
          industry: industry.trim() || null,
        })
        setBrief(res.brief)
      }
    } catch (e) { toast(e.message) }
    finally { setBusy(false) }
  }

  const saveToEntry = async (docType, title, content) => {
    try {
      await api.post('/api/documents/save', {
        pipeline_id: Number(pipelineId), doc_type: docType, title, content,
      })
      toast(`Saved to ${entry?.company}`, 'info')
    } catch (e) { toast(e.message) }
  }

  const canGenerate =
    tool === 'trainer' ? (pipelineId || industry.trim())
    : (pipelineId || pasted.trim().length >= 10)

  return (
    <div>
      <PageHead title="Studio"
        sub={`AI application documents for ${profile.name} — grounded in the live profile, never invented.`} />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[320px_1fr]">
        {/* ---------------------------------- controls */}
        <div className="space-y-4">
          <div className="card overflow-hidden">
            {TOOLS.map((t) => (
              <button key={t.id}
                onClick={() => setTool(t.id)}
                className={`block w-full border-b border-line px-4 py-3 text-left last:border-0 ${
                  tool === t.id ? 'bg-accent-soft/60' : 'hover:bg-black/[0.02]'}`}>
                <span className={`block text-sm font-semibold ${tool === t.id ? 'text-accent-deep' : ''}`}>{t.title}</span>
                <span className="block text-xs text-neutral-500">{t.desc}</span>
              </button>
            ))}
          </div>

          <div className="card space-y-3 p-4">
            {tool === 'templates' && (
              <>
                <Field label="Template">
                  <select className={inputCls} value={templateId}
                    onChange={(e) => { setTemplateId(e.target.value); setTplOut(null) }}>
                    <option value="">— pick a template —</option>
                    {templates.map((t) => (
                      <option key={t.id} value={t.id}>
                        {t.is_builtin ? '◆ ' : ''}{t.name} · {t.type} · {t.language}
                      </option>
                    ))}
                  </select>
                </Field>
                <div className="flex flex-wrap gap-1.5 text-xs">
                  <Btn className="!px-2 !py-1 !text-xs" onClick={() => setTplEditor({})}>+ New</Btn>
                  {template && (
                    <Btn className="!px-2 !py-1 !text-xs" onClick={duplicateTemplate}>Duplicate</Btn>
                  )}
                  {template && !template.is_builtin && (
                    <>
                      <Btn className="!px-2 !py-1 !text-xs" onClick={() => setTplEditor(template)}>Edit</Btn>
                      <Btn variant="danger" className="!px-2 !py-1 !text-xs" onClick={deleteTemplate}>Delete</Btn>
                    </>
                  )}
                  {template?.is_builtin && (
                    <span className="self-center text-neutral-400">built-in · read-only</span>
                  )}
                </div>
              </>
            )}
            <EntryPicker pipeline={pipeline} value={pipelineId} onChange={setPipelineId} allowNone />
            {tool !== 'trainer' && (
              <Field label="Or paste a posting">
                <textarea className={inputCls} rows={4} value={pasted}
                  onChange={(e) => setPasted(e.target.value)}
                  placeholder="Raw job posting text or URL…" />
              </Field>
            )}
            {tool === 'cover' && (
              <Field label="Tone">
                <div className="flex gap-1.5">
                  {TONES.map((t) => (
                    <button key={t.id} onClick={() => setTone(t.id)}
                      className={`rounded-lg border px-2.5 py-1.5 text-xs font-medium ${
                        tone === t.id ? 'border-accent bg-accent-soft text-accent-deep' : 'border-line text-neutral-500 hover:border-neutral-400'}`}>
                      {t.label}
                    </button>
                  ))}
                </div>
              </Field>
            )}
            {tool === 'trainer' && (
              <Field label="Or target an industry">
                <input className={inputCls} value={industry}
                  onChange={(e) => setIndustry(e.target.value)}
                  placeholder="e.g. Venture Capital" />
              </Field>
            )}
            {tool === 'templates' ? (
              <div className="space-y-2">
                <Btn className="w-full" onClick={fillTemplate} disabled={busy || !templateId}>
                  Fill placeholders
                </Btn>
                <Btn variant="accent" className="w-full" onClick={draftTemplateWithAI}
                  disabled={busy || !templateId || (!pipelineId && pasted.trim().length < 10)}>
                  {busy ? <Spinner label="drafting…" /> : '✦ Draft with AI'}
                </Btn>
              </div>
            ) : (
              <Btn variant="accent" className="w-full" onClick={generate} disabled={busy || !canGenerate}>
                {busy ? <Spinner label="generating…" /> : 'Generate'}
              </Btn>
            )}
          </div>
        </div>

        {/* ---------------------------------- output */}
        <div>
          {tool === 'templates' && (
            <OutputCanvas empty="Pick a template (and a pipeline entry), then Fill or ✦ Draft with AI.">
              {tplOut && (
                <div className="space-y-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="microlabel">
                      {tplOut.template_name} — editable
                    </span>
                    <div className="flex gap-2">
                      <Btn onClick={() => downloadText('draft.txt', tplOut.text)}>Download .txt</Btn>
                      {pipelineId && (
                        <Btn variant="primary" onClick={saveTplDraft}>Save to entry</Btn>
                      )}
                    </div>
                  </div>
                  {tplOut.unresolved.length > 0 && (
                    <div className="flex flex-wrap items-center gap-1.5 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800">
                      unresolved:
                      {tplOut.unresolved.map((p) => (
                        <code key={p} className="rounded bg-amber-100 px-1 font-mono">{'{{'}{p}{'}}'}</code>
                      ))}
                      <span className="text-amber-600">— link a pipeline entry with these fields, edit manually, or ✦ Draft with AI</span>
                    </div>
                  )}
                  <textarea
                    className="min-h-[460px] w-full resize-y rounded-xl border border-line bg-paper/50 p-5 font-serif text-[15px] leading-relaxed focus:border-accent focus:outline-none"
                    value={tplOut.text}
                    onChange={(e) => setTplOut({ ...tplOut, text: e.target.value })} />
                </div>
              )}
            </OutputCanvas>
          )}

          {tool === 'cover' && (
            <OutputCanvas empty="Pick a role, choose a tone, hit Generate.">
              {draft && (
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="microlabel">Draft — editable</span>
                    <div className="flex gap-2">
                      <Btn onClick={() => downloadText('cover-letter.txt', draft)}>Download .txt</Btn>
                      {pipelineId && (
                        <Btn variant="primary"
                          onClick={() => saveToEntry('cover_letter', `Cover letter (${tone}) — ${entry?.company}`, draft)}>
                          Save to entry
                        </Btn>
                      )}
                    </div>
                  </div>
                  <textarea
                    className="min-h-[460px] w-full resize-y rounded-xl border border-line bg-paper/50 p-5 font-serif text-[15px] leading-relaxed focus:border-accent focus:outline-none"
                    value={draft} onChange={(e) => setDraft(e.target.value)} />
                </div>
              )}
            </OutputCanvas>
          )}

          {tool === 'cv' && (
            <OutputCanvas empty="Tailors your master CV to a specific role — with a diff of every change.">
              {cvResult && (
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="flex gap-1.5">
                      {['diff', 'result'].map((v) => (
                        <button key={v} onClick={() => setCvView(v)}
                          className={`rounded-lg px-3 py-1.5 text-xs font-semibold capitalize ${
                            cvView === v ? 'bg-ink text-white' : 'text-neutral-500 hover:bg-black/5'}`}>
                          {v}
                        </button>
                      ))}
                    </div>
                    <div className="flex gap-2">
                      <Btn onClick={() => downloadText('cv-tailored.txt', cvResult.tailored)}>Download .txt</Btn>
                      {pipelineId && (
                        <Btn variant="primary"
                          onClick={() => saveToEntry('cv', `Tailored CV — ${entry?.company}`, cvResult.tailored)}>
                          Save to entry
                        </Btn>
                      )}
                    </div>
                  </div>
                  {cvView === 'diff' ? (
                    <pre className="max-h-[500px] overflow-auto rounded-xl border border-line bg-paper/50 p-4 text-xs leading-relaxed">
                      {cvResult.diff.map((l, i) => (
                        <div key={i} className={
                          l.op === 'add' ? 'bg-accent-soft text-accent-deep'
                          : l.op === 'remove' ? 'bg-red-50 text-red-600 line-through'
                          : l.op === 'hunk' ? 'text-neutral-300' : 'text-neutral-500'}>
                          {l.op === 'add' ? '+ ' : l.op === 'remove' ? '− ' : '  '}{l.text}
                        </div>
                      ))}
                    </pre>
                  ) : (
                    <textarea
                      className="min-h-[460px] w-full resize-y rounded-xl border border-line bg-paper/50 p-5 font-mono text-xs leading-relaxed focus:border-accent focus:outline-none"
                      value={cvResult.tailored}
                      onChange={(e) => setCvResult({ ...cvResult, tailored: e.target.value })} />
                  )}
                </div>
              )}
            </OutputCanvas>
          )}

          {tool === 'trainer' && (
            <OutputCanvas empty="Pick a company or industry to get a prep brief.">
              {brief && (
                <div className="space-y-6 text-sm">
                  <div className="flex items-center justify-between">
                    <span className="microlabel">Prep brief</span>
                    {pipelineId && (
                      <Btn variant="primary"
                        onClick={() => saveToEntry('brief', `Interview brief — ${entry?.company}`, JSON.stringify(brief, null, 2))}>
                        Save to entry
                      </Btn>
                    )}
                  </div>
                  <section>
                    <h3 className="display mb-3 font-semibold">Likely questions</h3>
                    <div className="space-y-3">
                      {(brief.questions || []).map((q, i) => (
                        <div key={i} className="rounded-xl border border-line bg-paper/50 p-4">
                          <p className="font-medium">{i + 1}. {q.q}</p>
                          <p className="mt-1.5 whitespace-pre-wrap text-neutral-600">{q.answer}</p>
                        </div>
                      ))}
                    </div>
                  </section>
                  <section>
                    <h3 className="display mb-3 font-semibold">Concepts to master</h3>
                    {(brief.concepts || []).map((c, i) => (
                      <p key={i} className="mb-2">
                        <Badge tone="accent">{c.name}</Badge>{' '}
                        <span className="text-neutral-600">{c.explanation}</span>
                      </p>
                    ))}
                  </section>
                  <section>
                    <h3 className="display mb-3 font-semibold">Ask them</h3>
                    <ul className="list-disc space-y-1 pl-5 text-neutral-600">
                      {(brief.questions_to_ask || []).map((q, i) => <li key={i}>{q}</li>)}
                    </ul>
                  </section>
                </div>
              )}
            </OutputCanvas>
          )}
        </div>
      </div>

      {tplEditor && (
        <TemplateEditorModal
          initial={tplEditor.id ? tplEditor : null}
          onClose={() => setTplEditor(null)}
          onSaved={(t) => { loadTemplates(); setTemplateId(String(t.id)) }} />
      )}
    </div>
  )
}
