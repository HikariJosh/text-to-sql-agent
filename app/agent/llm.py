from langchain.chat_models import init_chat_model

from app.conf.app_config import app_config

# LLM单例：使用OpenAI兼容接口连接大模型
# model_provider="openai" 表示用OpenAI的API协议，但通过base_url指向实际的模型服务
# temperature=0 确保SQL生成的确定性，同样的输入得到同样的输出
llm = init_chat_model(
    model=app_config.llm.model_name,
    model_provider="openai",
    api_key=app_config.llm.api_key,
    base_url=app_config.llm.base_url,
    temperature=0,
)


if __name__ == "__main__":
    # for chunk in llm.stream("What is the meaning of life?"):
    #     print(chunk.text)
    print(llm.invoke("你好，世界！"))
