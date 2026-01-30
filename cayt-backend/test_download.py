"""
YouTube 오디오 다운로드 테스트 스크립트
사용법: python test_download.py <youtube_url>
"""

import os
import sys
import glob
import yt_dlp

# 테스트용 출력 디렉토리 (삭제되지 않음)
OUTPUT_DIR = "/tmp/cayt_test"

def test_download(video_url: str):
    """YouTube 오디오 다운로드 테스트"""
    
    # 출력 디렉토리 생성
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # 기존 파일 정리
    for f in glob.glob(os.path.join(OUTPUT_DIR, "audio.*")):
        os.remove(f)
        print(f"기존 파일 삭제: {f}")
    
    output_template = os.path.join(OUTPUT_DIR, "audio.%(ext)s")
    
    ydl_opts = {
        'outtmpl': output_template,
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '128',
        }],
        # 403 오류 방지
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        },
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'web'],
            }
        },
        'retries': 3,
        # 디버그용 - quiet 끔
        'quiet': False,
        'no_warnings': False,
        'verbose': True,
    }
    
    print(f"\n{'='*50}")
    print(f"YouTube 오디오 다운로드 테스트")
    print(f"{'='*50}")
    print(f"URL: {video_url}")
    print(f"출력 디렉토리: {OUTPUT_DIR}")
    print(f"{'='*50}\n")
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=True)
            print(f"\n영상 제목: {info.get('title', 'N/A')}")
            print(f"영상 길이: {info.get('duration', 0)}초")
    except Exception as e:
        print(f"\n오류 발생: {e}")
        return
    
    # 결과 확인
    print(f"\n{'='*50}")
    print("다운로드 결과")
    print(f"{'='*50}")
    
    audio_files = glob.glob(os.path.join(OUTPUT_DIR, "audio.*"))
    
    if audio_files:
        for f in audio_files:
            size = os.path.getsize(f) / (1024 * 1024)
            print(f"✅ 파일: {f}")
            print(f"   크기: {size:.2f} MB")
    else:
        print("❌ 다운로드된 파일 없음")
        # 디렉토리 내용 확인
        print(f"\n{OUTPUT_DIR} 내용:")
        for f in os.listdir(OUTPUT_DIR):
            print(f"  - {f}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        # 기본 테스트 URL
        test_url = "https://www.youtube.com/watch?v=-JTq1BFBwmo"
        print(f"사용법: python {sys.argv[0]} <youtube_url>")
        print(f"기본 URL 사용: {test_url}\n")
    else:
        test_url = sys.argv[1]
    
    test_download(test_url)
