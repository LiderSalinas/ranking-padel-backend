import json
import os
import firebase_admin
from firebase_admin import credentials, messaging


def init_firebase():
    """
    Inicializa Firebase Admin una sola vez.
    Soporta:
      - FIREBASE_SERVICE_ACCOUNT_JSON (recomendado)
      - GOOGLE_APPLICATION_CREDENTIALS (ruta a archivo)
    """
    if firebase_admin._apps:
        return

    sa_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON", "").strip()

    if sa_json:
        # ENV con JSON completo
        cred_dict = json.loads(sa_json)
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)
        return

    # Alternativa: archivo apuntado por GOOGLE_APPLICATION_CREDENTIALS
    # firebase_admin lee la ruta si le pasamos credentials.Certificate(path)
    path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
    if path:
        cred = credentials.Certificate(path)
        firebase_admin.initialize_app(cred)
        return

    raise RuntimeError(
        "Firebase credentials no configuradas. "
        "Seteá FIREBASE_SERVICE_ACCOUNT_JSON o GOOGLE_APPLICATION_CREDENTIALS."
    )


def send_push_to_tokens(tokens: list[str], title: str, body: str, data: dict | None = None):
    """
    Envía push a una lista de tokens FCM (web).
    Retorna dict con conteo success/fail + errores.
    """
    init_firebase()

    tokens = [t.strip() for t in tokens if t and len(t.strip()) > 20]
    if not tokens:
        return {"ok": False, "detail": "No hay tokens válidos"}

    message = messaging.MulticastMessage(
        tokens=tokens,
        notification=messaging.Notification(title=title, body=body),
        data={k: str(v) for k, v in (data or {}).items()},
        # OJO: Web Push settings opcional
        webpush=messaging.WebpushConfig(
            headers={"Urgency": "high"},
        ),
    )

    resp = messaging.send_multicast(message)

    errors = []
    for idx, r in enumerate(resp.responses):
        if not r.success:
            errors.append(
                {
                    "token": tokens[idx],
                    "error": str(r.exception),
                }
            )

    return {
        "ok": True,
        "success_count": resp.success_count,
        "failure_count": resp.failure_count,
        "errors": errors,
    }
