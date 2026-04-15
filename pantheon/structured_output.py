"""Structured lead-output parsing and validation for Pantheon."""

from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass(frozen=True)
class ProposedTask:
    ref: str
    title: str
    input_text: str
    assigned_agent: str
    parent_ref: str | None


@dataclass(frozen=True)
class TaskProposalPayload:
    tasks: list[ProposedTask]


@dataclass(frozen=True)
class CompletionJudgmentPayload:
    judgment: str


@dataclass(frozen=True)
class ParsedPayload:
    output_type: str
    payload: TaskProposalPayload | CompletionJudgmentPayload


@dataclass(frozen=True)
class PayloadParseResult:
    payload: ParsedPayload | None
    rejection_reason: str | None


def parse_control_payload(final_text: str) -> PayloadParseResult:
    stripped_text = final_text.rstrip()
    if not stripped_text or not stripped_text.endswith("}"):
        return PayloadParseResult(payload=None, rejection_reason=None)

    payload_object = _extract_trailing_json_object(stripped_text)
    if payload_object is None:
        return PayloadParseResult(
            payload=None,
            rejection_reason="final output ends with malformed JSON payload block",
        )

    if not isinstance(payload_object, dict):
        return PayloadParseResult(
            payload=None,
            rejection_reason="structured payload must be a JSON object",
        )

    output_type = payload_object.get("output_type")
    if output_type == "task_proposal":
        try:
            proposal = _parse_task_proposal(payload_object)
        except ValueError as exc:
            return PayloadParseResult(payload=None, rejection_reason=str(exc))
        return PayloadParseResult(
            payload=ParsedPayload(output_type=output_type, payload=proposal),
            rejection_reason=None,
        )

    if output_type == "completion_judgment":
        try:
            judgment = _parse_completion_judgment(payload_object)
        except ValueError as exc:
            return PayloadParseResult(payload=None, rejection_reason=str(exc))
        return PayloadParseResult(
            payload=ParsedPayload(output_type=output_type, payload=judgment),
            rejection_reason=None,
        )

    if output_type is None:
        return PayloadParseResult(
            payload=None,
            rejection_reason="structured payload is missing output_type",
        )

    return PayloadParseResult(
        payload=None,
        rejection_reason=f"unsupported structured payload output_type: {output_type}",
    )


def _extract_trailing_json_object(text: str) -> object | None:
    decoder = json.JSONDecoder()
    for start_index in range(len(text) - 1, -1, -1):
        if text[start_index] != "{":
            continue
        try:
            parsed_object, parsed_end = decoder.raw_decode(text[start_index:])
        except json.JSONDecodeError:
            continue
        if text[start_index + parsed_end :].strip():
            continue
        return parsed_object
    return None


def _parse_task_proposal(payload_object: dict[object, object]) -> TaskProposalPayload:
    tasks_value = payload_object.get("tasks")
    if not isinstance(tasks_value, list) or not tasks_value:
        raise ValueError("task_proposal payload must include a non-empty tasks list")

    proposal_tasks: list[ProposedTask] = []
    seen_refs: set[str] = set()
    for entry in tasks_value:
        if not isinstance(entry, dict):
            raise ValueError("task_proposal tasks entries must be JSON objects")

        ref = _required_non_empty_string(entry, "ref")
        if ref in seen_refs:
            raise ValueError(f"task_proposal refs must be unique: {ref}")
        seen_refs.add(ref)

        parent_ref_value = entry.get("parent_ref")
        if parent_ref_value is not None and not isinstance(parent_ref_value, str):
            raise ValueError("task_proposal parent_ref must be a string or null")
        parent_ref = parent_ref_value.strip() if isinstance(parent_ref_value, str) else None
        if isinstance(parent_ref_value, str) and not parent_ref:
            raise ValueError("task_proposal parent_ref must not be empty")

        proposal_tasks.append(
            ProposedTask(
                ref=ref,
                title=_required_non_empty_string(entry, "title"),
                input_text=_required_non_empty_string(entry, "input_text"),
                assigned_agent=_required_non_empty_string(entry, "assigned_agent"),
                parent_ref=parent_ref,
            )
        )

    return TaskProposalPayload(tasks=proposal_tasks)


def _parse_completion_judgment(
    payload_object: dict[object, object]
) -> CompletionJudgmentPayload:
    judgment = _required_non_empty_string(payload_object, "judgment")
    if judgment != "complete":
        raise ValueError(f"unsupported completion_judgment value: {judgment}")
    return CompletionJudgmentPayload(judgment=judgment)


def _required_non_empty_string(payload_object: dict[object, object], key: str) -> str:
    value = payload_object.get(key)
    if not isinstance(value, str):
        raise ValueError(f"structured payload field must be a string: {key}")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"structured payload field must not be empty: {key}")
    return normalized
