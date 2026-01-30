"""
CAYT 자막 추출 모듈
yt-dlp를 사용하여 YouTube 영상에서 자막을 추출합니다.
수동 자막이 없는 경우 Faster-Whisper STT를 사용하여 음성 인식을 수행합니다.

아키텍처:
- 수동 자막 있음 → YouTube에서 다운로드 (고품질)
- 수동 자막 없음 → STT로 직접 음성 인식 (YouTube 자동 자막보다 빠름)
"""

import os
import json
import tempfile
import subprocess
from typing import Optional
from pathlib import Path

from app.models.subtitle import (
    SubtitleType,
    SubtitleSegment,
    SubtitleInfo,
    SubtitleData,
)
from app.utils.parsers import (
    extract_video_id,
    parse_vtt_content,
    merge_duplicate_segments,
    clean_subtitle_text,
)


class SubtitleExtractionError(Exception):
    """자막 추출 중 발생하는 예외"""
    pass


class SubtitleExtractor:
    """
    YouTube 자막 추출기 클래스
    
    전략:
    1. 수동 자막(제작자 업로드)이 있으면 다운로드하여 사용
    2. 수동 자막이 없으면 STT(Faster-Whisper)로 음성 인식
       - YouTube 자동 자막은 사용하지 않음 (속도 이점 없음)
    """
    
    def __init__(self, temp_dir: Optional[str] = None, enable_stt: bool = True):
        """
        Args:
            temp_dir: 임시 파일 저장 경로 (기본값: 시스템 임시 디렉토리)
            enable_stt: STT 사용 여부 (기본값: True)
        """
        self.temp_dir = temp_dir or tempfile.gettempdir()
        Path(self.temp_dir).mkdir(parents=True, exist_ok=True)
        self.enable_stt = enable_stt
        self._stt = None  # 지연 로딩
    
    def _get_stt(self):
        """STT 인스턴스 반환 (지연 로딩)"""
        if self._stt is None:
            try:
                from app.modules.stt import SpeechToText, STTConfig, WhisperModelSize
                config = STTConfig(
                    model_size=WhisperModelSize.TURBO,  # 속도/정확도 균형
                    vad_filter=True
                )
                self._stt = SpeechToText(config)
            except ImportError as e:
                print(f"[SubtitleExtractor] STT 모듈 로드 실패: {e}")
                return None
        return self._stt
    
    def _run_ytdlp(self, args: list[str], timeout: int = 60) -> subprocess.CompletedProcess:
        """yt-dlp 명령을 실행합니다."""
        try:
            result = subprocess.run(
                ["yt-dlp"] + args,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            return result
        except subprocess.TimeoutExpired:
            raise SubtitleExtractionError("yt-dlp 명령 실행 타임아웃")
        except FileNotFoundError:
            raise SubtitleExtractionError(
                "yt-dlp가 설치되어 있지 않습니다. "
                "'pip install yt-dlp'로 설치해주세요."
            )
        except Exception as e:
            raise SubtitleExtractionError(f"yt-dlp 실행 중 오류: {str(e)}")
    
    def get_video_info(self, video_url: str) -> dict:
        """YouTube 영상의 메타데이터를 가져옵니다."""
        video_id = extract_video_id(video_url)
        if not video_id:
            raise SubtitleExtractionError(f"유효하지 않은 YouTube URL: {video_url}")
        
        url = f"https://www.youtube.com/watch?v={video_id}"
        
        result = self._run_ytdlp([
            "--dump-json",
            "--no-download",
            url
        ])
        
        if result.returncode != 0:
            raise SubtitleExtractionError(
                f"영상 정보를 가져올 수 없습니다: {result.stderr}"
            )
        
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            raise SubtitleExtractionError("영상 정보 파싱 실패")
    
    def list_available_subtitles(self, video_url: str) -> list[SubtitleInfo]:
        """
        사용 가능한 자막 목록을 조회합니다.
        수동 자막만 반환합니다 (자동 자막은 STT로 대체).
        """
        try:
            info = self.get_video_info(video_url)
        except SubtitleExtractionError:
            return []
        
        subtitles: list[SubtitleInfo] = []
        
        # 수동 자막만 수집 (제작자 업로드)
        manual_subs = info.get("subtitles", {})
        for lang_code, sub_list in manual_subs.items():
            if sub_list:
                ext = "vtt"
                for sub in sub_list:
                    if sub.get("ext") == "vtt":
                        ext = "vtt"
                        break
                
                subtitles.append(SubtitleInfo(
                    language=lang_code,
                    language_name=self._get_language_name(lang_code),
                    subtitle_type=SubtitleType.MANUAL,
                    ext=ext
                ))
        
        return subtitles
    
    def has_manual_subtitle(self, video_url: str, language: str) -> bool:
        """특정 언어의 수동 자막 존재 여부 확인"""
        available = self.list_available_subtitles(video_url)
        return any(
            sub.language == language and sub.subtitle_type == SubtitleType.MANUAL
            for sub in available
        )
    
    def extract_subtitle(
        self,
        video_url: str,
        language: str = "en",
        force_stt: bool = False
    ) -> SubtitleData:
        """
        YouTube 영상에서 자막을 추출합니다.
        
        전략:
        1. force_stt=True이면 무조건 STT 사용
        2. 수동 자막이 있으면 다운로드
        3. 수동 자막이 없으면 STT 사용
        
        Args:
            video_url: YouTube 영상 URL 또는 ID
            language: 추출할 자막 언어 코드 (기본값: "en")
            force_stt: STT 강제 사용 여부 (기본값: False)
            
        Returns:
            SubtitleData 객체
        """
        video_id = extract_video_id(video_url)
        if not video_id:
            raise SubtitleExtractionError(f"유효하지 않은 YouTube URL: {video_url}")
        
        url = f"https://www.youtube.com/watch?v={video_id}"
        
        # 영상 정보 가져오기
        try:
            info = self.get_video_info(video_url)
            title = info.get("title", "")
        except SubtitleExtractionError:
            title = ""
        
        # STT 강제 사용
        if force_stt:
            print(f"[SubtitleExtractor] STT 강제 사용 모드")
            return self._extract_with_stt(video_url, video_id, title, language)
        
        # 수동 자막 확인
        has_manual = self.has_manual_subtitle(video_url, language)
        
        if has_manual:
            # 수동 자막 다운로드
            print(f"[SubtitleExtractor] 수동 자막 발견: {language}")
            segments = self._download_and_parse_subtitle(
                url=url,
                video_id=video_id,
                language=language
            )
            
            segments = merge_duplicate_segments(segments)
            for segment in segments:
                segment.text = clean_subtitle_text(segment.text)
            
            return SubtitleData(
                video_id=video_id,
                title=title,
                language=language,
                subtitle_type=SubtitleType.MANUAL,
                segments=segments
            )
        else:
            # 수동 자막 없음 → STT 사용
            print(f"[SubtitleExtractor] 수동 자막 없음, STT 사용")
            
            if not self.enable_stt:
                raise SubtitleExtractionError(
                    f"'{language}' 수동 자막이 없고 STT가 비활성화되어 있습니다."
                )
            
            return self._extract_with_stt(video_url, video_id, title, language)
    
    def _extract_with_stt(
        self,
        video_url: str,
        video_id: str,
        title: str,
        language: str
    ) -> SubtitleData:
        """STT를 사용하여 자막을 생성합니다."""
        stt = self._get_stt()
        
        if stt is None:
            raise SubtitleExtractionError(
                "STT 모듈을 사용할 수 없습니다. "
                "'pip install faster-whisper'로 설치해주세요."
            )
        
        if not stt.is_available():
            raise SubtitleExtractionError(
                "Faster-Whisper가 설치되지 않았습니다. "
                "'pip install faster-whisper'로 설치해주세요."
            )
        
        print(f"[SubtitleExtractor] STT 음성 인식 시작...")
        
        try:
            stt_result = stt.transcribe_youtube_audio(
                video_url=video_url,
                language=language if language != "auto" else None
            )
            
            print(f"[SubtitleExtractor] STT 완료: {stt_result.total_segments}개 세그먼트, "
                  f"감지 언어={stt_result.language}")
            
            return stt_result.to_subtitle_data(video_id=video_id, title=title)
            
        except Exception as e:
            raise SubtitleExtractionError(f"STT 음성 인식 실패: {str(e)}")
    
    def _download_and_parse_subtitle(
        self,
        url: str,
        video_id: str,
        language: str
    ) -> list[SubtitleSegment]:
        """수동 자막 파일을 다운로드하고 파싱합니다."""
        output_template = os.path.join(self.temp_dir, f"{video_id}.%(ext)s")
        
        args = [
            "--skip-download",
            "--write-sub",  # 수동 자막만
            "--sub-lang", language,
            "--sub-format", "vtt",
            "-o", output_template,
            url
        ]
        
        result = self._run_ytdlp(args)
        
        if result.returncode != 0:
            raise SubtitleExtractionError(f"자막 다운로드 실패: {result.stderr}")
        
        vtt_path = self._find_vtt_file(video_id, language)
        
        if not vtt_path:
            raise SubtitleExtractionError("다운로드된 자막 파일을 찾을 수 없습니다.")
        
        try:
            with open(vtt_path, "r", encoding="utf-8") as f:
                vtt_content = f.read()
            
            segments = parse_vtt_content(vtt_content)
            os.remove(vtt_path)
            
            return segments
            
        except Exception as e:
            raise SubtitleExtractionError(f"자막 파일 파싱 실패: {str(e)}")
    
    def _find_vtt_file(self, video_id: str, language: str) -> Optional[str]:
        """다운로드된 VTT 파일 경로를 찾습니다."""
        for filename in os.listdir(self.temp_dir):
            if filename.startswith(video_id) and filename.endswith(".vtt"):
                return os.path.join(self.temp_dir, filename)
        return None
    
    def _get_language_name(self, lang_code: str) -> str:
        """언어 코드를 언어 이름으로 변환합니다."""
        language_map = {
            "en": "English",
            "ko": "한국어",
            "ja": "日本語",
            "zh": "中文",
            "es": "Español",
            "fr": "Français",
            "de": "Deutsch",
            "pt": "Português",
            "ru": "Русский",
            "it": "Italiano",
        }
        return language_map.get(lang_code, lang_code)
    
    def is_stt_available(self) -> bool:
        """STT 사용 가능 여부 확인"""
        stt = self._get_stt()
        return stt is not None and stt.is_available()


# 편의 함수
_default_extractor: Optional[SubtitleExtractor] = None


def get_extractor() -> SubtitleExtractor:
    """기본 SubtitleExtractor 인스턴스를 반환합니다."""
    global _default_extractor
    if _default_extractor is None:
        _default_extractor = SubtitleExtractor()
    return _default_extractor


def extract_subtitle(
    video_url: str,
    language: str = "en",
    force_stt: bool = False
) -> SubtitleData:
    """YouTube 영상에서 자막을 추출하는 편의 함수입니다."""
    return get_extractor().extract_subtitle(video_url, language, force_stt)


def list_subtitles(video_url: str) -> list[SubtitleInfo]:
    """사용 가능한 수동 자막 목록을 조회하는 편의 함수입니다."""
    return get_extractor().list_available_subtitles(video_url)
