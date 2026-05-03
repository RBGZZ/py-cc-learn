"""Requirement review tool - analyzes spec and requirement documents."""

from dataclasses import dataclass

from server.tools.tool import ToolCallResult


class ReviewTool:
    """Analyzes requirement documents for completeness, consistency, quality, and risks."""

    def __init__(self):
        self._name = "Review"

    @property
    def name(self) -> str:
        return self._name

    @property
    def aliases(self) -> list[str] | None:
        return ["review"]

    @property
    def input_schema(self):
        @dataclass
        class ReviewInput:
            file_path: str = ""
            text: str = ""
            dimensions: list[str] = None

        return ReviewInput

    @property
    def max_result_size_chars(self) -> int:
        return 80000

    @property
    def search_hint(self) -> str:
        return "Review requirement documents"

    def is_concurrency_safe(self, input=None) -> bool:
        return False

    def is_read_only(self, input=None) -> bool:
        return True

    async def call(self, args, context, can_use_tool=None, parent_message=None, on_progress=None):
        file_path = getattr(args, "file_path", "") or ""
        text = getattr(args, "text", "") or ""

        if file_path:
            import os

            if os.path.isfile(file_path):
                with open(file_path, "r", encoding="utf-8") as f:
                    text = f.read()
            else:
                return ToolCallResult(data=f"Error: File not found: {file_path}")

        if not text.strip():
            return ToolCallResult(data="Error: No requirement text provided. Use file_path or text parameter.")

        prompt = self._build_review_prompt(text)

        result = await self._call_llm(prompt, context)

        return ToolCallResult(data=result)

    def _build_review_prompt(self, text: str) -> str:
        return f"""You are a senior requirements engineer. Analyze the following requirements document and provide a structured review report.

REVIEW DIMENSIONS:
1. **Completeness**: Does the document cover all necessary sections? (Background/Why, What Changes, Impact, Requirements, Scenarios)
2. **Consistency**: Do Requirements and Scenarios correspond? Are there any contradictions?
3. **Quality**: Are Scenarios written in proper WHEN/THEN format? Are they testable?
4. **Risks**: Identify uncovered edge cases, security risks, performance concerns, and migration issues.

REQUIREMENTS DOCUMENT:
```
{text[:8000]}
```

OUTPUT FORMAT:
## Review Report

### 1. Completeness Check
- [Section-by-section analysis of what's covered and what's missing]

### 2. Consistency Check
- [Cross-reference Requirements vs Scenarios, flag contradictions]

### 3. Quality Check
- [Scenario format compliance, testability assessment]

### 4. Risk Assessment
- [Edge cases, security, performance, migration risks]

### Overall Score
- Completeness: X/10
- Consistency: X/10
- Quality: X/10
- Risk: X/10 (lower is riskier)
"""

    async def _call_llm(self, prompt: str, context) -> str:
        provider = context.get("provider") if isinstance(context, dict) else getattr(context, "provider", None)

        if provider is None:
            return self._basic_review(prompt)

        try:
            messages = [{"role": "user", "content": prompt}]
            full_response = []
            async for event in provider.stream_chat(
                messages=messages,
                system_prompt="You are a senior requirements engineer. Be concise and structured.",
            ):
                if event.type == "text_delta":
                    full_response.append(event.data.get("text", ""))
                elif event.type == "assistant":
                    content = event.data.get("message", {}).get("content", [])
                    if isinstance(content, list):
                        for block in content:
                            if isinstance(block, dict) and block.get("type") == "text":
                                full_response.append(block.get("text", ""))
                    elif isinstance(content, str):
                        full_response.append(content)
            return "".join(full_response) if full_response else "No review output generated."
        except Exception as e:
            return f"Review error: {str(e)}"

    def _basic_review(self, prompt: str) -> str:
        text = prompt.split("```")[1] if "```" in prompt else ""
        lines = text.split("\n")

        checks = {
            "Why/Background": any("why" in l.lower() or "background" in l.lower() for l in lines),
            "What Changes": any("what" in l.lower() or "changes" in l.lower() for l in lines),
            "Impact": any("impact" in l.lower() for l in lines),
            "Requirements": any("requirement" in l.lower() for l in lines),
            "Scenarios": any("scenario" in l.lower() or "when" in l.lower() for l in lines),
        }

        found = [k for k, v in checks.items() if v]
        missing = [k for k, v in checks.items() if not v]

        return f"""## Basic Structural Review (no LLM)
### Completeness
- Sections found: {', '.join(found) if found else 'none'}
- Sections missing: {', '.join(missing) if missing else 'none'}
- Score: {len(found)}/5

### Recommendation
Run with a configured LLM provider for full analysis.
"""

    async def description(self, input, options) -> str:
        return "Review requirement documents for completeness, consistency, quality, and risks"

    async def prompt(self, options) -> str:
        return "Analyze requirement documents for completeness, consistency, quality, and risks"

    def user_facing_name(self, input=None) -> str:
        return self._name

    def to_auto_classifier_input(self, input) -> str:
        return getattr(input, "file_path", "") or getattr(input, "text", "") or ""

    def map_tool_result_to_tool_result_block_param(self, content, tool_use_id):
        return {
            "type": "tool_result",
            "tool_use_id": tool_use_id,
            "content": [{"type": "text", "text": str(content)}],
        }

    def render_tool_use_message(self, input, options):
        return None
