from pathlib import Path


def load_prompt(name: str) -> str:
    """
    加载prompt模板文件
    从项目根目录的prompts/文件夹下读取指定名称的.prompt文件
    e.g. load_prompt("generate_sql") -> 读取prompts/generate_sql.prompt的内容
    """
    prompt_path = Path(__file__).parents[2] / "prompts" / f"{name}.prompt"
    return prompt_path.read_text(encoding="utf-8")
