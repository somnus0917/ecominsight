"""Read-only source adapters."""

from ecom_insight.ingestion.external_orders import ExternalOrdersAdapter
from ecom_insight.ingestion.inventory import InventoryAdapter
from ecom_insight.ingestion.orders import OrdersAdapter
from ecom_insight.ingestion.settlement import SettlementAdapter
from ecom_insight.ingestion.sqlite_source import LuopanSQLiteAdapter

__all__ = [
    "ExternalOrdersAdapter",
    "InventoryAdapter",
    "LuopanSQLiteAdapter",
    "OrdersAdapter",
    "SettlementAdapter",
]
