"""
Fait utiliser à httpx le magasin de certificats du SYSTÈME (Windows) plutôt que
le bundle `certifi`.

Pourquoi (diagnostic 06/2026) : sur cette machine, un proxy / antivirus intercepte
le TLS et re-signe les connexions HTTPS avec une racine CA installée dans le magasin
Windows mais **absente du bundle certifi**. Or httpx (comme requests/pip) utilise
certifi par défaut → TOUTES les requêtes externes (prix Binance/CoinGecko, klines
OHLCV, news) échouaient avec `CERTIFICATE_VERIFY_FAILED` → le robot retombait sur un
prix statique et des bougies périmées (feed mort).

`ssl.create_default_context()` charge le magasin Windows (qui contient la racine du
proxy) → vérification OK. C'est **sécurisé** : on garde la vérification TLS complète
contre le magasin de confiance de l'OS (on ne fait PAS `verify=False`).

Mécanisme : on enveloppe `httpx.Client.__init__` / `httpx.AsyncClient.__init__` pour
forcer `verify=<contexte OS>` UNIQUEMENT quand l'appelant n'a pas fourni de `verify`
explicite (valeur par défaut `True`). Un contexte/chemin custom passé explicitement
est respecté. Couvre donc les ~11 points d'appel httpx du projet sans les modifier.

À importer tout en haut de `app/main.py`, avant toute requête httpx.
"""
import logging
import ssl
from functools import lru_cache

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def os_ssl_context() -> ssl.SSLContext:
    """Contexte SSL adossé au magasin de certificats de l'OS (Windows)."""
    return ssl.create_default_context()


def install_os_trust_store() -> None:
    """Patche httpx pour vérifier le TLS via le magasin de l'OS (idempotent)."""
    try:
        import httpx
    except Exception:  # httpx absent → rien à faire
        return

    if getattr(httpx, "_os_trust_installed", False):
        return

    for cls in (httpx.Client, httpx.AsyncClient):
        _original_init = cls.__init__

        def _make_init(original):
            def __init__(self, *args, **kwargs):
                # Ne touche au verify que s'il est laissé par défaut (True).
                if kwargs.get("verify", True) is True:
                    kwargs["verify"] = os_ssl_context()
                return original(self, *args, **kwargs)
            return __init__

        cls.__init__ = _make_init(_original_init)

    httpx._os_trust_installed = True
    logger.info("[ssl_trust] httpx utilise desormais le magasin de certificats de l'OS")


# Appliqué à l'import du module.
install_os_trust_store()
