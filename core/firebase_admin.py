# core/firebase_admin.py
import json
import os
from typing import Any, Dict, List, Optional

import firebase_admin
from firebase_admin import credentials, messaging


def init_firebase() -> None:
    if firebase_admin._apps:
        return

    raw = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON", "").strip()
    if raw:
        data = json.loads(raw)
        cred = credentials.Certificate(data)
        firebase_admin.initialize_app(cred)
        return

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
    return (os.getenv("FRONTEND_ORIGIN", "") or "").rstrip("/")


def _safe_str_data(data: Optional[Dict[str, Any]]) -> Dict[str, str]:
    safe: Dict[str, str] = {}
    if not data:
        return safe
    for k, v in data.items():
        if v is None:
            continue
        safe[str(k)] = str(v)
    return safe


def _looks_like_invalid_token(exc: Exception) -> bool:
    """
    Detecta tokens muertos/no registrados/invalidos.
    Firebase Admin no siempre expone una clase estable para esto, así que combinamos:
    - type name
    - mensaje
    """
    name = exc.__class__.__name__.lower()
    msg = (str(exc) or "").lower()

    # nombres comunes
    if "unregistered" in name or "notregistered" in name:
        return True
    if "invalid" in name and "token" in name:
        return True

    # mensajes comunes
    patterns = [
        "unregistered",
        "not registered",
        "registration token is not a valid",
        "requested entity was not found",
        "invalid registration token",
        "senderid mismatch",
    ]
    return any(p in msg for p in patterns)


def send_push_to_tokens(
    tokens: List[str],
    title: str,
    body: str,
    data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    init_firebase()

    tokens = [t.strip() for t in tokens if t and t.strip()]
    if not tokens:
        return {"ok": False, "success": 0, "failure": 0, "errors": ["No tokens"], "invalid_tokens": []}

    safe_data = _safe_str_data(data)
    safe_data.setdefault("title", str(title))
    safe_data.setdefault("body", str(body))

    origin = _frontend_origin()
    desafio_id = safe_data.get("desafio_id")
    if origin and desafio_id:
        link = f"{origin}/?open_desafio={desafio_id}"
    elif origin:
        link = f"{origin}/"
    else:
        link = "/"

    icon_url = f"{origin}/icon.png" if origin else "/icon.png"

    msg = messaging.MulticastMessage(
        tokens=tokens,
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
            notification=messaging.AndroidNotification(
                title=title,
                body=body,
            ),
        ),
    )

    try:
        resp = messaging.send_each_for_multicast(msg)

        errors = []
        invalid_tokens: List[str] = []

        for idx, r in enumerate(resp.responses):
            if not r.success:
                exc = r.exception
                errors.append({"token": tokens[idx], "error": str(exc)})
                if exc and _looks_like_invalid_token(exc):
                    invalid_tokens.append(tokens[idx])

        return {
            "ok": True,
            "success": resp.success_count,
            "failure": resp.failure_count,
            "errors": errors,
            "invalid_tokens": invalid_tokens,
        }

    except AttributeError:
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
        invalid_tokens: List[str] = []

        for idx, r in enumerate(batch.responses):
            if not r.success:
                exc = r.exception
                errors.append({"token": tokens[idx], "error": str(exc)})
                if exc and _looks_like_invalid_token(exc):
                    invalid_tokens.append(tokens[idx])

        return {
            "ok": True,
            "success": batch.success_count,
            "failure": batch.failure_count,
            "errors": errors,
            "invalid_tokens": invalid_tokens,
        }
