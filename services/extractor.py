import fitz  # PyMuPDF
import httpx
import uuid
import io
from services.supabase_client import supabase

async def process_document(document_id: str, file_url: str):
    """
    Downloads a PDF, extracts images and URLs, and uploads them to Supabase.
    """
    # 1. Download file to memory
    async with httpx.AsyncClient() as client:
        response = await client.get(file_url)
        response.raise_for_status()
        pdf_bytes = response.content

    # 2. Open PDF with PyMuPDF
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    
    assets_to_insert = []
    
    for page_num in range(len(doc)):
        page = doc[page_num]
        
        # --- Extract Images ---
        images = page.get_images(full=True)
        for img_index, img in enumerate(images):
            xref = img[0]
            base_image = doc.extract_image(xref)
            image_bytes = base_image["image"]
            image_ext = base_image["ext"]
            
            # Filter out tiny logos/icons (e.g., width or height < 100px)
            if base_image["width"] < 100 or base_image["height"] < 100:
                continue
                
            # Upload to Supabase Storage
            storage_path = f"{document_id}/page_{page_num + 1}_{img_index}.{image_ext}"
            supabase.storage.from_("extracted_assets").upload(
                path=storage_path,
                file=image_bytes,
                file_options={"content-type": f"image/{image_ext}"}
            )
            
            # Get Public URL
            public_url = supabase.storage.from_("extracted_assets").get_public_url(storage_path)
            
            assets_to_insert.append({
                "document_id": document_id,
                "asset_type": "image",
                "content": public_url,
                "page_number": page_num + 1,
                "metadata": {
                    "width": base_image["width"],
                    "height": base_image["height"],
                    "extension": image_ext
                }
            })
            
        # --- Extract URLs ---
        links = page.get_links()
        for link in links:
            if link["kind"] == fitz.LINK_URI:
                uri = link["uri"]
                
                # Try to extract the text covering the link for a clean UI label
                link_rect = link["from"]
                link_text = page.get_textbox(link_rect).strip()
                label = link_text if link_text else uri
                
                assets_to_insert.append({
                    "document_id": document_id,
                    "asset_type": "url",
                    "content": uri,
                    "page_number": page_num + 1,
                    "metadata": {
                        "label": label
                    }
                })

    # 3. Bulk Insert into Database
    if assets_to_insert:
        supabase.table("document_assets").insert(assets_to_insert).execute()
        
    doc.close()
    return {"images_found": len([a for a in assets_to_insert if a['asset_type'] == 'image']),
            "urls_found": len([a for a in assets_to_insert if a['asset_type'] == 'url'])}