"""
CAYT 유틸리티 함수 모듈
YouTube URL 파싱, VTT 파싱 등 공통 기능을 제공합니다.
"""

import re
from typing import Optional
from app.models.subtitle import SubtitleSegment


def extract_video_id(url_or_id: str) -> Optional[str]:
    """
    YouTube URL 또는 ID에서 Video ID를 추출합니다.
    
    지원 형식:
    - 전체 URL: https://www.youtube.com/watch?v=VIDEO_ID
    - 단축 URL: https://youtu.be/VIDEO_ID
    - 임베드 URL: https://www.youtube.com/embed/VIDEO_ID
    - 순수 ID: VIDEO_ID (11자리 영숫자)
    
    Args:
        url_or_id: YouTube URL 또는 Video ID
        
    Returns:
        추출된 Video ID 또는 None (추출 실패 시)
    """
    if not url_or_id:
        return None
    
    url_or_id = url_or_id.strip()
    
    # 패턴 정의: YouTube Video ID는 11자리 영숫자 + 일부 특수문자
    video_id_pattern = r"^[a-zA-Z0-9_-]{11}$"
    
    # 순수 Video ID인 경우
    if re.match(video_id_pattern, url_or_id):
        return url_or_id
    
    # URL 패턴들
    patterns = [
        # 표준 watch URL: youtube.com/watch?v=VIDEO_ID
        r"(?:youtube\.com/watch\?v=)([a-zA-Z0-9_-]{11})",
        # 단축 URL: youtu.be/VIDEO_ID
        r"(?:youtu\.be/)([a-zA-Z0-9_-]{11})",
        # 임베드 URL: youtube.com/embed/VIDEO_ID
        r"(?:youtube\.com/embed/)([a-zA-Z0-9_-]{11})",
        # Shorts URL: youtube.com/shorts/VIDEO_ID
        r"(?:youtube\.com/shorts/)([a-zA-Z0-9_-]{11})",
        # v 파라미터가 다른 위치에 있는 경우
        r"[?&]v=([a-zA-Z0-9_-]{11})",
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url_or_id)
        if match:
            return match.group(1)
    
    return None


def parse_vtt_timestamp(timestamp: str) -> float:
    """
    VTT 타임스탬프를 초 단위로 변환합니다.
    
    형식: HH:MM:SS.mmm 또는 MM:SS.mmm
    
    Args:
        timestamp: VTT 타임스탬프 문자열
        
    Returns:
        초 단위 시간 (float)
    """
    # 공백 제거
    timestamp = timestamp.strip()
    
    # HH:MM:SS.mmm 또는 MM:SS.mmm 패턴
    parts = timestamp.replace(",", ".").split(":")
    
    try:
        if len(parts) == 3:
            # HH:MM:SS.mmm
            hours = int(parts[0])
            minutes = int(parts[1])
            seconds = float(parts[2])
            return hours * 3600 + minutes * 60 + seconds
        elif len(parts) == 2:
            # MM:SS.mmm
            minutes = int(parts[0])
            seconds = float(parts[1])
            return minutes * 60 + seconds
        else:
            return 0.0
    except (ValueError, IndexError):
        return 0.0


def parse_vtt_content(vtt_content: str) -> list[SubtitleSegment]:
    """
    VTT 파일 내용을 파싱하여 SubtitleSegment 리스트로 변환합니다.
    
    Args:
        vtt_content: VTT 파일 전체 내용
        
    Returns:
        SubtitleSegment 객체 리스트
    """
    segments: list[SubtitleSegment] = []
    
    # 줄 단위로 분리
    lines = vtt_content.strip().split("\n")
    
    # WEBVTT 헤더 확인 및 건너뛰기
    start_index = 0
    for i, line in enumerate(lines):
        if line.strip().upper().startswith("WEBVTT"):
            start_index = i + 1
            break
    
    # 타임코드 패턴: 00:00:00.000 --> 00:00:00.000
    timestamp_pattern = re.compile(
        r"(\d{1,2}:)?(\d{2}):(\d{2})[.,](\d{3})\s*-->\s*(\d{1,2}:)?(\d{2}):(\d{2})[.,](\d{3})"
    )
    
    current_start: Optional[float] = None
    current_end: Optional[float] = None
    current_text_lines: list[str] = []
    
    for line in lines[start_index:]:
        line = line.strip()
        
        # 빈 줄: 현재 세그먼트 저장
        if not line:
            if current_start is not None and current_text_lines:
                text = " ".join(current_text_lines)
                # HTML 태그 제거 (예: <c>, </c>, <00:00:00.000> 등)
                text = re.sub(r"<[^>]+>", "", text)
                text = text.strip()
                
                if text:  # 빈 텍스트가 아닌 경우만 추가
                    segments.append(SubtitleSegment(
                        start=current_start,
                        end=current_end,
                        text=text
                    ))
            
            current_start = None
            current_end = None
            current_text_lines = []
            continue
        
        # 큐 식별자 건너뛰기 (숫자만 있는 줄)
        if line.isdigit():
            continue
        
        # 타임코드 줄
        timestamp_match = timestamp_pattern.search(line)
        if timestamp_match:
            # 시작 시간 파싱
            start_parts = line.split("-->")[0].strip()
            end_parts = line.split("-->")[1].strip().split()[0]  # 위치 정보 제거
            
            current_start = parse_vtt_timestamp(start_parts)
            current_end = parse_vtt_timestamp(end_parts)
            continue
        
        # 텍스트 줄
        if current_start is not None:
            current_text_lines.append(line)
    
    # 마지막 세그먼트 처리
    if current_start is not None and current_text_lines:
        text = " ".join(current_text_lines)
        text = re.sub(r"<[^>]+>", "", text)
        text = text.strip()
        
        if text:
            segments.append(SubtitleSegment(
                start=current_start,
                end=current_end,
                text=text
            ))
    
    return segments


def merge_duplicate_segments(segments: list[SubtitleSegment]) -> list[SubtitleSegment]:
    """
    중복되거나 연속된 동일 텍스트 세그먼트를 병합합니다.
    YouTube 자동 자막에서 자주 발생하는 중복을 처리합니다.
    
    Args:
        segments: 원본 세그먼트 리스트
        
    Returns:
        병합된 세그먼트 리스트
    """
    if not segments:
        return []
    
    merged: list[SubtitleSegment] = []
    current = segments[0]
    
    for next_segment in segments[1:]:
        # 텍스트가 동일하고 시간이 연속적인 경우 병합
        if (current.text == next_segment.text and 
            abs(current.end - next_segment.start) < 0.5):
            current = SubtitleSegment(
                start=current.start,
                end=next_segment.end,
                text=current.text
            )
        else:
            merged.append(current)
            current = next_segment
    
    merged.append(current)
    return merged


def clean_subtitle_text(text: str) -> str:
    """
    자막 텍스트를 정제합니다.
    
    - 불필요한 공백 제거
    - 특수 문자 정리
    - 음악/효과음 표시 정리
    
    Args:
        text: 원본 자막 텍스트
        
    Returns:
        정제된 텍스트
    """
    # 여러 공백을 하나로
    text = re.sub(r"\s+", " ", text)
    
    # 앞뒤 공백 제거
    text = text.strip()
    
    # [음악], [박수] 등의 표시는 유지 (맥락 정보)
    # 필요시 제거하려면 아래 주석 해제
    # text = re.sub(r"\[.*?\]", "", text)
    
    return text
