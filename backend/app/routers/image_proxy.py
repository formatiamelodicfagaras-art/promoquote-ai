"""
Image proxy endpoint — downloads, resizes, converts to WebP, and caches
external product images. Reduces 2-3 MB originals to ~30-50 KB thumbnails.
"""
import hashlib
import logging
import os
from io import BytesIO
from pathlib import Path

import httpx
from fastapi import APIRouter, Query
from fastapi.responses import Response
from PIL import Image

logger = logging.getLogger(__name__)
router = APIRouter()

CACHE_DIR = Path(os.environ.get("IMG_CACHE_DIR", "./data/img_cache"))
CACHE_DIR.mkdir(parents=True, exist_ok=True)

MAX_WIDTH = 400
QUALITY = 80
FETCH_TIMEOUT = 15.0


def _cache_key(url: str, w: int) -> str:
    h = hashlib.md5(f"{url}|{w}".encode()).hexdigest()
    return h


@router.get("/")
async def proxy_image(
    url: str = Query(..., description="Original image URL"),
    w: int = Query(MAX_WIDTH, ge=50, le=1200, description="Target width"),
):
    """Fetch, resize & cache an external image as WebP."""
    key = _cache_key(url, w)
    cached = CACHE_DIR / f"{key}.webp"

    # Serve from cache
    if cached.exists():
        return Response(
            content=cached.read_bytes(),
            media_type="image/webp",
            headers={"Cache-Control": "public, max-age=604800", "X-Cache": "HIT", "Access-Control-Allow-Origin": "*"},
        )

    # Fetch original
    try:
        async with httpx.AsyncClient(timeout=FETCH_TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
    except Exception as e:
        logger.warning(f"Image proxy fetch failed: {url} — {e}")
        return Response(status_code=502, content=b"fetch error")

    # Resize + convert to WebP
    try:
        img = Image.open(BytesIO(resp.content))
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        # Resize maintaining aspect ratio
        orig_w, orig_h = img.size
        if orig_w > w:
            ratio = w / orig_w
            new_h = int(orig_h * ratio)
            img = img.resize((w, new_h), Image.LANCZOS)

        buf = BytesIO()
        img.save(buf, format="WEBP", quality=QUALITY)
        data = buf.getvalue()
    except Exception as e:
        logger.warning(f"Image proxy resize failed: {url} — {e}")
        # Serve original if resize fails
        return Response(
            content=resp.content,
            media_type=resp.headers.get("content-type", "image/jpeg"),
            headers={"Cache-Control": "public, max-age=3600", "Access-Control-Allow-Origin": "*"},
        )

    # Write cache
    try:
        cached.write_bytes(data)
    except Exception:
        pass

    return Response(
        content=data,
        media_type="image/webp",
        headers={"Cache-Control": "public, max-age=604800", "X-Cache": "MISS", "Access-Control-Allow-Origin": "*"},
    )
