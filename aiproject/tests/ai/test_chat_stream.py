import asyncio
import json

import httpx
import pytest

from app.ai.assistant.client import chat_preview
from app.ai.assistant.client import DifyIntentClient
from app.ai.assistant.replies import saved_reply
from app.ai.dify_stream import DifyStreamError, chat_messages
from app.core.exceptions import BusinessError
from app.core.responses.streaming import chat_response


def frame(event, **fields):
    return "data: " + json.dumps({"event": event, **fields}, ensure_ascii=False) + "\n\n"


def test_chat_response_sends_partial_before_saved_result():
    async def check():
        finish = asyncio.Event()

        async def run(publish):
            publish("第一段")
            await finish.wait()
            return {"answer": "第一段，第二段", "version": 2}

        parts = chat_response(run).body_iterator
        assert (await anext(parts)).startswith(": connected")
        chunk = await asyncio.wait_for(anext(parts), timeout=2)
        assert "event: text" in chunk and "第一段" in chunk
        finish.set()
        result = await asyncio.wait_for(anext(parts), timeout=2)
        assert "event: result" in result and "第二段" in result
        with pytest.raises(StopAsyncIteration):
            await anext(parts)

    asyncio.run(check())


def test_chat_error_keeps_business_status_and_no_result():
    async def check():
        async def run(_publish):
            raise BusinessError(409, "对话已更新")

        parts = [part async for part in chat_response(run).body_iterator]
        assert "event: error" in parts[-1] and '"status": 409' in parts[-1]
        assert not any("event: result" in part for part in parts)

    asyncio.run(check())


def test_dify_chat_stream_reads_only_answers_and_detects_truncation(monkeypatch):
    real_client = httpx.AsyncClient
    events = [
        "event: ping\n\n",
        frame("workflow_started"),
        frame("node_finished", data={"outputs": {"secret": "internal"}}),
        frame("message", answer="你好", conversation_id="test-conversation"),
        frame("message", answer="，欢迎。", conversation_id="test-conversation"),
        frame("message_replace", answer="欢迎。"),
        frame("workflow_finished", data={"status": "succeeded"}),
        frame("message_end"),
    ]

    class Parts(httpx.AsyncByteStream):
        async def __aiter__(self):
            for event in events:
                data = event.encode("utf-8")
                yield data[:-4]
                yield data[-4:]

    def handle(request):
        assert request.url.path == "/v1/chat-messages"
        assert json.loads(request.content)["response_mode"] == "streaming"
        return httpx.Response(200, stream=Parts())

    monkeypatch.setattr(httpx, "AsyncClient", lambda **options: real_client(
        **options, transport=httpx.MockTransport(handle)))
    visible = []
    args = ("http://dify.test/v1", "key", 10, {"user": "123"}, visible.append)
    result = asyncio.run(chat_messages(*args))
    assert visible == ["你好", "你好，欢迎。", "欢迎。"]
    assert result == {"answer": "欢迎。", "conversation_id": "test-conversation"}

    events.pop()
    with pytest.raises(DifyStreamError):
        asyncio.run(chat_messages(*args))


def test_chat_preview_hides_structured_actions_and_partial_escapes():
    assert not chat_preview('{"intent":"lead_list","params":{},"reply":"内部字段')
    assert not chat_preview('{"intent":"chat","params":{"employee_id":7},"reply":"未通过的回复')
    start = '{"intent":"chat","params":{},"reply":"'
    assert chat_preview(start + r'你好\u73') == "你好"
    assert chat_preview(start + r'你好\u73b0\n进度') == "你好现\n进度"
    assert chat_preview(start + r'你好\ud83d') == "你好"


def test_chat_preview_skips_complete_reasoning_without_exposing_partial_reasoning():
    assert chat_preview('<think>内部推理尚未结束') == ''
    reasoning='<think>内部推理，不应展示给员工。</think>\n'
    assert chat_preview(reasoning+'{"intent":"chat","params":{},"reply":"现在可以帮你整理工作') == '现在可以帮你整理工作'
    assert chat_preview(reasoning+'{"intent":"todo_create","params":{"title":"待确认操作"}}') == ''


def test_business_result_streams_committed_details_before_final_state():
    async def check():
        answer = '本次返回 1 条待办：\n' + '到期时间：2026-11-18 10:16:22\n'*10
        result = {'messages':[{'role':'assistant','content':answer}],'version':1}
        async def run(_publish):
            return result
        parts = [part async for part in chat_response(run,final_text=saved_reply).body_iterator]
        frames = [json.loads(part.split('data: ',1)[1]) for part in parts if part.startswith('event: text')]
        assert len(frames) > 1
        assert frames[0]['text'] != answer and frames[-1]['text'] == answer
        assert parts[-1].startswith('event: result')
        assert json.loads(parts[-1].split('data: ',1)[1])['data'] == result
    asyncio.run(check())


@pytest.mark.parametrize('action,preview',[
    ('{"intent":"chat","params":{},"reply":"你好，欢迎。"}','你好，欢迎。'),
    ('{"intent":"todos","params":{"due_only":true}}',''),
])
def test_workflow_stream_returns_final_output_and_previews_only_chat(action,preview):
    events = [frame('workflow_started'),frame('node_finished',data={'outputs':{'password':'never-visible'}})]
    for fragment in [action[:20],action[20:]]:
        events.append(frame('text_chunk',data={'text':fragment}))
    events.append(frame('workflow_finished',data={'status':'succeeded','outputs':{'text':action}}))
    def handle(request):
        assert json.loads(request.content)['response_mode'] == 'streaming'
        return httpx.Response(200,content=''.join(events))
    visible=[]
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        result=DifyIntentClient._workflow_stream(client,'http://test/workflows/run',{}, {},visible.append)
        assert result['data']['outputs']['text'] == action
        assert (visible[-1] if visible else '') == preview
        assert 'never-visible' not in ''.join(visible)
        events.pop()
        with pytest.raises(ValueError,match='prematurely'):
            DifyIntentClient._workflow_stream(client,'http://test/workflows/run',{}, {},visible.append)
        events.append(frame('workflow_finished',data={'status':'failed'}))
        with pytest.raises(ValueError,match='succeed'):
            DifyIntentClient._workflow_stream(client,'http://test/workflows/run',{}, {},visible.append)
