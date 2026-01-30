"""
CAYT 컨텍스트 매니저 모듈
전체 자막 텍스트에서 주제와 핵심 용어를 추출하여
번역 품질을 높이기 위한 컨텍스트를 생성합니다.
"""

import re
from dataclasses import dataclass, field
from typing import Optional

import ollama

from config import get_settings


settings = get_settings()


@dataclass
class TranslationContext:
    """
    번역 컨텍스트 데이터 클래스
    LLM 프롬프트에 포함될 맥락 정보를 담습니다.
    """
    topic: str = ""                           # 영상 주제 (예: "프로그래밍 강의")
    domain: str = ""                          # 도메인 (예: "IT", "요리", "뉴스")
    key_terms: dict[str, str] = field(default_factory=dict)  # 용어 사전 {영어: 한국어}
    tone: str = "formal"                      # 말투 (formal/informal)
    additional_notes: str = ""                # 추가 참고사항
    
    def to_prompt_string(self) -> str:
        """프롬프트에 삽입할 컨텍스트 문자열을 생성합니다."""
        parts = []
        
        if self.domain:
            parts.append(f"[분야: {self.domain}]")
        
        if self.topic:
            parts.append(f"[주제: {self.topic}]")
        
        if self.key_terms:
            terms_str = ", ".join(f"{en}={ko}" for en, ko in list(self.key_terms.items())[:15])
            parts.append(f"[용어사전: {terms_str}]")
        
        return " ".join(parts)


# 도메인별 키워드 매핑
DOMAIN_KEYWORDS = {
    "IT": [
        "programming", "code", "software", "algorithm", "function",
        "variable", "class", "object", "database", "api", "server",
        "python", "javascript", "html", "css", "git", "deploy",
        "framework", "library", "debug", "compile", "runtime",
        "computer", "memory", "cpu", "data structure", "complexity",
        "priori", "posteriori", "analysis", "asymptotic", "notation"
    ],
    "요리": [
        "recipe", "cook", "ingredient", "kitchen", "bake", "fry",
        "boil", "chop", "slice", "sauce", "seasoning", "delicious",
        "taste", "flavor", "dish", "meal", "oven", "pan"
    ],
    "게임": [
        "game", "player", "level", "score", "character", "quest",
        "boss", "weapon", "skill", "multiplayer", "strategy",
        "gameplay", "controller", "fps", "rpg", "mmorpg"
    ],
    "비즈니스": [
        "business", "market", "investment", "revenue", "profit",
        "strategy", "management", "startup", "entrepreneur",
        "finance", "stock", "economy", "growth", "sales"
    ],
    "과학": [
        "science", "research", "experiment", "hypothesis", "theory",
        "data", "analysis", "study", "discovery", "physics",
        "chemistry", "biology", "laboratory", "molecule", "atom"
    ],
    "교육": [
        "learn", "teach", "student", "lecture", "course", "lesson",
        "tutorial", "example", "explain", "understand", "concept",
        "study", "practice", "exercise", "homework", "exam"
    ],
    "뉴스": [
        "news", "report", "breaking", "update", "politics",
        "government", "election", "president", "minister",
        "policy", "statement", "official", "announce"
    ],
}

# 도메인별 용어 사전
DOMAIN_TERMS = {
    "IT": {
        "function": "함수",
        "variable": "변수",
        "class": "클래스",
        "object": "객체",
        "method": "메서드",
        "parameter": "매개변수",
        "argument": "인자",
        "return": "반환",
        "loop": "반복문",
        "condition": "조건문",
        "array": "배열",
        "string": "문자열",
        "integer": "정수",
        "boolean": "불리언",
        "inheritance": "상속",
        "interface": "인터페이스",
        "module": "모듈",
        "package": "패키지",
        "library": "라이브러리",
        "framework": "프레임워크",
        "database": "데이터베이스",
        "query": "쿼리",
        "server": "서버",
        "client": "클라이언트",
        "request": "요청",
        "response": "응답",
        "algorithm": "알고리즘",
        "complexity": "복잡도",
        "time complexity": "시간 복잡도",
        "space complexity": "공간 복잡도",
        "priori analysis": "사전 분석",
        "posteriori testing": "사후 테스트",
        "asymptotic": "점근적",
        "notation": "표기법",
        "big O": "빅오",
        "data structure": "자료구조",
        "recursion": "재귀",
        "iteration": "반복",
        "stack": "스택",
        "queue": "큐",
        "tree": "트리",
        "graph": "그래프",
        "sorting": "정렬",
        "searching": "탐색",
    },
    "요리": {
        "recipe": "레시피",
        "ingredient": "재료",
        "seasoning": "양념",
        "sauce": "소스",
        "garnish": "가니쉬",
        "marinate": "재우다",
        "simmer": "끓이다",
        "sauté": "볶다",
    },
    "게임": {
        "level": "레벨",
        "character": "캐릭터",
        "skill": "스킬",
        "quest": "퀘스트",
        "boss": "보스",
        "item": "아이템",
        "damage": "데미지",
        "health": "체력",
    },
    "비즈니스": {
        "revenue": "매출",
        "profit": "이익",
        "investment": "투자",
        "market": "시장",
        "strategy": "전략",
        "growth": "성장",
    },
    "과학": {
        "hypothesis": "가설",
        "theory": "이론",
        "experiment": "실험",
        "data": "데이터",
        "analysis": "분석",
        "result": "결과",
    },
    "교육": {
        "lecture": "강의",
        "tutorial": "튜토리얼",
        "example": "예시",
        "concept": "개념",
        "exercise": "연습",
    },
}


