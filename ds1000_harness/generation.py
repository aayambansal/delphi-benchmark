from __future__ import annotations

import re
import time
from dataclasses import dataclass

_SYSTEM = (
    "Complete the DS-1000 Python task. Return only the Python code that "
    "replaces the solution placeholder. Do not include Markdown fences, "
    "explanations, or the surrounding program."
)


@dataclass(frozen=True)
class GenerationResult:
    provider: str
    model: str
    text: str
    latency_ms: float
    input_tokens: int | None
    output_tokens: int | None
    status: str
    error_type: str | None = None


def build_prompt(problem: str, context: str) -> str:
    return (
        "<retrieved_context>\n"
        f"{context.strip()}\n"
        "</retrieved_context>\n\n"
        f"{problem}"
    )


def postprocess_generation(text: str) -> str:
    fenced = re.search(r"```(?:python)?\s*(.*?)```", text, flags=re.DOTALL)
    if fenced:
        text = fenced.group(1)
    for marker in (
        "BEGIN SOLUTION\n<code>",
        "# SOLUTION START",
        "\n<code>",
    ):
        if marker in text:
            text = text.split(marker, 1)[1]
    for marker in ("</code>", "# SOLUTION END"):
        text = text.split(marker, 1)[0]
    return text.strip()


class Generator:
    def __init__(
        self,
        provider: str,
        model: str,
        api_key: str,
        *,
        max_output_tokens: int = 2000,
        max_attempts: int = 3,
        system_prompt: str = _SYSTEM,
    ) -> None:
        self.provider = provider
        self.model = model
        self.api_key = api_key
        self.max_output_tokens = max_output_tokens
        self.max_attempts = max_attempts
        self.system_prompt = system_prompt
        self._client = self._make_client()

    def _make_client(self):
        if self.provider == "openai":
            from openai import OpenAI

            return OpenAI(api_key=self.api_key)
        if self.provider == "anthropic":
            from anthropic import Anthropic

            return Anthropic(api_key=self.api_key)
        if self.provider == "google":
            from google import genai

            return genai.Client(api_key=self.api_key)
        raise ValueError(f"unsupported provider: {self.provider}")

    def _generate_once(self, prompt: str) -> tuple[str, int | None, int | None]:
        system_prompt = getattr(self, "system_prompt", _SYSTEM)
        if self.provider == "openai":
            response = self._client.responses.create(
                model=self.model,
                instructions=system_prompt,
                input=prompt,
                max_output_tokens=self.max_output_tokens,
            )
            usage = response.usage
            return (
                response.output_text,
                getattr(usage, "input_tokens", None),
                getattr(usage, "output_tokens", None),
            )
        if self.provider == "anthropic":
            response = self._client.messages.create(
                model=self.model,
                system=system_prompt,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=self.max_output_tokens,
            )
            text = "".join(
                block.text
                for block in response.content
                if getattr(block, "type", None) == "text"
            )
            return (
                text,
                getattr(response.usage, "input_tokens", None),
                getattr(response.usage, "output_tokens", None),
            )

        from google.genai import types

        response = self._client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                max_output_tokens=self.max_output_tokens,
                # Gemini 2.5 Pro requires thinking mode. A small explicit
                # budget prevents its automatic reasoning from consuming the
                # entire output allowance before emitting solution code.
                thinking_config=types.ThinkingConfig(thinking_budget=128),
            ),
        )
        usage = response.usage_metadata
        return (
            response.text or "",
            getattr(usage, "prompt_token_count", None),
            getattr(usage, "candidates_token_count", None),
        )

    def generate(self, prompt: str) -> GenerationResult:
        started = time.perf_counter()
        last_error: Exception | None = None
        for attempt in range(self.max_attempts):
            try:
                text, input_tokens, output_tokens = self._generate_once(prompt)
                return GenerationResult(
                    provider=self.provider,
                    model=self.model,
                    text=text,
                    latency_ms=(time.perf_counter() - started) * 1000,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    status="ok",
                )
            except Exception as exc:
                last_error = exc
                if attempt + 1 < self.max_attempts:
                    time.sleep(2**attempt)
        assert last_error is not None
        return GenerationResult(
            provider=self.provider,
            model=self.model,
            text="",
            latency_ms=(time.perf_counter() - started) * 1000,
            input_tokens=None,
            output_tokens=None,
            status="error",
            error_type=type(last_error).__name__,
        )
