from fastapi import Request, HTTPException
from qstash import Receiver
from core.config import settings

receiver = Receiver(
    current_signing_key=settings.QSTASH_CURRENT_SIGNING_KEY,
    next_signing_key=settings.QSTASH_NEXT_SIGNING_KEY,
)

async def verify_qstash_signature(request: Request):
    """
    Dependency to verify the incoming webhook signature.
    """
    # FIX: Use settings.ENVIRONMENT instead of os.getenv
    if settings.ENVIRONMENT == "development":
        return True

    signature = request.headers.get("Upstash-Signature")
    if not signature:
        raise HTTPException(status_code=401, detail="Missing Upstash-Signature header")

    body = await request.body()
    try:
        is_valid = receiver.verify(
            body=body.decode("utf-8"),
            signature=signature,
            url=str(request.url)
        )
        if not is_valid:
            raise HTTPException(status_code=401, detail="Invalid QStash signature")
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Signature verification failed: {str(e)}")
    
    return True