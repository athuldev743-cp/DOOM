from pydantic import BaseModel
class ChatRequest(BaseModel):
    message: str


class CommandRequest(BaseModel):
    command: str
    args: str = ""


class ApplyJobRequest(BaseModel):
    company: str
    role: str = ""
    job_index: int | None = None
    

class OpenJobRequest(BaseModel):
    job_id: int


class PrepareJobRequest(BaseModel):
    job_id: int


class ApproveJobRequest(BaseModel):
    job_id: int
    recipient_email: str | None = None
    cover_letter: str | None = None


class SendJobEmailRequest(BaseModel):
    job_id: int
