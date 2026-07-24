"""Rule-based request classification.

Performs three tasks:
  1. Hard-capability extraction (vision, tools, json).
  2. Task-type detection via regex patterns.
  3. Difficulty scoring via an interpretable cumulative-points system.

Task priority (when multiple signals fire):
    vision > tools > coding > translation > writing > reasoning > general

Coding and Reasoning can co-exist: if both match, ``task_type`` is set to
``"coding"`` and ``secondary_task`` to ``"reasoning"``.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Literal

from app.routing.request_features import RequestFeatures

logger = logging.getLogger(__name__)

TaskType = Literal["general", "coding", "reasoning", "writing", "translation", "tools", "vision"]
Difficulty = Literal["easy", "medium", "hard"]

# ---------------------------------------------------------------------------
# Regex patterns for task detection
# ---------------------------------------------------------------------------

_CODING_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"```", re.MULTILINE),                       # Markdown code blocks
    re.compile(r"\b(def|class|function|func|import|return|const|var|let|async|await)\b", re.IGNORECASE),
    re.compile(r"\b(public|private|protected|static|void|int|string|bool|struct|enum)\b", re.IGNORECASE),
    re.compile(r"\b(SELECT|INSERT|UPDATE|DELETE|CREATE|ALTER|DROP|JOIN|WHERE)\b", re.IGNORECASE),
    re.compile(r"\b(docker|kubernetes|kubectl|compose|container|image|pod)\b", re.IGNORECASE),
    re.compile(r"\b(git|commit|push|pull|merge|branch|rebase|stash|pull request|pr)\b", re.IGNORECASE),
    re.compile(r"\b(api|endpoint|rest|graphql|grpc|webhook|microservice)\b", re.IGNORECASE),
    re.compile(r"\b(debug|fix|bug|error|exception|traceback|stack ?trace|crash)\b", re.IGNORECASE),
    re.compile(r"\b(refactor|code review|code smell|technical debt|clean code)\b", re.IGNORECASE),
    re.compile(r"\b(implement|implementing|develop|build|deploy|compile|lint|format)\b", re.IGNORECASE),
    re.compile(r"\b(regex|regular expression|pattern match)\b", re.IGNORECASE),
    re.compile(r"\.(py|js|ts|tsx|jsx|java|cpp|c|cs|go|rs|rb|php|swift|kt|scala|sh|sql|html|css|vue|svelte)\b", re.IGNORECASE),
    # Chinese coding keywords
    re.compile(r"(代码|编程|函数|变量|类|接口|实现|修复|重构|调试|编译|部署|报错|异常|栈|框架|后端|前端|算法)"),
    re.compile(r"(写一个|编写|实现一个).*(函数|类|方法|程序|脚本|组件|服务|接口)"),
]

_REASONING_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\b(prove|proof|derive|derivation|deduce|theorem|lemma|corollary)\b", re.IGNORECASE),
    re.compile(r"\b(calculate|computation|equation|formula|solve|simplify|factor|integral|derivative)\b", re.IGNORECASE),
    re.compile(r"\b(probability|statistics|permutation|combination|binomial|poisson|normal distribution)\b", re.IGNORECASE),
    re.compile(r"\b(algorithm|complexity|big-?o|time complexity|space complexity|dynamic programming|greedy)\b", re.IGNORECASE),
    re.compile(r"\b(step.by.step|step-by-step|root cause|causal|inference|deductive|inductive)\b", re.IGNORECASE),
    re.compile(r"\b(logic puzzle|brain teaser|riddle|reasoning|analytical|systematic)\b", re.IGNORECASE),
    # Chinese reasoning keywords
    re.compile(r"(证明|推导|计算|方程|概率|排列|组合|复杂度|动态规划|贪心|逐步|分析|根因|推理|逻辑|数论|几何)"),
    re.compile(r"(证明|推导).*(定理|命题|公式)"),
    re.compile(r"(请|帮我).*(分析|推导|证明|计算|求解)"),
]

_WRITING_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\b(rewrite|rephrase|polish|proofread|edit|revise|paraphrase)\b", re.IGNORECASE),
    re.compile(r"\b(email|e-mail|letter|memo|report|essay|article|blog|copy|copywriting)\b", re.IGNORECASE),
    re.compile(r"\b(speech|presentation|slide|talk|keynote|script|screenplay)\b", re.IGNORECASE),
    re.compile(r"\b(social media|tweet|post|caption|hashtag|linkedin|instagram)\b", re.IGNORECASE),
    re.compile(r"\b(tone|style|voice|register|formal|informal|concise|verbose|tone of voice)\b", re.IGNORECASE),
    re.compile(r"\b(draft|outline|summary|abstract|executive summary)\b", re.IGNORECASE),
    # Chinese writing keywords
    re.compile(r"(改写|润色|润饰|校对|修改|邮件|文案|报告|演讲|稿件|草稿|大纲|摘要|正式|非正式|语气|风格)"),
    re.compile(r"(帮我|请).*(写|改写|润色|生成).*(邮件|文案|报告|文章|演讲|推文|文案)"),
]

_TRANSLATION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\b(translate|translation|localize|localization|i18n)\b", re.IGNORECASE),
    re.compile(r"\b(in (English|Chinese|Japanese|Korean|French|German|Spanish|Russian|Arabic))\b", re.IGNORECASE),
    re.compile(r"\b(to (English|Chinese|Japanese|Korean|French|German|Spanish|Russian|Arabic))\b", re.IGNORECASE),
    # Chinese translation keywords
    re.compile(r"(翻译|翻成|译为|译成|英译中|中译英|日译中|中译日)"),
]

# Patterns for difficulty scoring
_MATH_KEYWORDS_PATTERN = re.compile(
    r"\b(prove|proof|theorem|lemma|integral|derivative|differential|equation|"
    r"matrix|eigenvalue|polynomial|binomial|permutation|combination|"
    r"probability|bayes|markov|poisson|regression|optimization|"
    r"linear algebra|calculus|topology|manifold|stochastic)\b",
    re.IGNORECASE,
)
_MATH_KEYWORDS_CN = re.compile(
    r"(证明|定理|积分|微分|导数|方程|矩阵|特征值|多项式|排列|组合|"
    r"概率|贝叶斯|马尔可夫|泊松|回归|优化|线性代数|微积分|拓扑|随机)"
)

_CONSTRAINT_PATTERN = re.compile(
    r"\b(must|require|need|should|constraint|mandatory|necessary|essential|"
    r"limit|restrict|condition|rule|guideline|specification)\b"
    r"|(必须|要求|需要|应当|约束|限制|条件|规范)",
    re.IGNORECASE,
)

_COMPARISON_PATTERN = re.compile(
    r"\b(compare|comparison|versus|vs\.?|contrast|difference|"
    r"better|worse|alternative|option|trade-?off|pros and cons)\b"
    r"|(对比|比较|区别|差异|优劣|权衡|方案)",
    re.IGNORECASE,
)

_ARCHITECTURE_PATTERN = re.compile(
    r"\b(architecture|system design|end.to.end|full.stack|complete project|"
    r"microservice|distributed|scalable|production.ready|infrastructure)\b"
    r"|(架构|系统设计|端到端|全栈|完整项目|微服务|分布式|可扩展|生产环境|基础设施)",
    re.IGNORECASE,
)

_CODE_BLOCK_PATTERN = re.compile(r"```", re.MULTILINE)


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------

@dataclass
class RequestClassification:
    """Result of rule-based request classification."""

    task_type: TaskType
    difficulty: Difficulty
    required_capabilities: set[str] = field(default_factory=set)
    estimated_input_tokens: int = 0
    minimum_context_length: int = 0
    confidence: float = 1.0
    matched_rules: list[str] = field(default_factory=list)
    secondary_task: str | None = None


# ---------------------------------------------------------------------------
# Classification logic
# ---------------------------------------------------------------------------

def _detect_task_type(features: RequestFeatures) -> tuple[TaskType, str | None, list[str]]:
    """Detect the primary (and optionally secondary) task type.

    Returns ``(task_type, secondary_task, matched_rules)``.
    """
    matched: list[str] = []
    text = features.messages_text

    # --- Hard signals (highest priority) ---
    if features.has_images:
        matched.append("hard_signal:image_content")
        return "vision", None, matched

    if features.has_tools:
        matched.append("hard_signal:tools_present")

    # --- Soft signals ---
    coding_hit = any(p.search(text) for p in _CODING_PATTERNS)
    reasoning_hit = any(p.search(text) for p in _REASONING_PATTERNS)
    writing_hit = any(p.search(text) for p in _WRITING_PATTERNS)
    translation_hit = any(p.search(text) for p in _TRANSLATION_PATTERNS)

    if coding_hit:
        matched.append("regex:coding_keywords")

    if reasoning_hit:
        matched.append("regex:reasoning_keywords")

    if writing_hit:
        matched.append("regex:writing_keywords")

    if translation_hit:
        matched.append("regex:translation_keywords")

    # --- Apply priority: tools > coding > translation > writing > reasoning > general ---
    # (vision already handled above)
    secondary: str | None = None

    if features.has_tools:
        # If coding is also detected, tools still wins as primary
        if coding_hit:
            secondary = "coding"
        task_type: TaskType = "tools"
    elif coding_hit:
        task_type = "coding"
        # Coding + Reasoning can coexist
        if reasoning_hit:
            secondary = "reasoning"
    elif translation_hit:
        task_type = "translation"
    elif writing_hit:
        task_type = "writing"
    elif reasoning_hit:
        task_type = "reasoning"
    else:
        task_type = "general"

    return task_type, secondary, matched


def _compute_difficulty(features: RequestFeatures, task_type: TaskType, matched: list[str]) -> Difficulty:
    """Score difficulty using the cumulative-points system (plan §7.4)."""
    points = 0

    # +2 if estimated input > 16K tokens
    if features.estimated_input_tokens > 16_000:
        points += 2
        matched.append("difficulty:input_gt_16k (+2)")

    # +1 if estimated input > 4K tokens
    if features.estimated_input_tokens > 4_000:
        points += 1
        matched.append("difficulty:input_gt_4k (+1)")

    # +2 if tools present
    if features.has_tools:
        points += 2
        matched.append("difficulty:tools_present (+2)")

    # +1 if strict JSON schema requested
    if features.response_format:
        rf_type = features.response_format.get("type", "")
        if rf_type == "json_schema":
            points += 1
            matched.append("difficulty:json_schema (+1)")
        elif rf_type == "json_object":
            matched.append("difficulty:json_object (noted)")

    # +2 if image + text combined analysis
    if features.has_images and features.messages_text.strip():
        points += 2
        matched.append("difficulty:image_plus_text (+2)")

    # +2 if multiple code blocks
    code_blocks = _CODE_BLOCK_PATTERN.findall(features.messages_text)
    if len(code_blocks) >= 4:  # ``` appears twice per block → 2+ blocks
        points += 2
        matched.append("difficulty:multiple_code_blocks (+2)")

    # +2 if complex math / proof keywords
    has_math = bool(_MATH_KEYWORDS_PATTERN.search(features.messages_text)) or \
               bool(_MATH_KEYWORDS_CN.search(features.messages_text))
    if has_math:
        points += 2
        matched.append("difficulty:math_keywords (+2)")

    # +1 if 4+ explicit constraints
    constraint_count = len(_CONSTRAINT_PATTERN.findall(features.messages_text))
    if constraint_count >= 4:
        points += 1
        matched.append(f"difficulty:constraints_{constraint_count} (+1)")

    # +1 if 3+ comparison mentions
    comparison_count = len(_COMPARISON_PATTERN.findall(features.messages_text))
    if comparison_count >= 3:
        points += 1
        matched.append(f"difficulty:comparisons_{comparison_count} (+1)")

    # +1 if architecture / complete project request
    if _ARCHITECTURE_PATTERN.search(features.messages_text):
        points += 1
        matched.append("difficulty:architecture (+1)")

    # +1 if max_tokens >= 4000
    if features.max_tokens >= 4000:
        points += 1
        matched.append("difficulty:max_tokens_ge_4000 (+1)")

    # Map: 0-1 = easy, 2-4 = medium, 5+ = hard
    if points <= 1:
        difficulty: Difficulty = "easy"
    elif points <= 4:
        difficulty = "medium"
    else:
        difficulty = "hard"

    matched.append(f"difficulty:total_points={points} → {difficulty}")
    return difficulty


def _extract_required_capabilities(features: RequestFeatures) -> set[str]:
    """Extract hard-required capabilities from the request features."""
    caps: set[str] = set()

    if features.has_images:
        caps.add("vision")

    if features.has_tools:
        caps.add("tools")

    if features.response_format:
        rf_type = features.response_format.get("type", "")
        if rf_type in ("json_object", "json_schema"):
            caps.add("json")

    # Streaming is always required if the client requests it (handled separately
    # at the proxy layer, but we record it for completeness).
    # The proxy layer checks body["stream"]; we don't add it here because
    # stream support is a baseline expectation, not a model-selection filter.

    return caps


def _compute_confidence(
    features: RequestFeatures,
    task_type: TaskType,
    matched: list[str],
) -> float:
    """Heuristic confidence in the classification."""
    # Hard signals → high confidence
    if features.has_images:
        return 0.99
    if features.has_tools:
        return 0.95

    # Count regex matches for the selected task type
    text = features.messages_text
    signal_count = 0

    if task_type == "coding":
        signal_count = sum(1 for p in _CODING_PATTERNS if p.search(text))
    elif task_type == "reasoning":
        signal_count = sum(1 for p in _REASONING_PATTERNS if p.search(text))
    elif task_type == "writing":
        signal_count = sum(1 for p in _WRITING_PATTERNS if p.search(text))
    elif task_type == "translation":
        signal_count = sum(1 for p in _TRANSLATION_PATTERNS if p.search(text))

    if task_type == "general":
        # Low confidence when falling through to general
        return 0.50

    # More signals → higher confidence, capped at 0.90
    confidence = min(0.50 + signal_count * 0.10, 0.90)
    return round(confidence, 2)


def classify(features: RequestFeatures) -> RequestClassification:
    """Classify a request based on extracted features.

    Parameters
    ----------
    features:
        The ``RequestFeatures`` produced by :func:`extract_features`.

    Returns
    -------
    RequestClassification
    """
    # 1. Hard-capability extraction
    required_capabilities = _extract_required_capabilities(features)

    # 2. Task-type detection
    task_type, secondary_task, matched_rules = _detect_task_type(features)

    # 3. Difficulty scoring
    difficulty = _compute_difficulty(features, task_type, matched_rules)

    # 4. Confidence
    confidence = _compute_confidence(features, task_type, matched_rules)

    return RequestClassification(
        task_type=task_type,
        difficulty=difficulty,
        required_capabilities=required_capabilities,
        estimated_input_tokens=features.estimated_input_tokens,
        minimum_context_length=features.minimum_context_length,
        confidence=confidence,
        matched_rules=matched_rules,
        secondary_task=secondary_task,
    )
