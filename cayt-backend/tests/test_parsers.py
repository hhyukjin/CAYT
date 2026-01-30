"""
CAYT 유틸리티 함수 테스트
parsers.py 모듈의 함수들을 테스트합니다.
"""

import pytest
import sys
from pathlib import Path

# 프로젝트 루트 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.utils.parsers import (
    extract_video_id,
    parse_vtt_timestamp,
    parse_vtt_content,
    merge_duplicate_segments,
    clean_subtitle_text,
)
from app.models.subtitle import SubtitleSegment


class TestExtractVideoId:
    """extract_video_id 함수 테스트"""
    
    def test_standard_url(self):
        """표준 YouTube URL 테스트"""
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        assert extract_video_id(url) == "dQw4w9WgXcQ"
    
    def test_short_url(self):
        """단축 URL 테스트"""
        url = "https://youtu.be/dQw4w9WgXcQ"
        assert extract_video_id(url) == "dQw4w9WgXcQ"
    
    def test_embed_url(self):
        """임베드 URL 테스트"""
        url = "https://www.youtube.com/embed/dQw4w9WgXcQ"
        assert extract_video_id(url) == "dQw4w9WgXcQ"
    
    def test_shorts_url(self):
        """Shorts URL 테스트"""
        url = "https://www.youtube.com/shorts/dQw4w9WgXcQ"
        assert extract_video_id(url) == "dQw4w9WgXcQ"
    
    def test_pure_video_id(self):
        """순수 Video ID 테스트"""
        video_id = "dQw4w9WgXcQ"
        assert extract_video_id(video_id) == "dQw4w9WgXcQ"
    
    def test_url_with_extra_params(self):
        """추가 파라미터가 있는 URL 테스트"""
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=120s"
        assert extract_video_id(url) == "dQw4w9WgXcQ"
    
    def test_invalid_url(self):
        """유효하지 않은 URL 테스트"""
        assert extract_video_id("https://google.com") is None
        assert extract_video_id("invalid") is None
        assert extract_video_id("") is None
        assert extract_video_id(None) is None
    
    def test_url_with_hyphen_underscore(self):
        """하이픈, 언더스코어가 포함된 Video ID 테스트"""
        url = "https://www.youtube.com/watch?v=a-B_c1D2e3F"
        assert extract_video_id(url) == "a-B_c1D2e3F"


class TestParseVttTimestamp:
    """parse_vtt_timestamp 함수 테스트"""
    
    def test_full_format(self):
        """HH:MM:SS.mmm 형식 테스트"""
        assert parse_vtt_timestamp("00:01:30.500") == 90.5
        assert parse_vtt_timestamp("01:00:00.000") == 3600.0
    
    def test_short_format(self):
        """MM:SS.mmm 형식 테스트"""
        assert parse_vtt_timestamp("01:30.500") == 90.5
        assert parse_vtt_timestamp("00:05.250") == 5.25
    
    def test_comma_separator(self):
        """콤마 구분자 형식 테스트 (SRT 스타일)"""
        assert parse_vtt_timestamp("00:01:30,500") == 90.5
    
    def test_with_whitespace(self):
        """공백 포함 테스트"""
        assert parse_vtt_timestamp("  00:01:30.500  ") == 90.5


class TestParseVttContent:
    """parse_vtt_content 함수 테스트"""
    
    def test_basic_vtt(self):
        """기본 VTT 파싱 테스트"""
        vtt_content = """WEBVTT

00:00:01.000 --> 00:00:04.000
Hello, world!

00:00:05.000 --> 00:00:08.000
This is a test.
"""
        segments = parse_vtt_content(vtt_content)
        
        assert len(segments) == 2
        assert segments[0].start == 1.0
        assert segments[0].end == 4.0
        assert segments[0].text == "Hello, world!"
        assert segments[1].text == "This is a test."
    
    def test_multiline_subtitle(self):
        """여러 줄 자막 테스트"""
        vtt_content = """WEBVTT

00:00:01.000 --> 00:00:04.000
First line
Second line
"""
        segments = parse_vtt_content(vtt_content)
        
        assert len(segments) == 1
        assert segments[0].text == "First line Second line"
    
    def test_html_tags_removal(self):
        """HTML 태그 제거 테스트"""
        vtt_content = """WEBVTT

00:00:01.000 --> 00:00:04.000
<c>Hello</c> <00:00:02.500>world
"""
        segments = parse_vtt_content(vtt_content)
        
        assert len(segments) == 1
        assert "<" not in segments[0].text
        assert ">" not in segments[0].text
    
    def test_cue_identifiers(self):
        """큐 식별자 무시 테스트"""
        vtt_content = """WEBVTT

1
00:00:01.000 --> 00:00:04.000
First subtitle

2
00:00:05.000 --> 00:00:08.000
Second subtitle
"""
        segments = parse_vtt_content(vtt_content)
        
        assert len(segments) == 2
        assert segments[0].text == "First subtitle"


class TestMergeDuplicateSegments:
    """merge_duplicate_segments 함수 테스트"""
    
    def test_merge_duplicates(self):
        """중복 세그먼트 병합 테스트"""
        segments = [
            SubtitleSegment(start=0.0, end=2.0, text="Hello"),
            SubtitleSegment(start=2.0, end=4.0, text="Hello"),
            SubtitleSegment(start=4.0, end=6.0, text="World"),
        ]
        
        merged = merge_duplicate_segments(segments)
        
        assert len(merged) == 2
        assert merged[0].start == 0.0
        assert merged[0].end == 4.0
        assert merged[0].text == "Hello"
    
    def test_no_merge_different_text(self):
        """다른 텍스트는 병합하지 않음 테스트"""
        segments = [
            SubtitleSegment(start=0.0, end=2.0, text="Hello"),
            SubtitleSegment(start=2.0, end=4.0, text="World"),
        ]
        
        merged = merge_duplicate_segments(segments)
        
        assert len(merged) == 2
    
    def test_empty_list(self):
        """빈 리스트 테스트"""
        assert merge_duplicate_segments([]) == []


class TestCleanSubtitleText:
    """clean_subtitle_text 함수 테스트"""
    
    def test_multiple_spaces(self):
        """여러 공백 정리 테스트"""
        assert clean_subtitle_text("Hello    world") == "Hello world"
    
    def test_trim_whitespace(self):
        """앞뒤 공백 제거 테스트"""
        assert clean_subtitle_text("  Hello world  ") == "Hello world"
    
    def test_newlines(self):
        """줄바꿈 처리 테스트"""
        assert clean_subtitle_text("Hello\n\nworld") == "Hello world"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
