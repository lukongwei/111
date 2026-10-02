"""Context Gateway：Agent 与本地信息基础设施之间的唯一入口。"""

from .service import ContextGateway, GatewayError

__all__ = ["ContextGateway", "GatewayError"]

