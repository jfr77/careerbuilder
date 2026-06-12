import { useCallback, useEffect, useState } from 'react'
import { api } from './api.js'
import { Btn, Field, Icon, inputCls, Modal, ToastProvider, useToast } from './ui.jsx'
import ChatTab from './tabs/ChatTab.jsx'
import JobsTab from './tabs/JobsTab.jsx'
import PipelineTab from './tabs/PipelineTab.jsx'
import EventsTab from './tabs/EventsTab.jsx'
import StudioTab from './tabs/StudioTab.jsx'
import ProfileTab from './tabs/ProfileTab.jsx'

const NAV = [
  { id: 'chat', label: 'Chat', icon: 'chat' },
  { id: 'jobs', label: 'Discover', icon: 'discover' },
  { id: 'pipeline', label: 'Pipeline', icon: 'pipeline' },
  { id: 'studio', label: 'Studio', icon: 'studio' },
  { id: 'events', label: 'Events', icon: 'events' },
  { id: 'profile', label: 'Profile', icon: 'profile' },
]

const AVATAR_COLORS = ['#0e8a64', '#b45309', '#6d28d9', '#0369a1', '#be185d', '#4d7c0f']
const avatarColor = (id) => AVATAR_COLORS[id % AVATAR_COLORS.length]

function Avatar({ profile, size = 'h-8 w-8 text-xs' }) {
  return (
    <span className={`grid ${size} shrink-0 place-items-center rounded-full font-semibold text-white`}
      style={{ background: avatarColor(profile.id) }}>
      {profile.name.slice(0, 1).toUpperCase()}
    </span>
  )
}

function ProfileSwitcher({ profiles, active, onSwitch, onNew }) {
  const [open, setOpen] = useState(false)
  if (!active) return null
  return (
    <div className="relative">
      {open && (
        <div className="absolute bottom-full left-0 z-20 mb-2 w-56 rounded-xl border border-white/10 bg-ink-2 p-1.5 shadow-2xl">
          <p className="microlabel px-2.5 pb-1 pt-1.5 !text-neutral-500">Switch profile</p>
          {profiles.map((p) => (
            <button key={p.id}
              className={`flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-sm ${
                p.id === active.id ? 'bg-white/10 text-white' : 'text-neutral-300 hover:bg-white/5'}`}
              onClick={() => { onSwitch(p.id); setOpen(false) }}>
              <Avatar profile={p} size="h-6 w-6 text-[10px]" />
              <span className="truncate">{p.name}</span>
              {p.id === active.id && <span className="ml-auto text-accent">●</span>}
            </button>
          ))}
          <button
            className="mt-1 flex w-full items-center gap-2.5 rounded-lg border-t border-white/10 px-2.5 py-2 text-left text-sm text-neutral-300 hover:bg-white/5"
            onClick={() => { onNew(); setOpen(false) }}>
            <span className="grid h-6 w-6 place-items-center rounded-full border border-dashed border-neutral-500 text-neutral-400">+</span>
            New profile
          </button>
        </div>
      )}
      <button
        className="flex w-full items-center gap-2.5 rounded-xl px-2.5 py-2 text-left hover:bg-white/5"
        onClick={() => setOpen(!open)}>
        <Avatar profile={active} />
        <span className="min-w-0">
          <span className="block truncate text-sm font-medium text-white">{active.name}</span>
          <span className="block truncate text-xs text-neutral-500">{active.location || 'no location'}</span>
        </span>
        <span className="ml-auto text-neutral-500">⌄</span>
      </button>
    </div>
  )
}

