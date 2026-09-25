import asyncio
import logging
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, Query, HTTPException, Response
import yt_dlp

# Set up clean logging format
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - %(message)s"
)
logger = logging.getLogger("MusicAPI")

app = FastAPI(
    title="Production Telegram VC Music API",
    description="High-availability YouTube audio extraction API without cookie dependencies.",
    version="2.0.0"
)

# Base yt-dlp Configuration
BASE_YTDL_OPTS = {
    'format': 'bestaudio/best',
    'quiet': True,
    'no_warnings': True,
    'skip_download': True,
    'source_address': '0.0.0.0',
    'nocheckcertificate': True,
}

# Sequentially fallback through different client profiles if one fails
CLIENT_PROFILES: List[List[str]] = [
    ['ios', 'tvhtml5'],
    ['android', 'web'],
    ['mweb', 'android_vr']
]


@app.get("/health")
async def health_check():
    """Simple health check endpoint."""
    return {"ok": True, "status": "operational"}


@app.get("/search")
async def search_tracks(q: str = Query(..., min_length=1), limit: int = 5):
    """
    Search YouTube for songs without downloading.
    Returns metadata for top results.
    """
    loop = asyncio.get_running_loop()

    def _search() -> List[Dict[str, Any]]:
        opts = {
            **BASE_YTDL_OPTS,
            'extract_flat': 'in_playlist',
            'extractor_args': {
                'youtube': {
                    'player_client': ['ios', 'android', 'web']
                }
            }
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            res = ydl.extract_info(f"ytsearch{limit}:{q}", download=False)
            results = []
            if res and 'entries' in res:
                for entry in res['entries']:
                    if not entry:
                        continue
                    results.append({
                        "id": entry.get("id"),
                        "title": entry.get("title", "Unknown Title"),
                        "author": entry.get("uploader", "Unknown Artist"),
                        "duration": str(entry.get("duration", 0)),
                        "lengthSeconds": entry.get("duration", 0),
                        "thumbnail": entry.get("thumbnail") or f"https://i.ytimg.com/vi/{entry.get('id')}/hqdefault.jpg"
                    })
            return results

    try:
        data = await loop.run_in_executor(None, _search)
        return {
            "ok": True,
            "query": q,
            "count": len(data),
            "results": data
        }
    except Exception as e:
        logger.error(f"Search failed for query '{q}': {e}")
        raise HTTPException(
            status_code=500,
            detail={"ok": False, "error": str(e), "code": "SEARCH_FAILED"}
        )


@app.get("/audio")
async def get_audio_stream(id: str = Query(..., min_length=5)):
    """
    Extract direct playable audio URL using Client Spoofing.
    Iterates through iOS, Android, TV clients to bypass 403 Forbidden errors.
    """
    loop = asyncio.get_running_loop()

    for profile in CLIENT_PROFILES:
        def _extract() -> Optional[Dict[str, Any]]:
            opts = {
                **BASE_YTDL_OPTS,
                'extractor_args': {
                    'youtube': {
                        'player_client': profile,
                        'player_skip': ['webpage', 'configs']
                    }
                }
            }
            url = f"https://www.youtube.com/watch?v={id}"
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(url, download=False)

        try:
            info = await loop.run_in_executor(None, _extract)
            if not info:
                continue

            audio_url = info.get('url')

            # Fallback format extraction if top-level url is absent
            if not audio_url and info.get('formats'):
                for fmt in info.get('formats', []):
                    if fmt.get('acodec') != 'none' and fmt.get('vcodec') == 'none':
                        audio_url = fmt.get('url')
                        break

            if audio_url:
                logger.info(f"Successfully resolved stream for [{id}] using profile: {profile}")
                return {
                    "ok": True,
                    "id": id,
                    "title": info.get("title", "Unknown Title"),
                    "audio_url": audio_url,
                    "used_client": profile[0]
                }
        except yt_dlp.utils.DownloadError as err:
            logger.warning(f"Profile {profile} failed for video [{id}]: {err}")
            continue
        except Exception as err:
            logger.error(f"Unexpected error with profile {profile} for [{id}]: {err}")
            continue

    # Standardized failure response if all client profiles fail
    return {
        "ok": False,
        "error": "All client spoofing profiles failed to extract audio stream.",
        "code": "ALL_PROFILES_FAILED"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend:app", host="0.0.0.0", port=8000, reload=False)
