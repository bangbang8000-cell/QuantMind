# litellm 1.97.x + pydantic 2.13 compat shim (RD-Agent factor mining).
#
# litellm.types.utils.Message references ChatCompletionReasoningSummaryTextBlock,
# which pydantic 2.13 tries to resolve in utils.py's namespace where the name is
# absent -> PydanticUndefinedAnnotation ("Message is not fully defined").
# Inject the name from llms.openai where it is actually defined, then rebuild.
#
# Mounts into: /usr/local/lib/python3.10/site-packages/sitecustomize.py
# (see docker-compose.yml, quantmind.volumes). Loaded automatically by every
# python process at startup; harmless no-op if the structure changes upstream.

try:
    import litellm.types.utils as _U
    from litellm.types.llms.openai import ChatCompletionReasoningSummaryTextBlock

    _U.ChatCompletionReasoningSummaryTextBlock = ChatCompletionReasoningSummaryTextBlock
    _U.Message.model_rebuild()
except Exception:
    pass