class ContextManager:
    """
    컨텍스트 매니저 클래스
    전체 자막 텍스트를 분석하여 번역 컨텍스트를 생성합니다.
    """
    
    def __init__(
        self,
        model: str = None,
        ollama_host: str = None
    ):
        self.model = model or settings.LLM_MODEL
        self.ollama_host = ollama_host or settings.OLLAMA_HOST
        self.client = ollama.Client(host=self.ollama_host)
    
    def detect_domain(self, text: str) -> str:
        """텍스트에서 도메인(분야)을 감지합니다."""
        text_lower = text.lower()
        
        domain_scores = {}
        for domain, keywords in DOMAIN_KEYWORDS.items():
            score = sum(1 for keyword in keywords if keyword in text_lower)
            domain_scores[domain] = score
        
        if domain_scores:
            best_domain = max(domain_scores, key=domain_scores.get)
            if domain_scores[best_domain] >= 3:
                return best_domain
        
        return "일반"
    
    def extract_key_terms(self, text: str, domain: str) -> dict[str, str]:
        """텍스트와 도메인을 기반으로 핵심 용어를 추출합니다."""
        terms = {}
        text_lower = text.lower()
        
        # 해당 도메인의 용어 사전에서 매칭
        domain_terms = DOMAIN_TERMS.get(domain, {})
        for en_term, ko_term in domain_terms.items():
            if en_term.lower() in text_lower:
                terms[en_term] = ko_term
        
        # IT 도메인이 아니어도 IT 용어가 있으면 추가
        if domain != "IT":
            for en_term, ko_term in DOMAIN_TERMS.get("IT", {}).items():
                if en_term.lower() in text_lower and en_term not in terms:
                    terms[en_term] = ko_term
        
        return dict(list(terms.items())[:15])
    
    def analyze_rule_based(self, text: str) -> TranslationContext:
        """규칙 기반으로 텍스트를 분석합니다."""
        domain = self.detect_domain(text)
        key_terms = self.extract_key_terms(text, domain)
        
        return TranslationContext(
            topic="",
            domain=domain,
            key_terms=key_terms,
            tone="formal"
        )
    
    def analyze_with_llm(self, text: str) -> TranslationContext:
        """LLM을 사용하여 텍스트를 심층 분석합니다."""
        sample_text = text[:2000] if len(text) > 2000 else text
        
        prompt = f"""다음 영상 자막의 일부를 분석하여 JSON 형식으로 응답해주세요.

자막 샘플:
\"\"\"
{sample_text}
\"\"\"

다음 형식으로만 응답하세요 (다른 설명 없이):
{{
    "topic": "영상의 주제를 한국어로 간단히 (예: 파이썬 웹 개발 강의)",
    "domain": "분야 (IT/요리/게임/비즈니스/과학/교육/뉴스/일반 중 하나)",
    "tone": "적절한 말투 (formal/informal)"
}}"""
        
        try:
            response = self.client.chat(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0.3}
            )
            
            response_text = response["message"]["content"]
            
            import json
            json_match = re.search(r'\{[^}]+\}', response_text, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                
                context = TranslationContext(
                    topic=data.get("topic", ""),
                    domain=data.get("domain", "일반"),
                    tone=data.get("tone", "formal")
                )
                
                context.key_terms = self.extract_key_terms(text, context.domain)
                return context
                
        except Exception as e:
            print(f"[ContextManager] LLM 분석 실패, 규칙 기반으로 대체: {e}")
        
        return self.analyze_rule_based(text)
    
    def create_context(self, text: str, use_llm: bool = True) -> TranslationContext:
        """번역 컨텍스트를 생성합니다."""
        if use_llm:
            return self.analyze_with_llm(text)
        else:
            return self.analyze_rule_based(text)


def create_translation_context(text: str, use_llm: bool = True) -> TranslationContext:
    """번역 컨텍스트를 생성하는 편의 함수입니다."""
    manager = ContextManager()
    return manager.create_context(text, use_llm)
