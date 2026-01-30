"""
CAYT 현지화(Refiner) 모듈

2단계 번역 파이프라인:
1단계 - 초벌 번역가 (Initial Translator): 정확한 직역
2단계 - 현지화 전문가 (Localizer): 자연스러운 한국어로 다듬기

참고: "Beyond Human Translation: Harnessing Multi-Agent Collaboration 
       for Translating Ultra-Long Literary Texts" (Wu et al., 2024)
"""

import re
import uuid
import asyncio
from dataclasses import dataclass, field
from typing import Optional
from concurrent.futures import ThreadPoolExecutor

import ollama

from config import get_settings


settings = get_settings()

# 스레드 풀
_refiner_executor = ThreadPoolExecutor(max_workers=2)


@dataclass
class RefinedSegment:
    """현지화된 자막 세그먼트"""
    start: float
    end: float
    original_text: str       # 원문 (영어)
    initial_text: str        # 초벌 번역 (1단계)
    refined_text: str        # 현지화 번역 (2단계)


@dataclass 
class RefineResult:
    """현지화 결과"""
    video_id: str
    task_id: str
    segments: list[RefinedSegment] = field(default_factory=list)
    is_completed: bool = False
    error_message: str = ""
    
    @property
    def total_segments(self) -> int:
        return len(self.segments)


