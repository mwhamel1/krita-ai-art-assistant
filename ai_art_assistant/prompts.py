# SPDX-License-Identifier: MIT

"""Prompt pieces sent to OpenAI. No secrets, no krita import."""

from __future__ import annotations

DEFAULT_BASE_PROMPT = (
    "Painterly fantasy illustration. Strong silhouettes and a distinct composition. "
    "No UI, text, captions, borders, or card frames. Full-art only."
)

OPERATION_RULES = (
    "Preserve composition, proportions, pose, perspective, and subject identity. "
    "Follow the supplied sketch and placement. Do not invent a new layout."
)


class EmptyInstructionError(ValueError):
    pass


def compose_edit_prompt(
    base_prompt: str,
    user_instruction: str,
    has_selection: bool,
) -> str:
    instruction = (user_instruction or "").strip()
    if not instruction:
        raise EmptyInstructionError("Type an edit instruction first.")
    base = (base_prompt or "").strip() or DEFAULT_BASE_PROMPT
    if has_selection:
        scope = (
            "A mask is supplied. Treat transparent mask pixels as the region to edit. "
            "Leave opaque/unmasked areas unchanged as much as possible. "
            "The mask is guidance, not a hard crop."
        )
    else:
        scope = "Edit the entire image. Keep the existing composition."
    return "\n\n".join(
        (
            base,
            OPERATION_RULES,
            scope,
            "Artist instruction: " + instruction,
        )
    )
