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


def _frontend_origin() -> str:
    """
    Dominio de tu frontend para armar links e iconos absolutos.
    Seteá en Render: FRONTEND_ORIGIN=https://ranking-padel-web.vercel.app
    """
    return (os.getenv("FRONTEND_ORIGIN", "") or "").rstrip("/")


def _safe_str_data(data: Optional[Dict[str, Any]]) -> Dict[str, str]:
    # FCM data SOLO acepta string:string
    safe: Dict[str, str] = {}
    if not data:
        return safe

    for k, v in data.items():
        if v is None:
            continue
        safe[str(k)] = str(v)
    return safe


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

    safe_data = _safe_str_data(data)

    # ✅ IMPORTANTE (WEB):
    # Para que el SW tenga todo, ponemos title/body también en data.
    # (así funciona igual aunque el payload no traiga notification)
    safe_data.setdefault("title", str(title))
    safe_data.setdefault("body", str(body))

    # ✅ Link para click (abre tu web directo al desafío)
    origin = _frontend_origin()
    desafio_id = safe_data.get("desafio_id")
    if origin and desafio_id:
        link = f"{origin}/?open_desafio={desafio_id}"
    elif origin:
        link = f"{origin}/"
    else:
        # si no seteaste FRONTEND_ORIGIN, igual mandamos algo
        link = "/"

    # ✅ Icono ABSOLUTO recomendado para webpush (no relativo al backend)
    icon_url = f"{origin}/icon.png" if origin else "/icon.png"

    # ✅ DATA-first + webpush con link (lo más estable con Service Worker)
    msg = messaging.MulticastMessage(
        tokens=tokens,
        data=safe_data,
        webpush=messaging.WebpushConfig(
            headers={
                # alta prioridad en web push
                "Urgency": "high",
            },
            notification=messaging.WebpushNotification(
                title=title,
                body=body,
                icon=icon_url,
            ),
            fcm_options=messaging.WebpushFCMOptions(
                link=link
            ),
        ),
        # Opcional: si el día de mañana metés Android app, esto sirve.
        android=messaging.AndroidConfig(
            priority="high",
            notification=messaging.AndroidNotification(
                title=title,
                body=body,
            ),
        ),
    )

    try:
        resp = messaging.send_each_for_multicast(msg)
        errors = []
        for idx, r in enumerate(resp.responses):
            if not r.success:
                errors.append({"token": tokens[idx], "error": str(r.exception)})

        return {
            "ok": True,
            "success": resp.success_count,
            "failure": resp.failure_count,
            "errors": errors,
        }

    except AttributeError:
        # Fallback ultra compatible: send_all
        messages = []
        for t in tokens:
            messages.append(
                messaging.Message(
                    token=t,
                    data=safe_data,
                    webpush=messaging.WebpushConfig(
                        headers={"Urgency": "high"},
                        notification=messaging.WebpushNotification(
                            title=title,
                            body=body,
                            icon=icon_url,
                        ),
                        fcm_options=messaging.WebpushFCMOptions(link=link),
                    ),
                    android=messaging.AndroidConfig(
                        priority="high",
                        notification=messaging.AndroidNotification(title=title, body=body),
                    ),
                )
            )

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
