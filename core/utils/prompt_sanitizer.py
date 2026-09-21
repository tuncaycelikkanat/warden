"""Prompt sanitization and security filtering utility for LLM integrations."""

import re
from dataclasses import dataclass, field
from typing import ClassVar


@dataclass
class SanitizationResult:
    """Represents the output of prompt input sanitization."""
    sanitized_text: str
    is_safe: bool
    flags: list[str] = field(default_factory=list)


class PromptSanitizer:
    """Sanitizes user input and external text before inclusion in LLM prompt templates."""

    INJECTION_PATTERNS: ClassVar[list[tuple[str, str]]] = [
        (r"(?i)ignore\s+(all\s+)?(previous|prior)\s+instructions", "Instruction override attempt"),
        (r"(?i)system\s*:", "Role spoofing attempt (system:)"),
        (r"(?i)<\|im_start\|>", "ChatML delimiter injection"),
        (r"(?i)you\s+are\s+now\s+(in\s+)?(DAN|developer)\s+mode", "Jailbreak mode attempt"),
        (r"(?i)reveal\s+(your\s+)?(system\s+)?prompt", "System prompt exfiltration attempt"),
    ]

    MAX_INPUT_LENGTH: ClassVar[int] = 16000

    def sanitize(self, text: str) -> SanitizationResult:
        """Sanitizes the input text and flags prompt injection patterns."""
        if not text:
            return SanitizationResult(sanitized_text="", is_safe=True)

        flags = []
        truncated = text[: self.MAX_INPUT_LENGTH]
        if len(text) > self.MAX_INPUT_LENGTH:
            flags.append("Input truncated to maximum length")

        clean_text = truncated
        for pattern, reason in self.INJECTION_PATTERNS:
            if re.search(pattern, clean_text):
                flags.append(reason)
                clean_text = re.sub(pattern, "[FILTERED]", clean_text)

        # Strip null bytes and anomalous control characters
        clean_text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", clean_text)

        return SanitizationResult(
            sanitized_text=clean_text.strip(),
            is_safe=len(flags) == 0,
            flags=flags,
        )
