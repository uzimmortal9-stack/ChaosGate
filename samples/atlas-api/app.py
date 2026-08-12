from flask import Flask, jsonify, abort

app = Flask(__name__)

ITEMS = [
    {"sku": "sku-101", "name": "Obsidian mug", "price": 24, "stock": 40},
    {"sku": "sku-104", "name": "Field notebook", "price": 18, "stock": 120},
    {"sku": "sku-208", "name": "Brass caliper", "price": 64, "stock": 12},
]


@app.get("/health")
def health():
    return jsonify({"status": "ok", "service": "atlas-api"})


@app.get("/api/items")
def list_items():
    return jsonify({"items": ITEMS, "count": len(ITEMS)})


@app.get("/api/items/<sku>")
def get_item(sku: str):
    for item in ITEMS:
        if item["sku"] == sku:
            return jsonify(item)
    abort(404)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
