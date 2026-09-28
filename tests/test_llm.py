from engine.llm import OpenAILLM


def test_writer_stages_use_the_writer_model(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_MODEL", "cheap-model")
    monkeypatch.setenv("OPENAI_WRITER_MODEL", "writer-model")
    llm = OpenAILLM()
    assert llm.model_for("script") == llm.model_for("revision") == "writer-model"
    assert llm.model_for("directions") == llm.model_for("review") == llm.model_for(None) == "cheap-model"