function Shell() {
  const [profiles, setProfiles] = useState([])
  const [activeId, setActiveId] = useState(() => Number(localStorage.getItem('activeProfileId')) || null)
  const [tab, setTab] = useState('jobs')
  const [llmAvailable, setLlmAvailable] = useState(true)
  const [showNew, setShowNew] = useState(false)
  const [newName, setNewName] = useState('')
  const [newLocation, setNewLocation] = useState('')
  // cross-section jump: pipeline card → Studio generator, prefilled
  const [docRequest, setDocRequest] = useState(null)
  const toast = useToast()

  const loadProfiles = useCallback(async () => {
    try {
      const list = await api.get('/api/profiles')
      setProfiles(list)
      setActiveId((cur) => (list.some((p) => p.id === cur) ? cur : list[0]?.id ?? null))
    } catch (e) { toast(`Backend unreachable: ${e.message}`) }
  }, [toast])

  useEffect(() => { loadProfiles() }, [loadProfiles])
  useEffect(() => {
    api.get('/api/health').then((h) => setLlmAvailable(h.llm_available)).catch(() => {})
  }, [])
  useEffect(() => {
    if (activeId) localStorage.setItem('activeProfileId', String(activeId))
  }, [activeId])

  const active = profiles.find((p) => p.id === activeId)

  const createProfile = async () => {
    if (!newName.trim()) return
    try {
      const p = await api.post('/api/profiles', { name: newName.trim(), location: newLocation.trim() || null })
      setShowNew(false); setNewName(''); setNewLocation('')
      setProfiles((ps) => [...ps, p]); setActiveId(p.id)
    } catch (e) { toast(e.message) }
  }

  const openStudio = (req) => { setDocRequest(req); setTab('studio') }

  return (
    <div className="flex min-h-screen">
      {/* ------------------------------------------------ ink sidebar */}
      <aside className="fixed inset-y-0 left-0 z-30 flex w-60 flex-col bg-ink px-3 py-5">
        <div className="mb-8 flex items-center gap-2.5 px-2.5">
          <span className="display grid h-8 w-8 place-items-center rounded-lg bg-accent text-base font-bold text-white">c</span>
          <span className="display text-[17px] font-semibold tracking-tight text-white">carreerbuilder</span>
        </div>
        <nav className="flex flex-col gap-0.5">
          {NAV.map((n) => (
            <button key={n.id} onClick={() => setTab(n.id)}
              className={`flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-colors ${
                tab === n.id ? 'bg-white/10 text-white' : 'text-neutral-400 hover:bg-white/5 hover:text-neutral-200'}`}>
              <Icon name={n.icon} className={`h-[18px] w-[18px] ${tab === n.id ? 'text-accent' : ''}`} />
              {n.label}
            </button>
          ))}
        </nav>
        <div className="mt-auto space-y-3">
          {!llmAvailable && (
            <p className="rounded-xl border border-amber-400/20 bg-amber-400/10 px-3 py-2.5 text-xs leading-relaxed text-amber-200">
              AI features off — set <code className="font-mono">ANTHROPIC_API_KEY</code> in .env and restart the backend.
            </p>
          )}
          <ProfileSwitcher profiles={profiles} active={active}
            onSwitch={setActiveId} onNew={() => setShowNew(true)} />
        </div>
      </aside>

      {/* ------------------------------------------------ content */}
      <main className="ml-60 min-w-0 flex-1 px-8 py-8">
        <div className="mx-auto max-w-5xl">
          {!active ? (
            <p className="text-sm text-neutral-500">Loading profiles… (is the backend running on :8000?)</p>
          ) : (
            <>
              {tab === 'chat' && <ChatTab profile={active} />}
              {tab === 'jobs' && <JobsTab profile={active} />}
              {tab === 'pipeline' && <PipelineTab profile={active} onGenerateDoc={openStudio} />}
              {tab === 'studio' && (
                <StudioTab profile={active} docRequest={docRequest}
                  onDocRequestHandled={() => setDocRequest(null)} />
              )}
              {tab === 'events' && <EventsTab profile={active} />}
              {tab === 'profile' && (
                <ProfileTab profile={active} profiles={profiles} onProfilesChanged={loadProfiles} />
              )}
            </>
          )}
        </div>
      </main>

      {showNew && (
        <Modal title="New profile" onClose={() => setShowNew(false)}>
          <div className="space-y-3">
            <Field label="Name"><input className={inputCls} value={newName} onChange={(e) => setNewName(e.target.value)} autoFocus /></Field>
            <Field label="Location"><input className={inputCls} value={newLocation} onChange={(e) => setNewLocation(e.target.value)} placeholder="optional" /></Field>
            <p className="text-xs text-neutral-500">Everything else (education, skills, CV, …) is editable later in Profile.</p>
            <div className="flex justify-end gap-2">
              <Btn onClick={() => setShowNew(false)}>Cancel</Btn>
              <Btn variant="primary" onClick={createProfile} disabled={!newName.trim()}>Create</Btn>
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}

export default function App() {
  return (
    <ToastProvider>
      <Shell />
    </ToastProvider>
  )
}
