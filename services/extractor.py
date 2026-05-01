import fitz  # PyMuPDF
import httpx
import zipfile
import io
import re
from urllib.parse import urlparse
from services.supabase_client import supabase

async def process_document(document_id: str, file_url: str):
    """
    Downloads a file, detects its type, extracts images/URLs, and uploads to Supabase.
    """
    # 1. Download file to memory
    async with httpx.AsyncClient() as client:
        response = await client.get(file_url)
        response.raise_for_status()
        file_bytes = response.content

    # 2. Determine file type from URL (or Supabase storage metadata)
    parsed_url = urlparse(file_url)
    ext = parsed_url.path.split('.')[-1].lower()

    assets_to_insert = []

    # 3. ROUTER: Send to the correct extraction engine
    if ext == "pdf":
        assets_to_insert = extract_from_pdf(document_id, file_bytes)
    elif ext in ["docx", "pptx"]:
        assets_to_insert = extract_from_office_zip(document_id, file_bytes, ext)
    elif ext in ["md", "html"]:
        assets_to_insert = extract_from_text(document_id, file_bytes, ext)
    else:
        print(f"Unsupported visual extraction for type: {ext}. Skipping asset extraction.")
        return {"images_found": 0, "urls_found": 0}

    # 4. Bulk Insert into Database
    if assets_to_insert:
        supabase.table("document_assets").insert(assets_to_insert).execute()
        
    return {
        "images_found": len([a for a in assets_to_insert if a['asset_type'] == 'image']),
        "urls_found": len([a for a in assets_to_insert if a['asset_type'] == 'url'])
    }

def extract_from_pdf(document_id: str, file_bytes: bytes):
    """Extract images and URLs from a PDF file."""
    assets = []
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    
    for page_num in range(len(doc)):
        page = doc[page_num]
        
        # Images
        for img_index, img in enumerate(page.get_images(full=True)):
            xref = img[0]
            base_image = doc.extract_image(xref)
            if base_image["width"] < 100 or base_image["height"] < 100: continue
                
            storage_path = f"{document_id}/pdf_p{page_num + 1}_{img_index}.{base_image['ext']}"
            supabase.storage.from_("extracted_assets").upload(
                path=storage_path, file=base_image["image"], file_options={"content-type": f"image/{base_image['ext']}"}
            )
            public_url = supabase.storage.from_("extracted_assets").get_public_url(storage_path)
            
            assets.append({
                "document_id": document_id, "asset_type": "image", "content": public_url, "page_number": page_num + 1,
                "metadata": {"width": base_image["width"], "height": base_image["height"], "extension": base_image['ext']}
            })
            
        # URLs
        for link in page.get_links():
            if link["kind"] == fitz.LINK_URI:
                assets.append({
                    "document_id": document_id, "asset_type": "url", "content": link["uri"], "page_number": page_num + 1,
                    "metadata": {"label": link.get("uri")}
                })
    doc.close()
    return assets

def extract_from_office_zip(document_id: str, file_bytes: bytes, ext: str):
    """
    DOCX and PPTX are ZIP files. We extract images from media folders
    and parse .rels XML files to grab all external URLs.
    """
    assets = []
    
    # Word puts images in 'word/media/', PowerPoint in 'ppt/media/'
    media_prefix = "word/media/" if ext == "docx" else "ppt/media/"
    
    # Regex to find external links in .rels files
    # Looks for: Target="https://..." TargetMode="External"
    url_pattern = re.compile(rb'Target="([^"]+)"\s+TargetMode="External"')
    
    try:
        with zipfile.ZipFile(io.BytesIO(file_bytes)) as archive:
            # Keep track of unique URLs to avoid duplicates
            found_urls = set()

            for file_name in archive.namelist():
                
                # --- 1. EXTRACT IMAGES ---
                if file_name.startswith(media_prefix):
                    image_bytes = archive.read(file_name)
                    image_ext = file_name.split('.')[-1].lower()
                    
                    if image_ext not in ["png", "jpg", "jpeg", "gif", "svg", "webp"]:
                        continue

                    safe_name = file_name.replace("/", "_")
                    storage_path = f"{document_id}/{safe_name}"
                    
                    # Upload to Supabase
                    supabase.storage.from_("extracted_assets").upload(
                        path=storage_path, file=image_bytes, file_options={"content-type": f"image/{image_ext}"}
                    )
                    public_url = supabase.storage.from_("extracted_assets").get_public_url(storage_path)
                    
                    assets.append({
                        "document_id": document_id, 
                        "asset_type": "image", 
                        "content": public_url, 
                        "page_number": 1, 
                        "metadata": {"source": file_name, "extension": image_ext}
                    })

                # --- 2. EXTRACT URLS ---
                elif file_name.endswith('.rels'):
                    rels_data = archive.read(file_name)
                    matches = url_pattern.findall(rels_data)
                    
                    for match in matches:
                        url = match.decode('utf-8', errors='ignore')
                        
                        # Filter out internal microsoft schemas, keep real web links
                        if url.startswith('http') and url not in found_urls:
                            found_urls.add(url)
                            assets.append({
                                "document_id": document_id,
                                "asset_type": "url",
                                "content": url,
                                "page_number": 1,
                                "metadata": {"label": url, "source": "rels_file"}
                            })

    except zipfile.BadZipFile:
        print(f"Failed to unzip {ext} file.")
        
    return assets

def extract_from_text(document_id: str, file_bytes: bytes, ext: str):
    """
    HTML and Markdown usually don't EMBED images, they LINK to them.
    We use regex to scrape out the URLs and Image links.
    """
    assets = []
    text = file_bytes.decode('utf-8', errors='ignore')
    
    # 1. Regex to find Markdown images: ![alt](url)
    md_images = re.findall(r'!\[.*?\]\((.*?)\)', text)
    # 2. Regex to find HTML images: <img src="url">
    html_images = re.findall(r'<img[^>]+src=["\'](.*?)["\']', text, re.IGNORECASE)
    
    all_image_links = list(set(md_images + html_images))
    
    for img_url in all_image_links:
        if img_url.startswith("http"): # Only grab external images, ignore local relative paths
            assets.append({
                "document_id": document_id, "asset_type": "image", "content": img_url, 
                "page_number": 1, "metadata": {"source": "external_link"}
            })

    # Find raw web links
    urls = re.findall(r'(https?://[^\s<)"]+)', text)
    for url in set(urls):
        # Prevent double-counting images as URLs
        if url not in all_image_links:
            assets.append({
                "document_id": document_id, "asset_type": "url", "content": url, 
                "page_number": 1, "metadata": {"label": url}
            })
            
    return assets