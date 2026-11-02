"""ShopDesk: billing and stock for small shops."""
from . import core
from .web import create_app

__all__ = ["core", "create_app"]
