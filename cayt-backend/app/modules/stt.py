"""
CAYT STT (Speech-to-Text) 모듈

Faster-Whisper를 사용하여 자막이 없는 영상의 음성을 텍스트로 변환합니다.
"""

import os
import glob
import shutil
import subprocess
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Literal
from enum import Enum
from threading import Lock

from config import get_settings
from app.models.subtitle import SubtitleSegment, SubtitleData, SubtitleType


settings = get_settings()

# STT 전용 임시 디렉토리
STT_TEMP_DIR = "/tmp/cayt_stt"

# 최소 유효 오디오 파일 크기 (10KB)
MIN_AUDIO_FILE_SIZE = 10 * 1024

# 다운로드 락 (동시 다운로드 방지)
_download_locks: dict[str, Lock] = {}
_global_lock = Lock()


def get_download_lock(video_id: str) -> Lock:
    """video_id별 다운로드 락 반환"""
    with _global_lock:
        if video_id not in _download_locks:
            _download_locks[video_id] = Lock()
        return _download_locks[video_id]


def extract_video_id(url: str) -> Optional[str]:
    """YouTube URL에서 video_id 추출"""
    from urllib.parse import urlparse, parse_qs
    try:
        parsed = urlparse(url)
        return parse_qs(parsed.query).get('v', [None])[0]
    except:
        return None


def build_clean_youtube_url(video_id: str) -> str:
    """순수한 YouTube URL 생성 (playlist 등 제거)"""
    return f"https://www.youtube.com/watch?v={video_id}"


class WhisperModelSize(str, Enum):
    """Whisper 모델 크기"""
    TINY = "tiny"
    BASE = "base"
    SMALL = "small"
    MEDIUM = "medium"
    LARGE_V2 = "large-v2"
    LARGE_V3 = "large-v3"
    TURBO = "large-v3-turbo"


@dataclass
class STTConfig:
    """STT 설정"""
    model_size: WhisperModelSize = WhisperModelSize.TURBO
    device: Literal["auto", "cuda", "cpu"] = "auto"
    compute_type: Literal["auto", "float16", "int8", "float32"] = "auto"
    language: Optional[str] = None
    task: Literal["transcribe", "translate"] = "transcribe"
    beam_size: int = 5
    vad_filter: bool = True
    word_timestamps: bool = False


@dataclass
class STTSegment:
    """STT 결과 세그먼트"""
    start: float
    end: float
    text: str
    confidence: float = 0.0
    
    def to_subtitle_segment(self) -> SubtitleSegment:
        return SubtitleSegment(
            start=self.start,
            end=self.end,
            text=self.text.strip()
        )


@dataclass
class STTResult:
    """STT 결과"""
    segments: list[STTSegment] = field(default_factory=list)
    language: str = ""
    language_probability: float = 0.0
    duration: float = 0.0
    
    @property
    def total_segments(self) -> int:
        return len(self.segments)
    
    @property
    def full_text(self) -> str:
        return " ".join(seg.text.strip() for seg in self.segments)
    
    def to_subtitle_data(self, video_id: str, title: str = "") -> SubtitleData:
        return SubtitleData(
            video_id=video_id,
            title=title,
            language=self.language,
            subtitle_type=SubtitleType.AUTO,
            segments=[seg.to_subtitle_segment() for seg in self.segments]
        )


