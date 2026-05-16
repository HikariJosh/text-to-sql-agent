import re
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def _to_json_safe(value):
    """将数据库返回的值转为 JSON 可序列化的类型"""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


# 禁止在 LLM 生成的 SQL 中出现的危险关键字
_DANGEROUS_KEYWORDS = re.compile(
    r"\b(DROP|DELETE|UPDATE|INSERT|ALTER|TRUNCATE|CREATE|REPLACE|RENAME|GRANT|REVOKE)\b",
    re.IGNORECASE,
)


class DWRepository:
    """
    数据仓库MySQL仓库：负责dw库的查询操作
    包括获取字段类型、字段取值、数据库信息、SQL验证和执行
    dw库是真正的业务数据所在，最终的SQL查询在这里执行
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _sanitize_sql(sql: str) -> str:
        """
        对 LLM 生成的 SQL 做基础安全校验：
        1. 必须以 SELECT / WITH 开头（只允许查询语句）
        2. 不得包含 DDL/DML 危险关键字
        3. 末尾无 LIMIT 时自动追加 LIMIT 1000 防止全表扫描
        """
        normalized = sql.strip().rstrip(";")

        if not re.match(r"^\s*(SELECT|WITH)\b", normalized, re.IGNORECASE):
            raise ValueError(f"仅允许 SELECT/WITH 查询语句，拒绝执行: {sql[:80]}...")

        if _DANGEROUS_KEYWORDS.search(normalized):
            raise ValueError(f"SQL 包含危险关键字，拒绝执行: {sql[:80]}...")

        if not re.search(r"\bLIMIT\b\s+\d+\s*$", normalized, re.IGNORECASE):
            normalized += " LIMIT 1000"

        return normalized

    async def get_column_types(self, table_name):
        """获取表的字段类型信息，返回{字段名: 类型}的映射，用于构建知识库"""
        sql = f"SHOW COLUMNS FROM `{table_name}`"
        result = await self.session.execute(text(sql))
        result_dict = result.mappings().fetchall()
        return {row["Field"]: row["Type"] for row in result_dict}

    async def get_column_values(self, table_name, column_name, limit=10):
        """获取字段的去重示例值，limit=10用于建立索引时的示例，limit=10^9用于全量同步到ES"""
        sql = f"SELECT DISTINCT `{column_name}` FROM `{table_name}` LIMIT {limit}"
        result = await self.session.execute(text(sql))
        rows = result.mappings().fetchall()
        return [_to_json_safe(row[column_name]) for row in rows]

    async def get_db_info(self) -> dict:
        """获取数据库环境信息(版本、方言)，传给LLM帮助生成正确的SQL语法"""
        sql = "select version() as version"
        result = await self.session.execute(text(sql))
        version = result.scalar()
        dialect = self.session.bind.dialect.name
        return {"version": version, "dialect": dialect}

    async def validate_sql(self, sql):
        """通过EXPLAIN验证SQL语法，不合法会抛出异常"""
        safe_sql = self._sanitize_sql(sql)
        explain_sql = f"EXPLAIN {safe_sql}"
        await self.session.execute(text(explain_sql))

    async def execute_sql(self, sql) -> list[dict]:
        """执行SQL查询，返回list[dict]格式的结果"""
        safe_sql = self._sanitize_sql(sql)
        result = await self.session.execute(text(safe_sql))
        rows = result.mappings().fetchall()
        return [dict(row) for row in rows]
