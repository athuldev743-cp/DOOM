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
    