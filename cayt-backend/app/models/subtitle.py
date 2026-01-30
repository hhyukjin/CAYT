"""
CAYT 자막 데이터 모델
Pydantic을 사용하여 자막 데이터 구조를 정의합니다.
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional
from enum import Enum


class SubtitleType(str, Enum):
    """자막 유형 열거형"""
    MANUAL = "manual"           # 수동 자막 (제작자 업로드)
    AUTO_GENERATED = "auto_generated"  # YouTube 자동 생성 자막
    AUTO = "auto"               # STT로 생성된 자막 (Faster-Whisper)
    NONE = "none"               # 자막 없음


class SubtitleSegment(BaseModel):
    """
    개별 자막 세그먼트 모델
    하나의 자막 구간을 나타냅니다.
    """
    start: float = Field(..., ge=0, description="시작 시간 (초)")
    end: float = Field(..., ge=0, description="종료 시간 (초)")
    text: str = Field(..., min_length=0, description="자막 텍스트")
    
    @field_validator("end")
    @classmethod
    def end_must_be_after_start(cls, v: float, info) -> float:
        """종료 시간이 시작 시간보다 커야 합니다."""
        if "start" in info.data and v < info.data["start"]:
            raise ValueError("종료 시간은 시작 시간보다 커야 합니다")
        return v
    
    @property
    def duration(self) -> float:
        """자막 표시 시간 (초)"""
        return self.end - self.start


class SubtitleInfo(BaseModel):
    """
    자막 메타데이터 모델
    사용 가능한 자막 정보를 나타냅니다.
    """
    language: str = Field(..., description="언어 코드 (예: en, ko)")
    language_name: str = Field(default="", description="언어 이름 (예: English)")
    subtitle_type: SubtitleType = Field(..., description="자막 유형")
    ext: str = Field(default="vtt", description="파일 확장자")


class SubtitleData(BaseModel):
    """
    전체 자막 데이터 모델
    추출된 자막의 전체 정보를 담습니다.
    """
    video_id: str = Field(..., description="YouTube 영상 ID")
    title: Optional[str] = Field(default=None, description="영상 제목")
    language: str = Field(..., description="자막 언어")
    subtitle_type: SubtitleType = Field(..., description="자막 유형")
    segments: list[SubtitleSegment] = Field(default_factory=list, description="자막 세그먼트 목록")
    
    @property
    def total_segments(self) -> int:
        """전체 자막 세그먼트 수"""
        return len(self.segments)
    
    @property
    def full_text(self) -> str:
        """전체 자막 텍스트 (공백으로 연결)"""
        return " ".join(segment.text for segment in self.segments)
    
    @property
    def duration(self) -> float:
        """영상 길이 추정값 (마지막 자막 종료 시간)"""
        if not self.segments:
            return 0.0
        return self.segments[-1].end


class VideoSubtitleRequest(BaseModel):
    """
    자막 추출 요청 모델
    API 요청 시 사용됩니다.
    """
    video_url: str = Field(..., description="YouTube 영상 URL 또는 ID")
    language: str = Field(default="en", description="추출할 자막 언어")
    prefer_manual: bool = Field(default=True, description="수동 자막 우선 여부")
    use_stt_fallback: bool = Field(default=True, description="자막 없을 때 STT 사용 여부")


class VideoSubtitleResponse(BaseModel):
    """
    자막 추출 응답 모델
    API 응답 시 사용됩니다.
    """
    success: bool = Field(..., description="성공 여부")
    message: str = Field(default="", description="응답 메시지")
    data: Optional[SubtitleData] = Field(default=None, description="자막 데이터")
    available_subtitles: list[SubtitleInfo] = Field(
        default_factory=list, 
        description="사용 가능한 자막 목록"
    )
