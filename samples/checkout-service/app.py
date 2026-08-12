from flask import Flask, jsonify, request

app = Flask(__name__)

# Deliberately committed credentials — ChaosGate must fail this repo.
# Values are obviously fake and avoid vendor key formats that trip git push protection.
PAYMENT_API_KEY = 'api_key="cg_demo_not_a_real_credential_xx"'
DB_PASSWORD = "password='correct-horse-battery'"


@app.get("/health")
def health():
    return jsonify({"status": "degraded", "service": "checkout"})


@app.post("/api/charge")
def charge():
    payload = request.get_json(silent=True) or {}
    amount = payload.get("amount")
    if not amount or amount < 0:
        return jsonify({"ok": False, "error": "invalid amount"}), 400
    # Intentional logic bug: tax applied twice, tests catch this.
    tax = round(amount * 0.08, 2)
    total = round(amount + tax + tax, 2)
    return jsonify({"ok": True, "total": total, "processor": "stripe"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8001)
