"""Builders that turn DB rows into compact text blocks for LLM prompts.
Always built from the live profiles row — never from hardcoded strings."""

import json

from .models import Job, PipelineEntry, Profile


def profile_block(p: Profile) -> str:
    langs = p.languages or []
    if langs and isinstance(langs[0], dict):
        lang_str = ", ".join(f"{l.get('language')} ({l.get('level')})" for l in langs)
    else:
        lang_str = ", ".join(str(l) for l in langs)
    return (
        f"Name: {p.name}\n"
        f"Location: {p.location or 'n/a'}\n"
        f"Education: {p.education or 'n/a'}\n"
        f"Experience: {p.experience_summary or 'n/a'}\n"
        f"Skills: {', '.join(p.skills or []) or 'n/a'}\n"
        f"Languages: {lang_str or 'n/a'}\n"
        f"What they expect from a role: {p.role_expectations or 'n/a'}\n"
        f"Knowledge/skills they want to gain: {p.learning_goals or 'n/a'}\n"
        f"Target industries: {', '.join(p.target_industries or []) or 'n/a'}\n"
        f"Target companies: {', '.join(p.target_companies or []) or 'n/a'}\n"
        f"Availability: {p.availability or 'n/a'}"
    )


def pipeline_block(entries: list[PipelineEntry]) -> str:
    if not entries:
        return "(pipeline is empty)"
    lines = []
    for e in entries:
        bits = [f"{e.company} — {e.role} [{e.type}] stage={e.stage}"]
        if e.start_date:
            bits.append(f"start {e.start_date}")
        if e.deadline:
            bits.append(f"deadline {e.deadline}")
        if e.reached_out:
            bits.append("reached out")
        if e.notes:
            bits.append(f"notes: {e.notes}")
        lines.append("- " + ", ".join(bits))
    return "\n".join(lines)


def job_block(j: Job) -> str:
    desc = (j.description or "")[:2000]
    return (
        f"Title: {j.title}\nCompany: {j.company}\nLocation: {j.location or 'n/a'}\n"
        f"Employment: {j.employment or 'n/a'}\nDepartment: {j.department or 'n/a'}\n"
        f"URL: {j.url or 'n/a'}"
        + (f"\nDescription: {desc}" if desc else "")
    )


def matches_block(rows) -> str:
    """rows: iterable of (Job, JobScore|None) for recent relevant matches."""
    lines = []
    for job, score in rows:
        fit = f" fit {score.fit_score}/10 — {score.fit_note}" if score and score.fit_score else ""
        lines.append(f"- {job.title} at {job.company} ({job.location or 'n/a'}){fit}")
    return "\n".join(lines) or "(no scraped job matches yet)"


def profile_dict(p: Profile) -> dict:
    return {
        "id": p.id, "name": p.name, "location": p.location, "education": p.education,
        "experience_summary": p.experience_summary, "skills": p.skills,
        "languages": p.languages, "role_expectations": p.role_expectations,
        "learning_goals": p.learning_goals, "target_industries": p.target_industries,
        "target_companies": p.target_companies, "availability": p.availability,
        "cv_base": p.cv_base,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }
