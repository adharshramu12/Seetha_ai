"""
Unified AI client for Seetha.

One function — chat_completion() — used by every module that needs an
LLM (brain, WhatsApp intent extraction, YouTube smart-play, research).

Provider order:
  1. NVIDIA NIM   (free key from build.nvidia.com, OpenAI-compatible API)
  2. Groq         (optional fallback, free key from console.groq.com)

Keys come from the user's local Settings (settings_store) or .env —
they belong to the user and never leave their machine except to go
directly to the provider they chose.
"""

import requests

from seetha.config import get_key
from seetha.logger import setup_logger

logger = setup_logger()

NIM_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

DEFAULT_NIM_MODEL = "meta/llama-3.3-70b-instruct"
DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"

NO_KEY_MSG = (
    "No AI key configured. Open Settings and add your free NVIDIA API key "
    "(build.nvidia.com) so I can think properly."
)


def has_brain_key() -> bool:
    """True if at least one chat-capable provider key is configured."""
    return bool(get_key("NVIDIA_API_KEY") or get_key("GROQ_API_KEY"))


def chat_completion(messages, max_tokens=1000, temperature=0.6,
                    json_mode=False, timeout=30):
    """
    Runs a chat completion against the first available provider.

    Args:
        messages: OpenAI-style [{"role": ..., "content": ...}, ...]
        json_mode: ask the provider for strict JSON output (Groq supports
                   this natively; for NIM we rely on the prompt itself).

    Returns:
        (content, error): content is the reply string or None;
                          error is None on success, else a description.
    """
    errors = []

    # ---- 1. NVIDIA NIM ----
    nvidia_key = get_key("NVIDIA_API_KEY")
    if nvidia_key:
        model = get_key("NIM_MODEL") or DEFAULT_NIM_MODEL
        try:
            resp = requests.post(
                NIM_URL,
                headers={
                    "Authorization": f"Bearer {nvidia_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                },
                timeout=timeout,
            )
            if resp.status_code == 200:
                content = resp.json()["choices"][0]["message"]["content"]
                if content and content.strip():
                    return content.strip(), None
                errors.append("NVIDIA returned an empty reply")
            else:
                logger.warning(f"NVIDIA NIM error {resp.status_code}: {resp.text[:200]}")
                errors.append(f"NVIDIA error {resp.status_code}")
        except requests.RequestException as e:
            logger.warning(f"NVIDIA NIM unreachable: {e}")
            errors.append("NVIDIA unreachable")

    # ---- 2. Groq fallback ----
    groq_key = get_key("GROQ_API_KEY")
    if groq_key:
        try:
            payload = {
                "model": DEFAULT_GROQ_MODEL,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
            if json_mode:
                payload["response_format"] = {"type": "json_object"}
            resp = requests.post(
                GROQ_URL,
                headers={
                    "Authorization": f"Bearer {groq_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=timeout,
            )
            if resp.status_code == 200:
                content = resp.json()["choices"][0]["message"]["content"]
                if content and content.strip():
                    return content.strip(), None
                errors.append("Groq returned an empty reply")
            else:
                logger.warning(f"Groq error {resp.status_code}: {resp.text[:200]}")
                errors.append(f"Groq error {resp.status_code}")
        except requests.RequestException as e:
            logger.warning(f"Groq unreachable: {e}")
            errors.append("Groq unreachable")

    if not nvidia_key and not groq_key:
        return None, NO_KEY_MSG

    return None, "; ".join(errors) if errors else "Unknown AI error"


DEFAULT_NIM_VISION_MODEL = "meta/llama-3.2-11b-vision-instruct"
DEFAULT_GROQ_VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"


def _image_to_data_uri(pil_image, max_b64_len=170_000):
    """Downscales/compresses a PIL image until its base64 fits inline API limits."""
    import base64
    import io

    for size, quality in ((900, 60), (700, 45), (520, 35)):
        img = pil_image.copy()
        img.thumbnail((size, size))
        buf = io.BytesIO()
        img.convert("RGB").save(buf, "JPEG", quality=quality)
        b64 = base64.b64encode(buf.getvalue()).decode()
        if len(b64) <= max_b64_len:
            return f"data:image/jpeg;base64,{b64}"
    return f"data:image/jpeg;base64,{b64}"  # smallest attempt


def vision_completion(prompt, pil_image, max_tokens=200, timeout=40):
    """
    Asks a vision model a question about an image (used by the agent
    loop to VERIFY that actions actually worked on screen).

    Returns (content, error). Returns (None, reason) gracefully when no
    vision-capable provider is configured — callers should treat that
    as "verification unavailable", not a failure.
    """
    try:
        data_uri = _image_to_data_uri(pil_image)
    except Exception as e:
        return None, f"image encode failed: {e}"

    content = [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": data_uri}},
    ]
    messages = [{"role": "user", "content": content}]
    errors = []

    # ---- 1. NVIDIA NIM vision ----
    nvidia_key = get_key("NVIDIA_API_KEY")
    if nvidia_key:
        model = get_key("NIM_VISION_MODEL") or DEFAULT_NIM_VISION_MODEL
        try:
            resp = requests.post(
                NIM_URL,
                headers={"Authorization": f"Bearer {nvidia_key}",
                         "Content-Type": "application/json"},
                json={"model": model, "messages": messages,
                      "max_tokens": max_tokens, "temperature": 0.1},
                timeout=timeout,
            )
            if resp.status_code == 200:
                out = resp.json()["choices"][0]["message"]["content"]
                if out and out.strip():
                    return out.strip(), None
            errors.append(f"NVIDIA vision {resp.status_code}")
        except requests.RequestException as e:
            logger.warning(f"NVIDIA vision unreachable: {e}")
            errors.append("NVIDIA vision unreachable")

    # ---- 2. Groq multimodal fallback ----
    groq_key = get_key("GROQ_API_KEY")
    if groq_key:
        try:
            resp = requests.post(
                GROQ_URL,
                headers={"Authorization": f"Bearer {groq_key}",
                         "Content-Type": "application/json"},
                json={"model": DEFAULT_GROQ_VISION_MODEL, "messages": messages,
                      "max_tokens": max_tokens, "temperature": 0.1},
                timeout=timeout,
            )
            if resp.status_code == 200:
                out = resp.json()["choices"][0]["message"]["content"]
                if out and out.strip():
                    return out.strip(), None
            errors.append(f"Groq vision {resp.status_code}")
        except requests.RequestException as e:
            logger.warning(f"Groq vision unreachable: {e}")
            errors.append("Groq vision unreachable")

    if not nvidia_key and not groq_key:
        return None, "no vision provider configured"
    return None, "; ".join(errors) if errors else "vision unavailable"


def test_connection():
    """
    Quick end-to-end check used by the Settings window's Test button.
    Returns (ok: bool, message: str).
    """
    if not has_brain_key():
        return False, NO_KEY_MSG

    content, err = chat_completion(
        [{"role": "user", "content": "Reply with exactly: OK"}],
        max_tokens=10,
        timeout=20,
    )
    if content:
        provider = "NVIDIA NIM" if get_key("NVIDIA_API_KEY") else "Groq"
        return True, f"{provider} is working. Reply: {content[:60]}"
    return False, f"Connection failed: {err}"
