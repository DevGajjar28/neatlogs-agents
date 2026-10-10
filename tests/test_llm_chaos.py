"""Chaos llm_bad_json fires once then allows normal invokes."""

from langchain_core.messages import AIMessage

from app.infra.chaos import ChaosLlmBadJson, clear_kill_armed, set_chaos
from app.llm import _ChaosLlmProxy


class _FakeLLM:
    def invoke(self, prompt):
        return AIMessage(content="ok")

    def with_structured_output(self, schema):
        return self


def test_llm_bad_json_fires_once():
    clear_kill_armed()
    set_chaos("llm_bad_json")
    proxy = _ChaosLlmProxy(_FakeLLM())
    try:
        proxy.invoke("hi")
        raised = False
    except ChaosLlmBadJson:
        raised = True
    assert raised
    out = proxy.invoke("hi again")
    assert out.content == "ok"