def check_ffmpeg_available() -> bool:
    """FFmpeg 설치 여부 확인"""
    try:
        result = subprocess.run(
            ['ffmpeg', '-version'],
            capture_output=True,
            timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def find_audio_file(video_id: str) -> Optional[str]:
    """
    다운로드된 오디오 파일 찾기
    최소 크기(10KB) 이상인 파일만 유효한 캐시로 인정
    """
    output_dir = os.path.join(STT_TEMP_DIR, video_id)
    
    if not os.path.exists(output_dir):
        return None
    
    # 우선순위: mp3 > m4a > webm > mp4
    for ext in ['mp3', 'm4a', 'webm', 'mp4']:
        file_path = os.path.join(output_dir, f"audio.{ext}")
        if os.path.exists(file_path):
            file_size = os.path.getsize(file_path)
            # 최소 크기 이상이어야 유효
            if file_size >= MIN_AUDIO_FILE_SIZE:
                return file_path
            else:
                # 손상된 파일 삭제
                print(f"[STT] 손상된 캐시 파일 삭제: {file_path} ({file_size} bytes)")
                try:
                    os.remove(file_path)
                except:
                    pass
    
    return None


def clear_invalid_cache(video_id: str) -> bool:
    """손상된 캐시 디렉토리 삭제"""
    output_dir = os.path.join(STT_TEMP_DIR, video_id)
    if os.path.exists(output_dir):
        try:
            shutil.rmtree(output_dir)
            print(f"[STT] 손상된 캐시 디렉토리 삭제: {video_id}")
            return True
        except:
            pass
    return False


class SpeechToText:
    """Faster-Whisper 기반 음성 인식 클래스"""
    
    def __init__(self, config: STTConfig = None):
        self.config = config or STTConfig()
        self._model = None
        self._model_loaded = False
        self._ffmpeg_available = None
        
        # STT 전용 임시 디렉토리 생성
        os.makedirs(STT_TEMP_DIR, exist_ok=True)
        
        print(f"[STT] 설정: model={self.config.model_size.value}, device={self.config.device}")
    
    @property
    def ffmpeg_available(self) -> bool:
        if self._ffmpeg_available is None:
            self._ffmpeg_available = check_ffmpeg_available()
        return self._ffmpeg_available
    
    def _get_device_and_compute(self) -> tuple[str, str]:
        device = self.config.device
        compute_type = self.config.compute_type
        
        if device == "auto":
            try:
                import torch
                device = "cuda" if torch.cuda.is_available() else "cpu"
            except ImportError:
                device = "cpu"
        
        if compute_type == "auto":
            compute_type = "float16" if device == "cuda" else "int8"
        
        return device, compute_type
    
    def _load_model(self):
        if self._model_loaded:
            return
        
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            raise ImportError(
                "faster-whisper가 설치되지 않았습니다. "
                "'pip install faster-whisper' 명령으로 설치해주세요."
            )
        
        device, compute_type = self._get_device_and_compute()
        
        print(f"[STT] 모델 로딩: {self.config.model_size.value} on {device} ({compute_type})")
        
        self._model = WhisperModel(
            self.config.model_size.value,
            device=device,
            compute_type=compute_type
        )
        
        self._model_loaded = True
        print(f"[STT] 모델 로드 완료")
    
    def transcribe(
        self,
        audio_path: str,
        language: str = None,
        progress_callback: callable = None
    ) -> STTResult:
        self._load_model()
        
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"오디오 파일을 찾을 수 없습니다: {audio_path}")
        
        file_size = os.path.getsize(audio_path)
        file_size_mb = file_size / (1024 * 1024)
        
        # 파일 크기 검증
        if file_size < MIN_AUDIO_FILE_SIZE:
            raise ValueError(f"오디오 파일이 너무 작습니다: {file_size} bytes (최소 {MIN_AUDIO_FILE_SIZE} bytes 필요)")
        
        print(f"[STT] 음성 인식 시작: {audio_path} ({file_size_mb:.1f}MB)")
        
        segments_gen, info = self._model.transcribe(
            audio_path,
            language=language or self.config.language,
            task=self.config.task,
            beam_size=self.config.beam_size,
            vad_filter=self.config.vad_filter,
            word_timestamps=self.config.word_timestamps
        )
        
        result = STTResult(
            language=info.language,
            language_probability=info.language_probability,
            duration=info.duration
        )
        
        print(f"[STT] 세그먼트 처리 중...")
        for idx, segment in enumerate(segments_gen):
            stt_segment = STTSegment(
                start=segment.start,
                end=segment.end,
                text=segment.text,
                confidence=segment.avg_logprob if hasattr(segment, 'avg_logprob') else 0.0
            )
            result.segments.append(stt_segment)
            
            if (idx + 1) % 50 == 0:
                print(f"[STT] 처리 중... {idx + 1}개 세그먼트")
        
        print(f"[STT] 음성 인식 완료: {result.total_segments}개 세그먼트, "
              f"언어={result.language} ({result.language_probability:.1%}), "
              f"길이={result.duration:.1f}초")
        
        return result
    
    def _download_youtube_audio(self, video_id: str) -> str:
        """
        YouTube 오디오를 다운로드합니다.
        이미 다운로드된 파일이 있으면 재사용합니다.
        
        Args:
            video_id: YouTube 영상 ID (URL 아님!)
        """
        # 락 획득 (동시 다운로드 방지)
        lock = get_download_lock(video_id)
        
        with lock:
            # 이미 다운로드된 유효한 파일 확인
            existing = find_audio_file(video_id)
            if existing:
                file_size = os.path.getsize(existing) / (1024 * 1024)
                print(f"[STT] 캐시된 오디오 사용: {existing} ({file_size:.1f}MB)")
                return existing
            
            # 손상된 캐시 디렉토리 정리
            clear_invalid_cache(video_id)
            
            # 순수한 YouTube URL 생성 (playlist 파라미터 제거)
            clean_url = build_clean_youtube_url(video_id)
            
            # 다운로드 시작
            import yt_dlp
            
            output_dir = os.path.join(STT_TEMP_DIR, video_id)
            os.makedirs(output_dir, exist_ok=True)
            
            # 기존 파일 정리
            for f in glob.glob(os.path.join(output_dir, "audio.*")):
                try:
                    os.remove(f)
                    print(f"[STT] 기존 파일 삭제: {f}")
                except:
                    pass
            
            output_template = os.path.join(output_dir, "audio.%(ext)s")
            
            ydl_opts = {
                'outtmpl': output_template,
                'format': 'bestaudio/best',
                'quiet': True,
                'no_warnings': True,
                'retries': 3,
                'fragment_retries': 3,
                'noplaylist': True,
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                },
                'extractor_args': {
                    'youtube': {
                        'player_client': ['android', 'web'],
                    }
                },
            }
            
            if self.ffmpeg_available:
                ydl_opts['postprocessors'] = [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '128',
                }]
            
            print(f"[STT] YouTube 오디오 다운로드 시작: {video_id}")
            print(f"[STT] URL: {clean_url}")
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([clean_url])
            
            # 다운로드된 파일 찾기
            audio_path = find_audio_file(video_id)
            
            if not audio_path:
                # 다운로드 실패 시 디렉토리 정리
                clear_invalid_cache(video_id)
                raise FileNotFoundError("오디오 다운로드에 실패했습니다. 파일이 생성되지 않았거나 크기가 너무 작습니다.")
            
            file_size = os.path.getsize(audio_path) / (1024 * 1024)
            print(f"[STT] 오디오 다운로드 완료: {os.path.basename(audio_path)} ({file_size:.1f}MB)")
            
            return audio_path
    
    def transcribe_youtube_audio(
        self,
        video_url: str,
        language: str = None,
        progress_callback: callable = None
    ) -> STTResult:
        """YouTube 영상의 오디오를 추출하여 음성 인식합니다."""
        video_id = extract_video_id(video_url)
        
        if not video_id:
            raise ValueError(f"유효하지 않은 YouTube URL: {video_url}")
        
        print(f"[STT] 요청 URL: {video_url}")
        print(f"[STT] 추출된 video_id: {video_id}")
        
        # 오디오 다운로드
        audio_path = self._download_youtube_audio(video_id)
        
        # 모델 로드
        self._load_model()
        
        # 음성 인식
        return self.transcribe(audio_path, language, progress_callback)
    
    def is_available(self) -> bool:
        try:
            from faster_whisper import WhisperModel
            return True
        except ImportError:
            return False
    
    def get_available_models(self) -> list[str]:
        return [m.value for m in WhisperModelSize]


