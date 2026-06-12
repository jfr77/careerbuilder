"""Request bodies. Responses are plain dicts assembled in the routers."""

from pydantic import BaseModel, Field

PIPELINE_TYPES = {"fa", "analytics", "consulting", "vc", "other"}
PIPELINE_STAGES = {"researching", "applied", "in_progress", "offer", "rejected"}


class ProfileCreate(BaseModel):
    name: str
    location: str | None = None


class ProfileUpdate(BaseModel):
    name: str | None = None
    location: str | None = None
    education: str | None = None
    experience_summary: str | None = None
    skills: list[str] | None = None
    languages: list | None = None
    role_expectations: str | None = None
    learning_goals: str | None = None
    target_industries: list[str] | None = None
    target_companies: list[str] | None = None
    availability: str | None = None
    cv_base: str | None = None


class PipelineCreate(BaseModel):
    company: str
    role: str
    type: str = "other"
    stage: str = "researching"
    job_id: int | None = None
    link: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    deadline: str | None = None
    reached_out: bool = False
    notes: str | None = None


class PipelineUpdate(BaseModel):
    company: str | None = None
    role: str | None = None
    type: str | None = None
    stage: str | None = None
    link: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    deadline: str | None = None
    reached_out: bool | None = None
    notes: str | None = None


class PromptFilterBody(BaseModel):
    prompt: str = Field(min_length=3)


class SavedFilterCreate(BaseModel):
    name: str = Field(min_length=1)
    filter: dict = {}


class PasteExtract(BaseModel):
    text: str = Field(min_length=10)


class ChatSend(BaseModel):
    message: str = Field(min_length=1)


class WatchlistAdd(BaseModel):
    slug: str = Field(min_length=1)


class EventSaveBody(BaseModel):
    saved: bool


class CoverLetterRequest(BaseModel):
    pipeline_id: int | None = None
    pasted_posting: str | None = None
    tone: str = "formal_en"  # formal_de | formal_en | startup


class SaveDocumentBody(BaseModel):
    pipeline_id: int
    doc_type: str  # cover_letter | cv | brief
    title: str
    content: str


class CVTailorRequest(BaseModel):
    pipeline_id: int | None = None
    job_id: int | None = None
    pasted_posting: str | None = None


class TrainerRequest(BaseModel):
    pipeline_id: int | None = None
    industry: str | None = None
