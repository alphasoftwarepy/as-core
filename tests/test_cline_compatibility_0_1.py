"""
Tests for AS-Core — Cline Compatibility 0.1: Content Block Normalization
=============================================================================
Validates:
1. Traditional OpenAI request with content: str passes without change.
2. Cline request with content: list[dict] (text blocks) passes and normalizes to str.
3. Text blocks are concatenated in exact order.
4. Internal representation is invariant (str), protecting Cognitive Core.
"""

from api.models import ChatCompletionRequest, ChatMessage


def test_traditional_string_content_preserved():
    """Traditional OpenAI message with content as plain string."""
    req = ChatCompletionRequest(
        model="chat",
        messages=[ChatMessage(role="user", content="hola")],
    )
    assert req.messages[0].content == "hola"
    assert isinstance(req.messages[0].content, str)
    assert req.get_last_user_message() == "hola"


def test_cline_text_blocks_normalized_to_string_in_order():
    """Cline message with multimodal text blocks normalized to string."""
    blocks = [
        {"type": "text", "text": "<task>\nhola\n</task>"},
        {"type": "text", "text": "Instrucción adicional"},
        {"type": "text", "text": "<environment_details>\nsistema operativo win32\n</environment_details>"},
    ]
    req = ChatCompletionRequest(
        model="chat",
        messages=[ChatMessage(role="user", content=blocks)],
    )
    msg = req.messages[0]
    assert isinstance(msg.content, str)
    expected = "<task>\nhola\n</task>\nInstrucción adicional\n<environment_details>\nsistema operativo win32\n</environment_details>"
    assert msg.content == expected
    assert req.get_last_user_message() == expected


def test_mixed_and_empty_blocks():
    """Handles empty or mixed blocks gracefully."""
    blocks = [
        {"type": "text", "text": "Primero"},
        {"type": "other"},  # Non-text block ignored
        "Segundo en texto plano",
        {"type": "text", "text": "Tercero"},
    ]
    msg = ChatMessage(role="user", content=blocks)
    assert msg.content == "Primero\nSegundo en texto plano\nTercero"
    assert isinstance(msg.content, str)


def test_full_request_validation_from_dict():
    """Simulates FastAPI Pydantic parsing of raw JSON payload from Cline."""
    payload = {
        "model": "chat",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "<task>\nhola\n</task>"},
                    {"type": "text", "text": "# task_progress RECOMMENDED"},
                ],
            }
        ],
        "stream": True,
        "temperature": 0.0,
    }
    req = ChatCompletionRequest.model_validate(payload)
    assert req.model == "chat"
    assert req.stream is True
    assert req.messages[0].role == "user"
    assert req.messages[0].content == "<task>\nhola\n</task>\n# task_progress RECOMMENDED"
    assert isinstance(req.messages[0].content, str)
