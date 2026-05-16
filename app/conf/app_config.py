import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from omegaconf import OmegaConf

load_dotenv()

if not OmegaConf.has_resolver("oc.env"):
    OmegaConf.register_new_resolver("oc.env", lambda key, default=None: os.environ.get(key, default))


# 此文档用于定义AppConfig类和相关的配置结构，以及加载和解析配置文件的逻辑。
# AppConfig类包含了应用程序所需的各种配置项，如日志(logging)配置、数据库(db)配置、向量数据库(qdrant)配置、嵌入模型(embedding)配置、搜索引擎(es)配置和LLM配置等。
# 通过使用OmegaConf库，可以方便地从YAML文件中加载配置，并将其转换为AppConfig对象，供应用程序使用。
# e.g. AppConfig.db_meta.host 可获取 meta 数据库主机地址，AppConfig.logging.file.path 可获取日志路径等。
# 配置文件: conf/app.yaml
@dataclass
class FileConfig:
    enable: bool
    level: str
    path: str
    rotation: str
    retention: str


@dataclass
class ConsoleConfig:
    enable: bool
    level: str


@dataclass
class LoggingConfig:
    file: FileConfig
    console: ConsoleConfig


@dataclass
class DBConfig:
    host: str
    port: int
    user: str
    password: str
    database: str


@dataclass
class QdrantConfig:
    host: str
    port: int
    embedding_size: int


@dataclass
class EmbeddingConfig:
    host: str
    port: int
    model: str


@dataclass
class ESConfig:
    host: str
    port: int
    index_name: str


@dataclass
class LLMConfig:
    model_name: str
    api_key: str
    base_url: str


@dataclass
class AppConfig:
    logging: LoggingConfig
    db_meta: DBConfig
    db_dw: DBConfig
    qdrant: QdrantConfig
    embedding: EmbeddingConfig
    es: ESConfig
    llm: LLMConfig


def _load_config() -> AppConfig:
    config_file = Path(__file__).parents[2] / "conf" / "app_config.yaml"
    content = OmegaConf.load(config_file)
    schema = OmegaConf.structured(AppConfig)
    merged = OmegaConf.merge(schema, content)
    return OmegaConf.to_object(merged)


app_config: AppConfig = _load_config()

if __name__ == "__main__":
    print(type(app_config), app_config)
