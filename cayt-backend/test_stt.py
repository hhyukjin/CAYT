"""
STT 모듈 직접 테스트
서버 없이 STT 기능만 테스트합니다.
"""

import sys
import os

# 프로젝트 경로 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.modules.stt import SpeechToText, STTConfig, WhisperModelSize

def test_stt(video_url: str):
    print("=" * 60)
    print("STT 직접 테스트")
    print("=" * 60)
    print(f"URL: {video_url}")
    print()
    
    # STT 인스턴스 생성
    config = STTConfig(
        model_size=WhisperModelSize.TURBO,
        vad_filter=True
    )
    stt = SpeechToText(config)
    
    print("[1] 오디오 다운로드 및 음성 인식 시작...")
    print()
    
    try:
        result = stt.transcribe_youtube_audio(
            video_url=video_url,
            language="en"
        )
        
        print()
        print("=" * 60)
        print("결과")
        print("=" * 60)
        print(f"세그먼트 수: {result.total_segments}")
        print(f"감지 언어: {result.language} ({result.language_probability:.1%})")
        print(f"영상 길이: {result.duration:.1f}초")
        print()
        print("처음 5개 세그먼트:")
        for i, seg in enumerate(result.segments[:5]):
            print(f"  [{seg.start:.1f}s - {seg.end:.1f}s] {seg.text}")
        
        print()
        print("✅ 테스트 성공!")
        
    except Exception as e:
        print(f"❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        test_url = "https://www.youtube.com/watch?v=-JTq1BFBwmo"
        print(f"사용법: python {sys.argv[0]} <youtube_url>")
        print(f"기본 URL 사용: {test_url}\n")
    else:
        test_url = sys.argv[1]
    
    test_stt(test_url)
