"""Transcribe a short WAV draft using the server's private Dify app."""
from contextlib import closing
from io import BytesIO
from secrets import token_hex
import wave

import httpx

from app.core.config import get_settings
from app.core.exceptions import BusinessError

MAX_AUDIO_BYTES = 8 * 1024 * 1024
MAX_SECONDS = 120
MAX_DRAFT_LENGTH = 10_000


def _validate_wav(audio: bytes) -> None:
    if len(audio) > MAX_AUDIO_BYTES:
        raise BusinessError(413, "录音文件超过 8 MB，请缩短录音")
    try:
        with closing(wave.open(BytesIO(audio), "rb")) as wav:
            rate = wav.getframerate()
            frames = wav.getnframes()
            if wav.getnchannels() != 1 or wav.getsampwidth() != 2 or rate != 16_000 or not frames:
                raise ValueError("unsupported audio")
            if frames > rate * MAX_SECONDS:
                raise BusinessError(422, "录音最多 2 分钟，请分段录制")
            if len(wav.readframes(frames)) != frames * 2:
                raise ValueError("incomplete audio")
    except (wave.Error, EOFError, ValueError):
        raise BusinessError(422, "录音无效，请重新录制") from None


async def transcribe_audio(audio: bytes) -> str:
    _validate_wav(audio)
    settings = get_settings()
    key = (settings.dify_report_transcription_api_key.get_secret_value()
           or settings.dify_ent_chatflow_api_key.get_secret_value())
    if not key:
        raise BusinessError(503, "语音转写未配置，请手动输入文字")

    try:
        async with httpx.AsyncClient(trust_env=False, timeout=httpx.Timeout(settings.dify_timeout_seconds, connect=5)) as client:
            response = await client.post(
                settings.dify_api_url.rstrip("/") + "/audio-to-text",
                headers={"Authorization": "Bearer " + key},
                data={"user": "employee-audio-" + token_hex(16)},
                files={"file": ("recording.wav", audio, "audio/wav")},
            )
            if not response.is_success:
                code = response.json().get("code") if response.headers.get("content-type", "").startswith("application/json") else None
                if code in {"speech_to_text_disabled", "provider_not_initialize", "provider_not_support_speech_to_text",
                            "provider_quota_exceeded", "model_currently_not_support"}:
                    raise BusinessError(503, "语音转写模型暂不可用，请手动填写或稍后再试")
            response.raise_for_status()
            payload = response.json()
    except httpx.TimeoutException:
        raise BusinessError(504, "语音转写超时，请重试") from None
    except (httpx.HTTPError, ValueError, AttributeError):
        raise BusinessError(502, "语音转写服务暂不可用，请重试或手动填写") from None

    text = payload.get("text") if isinstance(payload, dict) else None
    if not isinstance(text, str) or not text.strip():
        raise BusinessError(422, "未识别到语音，请检查麦克风后重新录制")
    text = text.strip()
    if len(text) > MAX_DRAFT_LENGTH:
        raise BusinessError(422, "转写文字太长，请缩短录音")
    return text
