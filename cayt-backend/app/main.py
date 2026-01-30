"""
CAYT Backend - FastAPI 메인 애플리케이션
YouTube 자막 추출 및 번역 API를 제공합니다.
"""

import sys
import uuid
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from typing import Optional

from config import get_settings
from app.models import (
    VideoSubtitleRequest,
    VideoSubtitleResponse,
    SubtitleInfo,
    SubtitleData,
)
from app.models.subtitle import SubtitleType
from app.modules import (
    SubtitleExtractor,
    SubtitleExtractionError,
    Translator,
    TranslationResult,
    TranslationStatus,
    get_cache,
    CachedTranslation,
)
from app.modules.stt import clear_audio_cache, get_audio_cache_stats
from app.utils import extract_video_id


settings = get_settings()

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Context-Aware YouTube Translator - 맥락 기반 유튜브 자막 번역 API",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "chrome-extension://*",
        "http://localhost:*",
        "http://127.0.0.1:*",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 인스턴스 생성
extractor = SubtitleExtractor(temp_dir=settings.TEMP_DIR, enable_stt=True)
translator = Translator()
cache = get_cache()


# ===== 요청 로깅 미들웨어 =====

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    
    # 번역 요청만 상세 로깅
    if "/translate" in request.url.path and request.method == "GET":
        video_url = request.query_params.get("video_url", "")
        video_id = extract_video_id(video_url) if video_url else "unknown"
        print(f"\n{'='*60}")
        print(f"[REQUEST] 번역 요청 시작")
        print(f"  Video ID: {video_id}")
        print(f"  Client: {request.client.host if request.client else 'unknown'}")
        print(f"  Time: {time.strftime('%H:%M:%S')}")
        print(f"{'='*60}")
    
    response = await call_next(request)
    
    duration = time.time() - start_time
    
    if "/translate" in request.url.path and request.method == "GET":
        print(f"[RESPONSE] 완료 ({duration:.2f}초, status={response.status_code})")
    
    return response


# ===== Health =====

@app.get("/", tags=["Health"])
async def root():
    return {
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running"
    }


@app.get("/health", tags=["Health"])
async def health_check():
    ollama_status = "connected" if translator.check_connection() else "disconnected"
    stt_status = "available" if extractor.is_stt_available() else "unavailable"
    cache_stats = cache.get_stats()
    audio_stats = get_audio_cache_stats()
    
    return {
        "status": "healthy",
        "ollama": ollama_status,
        "model": settings.LLM_MODEL,
        "stt": stt_status,
        "translation_cache": cache_stats,
        "audio_cache": audio_stats,
    }


# ===== Cache =====

@app.get("/api/v1/cache/stats", tags=["Cache"])
async def get_cache_stats():
    """캐시 통계 조회"""
    return {
        "success": True,
        "translation_cache": cache.get_stats(),
        "audio_cache": get_audio_cache_stats(),
    }


@app.delete("/api/v1/cache/{video_id}", tags=["Cache"])
async def clear_video_cache(video_id: str):
    """특정 영상 캐시 삭제 (번역 + 오디오)"""
    translation_removed = cache.remove(video_id)
    audio_removed = clear_audio_cache(video_id)
    
    return {
        "success": translation_removed or audio_removed > 0,
        "video_id": video_id,
        "translation_removed": translation_removed,
        "audio_removed": audio_removed,
    }


@app.delete("/api/v1/cache", tags=["Cache"])
async def clear_all_cache():
    """전체 캐시 초기화 (번역 + 오디오)"""
    translation_count = cache.clear()
    audio_count = clear_audio_cache()
    
    return {
        "success": True,
        "translation_cleared": translation_count,
        "audio_cleared": audio_count,
    }


# ===== Subtitles =====

@app.get("/api/v1/subtitles/list", tags=["Subtitles"])
async def list_available_subtitles(
    video_url: str = Query(..., description="YouTube 영상 URL 또는 Video ID")
) -> dict:
    """사용 가능한 수동 자막 목록을 조회합니다."""
    video_id = extract_video_id(video_url)
    if not video_id:
        raise HTTPException(status_code=400, detail="유효하지 않은 YouTube URL입니다.")
    
    try:
        subtitles = extractor.list_available_subtitles(video_url)
        stt_available = extractor.is_stt_available()
        
        return {
            "success": True,
            "video_id": video_id,
            "manual_subtitles": [sub.model_dump() for sub in subtitles],
            "total_count": len(subtitles),
            "stt_available": stt_available,
            "message": "수동 자막이 없으면 STT로 음성 인식됩니다." if stt_available else None
        }
    except SubtitleExtractionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"서버 오류: {str(e)}")


