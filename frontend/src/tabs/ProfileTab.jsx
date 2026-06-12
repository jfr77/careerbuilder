// Profile — edit every field of the active profile; document generation lives
// in Studio. Saving offers an optional re-score of already-scored jobs.
import { useEffect, useState } from 'react'
import { api } from '../api.js'
import { Btn, Field, inputCls, Modal, PageHead, Spinner, useToast } from '../ui.jsx'

const listToText = (v) => (Array.isArray(v) ? v.join(', ') : '')
const textToList = (s) => s.split(',').map((x) => x.trim()).filter(Boolean)
const langsToText = (v) =>
  (v || []).map((l) => (typeof l === 'string' ? l : `${l.language} (${l.level})`)).join(', ')

export default function ProfileTab({ profile, profiles, onProfilesChanged }) {
  const [form, setForm] = useState(null)
  const [saving, setSaving] = useState(false)
  const [askRescore, setAskRescore] = useState(false)
  const [rescoring, setRescoring] = useState(false)
  const toast = useToast()

  useEffect(() => {
    setForm({
      name: profile.name ?? '', location: profile.location ?? '',
      education: profile.education ?? '', experience_summary: profile.experience_summary ?? '',
      skills: listToText(profile.skills), languages: langsToText(profile.languages),
      role_expectations: profile.role_expectations ?? '', learning_goals: profile.learning_goals ?? '',
      target_industries: listToText(profile.target_industries),
      target_companies: listToText(profile.target_companies),
      availability: profile.availability ?? '', cv_base: profile.cv_base ?? '',
    })
  }, [profile.id])

  if (!form) return null
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })

  const save = async () => {
    setSaving(true)
    try {
      await api.patch(`/api/profiles/${profile.id}`, {
        ...form,
        skills: textToList(form.skills),
        languages: textToList(form.languages),
        target_industries: textToList(form.target_industries),
        target_companies: textToList(form.target_companies),
      })
      onProfilesChanged()
      setAskRescore(true)
    } catch (e) { toast(e.message) }
    finally { setSaving(false) }
  }

  const rescoreAll = async () => {
    setRescoring(true)
    try {
      const jobs = await api.get(`/api/jobs?profile_id=${profile.id}`)
      const scored = jobs.filter((j) => j.fit_score != null)
      for (const j of scored) {
        await api.post(`/api/jobs/${j.id}/score?profile_id=${profile.id}`)
      }
      toast(`Re-scored ${scored.length} job(s) against the updated profile`, 'info')
    } catch (e) { toast(e.message) }
    finally { setRescoring(false); setAskRescore(false) }
  }

  const deleteProfile = async () => {
    if (!confirm(`Delete profile "${profile.name}"? This removes their pipeline, scores, chat and saved events.`)) return
    try {
      await api.del(`/api/profiles/${profile.id}`)
      onProfilesChanged()
      toast(`Deleted ${profile.name}`, 'info')
    } catch (e) { toast(e.message) }
  }

  return (
    <div>
      <PageHead title="Profile" sub="Everything the AI knows about this person — scoring, chat and Studio all read from here.">
        <Btn variant="danger" onClick={deleteProfile} disabled={profiles.length <= 1}
          title={profiles.length <= 1 ? 'Cannot delete the last profile' : ''}>
          Delete profile
        </Btn>
        <Btn variant="primary" onClick={save} disabled={saving}>{saving ? 'Saving…' : 'Save profile'}</Btn>
      </PageHead>

      <div className="space-y-5">
        <section className="card p-5">
          <h2 className="microlabel mb-4">Basics</h2>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <Field label="Name"><input className={inputCls} value={form.name} onChange={set('name')} /></Field>
            <Field label="Location"><input className={inputCls} value={form.location} onChange={set('location')} /></Field>
            <Field label="Education"><input className={inputCls} value={form.education} onChange={set('education')} /></Field>
            <Field label="Availability"><input className={inputCls} value={form.availability} onChange={set('availability')} /></Field>
            <div className="md:col-span-2">
              <Field label="Experience summary">
                <textarea className={inputCls} rows={2} value={form.experience_summary} onChange={set('experience_summary')} />
              </Field>
            </div>
            <Field label="Skills (comma-separated)"><input className={inputCls} value={form.skills} onChange={set('skills')} /></Field>
            <Field label="Languages (comma-separated)" hint="e.g. German (native), English (fluent)">
              <input className={inputCls} value={form.languages} onChange={set('languages')} />
            </Field>
            <Field label="Target industries"><input className={inputCls} value={form.target_industries} onChange={set('target_industries')} /></Field>
            <Field label="Target companies"><input className={inputCls} value={form.target_companies} onChange={set('target_companies')} /></Field>
          </div>
        </section>

        <section className="card p-5">
          <h2 className="microlabel mb-4">What drives the matching</h2>
          <div className="grid grid-cols-1 gap-4">
            <Field label="What I expect from my role">
              <textarea className={inputCls} rows={3} value={form.role_expectations} onChange={set('role_expectations')} />
            </Field>
            <Field label="Knowledge & skills I want to gain">
              <textarea className={inputCls} rows={3} value={form.learning_goals} onChange={set('learning_goals')} />
            </Field>
          </div>
        </section>

        <section className="card p-5">
          <h2 className="microlabel mb-4">Master CV</h2>
          <Field label="cv_base" hint="Plain-text master CV — Studio's CV tailor only reorders/rephrases this content.">
            <textarea className={`${inputCls} font-mono text-xs leading-relaxed`} rows={14} value={form.cv_base} onChange={set('cv_base')} />
          </Field>
        </section>
      </div>

      {askRescore && (
        <Modal title="Profile saved" onClose={() => setAskRescore(false)}>
          <p className="mb-4 text-sm text-neutral-600">
            Re-score open jobs against the updated profile? This re-runs LLM scoring for every job
            that already has a score for {form.name}.
          </p>
          <div className="flex justify-end gap-2">
            <Btn onClick={() => setAskRescore(false)}>Not now</Btn>
            <Btn variant="accent" onClick={rescoreAll} disabled={rescoring}>
              {rescoring ? <Spinner label="re-scoring…" /> : 'Re-score jobs'}
            </Btn>
          </div>
        </Modal>
      )}
    </div>
  )
}
