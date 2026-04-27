from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from core.security import verify_qstash_signature
from services.extractor import process_document

router = APIRouter()

class ExtractPayload(BaseModel):
    documentId: str
    fileUrl: str
    userId: str
    isPremium: bool

@router.post("/extract", dependencies=[Depends(verify_qstash_signature)])
async def extract_assets_endpoint(payload: ExtractPayload):
    try:
        # Await the processing directly so QStash knows if it succeeded or failed
        result = await process_document(
            document_id=payload.documentId,
            file_url=payload.fileUrl
        )
        return {"status": "success", "data": result}
    except Exception as e:
        print(f"Extraction Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))