@app.get("/api/v1/subtitles/extract", tags=["Subtitles"])
async def extract_subtitle_endpoint(
    video_url: str = Query(..., description="YouTube 영상 URL"),
    language: str = Query(default="en", description="자막 언어 코드"),
    force_stt: bool = Query(default=False, description="STT 강제 사용")
) -> VideoSubtitleResponse:
    """YouTube 영상에서 자막을 추출합니다."""
    video_id = extract_video_id(video_url)
    if not video_id:
        return VideoSubtitleResponse(
            success=False,
            message="유효하지 않은 YouTube URL입니다.",
            data=None,
            available_subtitles=[]
        )
    
    try:
        available = extractor.list_available_subtitles(video_url)
        subtitle_data = extractor.extract_subtitle(
            video_url=video_url,
            language=language,
            force_stt=force_stt
        )
        
        if subtitle_data.subtitle_type == SubtitleType.AUTO:
            message = f"STT 음성 인식 완료 ({subtitle_data.total_segments}개 세그먼트)"
        else:
            message = f"수동 자막 추출 완료 ({subtitle_data.total_segments}개 세그먼트)"
        
        return VideoSubtitleResponse(
            success=True,
            message=message,
            data=subtitle_data,
            available_subtitles=available
        )
    except SubtitleExtractionError as e:
        return VideoSubtitleResponse(
            success=False,
            message=str(e),
            data=None,
            available_subtitles=[]
        )
    except Exception as e:
        return VideoSubtitleResponse(
            success=False,
            message=f"서버 오류: {str(e)}",
            data=None,
            available_subtitles=[]
        )


# ===== STT =====

@app.get("/api/v1/stt/status", tags=["STT"])
async def get_stt_status() -> dict:
    """STT (Faster-Whisper) 상태를 확인합니다."""
    try:
        from app.modules.stt import get_stt
        
        stt = get_stt()
        is_available = stt.is_available()
        
        return {
            "success": True,
            "available": is_available,
            "models": stt.get_available_models() if is_available else [],
            "current_config": {
                "model_size": stt.config.model_size.value,
                "device": stt.config.device,
                "vad_filter": stt.config.vad_filter
            } if is_available else None,
            "audio_cache": get_audio_cache_stats(),
        }
    except Exception as e:
        return {
            "success": False,
            "available": False,
            "message": f"STT 상태 확인 실패: {str(e)}"
        }


# ===== Translation =====

