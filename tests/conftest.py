"""
测试公共 fixtures
"""

import pytest


@pytest.fixture
def sample_query():
    """示例用户查询"""
    return "查询各省份的GMV"
