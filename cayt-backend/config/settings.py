"""
CAYT Backend 설정 모듈
환경 변수 및 애플리케이션 상수를 관리합니다.
"""

from pydantic_settings import BaseSettings
from typing import Optional, Literal
from functools import lru_cache


class Settings(BaseSettings):
    """
    애플리케이션 설정 클래스
    환경 변수에서 값을 로드하며, 기본값을 제공합니다.
    """
    
    # 애플리케이션 기본 설정
    APP_NAME: str = "CAYT Backend"
    APP_VERSION: str = "0.2.0"  # Phase 2
    DEBUG: bool = True
    
    # 서버 설정
    HOST: str = "127.0.0.1"
    PORT: int = 8000
    
    # 자막 추출 설정
    SUBTITLE_LANGUAGES: list[str] = ["en"]  # 우선 추출할 언어 목록
    SUBTITLE_FORMAT: str = "vtt"  # 자막 포맷 (vtt, srt, json3)
    ENABLE_STT_FALLBACK: bool = True  # 자막 없을 때 STT 사용 여부
    
    # 임시 파일 저장 경로
    TEMP_DIR: str = "/tmp/cayt"
    
    # LLM 설정
    OLLAMA_HOST: str = "http://localhost:11434"
    LLM_MODEL: str = "translategemma:4b"
    
    # 번역 설정
    SOURCE_LANGUAGE: str = "en"
    TARGET_LANGUAGE: str = "ko"
    
    # 번역 배치 설정
    TRANSLATION_BATCH_SIZE: int = 10  # 한 번에 번역할 세그먼트 수
    TRANSLATION_MAX_RETRIES: int = 3  # 번역 실패 시 재시도 횟수
    
    # ----------------
    # STT (Faster-Whisper) 설정
    # ----------------
    STT_MODEL_SIZE: Literal[
        "tiny", "base", "small", "medium", 
        "large-v2", "large-v3", "large-v3-turbo"
    ] = "large-v3-turbo"  # 속도/정확도 균형
    
    STT_DEVICE: Literal["auto", "cuda", "cpu"] = "auto"  # 자동 감지
    STT_COMPUTE_TYPE: Literal["auto", "float16", "int8", "float32"] = "auto"
    STT_VAD_FILTER: bool = True  # 음성 구간 자동 감지
    STT_BEAM_SIZE: int = 5  # 빔 서치 크기
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    """
    설정 인스턴스를 반환합니다.
    lru_cache를 사용하여 싱글톤 패턴을 구현합니다.
    """
    return Settings()
