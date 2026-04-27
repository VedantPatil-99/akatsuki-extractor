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
    if settings.ENVIRONMENT == "development":
        return True

    signature = request.headers.get("Upstash-Signature")
    if not signature:
        raise HTTPException(status_code=401, detail="Missing Upstash-Signature header")

    body = await request.body()
    
    # Force rebuild the exact HTTPS URL using the original Host header
    host = request.headers.get("host")
    actual_url = f"https://{host}{request.url.path}"

    try:
        is_valid = receiver.verify(
            body=body.decode("utf-8"),
            signature=signature,
            url=actual_url
        )
        if not is_valid:
            print("🛑 QSTASH ERROR: Signature evaluated to False but threw no exception.")
            raise HTTPException(status_code=401, detail="Invalid QStash signature")
            
    except Exception as e:
        # This print statement is our smoking gun. It will show in Railway App Logs!
        print(f"🛑 QSTASH VERIFICATION FAILED: {str(e)}")
        print(f"🛑 URL CHECKED: {actual_url}")
        raise HTTPException(status_code=401, detail=f"Signature verification failed: {str(e)}")
    
    return True