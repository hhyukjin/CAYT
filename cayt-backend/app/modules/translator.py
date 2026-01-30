"""
CAYT 번역기 모듈 (문맥 기반 번역)

번역 흐름:
1. 전체 텍스트로 문맥 분석 (도메인, 용어)
2. 전체 텍스트를 문장 단위로 번역 요청
3. 번역된 문장을 원본 세그먼트 타임코드에 매핑
"""

import re
import uuid
import asyncio
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum
from concurrent.futures import ThreadPoolExecutor

import ollama

from config import get_settings
from app.models.subtitle import SubtitleSegment, SubtitleData, SubtitleType
from app.modules.context_manager import TranslationContext, ContextManager


settings = get_settings()

_executor = ThreadPoolExecutor(max_workers=2)


class TranslationStatus(str, Enum):
    """번역 상태"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TranslatedSegment:
    """번역된 자막 세그먼트"""
    start: float
    end: float
    original_text: str
    translated_text: str
    
    def to_subtitle_segment(self) -> SubtitleSegment:
        return SubtitleSegment(
            start=self.start,
            end=self.end,
            text=self.translated_text
        )


@dataclass
class TranslationResult:
    """번역 결과"""
    video_id: str
    title: str
    source_language: str
    target_language: str
    context: TranslationContext
    task_id: str = ""
    segments: list[TranslatedSegment] = field(default_factory=list)
    status: TranslationStatus = TranslationStatus.PENDING
    error_message: str = ""
    
    @property
    def total_segments(self) -> int:
        return len(self.segments)


@dataclass
class MergedSentence:
    """병합된 문장 (문장 경계 기준)"""
    text: str
    segment_indices: list[int]  # 원본 세그먼트 인덱스들
    start: float
    end: float


class Translator:
    """문맥 기반 번역기"""
    
    def __init__(
        self,
        model: str = None,
        ollama_host: str = None,
        source_lang: str = None,
        target_lang: str = None
    ):
        self.model = model or settings.LLM_MODEL
        self.ollama_host = ollama_host or settings.OLLAMA_HOST
        self.source_lang = source_lang or settings.SOURCE_LANGUAGE
        self.target_lang = target_lang or settings.TARGET_LANGUAGE
        self.max_retries = settings.TRANSLATION_MAX_RETRIES
        
        self.client = ollama.Client(host=self.ollama_host)
        self.context_manager = ContextManager(
            model=self.model,
            ollama_host=self.ollama_host
        )
        
        self._cancelled_tasks: set[str] = set()
        self._cancelled_videos: set[str] = set()
        
        print(f"[Translator] 모델: {self.model}")
    
    # ==========================================
    # 문장 병합 로직
    # ==========================================
    
    def _is_sentence_end(self, text: str) -> bool:
        """문장 끝인지 확인 (마침표, 물음표, 느낌표)"""
        text = text.strip()
        if not text:
            return False
        return text[-1] in '.?!。？！'
    
    def _merge_segments_to_sentences(
        self,
        segments: list[SubtitleSegment]
    ) -> list[MergedSentence]:
        """
        세그먼트들을 문장 단위로 병합합니다.
        문장 끝(마침표 등)을 기준으로 병합합니다.
        """
        merged = []
        current_text = ""
        current_indices = []
        current_start = 0.0
        
        for i, seg in enumerate(segments):
            if not current_indices:
                current_start = seg.start
            
            current_text += " " + seg.text if current_text else seg.text
            current_indices.append(i)
            
            # 문장 끝이면 병합 완료
            if self._is_sentence_end(seg.text):
                merged.append(MergedSentence(
                    text=current_text.strip(),
                    segment_indices=current_indices.copy(),
                    start=current_start,
                    end=seg.end
                ))
                current_text = ""
                current_indices = []
        
        # 마지막 미완성 문장 처리
        if current_text:
            merged.append(MergedSentence(
                text=current_text.strip(),
                segment_indices=current_indices.copy(),
                start=current_start,
                end=segments[-1].end if segments else 0.0
            ))
        
        return merged
    
    # ==========================================
    # 프롬프트 생성
    # ==========================================
    
    def _build_translation_prompt(
        self,
        sentences: list[MergedSentence],
        context: TranslationContext
    ) -> str:
        """문맥 기반 번역 프롬프트 생성"""
        
        # 문장들을 번호와 함께 구성
        numbered_sentences = "\n".join(
            f"[{i+1}] {sent.text}" for i, sent in enumerate(sentences)
        )
        
        # 용어 사전 문자열
        terms_str = ""
        if context.key_terms:
            terms_list = [f"{en} = {ko}" for en, ko in context.key_terms.items()]
            terms_str = "\n".join(terms_list)
        
        prompt = f"""당신은 전문 영상 자막 번역가입니다.

## 번역 정보
- 분야: {context.domain or '일반'}
- 주제: {context.topic or '영상 자막'}
- 원본 언어: 영어
- 번역 언어: 한국어

