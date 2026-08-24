"""Legacy billing service.

Demonstrates the supply-chain failure modes that code review does not catch:
credentials live in .env (correctly), but .env was committed, and the pinned
dependencies carry published CVEs.
"""
import os

from flask import Flask, jsonify

app = Flask(__name__)

# Correct practice: read from the environment, never hardcode.
STRIPE_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
DB_URL = os.environ.get("DATABASE_URL", "")


@app.get("/health")
def health():
    return jsonify(status="ok", service="legacy-billing")


@app.get("/api/invoices")
def invoices():
    return jsonify(invoices=[
        {"id": "inv-1001", "amount": 4200, "currency": "usd", "paid": True},
        {"id": "inv-1002", "amount": 890, "currency": "usd", "paid": False},
    ])
