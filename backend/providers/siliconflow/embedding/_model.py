"""按模型能力传递 dimensions，复用框架的分批、重试和结果顺序处理。"""
from agentscope.embedding import OpenAIEmbeddingModel


class SiliconFlowEmbeddingModel(OpenAIEmbeddingModel):
    # 使用小批次，避免直接沿用 OpenAI 的 2048 条默认批次。
    _TEXT_BATCH_SIZE = 32

    def __init__(self, credential, model, dimensions, **kwargs):
        card = next((card for card in self.list_models() if card.name == model), None)
        if card is None:
            raise ValueError(f"未配置的硅基流动嵌入模型：{model}")
        resolved = dimensions if dimensions is not None else (kwargs.get("parameters") or self.Parameters()).model_dump().get("dimensions")
        supported = card.supported_dimensions or [card.dimensions]
        if resolved not in supported:
            raise ValueError(f"模型 {model} 不支持所选向量维度。")
        # 官方仅为 Qwen3 Embedding 提供可变维度；BGE 不能发送 dimensions。
        super().__init__(credential=credential, model=model, dimensions=dimensions,
                         pass_dimensions=model.startswith("Qwen/Qwen3-Embedding-"), **kwargs)