## 용어 사전 (반드시 이 번역을 사용하세요)
{terms_str if terms_str else '(없음)'}

## 번역 규칙
1. 반드시 한글로만 번역하세요.
2. 자연스러운 한국어 문장으로 번역하세요.
3. 용어 사전에 있는 단어는 반드시 해당 번역을 사용하세요.
4. 문맥상 연결되는 문장은 자연스럽게 번역하세요.
5. 각 문장의 번호 [1], [2], [3]... 를 반드시 유지하세요.
6. 번역문만 출력하고, 설명이나 부가 정보는 출력하지 마세요.

## 번역할 문장들
{numbered_sentences}

## 출력 형식 (번호를 반드시 유지)
[1] 첫 번째 문장의 한국어 번역
[2] 두 번째 문장의 한국어 번역
...

번역을 시작하세요:"""
        
        return prompt
    
    # ==========================================
    # 응답 파싱
    # ==========================================
    
    def _parse_translation_response(
        self,
        response_text: str,
        sentences: list[MergedSentence],
        original_segments: list[SubtitleSegment]
    ) -> list[TranslatedSegment]:
        """
        번역 응답을 파싱하여 타임코드와 매핑합니다.
        """
        # [번호] 형식으로 분리
        pattern = r'\[(\d+)\]\s*(.+?)(?=\[\d+\]|$)'
        matches = re.findall(pattern, response_text, re.DOTALL)
        
        # 번호 → 번역 매핑
        translations = {}
        for num_str, trans_text in matches:
            num = int(num_str)
            translations[num] = trans_text.strip()
        
        # 결과 생성
        result = []
        
        for i, sentence in enumerate(sentences):
            sentence_num = i + 1
            translated = translations.get(sentence_num, sentence.text)
            
            # 이 문장에 포함된 세그먼트 수
            seg_count = len(sentence.segment_indices)
            
            if seg_count == 1:
                # 단일 세그먼트 → 그대로 매핑
                seg_idx = sentence.segment_indices[0]
                orig_seg = original_segments[seg_idx]
                result.append(TranslatedSegment(
                    start=orig_seg.start,
                    end=orig_seg.end,
                    original_text=orig_seg.text,
                    translated_text=translated
                ))
            else:
                # 다중 세그먼트 → 번역을 첫 세그먼트에, 나머지는 빈 문자열
                # 또는 전체 타임코드로 하나의 세그먼트 생성
                first_idx = sentence.segment_indices[0]
                last_idx = sentence.segment_indices[-1]
                
                # 원본 텍스트 병합
                orig_texts = [original_segments[idx].text for idx in sentence.segment_indices]
                orig_combined = " ".join(orig_texts)
                
                result.append(TranslatedSegment(
                    start=original_segments[first_idx].start,
                    end=original_segments[last_idx].end,
                    original_text=orig_combined,
                    translated_text=translated
                ))
        
        return result
    
    # ==========================================
    # 번역 실행
    # ==========================================
    
    def _translate_sync(
        self,
        sentences: list[MergedSentence],
        context: TranslationContext,
        original_segments: list[SubtitleSegment]
    ) -> list[TranslatedSegment]:
        """동기 번역 수행"""
        
        prompt = self._build_translation_prompt(sentences, context)
        
        for attempt in range(self.max_retries):
            try:
                response = self.client.chat(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    options={"temperature": 0.3}
                )
                
                response_text = response["message"]["content"]
                print(f"[Translator] 응답 길이: {len(response_text)} chars")
                
                return self._parse_translation_response(
                    response_text, sentences, original_segments
                )
                
            except Exception as e:
                print(f"[Translator] 번역 시도 {attempt + 1}/{self.max_retries} 실패: {e}")
                if attempt == self.max_retries - 1:
                    # 실패 시 원본 반환
                    return [
                        TranslatedSegment(
                            start=sent.start,
                            end=sent.end,
                            original_text=sent.text,
                            translated_text=sent.text  # 번역 실패 → 원본
                        )
                        for sent in sentences
                    ]
        
        return []
    
    async def _translate_async(
        self,
        sentences: list[MergedSentence],
        context: TranslationContext,
        original_segments: list[SubtitleSegment],
        task_id: str = None,
        video_id: str = None
    ) -> list[TranslatedSegment]:
        """비동기 번역 수행"""
        
        if self.is_cancelled(task_id, video_id):
            return []
        
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            _executor,
            self._translate_sync,
            sentences,
            context,
            original_segments
        )
        
        return result
    
    # ==========================================
    # 메인 번역 함수
    # ==========================================
    
    async def translate_subtitle_data_async(
        self,
        subtitle_data: SubtitleData,
        use_llm_context: bool = True,
        task_id: str = None
    ) -> TranslationResult:
        """
        전체 자막 데이터를 문맥 기반으로 번역합니다.
        
        흐름:
        1. 전체 텍스트로 문맥 분석
        2. 세그먼트를 문장 단위로 병합
        3. 청크 단위로 번역 (너무 길면 분할)
        4. 타임코드에 매핑
        """
        if not task_id:
            task_id = str(uuid.uuid4())
        
        video_id = subtitle_data.video_id
        
        print(f"[Translator] 번역 시작: video={video_id}, segments={len(subtitle_data.segments)}")
        
        result = TranslationResult(
            video_id=video_id,
            title=subtitle_data.title or "",
            source_language=subtitle_data.language,
            target_language=self.target_lang,
            context=TranslationContext(),
            task_id=task_id,
            status=TranslationStatus.IN_PROGRESS
        )
        
        try:
            # 취소 확인
            if self.is_cancelled(task_id, video_id):
                result.status = TranslationStatus.CANCELLED
                return result
            
            # 1. 문맥 분석
            print(f"[Translator] 1단계: 문맥 분석")
            full_text = subtitle_data.full_text
            result.context = self.context_manager.create_context(
                full_text,
                use_llm=use_llm_context
            )
            print(f"[Translator] 문맥: 도메인={result.context.domain}, 용어={len(result.context.key_terms)}개")
            
            if self.is_cancelled(task_id, video_id):
                result.status = TranslationStatus.CANCELLED
                return result
            
            # 2. 세그먼트를 문장 단위로 병합
            print(f"[Translator] 2단계: 문장 병합")
            segments = subtitle_data.segments
            merged_sentences = self._merge_segments_to_sentences(segments)
            print(f"[Translator] {len(segments)}개 세그먼트 → {len(merged_sentences)}개 문장")
            
            # 3. 청크 단위로 번역 (한 번에 최대 30문장)
            CHUNK_SIZE = 30
            all_translated = []
            
            for i in range(0, len(merged_sentences), CHUNK_SIZE):
                if self.is_cancelled(task_id, video_id):
                    result.status = TranslationStatus.CANCELLED
                    break
                
                chunk = merged_sentences[i:i + CHUNK_SIZE]
                chunk_num = i // CHUNK_SIZE + 1
                total_chunks = (len(merged_sentences) + CHUNK_SIZE - 1) // CHUNK_SIZE
                
                print(f"[Translator] 3단계: 번역 청크 {chunk_num}/{total_chunks} ({len(chunk)}문장)")
                
                translated = await self._translate_async(
                    chunk, result.context, segments, task_id, video_id
                )
                
                if translated:
                    all_translated.extend(translated)
                
                await asyncio.sleep(0.01)
            
            result.segments = all_translated
            
            if result.status == TranslationStatus.IN_PROGRESS:
                result.status = TranslationStatus.COMPLETED
                print(f"[Translator] 번역 완료: {result.total_segments}개 세그먼트")
            
        except Exception as e:
            result.status = TranslationStatus.FAILED
            result.error_message = str(e)
            print(f"[Translator] 번역 실패: {e}")
            import traceback
            traceback.print_exc()
        
        finally:
            self._cleanup(task_id, video_id)
        
        return result
    
    # ==========================================
    # 취소 관리
    # ==========================================
    
    def is_cancelled(self, task_id: str = None, video_id: str = None) -> bool:
        if task_id and task_id in self._cancelled_tasks:
            return True
        if video_id and video_id in self._cancelled_videos:
            return True
        return False
    
    def cancel_task(self, task_id: str) -> bool:
        self._cancelled_tasks.add(task_id)
        return True
    
    def cancel_video(self, video_id: str) -> bool:
        self._cancelled_videos.add(video_id)
        return True
    
    def _cleanup(self, task_id: str = None, video_id: str = None):
        if task_id:
            self._cancelled_tasks.discard(task_id)
        if video_id:
            self._cancelled_videos.discard(video_id)
    
    # ==========================================
    # 유틸리티
    # ==========================================
    
    def check_connection(self) -> bool:
        try:
            self.client.list()
            return True
        except Exception:
            return False
    
    def list_models(self) -> list[str]:
        try:
            response = self.client.list()
            return [model["name"] for model in response.get("models", [])]
        except Exception:
            return []
    
    def translate_subtitle_data(
        self,
        subtitle_data: SubtitleData,
        use_llm_context: bool = True,
        progress_callback: callable = None,
        task_id: str = None
    ) -> TranslationResult:
        """동기 버전"""
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(
                self.translate_subtitle_data_async(
                    subtitle_data, use_llm_context, task_id
                )
            )
        finally:
            loop.close()


# 편의 함수
_default_translator: Optional[Translator] = None


def get_translator() -> Translator:
    global _default_translator
    if _default_translator is None:
        _default_translator = Translator()
    return _default_translator


def translate_subtitles(
    subtitle_data: SubtitleData,
    use_llm_context: bool = True
) -> TranslationResult:
    return get_translator().translate_subtitle_data(
        subtitle_data, use_llm_context
    )