class Refiner:
    """
    현지화 전문가 (Localizer) 클래스
    
    역할: 초벌 번역된 텍스트를 한국 문화와 언어에 맞게 
          자연스럽고 이해하기 쉽게 수정합니다.
    
    특징:
    - 앞뒤 문맥을 참고하여 일관성 유지
    - 원문과 초벌 번역을 함께 참고
    - 창의성을 발휘하여 자연스러운 표현 사용
    """
    
    # 현지화 전문가 시스템 프롬프트
    LOCALIZER_SYSTEM_PROMPT = """You are a Korean Localization Specialist.

Your role is to refine machine-translated Korean subtitles to sound natural and fluent to native Korean speakers.

## Your Expertise:
- Deep understanding of Korean culture and language nuances
- Ability to adapt content for Korean audiences
- Creative yet accurate expression

## Guidelines:
1. PRESERVE the original meaning accurately
2. USE natural Korean expressions that native speakers would use
3. CONSIDER the context (previous and next sentences) for consistency
4. MAINTAIN appropriate speech level (존댓말/반말) consistently
5. ADAPT cultural references when necessary
6. KEEP the translation concise for subtitle readability

## You will receive:
- Original English text
- Initial Korean translation (reference)
- Context (previous/next subtitles)

## Output:
- Only the refined Korean translation
- No explanations or notes"""

    def __init__(
        self,
        model: str = None,
        ollama_host: str = None
    ):
        self.model = model or settings.LLM_MODEL
        self.ollama_host = ollama_host or settings.OLLAMA_HOST
        self.batch_size = 5
        self.max_retries = 2
        
        self.client = ollama.Client(host=self.ollama_host)
        
        # 취소 추적
        self._cancelled_tasks: set[str] = set()
        
        print(f"[Refiner] 현지화 전문가 모델: {self.model}")
    
    def _build_localization_prompt(
        self,
        segments_with_context: list[dict]
    ) -> str:
        """
        현지화 전문가용 프롬프트 생성
        
        각 세그먼트에 대해:
        - 원문 (영어)
        - 초벌 번역 (한국어)
        - 앞뒤 문맥
        """
        prompt_parts = []
        
        for i, seg in enumerate(segments_with_context, 1):
            # 문맥 정보
            context_info = []
            if seg.get('prev_original'):
                context_info.append(f"[Previous] {seg['prev_original']}")
                if seg.get('prev_translation'):
                    context_info.append(f"         → {seg['prev_translation']}")
            
            if seg.get('next_original'):
                context_info.append(f"[Next] {seg['next_original']}")
                if seg.get('next_translation'):
                    context_info.append(f"     → {seg['next_translation']}")
            
            context_block = "\n".join(context_info) if context_info else "(No context available)"
            
            prompt_parts.append(f"""
---
Subtitle #{i}

Context:
{context_block}

[Original English]
{seg['original']}

[Initial Korean Translation]
{seg['initial']}

Refine the Korean translation to be more natural:""")
        
        return "\n".join(prompt_parts)
    
    def _parse_batch_response(
        self,
        response_text: str,
        count: int,
        fallback_texts: list[str]
    ) -> list[str]:
        """배치 응답 파싱"""
        lines = response_text.strip().split("\n")
        results = [""] * count
        
        # 패턴 매칭 시도
        current_idx = 0
        for line in lines:
            line = line.strip()
            if not line or line.startswith("---") or line.startswith("["):
                continue
            
            # "1. 번역문" 또는 "#1: 번역문" 형식
            match = re.match(r"^(?:Subtitle\s*)?#?(\d+)[\.\):\s]+(.+)$", line, re.IGNORECASE)
            if match:
                idx = int(match.group(1)) - 1
                if 0 <= idx < count:
                    results[idx] = match.group(2).strip()
                continue
            
            # 번호 없이 순차적으로
            if current_idx < count and not results[current_idx]:
                # 메타 텍스트 제외
                if not any(skip in line.lower() for skip in ['context:', 'original', 'translation', 'refine', 'subtitle']):
                    results[current_idx] = line
                    current_idx += 1
        
        # 빈 결과는 fallback으로 채우기
        for i in range(count):
            if not results[i]:
                results[i] = fallback_texts[i] if i < len(fallback_texts) else ""
        
        return results
    
    def is_cancelled(self, task_id: str) -> bool:
        return task_id in self._cancelled_tasks
    
    def cancel_task(self, task_id: str) -> bool:
        print(f"[Refiner] 작업 취소 요청: {task_id}")
        self._cancelled_tasks.add(task_id)
        return True
    
    def _cleanup(self, task_id: str):
        self._cancelled_tasks.discard(task_id)
    
    def _refine_batch_sync(
        self,
        segments_with_context: list[dict]
    ) -> list[str]:
        """동기 배치 현지화"""
        prompt = self._build_localization_prompt(segments_with_context)
        fallback_texts = [seg['initial'] for seg in segments_with_context]
        
        for attempt in range(self.max_retries):
            try:
                response = self.client.chat(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": self.LOCALIZER_SYSTEM_PROMPT},
                        {"role": "user", "content": prompt}
                    ],
                    options={
                        "temperature": 0.7,  # 창의성 허용
                        "top_p": 0.9
                    }
                )
                
                response_text = response["message"]["content"]
                return self._parse_batch_response(
                    response_text, 
                    len(segments_with_context),
                    fallback_texts
                )
                
            except Exception as e:
                print(f"[Refiner] 배치 시도 {attempt + 1}/{self.max_retries} 실패: {e}")
                if attempt == self.max_retries - 1:
                    return fallback_texts
        
        return fallback_texts
    
    async def refine_batch_async(
        self,
        segments_with_context: list[dict],
        task_id: str = None
    ) -> list[str]:
        """비동기 배치 현지화"""
        if task_id and self.is_cancelled(task_id):
            return []
        
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            _refiner_executor,
            self._refine_batch_sync,
            segments_with_context
        )
        
        if task_id and self.is_cancelled(task_id):
            return []
        
        return result
    
    async def refine_segments_async(
        self,
        segments: list[dict],
        video_id: str,
        task_id: str = None
    ) -> RefineResult:
        """
        전체 세그먼트를 현지화합니다.
        
        Args:
            segments: 1단계 번역 결과 [{"start", "end", "original", "translated"}, ...]
            video_id: 영상 ID
            task_id: 작업 ID
        """
        if not task_id:
            task_id = str(uuid.uuid4())
        
        print(f"[Refiner] 현지화 시작: task={task_id}, video={video_id}, segments={len(segments)}")
        
        result = RefineResult(
            video_id=video_id,
            task_id=task_id
        )
        
        try:
            total = len(segments)
            
            for i in range(0, total, self.batch_size):
                if self.is_cancelled(task_id):
                    print(f"[Refiner] 취소됨: {task_id}")
                    result.error_message = "취소됨"
                    return result
                
                batch_end = min(i + self.batch_size, total)
                batch = segments[i:batch_end]
                
                # 각 세그먼트에 앞뒤 문맥 추가
                segments_with_context = []
                for j, seg in enumerate(batch):
                    global_idx = i + j
                    
                    # 이전 문맥 (1개)
                    prev_original = ""
                    prev_translation = ""
                    if global_idx > 0:
                        prev_original = segments[global_idx - 1].get("original", "")
                        prev_translation = segments[global_idx - 1].get("translated", "")
                    
                    # 다음 문맥 (1개)
                    next_original = ""
                    next_translation = ""
                    if global_idx < total - 1:
                        next_original = segments[global_idx + 1].get("original", "")
                        next_translation = segments[global_idx + 1].get("translated", "")
                    
                    segments_with_context.append({
                        "original": seg["original"],
                        "initial": seg["translated"],
                        "prev_original": prev_original,
                        "prev_translation": prev_translation,
                        "next_original": next_original,
                        "next_translation": next_translation,
                    })
                
                print(f"[Refiner] 배치 현지화: {i+1}-{batch_end}/{total}")
                
                refined_texts = await self.refine_batch_async(segments_with_context, task_id)
                
                if not refined_texts and self.is_cancelled(task_id):
                    result.error_message = "취소됨"
                    return result
                
                # 결과 저장
                for j, (seg, refined) in enumerate(zip(batch, refined_texts)):
                    result.segments.append(RefinedSegment(
                        start=seg["start"],
                        end=seg["end"],
                        original_text=seg["original"],
                        initial_text=seg["translated"],
                        refined_text=refined if refined else seg["translated"]
                    ))
                
                await asyncio.sleep(0.01)
            
            result.is_completed = True
            print(f"[Refiner] 현지화 완료: {task_id} ({result.total_segments}개)")
            
        except Exception as e:
            result.error_message = str(e)
            print(f"[Refiner] 현지화 실패: {task_id} - {e}")
        
        finally:
            self._cleanup(task_id)
        
        return result
    
    def check_connection(self) -> bool:
        try:
            self.client.list()
            return True
        except Exception:
            return False


# 편의 함수
_default_refiner: Optional[Refiner] = None


def get_refiner() -> Refiner:
    global _default_refiner
    if _default_refiner is None:
        _default_refiner = Refiner()
    return _default_refiner
