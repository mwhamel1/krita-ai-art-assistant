# SPDX-License-Identifier: MIT

"""OpenAI Image Edit over HTTPS. No third-party SDK. Tests inject a fake poster."""

from __future__ import annotations

import base64
import json
import ssl
import uuid
import urllib.error
import urllib.request

EDIT_URL = "https://api.openai.com/v1/images/edits"
DEFAULT_TIMEOUT = 180


class OpenAIRequestError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def map_http_error(status: int, body_text: str) -> OpenAIRequestError:
    lowered = (body_text or "").lower()
    if status == 401:
        return OpenAIRequestError(
            "The API key was rejected. Check it in Settings. "
            "ChatGPT Plus is not an API key.",
            status,
        )
    if status == 429:
        if "quota" in lowered or "billing" in lowered or "insufficient" in lowered:
            return OpenAIRequestError(
                "OpenAI says this API account is out of credits. "
                "Add API credit (not ChatGPT Plus) and try once.",
                status,
            )
        return OpenAIRequestError(
            "OpenAI asked us to slow down (rate limit). Wait, then press Generate once.",
            status,
        )
    if status == 400 and "invalid" in lowered and "size" in lowered:
        return OpenAIRequestError(
            "OpenAI rejected the image size. The plugin will not stretch the canvas.",
            status,
        )
    snippet = _safe_error_message(body_text)
    return OpenAIRequestError(
        f"OpenAI returned HTTP {status}. {snippet}".strip(),
        status,
    )


def _safe_error_message(body_text: str) -> str:
    try:
        payload = json.loads(body_text)
        message = payload.get("error", {}).get("message")
        if isinstance(message, str) and message:
            return message[:300]
    except (json.JSONDecodeError, AttributeError, TypeError):
        pass
    return ""


def _multipart(fields: dict[str, str], files: list[tuple[str, str, bytes]]) -> tuple[bytes, str]:
    boundary = "----KritaAIArtAssistant" + uuid.uuid4().hex
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.append(f"--{boundary}\r\n".encode("utf-8"))
        chunks.append(
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8")
        )
        chunks.append(value.encode("utf-8"))
        chunks.append(b"\r\n")
    for field_name, filename, content in files:
        chunks.append(f"--{boundary}\r\n".encode("utf-8"))
        chunks.append(
            (
                f'Content-Disposition: form-data; name="{field_name}"; '
                f'filename="{filename}"\r\n'
                "Content-Type: image/png\r\n\r\n"
            ).encode("utf-8")
        )
        chunks.append(content)
        chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
    body = b"".join(chunks)
    content_type = f"multipart/form-data; boundary={boundary}"
    return body, content_type


def _default_poster(url: str, body: bytes, headers: dict, timeout: int) -> tuple[int, bytes]:
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    context = ssl.create_default_context()
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
            return response.getcode(), response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read() or b""


def decode_result_png(payload: dict) -> bytes:
    try:
        encoded = payload["data"][0]["b64_json"]
    except (KeyError, IndexError, TypeError) as exc:
        raise OpenAIRequestError(
            "OpenAI returned a response this plugin could not read as an image."
        ) from exc
    try:
        return base64.b64decode(encoded)
    except (ValueError, TypeError) as exc:
        raise OpenAIRequestError("OpenAI image data was not valid.") from exc


def edit_image(
    api_key: str,
    image_png: bytes,
    prompt: str,
    model: str,
    quality: str,
    size: str,
    mask_png: bytes | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    poster=_default_poster,
) -> bytes:
    if not (api_key or "").strip():
        raise OpenAIRequestError("Save an OpenAI API key in Settings first.")
    if not image_png:
        raise OpenAIRequestError("No source image to send.")
    fields = {
        "model": model,
        "prompt": prompt,
        "size": size,
        "quality": quality,
        "n": "1",
        "output_format": "png",
    }
    files = [("image[]", "image.png", image_png)]
    if mask_png:
        files.append(("mask", "mask.png", mask_png))
    body, content_type = _multipart(fields, files)
    headers = {
        "Authorization": "Bearer " + api_key.strip(),
        "Content-Type": content_type,
        "User-Agent": "krita-ai-art-assistant/phase2",
    }
    try:
        status, raw = poster(EDIT_URL, body, headers, timeout)
    except urllib.error.URLError as exc:
        raise OpenAIRequestError(
            "Could not reach OpenAI. Check the network, then press Generate once."
        ) from exc
    text = raw.decode("utf-8", errors="replace")
    if status != 200:
        raise map_http_error(status, text)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise OpenAIRequestError("OpenAI returned a non-JSON response.") from exc
    return decode_result_png(payload)
