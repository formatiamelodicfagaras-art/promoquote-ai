from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.database import get_db
from app.schemas.chat import ChatRequest
from app.services.ai_service import process_chat_message

router = APIRouter()


@router.post("/")
async def chat(request: ChatRequest, db: AsyncSession = Depends(get_db)):
    """
    AI chat endpoint with Server-Sent Events streaming.

    Sends events:
    - type: "text"          → AI text response chunk
    - type: "products"      → Product card data array
    - type: "quote_update"  → Quote created/updated
    - type: "tool_call"     → Tool being executed (for UI indicators)
    - type: "error"         → Error message
    - type: "done"          → Stream complete
    """
    return EventSourceResponse(
        process_chat_message(
            message=request.message,
            conversation_history=request.conversation_history,
            quote_id=request.quote_id,
            db=db,
        )
    )
