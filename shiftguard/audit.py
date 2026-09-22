"""Structured operational audit events without credentials or request bodies."""
import json
import logging

from flask import g, request
from flask_login import current_user


def init_app(app):
    if "audit_logger" in app.extensions:
        return
    logger = logging.Logger("shiftguard.audit", level=logging.INFO)
    logger.propagate = False
    logger.addHandler(
        app.extensions.get("shiftguard_log_handler", logging.NullHandler())
    )
    app.extensions["audit_logger"] = logger

    @app.after_request
    def record_event(response):
        endpoint = request.endpoint or "unmatched"
        if endpoint in {"static", "api.health"}:
            return response
        actor_id = getattr(g, "audit_actor_id", None)
        if actor_id is None and current_user.is_authenticated:
            actor_id = int(current_user.get_id())
        event = {
            "event": endpoint, "method": request.method,
            "status": response.status_code, "actor_id": actor_id,
            "resource_ids": {key: value for key, value in (request.view_args or {}).items()
                             if isinstance(value, int)},
        }
        if response.is_json and 200 <= response.status_code < 300:
            body = response.get_json(silent=True)
            if isinstance(body, dict):
                event["result"] = {
                    key: body[key] for key in ("id", "imported_records", "skipped_duplicates", "total_rows")
                    if type(body.get(key)) is int
                }
                if body.get("status") in {"approved", "rejected", "draft"}:
                    event["decision"] = body["status"]
        logger.log(
            logging.WARNING if response.status_code >= 400 else logging.INFO,
            json.dumps(event, sort_keys=True),
        )
        return response
