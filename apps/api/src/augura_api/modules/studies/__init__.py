"""Interface publique du module studies — les autres modules n'importent que ceci."""

from augura_api.modules.studies.router import router

__all__ = ["router"]
