"""Start the app: python -m shopdesk [data.db] [--port 8046]"""
import sys

from .fieldkit import main_cli
from .web import create_app

sys.exit(main_cli(create_app, "shop.db", 8046, sys.argv))