# ============================================
# 오디오 캐시 관리
# ============================================

def clear_audio_cache(video_id: str = None) -> int:
    """
    오디오 캐시 삭제
    video_id가 None이면 전체 삭제
    """
    count = 0
    
    if video_id:
        output_dir = os.path.join(STT_TEMP_DIR, video_id)
        if os.path.exists(output_dir):
            shutil.rmtree(output_dir)
            count = 1
            print(f"[STT] 오디오 캐시 삭제: {video_id}")
    else:
        if os.path.exists(STT_TEMP_DIR):
            for item in os.listdir(STT_TEMP_DIR):
                item_path = os.path.join(STT_TEMP_DIR, item)
                if os.path.isdir(item_path):
                    shutil.rmtree(item_path)
                    count += 1
            print(f"[STT] 전체 오디오 캐시 삭제: {count}개")
    
    return count


def get_audio_cache_stats() -> dict:
    """오디오 캐시 통계"""
    if not os.path.exists(STT_TEMP_DIR):
        return {"cached_videos": 0, "total_size_mb": 0, "video_ids": []}
    
    video_ids = []
    total_size = 0
    
    for item in os.listdir(STT_TEMP_DIR):
        item_path = os.path.join(STT_TEMP_DIR, item)
        if os.path.isdir(item_path):
            video_ids.append(item)
            for f in glob.glob(os.path.join(item_path, "*")):
                total_size += os.path.getsize(f)
    
    return {
        "cached_videos": len(video_ids),
        "total_size_mb": round(total_size / (1024 * 1024), 2),
        "video_ids": video_ids,
    }


# ============================================
# 편의 함수
# ============================================

_default_stt: Optional[SpeechToText] = None


def get_stt(config: STTConfig = None) -> SpeechToText:
    global _default_stt
    if _default_stt is None or config is not None:
        _default_stt = SpeechToText(config)
    return _default_stt


def transcribe_audio(audio_path: str, language: str = None) -> STTResult:
    return get_stt().transcribe(audio_path, language)


def transcribe_youtube(video_url: str, language: str = None) -> STTResult:
    return get_stt().transcribe_youtube_audio(video_url, language)