@app.get("/api/v1/translate", tags=["Translation"])
async def translate_video_subtitles(
    video_url: str = Query(..., description="YouTube 영상 URL"),
    source_lang: str = Query(default="en", description="원본 언어 코드"),
    use_context: bool = Query(default=True, description="LLM 컨텍스트 분석 사용"),
    force_stt: bool = Query(default=False, description="STT 강제 사용"),
    no_cache: bool = Query(default=False, description="캐시 무시하고 새로 번역")
) -> dict:
    """
    YouTube 영상의 자막을 한국어로 번역합니다.
    캐시된 결과가 있으면 즉시 반환합니다.
    """
    video_id = extract_video_id(video_url)
    if not video_id:
        raise HTTPException(status_code=400, detail="유효하지 않은 YouTube URL입니다.")
    
    task_id = str(uuid.uuid4())[:8]
    
    print(f"[API] 번역 요청: video_id={video_id}, no_cache={no_cache}")
    
    # 1. 캐시 확인 (no_cache가 아닌 경우)
    if not no_cache:
        cached = cache.get(video_id)
        if cached:
            print(f"[API] ✅ 캐시 히트! 즉시 반환: {video_id}")
            return cached.to_response(task_id)
    
    # 2. 이미 진행 중인지 확인
    if cache.is_in_progress(video_id):
        print(f"[API] ⚠️ 이미 진행 중: {video_id}")
        raise HTTPException(
            status_code=409,
            detail="이 영상은 이미 번역 중입니다. 잠시 후 다시 시도해주세요."
        )
    
    # 3. Ollama 연결 확인
    if not translator.check_connection():
        raise HTTPException(
            status_code=503,
            detail="Ollama 서버에 연결할 수 없습니다. 'ollama serve' 명령으로 서버를 시작해주세요."
        )
    
    # 4. 번역 시작
    cache.set_in_progress(video_id, True)
    
    try:
        # 자막 추출
        print(f"[API] 📥 자막 추출 시작: {video_id}")
        subtitle_data = extractor.extract_subtitle(
            video_url=video_url,
            language=source_lang,
            force_stt=force_stt
        )
        print(f"[API] 📥 자막 추출 완료: {subtitle_data.total_segments}개 세그먼트")
        
        # 번역 수행
        print(f"[API] 🔄 번역 시작: {video_id}")
        translation_result = await translator.translate_subtitle_data_async(
            subtitle_data=subtitle_data,
            use_llm_context=use_context
        )
        
        if translation_result.status == TranslationStatus.FAILED:
            raise HTTPException(
                status_code=500,
                detail=f"번역 실패: {translation_result.error_message}"
            )
        
        if translation_result.status == TranslationStatus.CANCELLED:
            return {
                "success": False,
                "task_id": task_id,
                "video_id": video_id,
                "message": "번역이 취소되었습니다.",
                "segments": [],
                "total_segments": 0
            }
        
        # 응답 생성
        source_type = "stt" if subtitle_data.subtitle_type == SubtitleType.AUTO else "manual"
        segments = [
            {
                "start": seg.start,
                "end": seg.end,
                "original": seg.original_text,
                "translated": seg.translated_text
            }
            for seg in translation_result.segments
        ]
        
        # 캐시 저장
        cached_translation = CachedTranslation(
            video_id=video_id,
            title=translation_result.title,
            source_language=translation_result.source_language,
            target_language=translation_result.target_language,
            source_type=source_type,
            context={
                "topic": translation_result.context.topic,
                "domain": translation_result.context.domain,
                "key_terms": translation_result.context.key_terms,
            },
            segments=segments,
            total_segments=translation_result.total_segments,
        )
        cache.set(video_id, cached_translation)
        
        print(f"[API] ✅ 번역 완료 및 캐시 저장: {video_id}")
        
        return {
            "success": True,
            "task_id": task_id,
            "video_id": video_id,
            "title": translation_result.title,
            "source_language": translation_result.source_language,
            "target_language": translation_result.target_language,
            "source_type": source_type,
            "context": {
                "topic": translation_result.context.topic,
                "domain": translation_result.context.domain,
                "key_terms": translation_result.context.key_terms,
            },
            "segments": segments,
            "total_segments": translation_result.total_segments,
            "cached": False,
        }
        
    except HTTPException:
        raise
    except SubtitleExtractionError as e:
        print(f"[API] ❌ 자막 추출 오류: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(f"[API] ❌ 서버 오류: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"서버 오류: {str(e)}")
    finally:
        # 진행 상태 해제
        cache.set_in_progress(video_id, False)


@app.get("/api/v1/translate/models", tags=["Translation"])
async def list_available_models() -> dict:
    """사용 가능한 LLM 모델 목록을 조회합니다."""
    return {
        "success": True,
        "current_model": settings.LLM_MODEL,
        "available_models": translator.list_models(),
        "ollama_host": settings.OLLAMA_HOST
    }


@app.post("/api/v1/translate/cancel", tags=["Translation"])
async def cancel_translation(
    task_id: Optional[str] = Query(default=None, description="취소할 작업 ID"),
    video_id: Optional[str] = Query(default=None, description="취소할 영상 ID")
) -> dict:
    """진행 중인 번역 작업을 취소합니다."""
    if not task_id and not video_id:
        raise HTTPException(status_code=400, detail="task_id 또는 video_id를 제공해야 합니다.")
    
    success = False
    if task_id:
        success = translator.cancel_task(task_id)
    if video_id:
        success = translator.cancel_video(video_id) or success
        cache.set_in_progress(video_id, False)
    
    return {
        "success": success,
        "task_id": task_id,
        "video_id": video_id,
        "message": "작업 취소 요청 완료"
    }


# ===== 예외 핸들러 =====

@app.exception_handler(SubtitleExtractionError)
async def subtitle_extraction_error_handler(request, exc: SubtitleExtractionError):
    return JSONResponse(status_code=400, content={"success": False, "message": str(exc)})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)
