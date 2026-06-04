from pydantic import BaseModel


class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    message: str
    conversation_history: list[ChatMessage] = []
    quote_id: str | None = None


class SSEEvent(BaseModel):
    """Server-Sent Event payload."""
    type: str  # "text", "products", "quote_update", "tool_call", "error", "done"
    data: dict | list | str | None = None
