"""Public interface for the studies module — other modules import only this."""

from augura_api.modules.studies.router import router

__all__ = ["router"]
