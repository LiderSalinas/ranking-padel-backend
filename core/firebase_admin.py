# core/firebase_admin.py
import json
import os
from typing import Any, Dict, List, Optional

import firebase_admin
from firebase_admin import credentials, messaging


# ---- Init (1 vez) ----
def init_firebase() -> None:
    if firebase_admin._apps:
        return

    # Opción A: JSON completo en env var (recomendado en Render)
    raw = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON", "").strip()
    if raw:
        data = json.loads(raw)
        cred = credentials.Certificate(data)
        firebase_admin.initialize_app(cred)
        return

    # Opción B: ruta a archivo montado como Secret File en Render
    path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
    if path:
        cred = credentials.Certificate(path)
        firebase_admin.initialize_app(cred)
        return

    raise RuntimeError(
        "Firebase Admin no configurado. "
        "Seteá FIREBASE_SERVICE_ACCOUNT_JSON o GOOGLE_APPLICATION_CREDENTIALS."
    )


# ---- Envío ----
def send_push_to_tokens(
    tokens: List[str],
    title: str,
    body: str,
    data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    init_firebase()

    tokens = [t.strip() for t in tokens if t and t.strip()]
    if not tokens:
        return {"ok": False, "success": 0, "failure": 0, "errors": ["No tokens"]}

    # FCM data SOLO acepta string:string
    safe_data: Dict[str, str] = {}
    if data:
        for k, v in data.items():
            if v is None:
                continue
            safe_data[str(k)] = str(v)

    msg = messaging.MulticastMessage(
        tokens=tokens,
        notification=messaging.Notification(title=title, body=body),
        data=safe_data,
        webpush=messaging.WebpushConfig(
            notification=messaging.WebpushNotification(
                title=title,
                body=body,
                icon="/icon.png",
            )
        ),
    )

    # ✅ API nueva (reemplaza send_multicast)
    try:
        resp = messaging.send_each_for_multicast(msg)
        errors = []
        for idx, r in enumerate(resp.responses):
            if not r.success:
                errors.append(
                    {"token": tokens[idx], "error": str(r.exception)}
                )

        return {
            "ok": True,
            "success": resp.success_count,
            "failure": resp.failure_count,
            "errors": errors,
        }

    except AttributeError:
        # Fallback ultra compatible: send_all
        messages = [
            messaging.Message(
                token=t,
                notification=messaging.Notification(title=title, body=body),
                data=safe_data,
                webpush=messaging.WebpushConfig(
                    notification=messaging.WebpushNotification(
                        title=title,
                        body=body,
                        icon="/icon.png",
                    )
                ),
            )
            for t in tokens
        ]

        batch = messaging.send_all(messages)
        errors = []
        for idx, r in enumerate(batch.responses):
            if not r.success:
                errors.append({"token": tokens[idx], "error": str(r.exception)})

        return {
            "ok": True,
            "success": batch.success_count,
            "failure": batch.failure_count,
            "errors": errors,
        }
