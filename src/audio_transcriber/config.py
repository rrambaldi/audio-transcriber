# -*- coding: utf-8 -*-
"""Caricamento della configurazione da un file .env (KEY=VALUE), senza dipendenze."""
import os


def load_dotenv(path=None):
    """Carica un file .env dalla cartella corrente (o dal percorso indicato).
    Le variabili gia' presenti nell'ambiente hanno la precedenza."""
    if path is None:
        path = os.path.join(os.getcwd(), ".env")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
