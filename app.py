from __future__ import annotations

import logging
import time

from flask import Flask, Response, g, render_template, request, send_from_directory
from flask_cors import CORS

from core import metrics, toolchain
from core.api import api, hooks
from core.db import SessionLocal, init_db
from core.seed import seed_samples
from core.settings import HOST, PORT, SECRET_KEY
from core.workspace_api import ws_api

VERSION = "2.0.0"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("chaosgate")


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder="web/templates",
        static_folder="web/static",
        static_url_path="/static",
    )
    app.config["SECRET_KEY"] = SECRET_KEY
    app.config["JSON_SORT_KEYS"] = False
    app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024
    app.config["TEMPLATES_AUTO_RELOAD"] = True

    CORS(app, resources={r"/api/*": {"origins": "*"}, r"/webhook/*": {"origins": "*"}, r"/metrics": {"origins": "*"}})

    init_db()
    db = SessionLocal()
    try:
        seed_samples(db)
    finally:
        db.close()

    metrics.bootstrap(VERSION)
    caps = toolchain.probe(force=True)
    metrics.record_toolchain(caps)
    ready = [name for name, tool in caps["tools"].items() if tool.get("available")]
    degraded = [name for name, tool in caps["tools"].items() if not tool.get("available")]
    log.info("toolchain ready: %s", ", ".join(ready) or "none")
    if degraded:
        log.info("toolchain degraded: %s (those stages run in reduced mode)", ", ".join(degraded))

    app.register_blueprint(api)
    app.register_blueprint(ws_api)
    app.register_blueprint(hooks)

    # ------------------------------------------------------ request metrics
    @app.before_request
    def _start_timer():
        g._started = time.perf_counter()

    @app.after_request
    def _record(response: Response):
        started = getattr(g, "_started", None)
        endpoint = request.endpoint or "unknown"
        if started is not None and endpoint not in ("static", "metrics_endpoint"):
            elapsed = time.perf_counter() - started
            try:
                metrics.http_request_duration_seconds.observe(
                    elapsed, method=request.method, endpoint=endpoint
                )
                metrics.http_requests_total.inc(
                    method=request.method, endpoint=endpoint, status=str(response.status_code)
                )
            except Exception:  # noqa: BLE001
                pass
        response.headers.setdefault("X-ChaosGate-Version", VERSION)
        return response

    # ---------------------------------------------------------- exposition
    @app.get("/metrics")
    def metrics_endpoint():
        return Response(metrics.render(), mimetype="text/plain; version=0.0.4; charset=utf-8")

    @app.get("/healthz")
    def healthz():
        return {"status": "ok", "service": "chaosgate", "version": VERSION}

    @app.get("/readyz")
    def readyz():
        caps = toolchain.probe()
        return {
            "status": "ready",
            "capabilities": caps["summary"],
            "degraded": [n for n, t in caps["tools"].items() if not t.get("available")],
        }

    @app.get("/favicon.svg")
    def favicon():
        return send_from_directory(app.static_folder, "img/mark.svg")

    @app.errorhandler(404)
    def not_found(_):
        if request.path.startswith(("/api/", "/webhook/")):
            return {"error": "not found"}, 404
        return render_template("index.html"), 200

    @app.errorhandler(500)
    def server_error(exc):
        log.exception("unhandled error: %s", exc)
        if request.path.startswith(("/api/", "/webhook/")):
            return {"error": "internal server error"}, 500
        return render_template("index.html"), 500

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def spa(path: str):
        if path.startswith(("api/", "webhook/", "metrics")):
            return {"error": "not found"}, 404
        return render_template("index.html")

    return app


app = create_app()


if __name__ == "__main__":
    log.info("ChaosGate %s listening on http://%s:%s", VERSION, HOST, PORT)
    app.run(host=HOST, port=PORT, debug=False, threaded=True)
