"""
CAYT 번역 결과 캐시 모듈

영상별 번역 결과를 메모리에 캐싱하여 중복 요청을 방지합니다.
"""

import time
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from threading import Lock


@dataclass
class CachedTranslation:
    """캐싱된 번역 결과"""
    video_id: str
    title: str
    source_language: str
    target_language: str
    source_type: str  # "manual" or "stt"
    context: Dict[str, Any]
    segments: list
    total_segments: int
    created_at: float = field(default_factory=time.time)
    
    def is_expired(self, ttl_seconds: int = 3600) -> bool:
        """캐시 만료 여부 확인 (기본 1시간)"""
        return time.time() - self.created_at > ttl_seconds
    
    def to_response(self, task_id: str) -> dict:
        """API 응답 형식으로 변환"""
        return {
            "success": True,
            "task_id": task_id,
            "video_id": self.video_id,
            "title": self.title,
            "source_language": self.source_language,
            "target_language": self.target_language,
            "source_type": self.source_type,
            "context": self.context,
            "segments": self.segments,
            "total_segments": self.total_segments,
            "cached": True,
        }


class TranslationCache:
    """
    번역 결과 캐시 관리자
    
    Thread-safe 메모리 캐시로 구현됩니다.
    """
    
    def __init__(self, max_size: int = 100, ttl_seconds: int = 3600):
        """
        Args:
            max_size: 최대 캐시 항목 수
            ttl_seconds: 캐시 유효 시간 (초)
        """
        self._cache: Dict[str, CachedTranslation] = {}
        self._lock = Lock()
        self._max_size = max_size
        self._ttl_seconds = ttl_seconds
        
        # 진행 중인 작업 추적 (중복 요청 방지)
        self._in_progress: Dict[str, bool] = {}
    
    def get(self, video_id: str) -> Optional[CachedTranslation]:
        """캐시된 번역 결과 조회"""
        with self._lock:
            cached = self._cache.get(video_id)
            
            if cached is None:
                return None
            
            # 만료 확인
            if cached.is_expired(self._ttl_seconds):
                del self._cache[video_id]
                return None
            
            print(f"[Cache] 캐시 히트: {video_id}")
            return cached
    
    def set(self, video_id: str, translation: CachedTranslation) -> None:
        """번역 결과 캐싱"""
        with self._lock:
            # 캐시 크기 제한
            if len(self._cache) >= self._max_size:
                self._evict_oldest()
            
            self._cache[video_id] = translation
            print(f"[Cache] 캐시 저장: {video_id} ({translation.total_segments}개 세그먼트)")
    
    def remove(self, video_id: str) -> bool:
        """캐시 항목 제거"""
        with self._lock:
            if video_id in self._cache:
                del self._cache[video_id]
                print(f"[Cache] 캐시 제거: {video_id}")
                return True
            return False
    
    def clear(self) -> int:
        """전체 캐시 초기화"""
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            self._in_progress.clear()
            print(f"[Cache] 캐시 초기화: {count}개 항목 제거")
            return count
    
    def is_in_progress(self, video_id: str) -> bool:
        """번역 진행 중 여부 확인"""
        with self._lock:
            return self._in_progress.get(video_id, False)
    
    def set_in_progress(self, video_id: str, in_progress: bool) -> None:
        """번역 진행 상태 설정"""
        with self._lock:
            if in_progress:
                self._in_progress[video_id] = True
                print(f"[Cache] 번역 시작: {video_id}")
            else:
                self._in_progress.pop(video_id, None)
                print(f"[Cache] 번역 완료/취소: {video_id}")
    
    def _evict_oldest(self) -> None:
        """가장 오래된 캐시 항목 제거"""
        if not self._cache:
            return
        
        oldest_id = min(self._cache.keys(), key=lambda k: self._cache[k].created_at)
        del self._cache[oldest_id]
        print(f"[Cache] 오래된 캐시 제거: {oldest_id}")
    
    def get_stats(self) -> dict:
        """캐시 통계"""
        with self._lock:
            return {
                "cached_videos": len(self._cache),
                "in_progress": len(self._in_progress),
                "max_size": self._max_size,
                "ttl_seconds": self._ttl_seconds,
                "video_ids": list(self._cache.keys()),
            }


# 글로벌 캐시 인스턴스
_translation_cache: Optional[TranslationCache] = None


def get_cache() -> TranslationCache:
    """글로벌 캐시 인스턴스 반환"""
    global _translation_cache
    if _translation_cache is None:
        _translation_cache = TranslationCache()
    return _translation_cache
