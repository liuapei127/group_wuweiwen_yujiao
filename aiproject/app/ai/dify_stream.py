"""Read Dify Chatflow messages and keep only the answer and conversation ID."""
import json

import httpx


class DifyStreamError(ValueError):
    pass


class ChatAnswer:
    def __init__(self):
        self.text = ""
        self.conversation_id = None
        self.finished = False
        self.waiting_for_workflow = False

    def accept(self, line):
        if not line.startswith("data:"):
            return False
        event = json.loads(line[5:].strip())
        kind = event.get("event")
        data = event.get("data") or {}
        if kind == "error" or (kind == "workflow_finished" and data.get("status") in {"failed", "stopped"}):
            raise DifyStreamError("Dify generation failed")
        if kind == "workflow_started":
            self.waiting_for_workflow = True
        if kind == "workflow_finished":
            self.waiting_for_workflow = False
        if isinstance(event.get("conversation_id"), str):
            self.conversation_id = event["conversation_id"]
        if kind == "message_end":
            self.finished = True
        value = event.get("answer")
        if not isinstance(value, str):
            return False
        if kind in ("message", "agent_message"):
            self.text += value
        elif kind == "message_replace":
            self.text = value
        else:
            return False
        if len(self.text) > 100_000:
            raise DifyStreamError("Dify answer exceeded the limit")
        return True

    def response(self):
        if not self.finished:
            raise DifyStreamError("Dify stream ended prematurely")
        return {"answer": self.text, "conversation_id": self.conversation_id}


async def chat_messages(api_url, key, timeout, payload, on_text):
    async with httpx.AsyncClient(trust_env=False, timeout=httpx.Timeout(timeout, connect=5)) as client:
        async with client.stream(
            "POST", api_url.rstrip("/") + "/chat-messages",
            headers={"Authorization": "Bearer " + key},
            json={**payload, "response_mode": "streaming"},
        ) as response:
            response.raise_for_status()
            answer = ChatAnswer()
            async for line in response.aiter_lines():
                if answer.accept(line):
                    on_text(answer.text)
                if answer.finished and not answer.waiting_for_workflow:
                    break
    return answer.response()
