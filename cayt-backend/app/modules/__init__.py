"""
CAYT 모듈 패키지
핵심 비즈니스 로직을 포함합니다.
"""

from .subtitle_extractor import (
    SubtitleExtractor,
    SubtitleExtractionError,
    extract_subtitle,
    list_subtitles,
    get_extractor,
)

from .context_manager import (
    TranslationContext,
    ContextManager,
    create_translation_context,
)

from .translator import (
    Translator,
    TranslationResult,
    TranslatedSegment,
    TranslationStatus,
    get_translator,
    translate_subtitles,
)

from .stt import (
    SpeechToText,
    STTConfig,
    STTResult,
    STTSegment,
    WhisperModelSize,
    get_stt,
    transcribe_audio,
    transcribe_youtube,
)

from .cache import (
    TranslationCache,
    CachedTranslation,
    get_cache,
)

__all__ = [
    # 자막 추출
    "SubtitleExtractor",
    "SubtitleExtractionError",
    "extract_subtitle",
    "list_subtitles",
    "get_extractor",
    # 컨텍스트 관리
    "TranslationContext",
    "ContextManager",
    "create_translation_context",
    # 번역
    "Translator",
    "TranslationResult",
    "TranslatedSegment",
    "TranslationStatus",
    "get_translator",
    "translate_subtitles",
    # STT (음성 인식)
    "SpeechToText",
    "STTConfig",
    "STTResult",
    "STTSegment",
    "WhisperModelSize",
    "get_stt",
    "transcribe_audio",
    "transcribe_youtube",
    # 캐시
    "TranslationCache",
    "CachedTranslation",
    "get_cache",
]
