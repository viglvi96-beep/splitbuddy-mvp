from __future__ import annotations
import os
from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4
from datetime import datetime

from flask import Flask, request, jsonify, redirect, make_response
from flask_cors import CORS

# ---------- Flask ----------
app = Flask(__name__, static_folder="static", static_url_path="/static")
CORS(app)

# ---------- Access (4 токени) ----------
ACCESS_TOKENS = [
    "you-123-Vitalii",
    "friend1-456",
    "friend2-789",
    "friend3-abc",
]
ENV_TOKENS = os.environ.get("ACCESS_TOKENS")
if ENV_TOKENS:
    ACCESS_TOKENS = [t.strip() for t in ENV_TOKENS.split(",") if t.strip()]
@app.before_request
def simple_gate():
    from flask import request
    # дозволяємо форму і сам /auth
    if request.path in ("/auth",) or request.path.startswith("/static/join.html"):
        return None

    # варіант входу через ?k=код (зручно давати посиланням)
    k = request.args.get("k")
    if k:
        resp = make_response(redirect(request.path or "/"))
        resp.set_cookie("access", k, httponly=False, samesite="Lax")
        return resp

    # cookie вже стоїть і валідна?
    cookie_k = request.cookies.get("access")
    if cookie_k and cookie_k in ACCESS_TOKENS:
        return None

    # інакше просимо ввести код
    if request.path == "/" or request.path.startswith(("/e/", "/api/", "/static/index.html")):
        return redirect("/static/join.html")
@app.post("/auth")
def auth():
    data = request.get_json(force=True, silent=True) or {}
    code = (data.get("code") or "").strip()
    if code in ACCESS_TOKENS:
        resp = make_response(jsonify({"ok": True}))
        # збережемо у cookie і впустимо надалі без повторного вводу
        resp.set_cookie("access", code, httponly=False, samesite="Lax")
        return resp
    return jsonify({"ok": False, "error": "invalid_code"}), 401
def simple_gate():
    from flask import request
    if request.path.startswith("/static/join.html"):
        return None
    k = request.args.get("k")
    if k:
        resp = make_response(redirect(request.path or "/"))
        resp.set_cookie("access", k, httponly=False, samesite="Lax")
        return resp
    cookie_k = request.cookies.get("access")
    if cookie_k in ACCESS_TOKENS:
        return None
    if request.path == "/" or request.path.startswith(("/e/", "/api/", "/static/index.html")):
        return redirect("/static/join.html")
    return None

# ---------- DB: Postgres (Neon) ----------
import psycopg
from psycopg.rows import dict_row

DATABASE_URL = os.environ["DATABASE_URL"]  # мусить бути задана
def get_db():
    # autocommit для простоти
    return psycopg.connect(DATABASE_URL, autocommit=True, row_factory=dict_row)

def init_db():
    sql = """
    CREATE TABLE IF NOT EXISTS events (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        currency TEXT NOT NULL DEFAULT 'UAH',
        created_at TIMESTAMPTZ NOT NULL
    );
    CREATE TABLE IF NOT EXISTS participants (
        id SERIAL PRIMARY KEY,
        event_id TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
        name TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS expenses (
        id SERIAL PRIMARY KEY,
        event_id TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
        title TEXT NOT NULL,
        amount_cents INTEGER NOT NULL,
        paid_by INTEGER NOT NULL REFERENCES participants(id) ON DELETE CASCADE,
        created_at TIMESTAMPTZ NOT NULL
    );
    CREATE TABLE IF NOT EXISTS expense_participants (
        expense_id INTEGER NOT NULL REFERENCES expenses(id) ON DELETE CASCADE,
        participant_id INTEGER NOT NULL REFERENCES participants(id) ON DELETE CASCADE,
        PRIMARY KEY (expense_id, participant_id)
    );
    """
    with get_db() as conn, conn.cursor() as cur:
        cur.execute(sql)

def to_cents(amount) -> int:
    d = Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return int(d * 100)

def from_cents(cents: int) -> str:
    return f"{Decimal(cents) / Decimal(100):.2f}"

def now_ts():
    # використовуємо UTC
    return datetime.utcnow()

def event_exists(event_id: str) -> bool:
    with get_db() as conn, conn.cursor() as cur:
        cur.execute("SELECT 1 FROM events WHERE id=%s", (event_id,))
        return cur.fetchone() is not None

# ---------- Pages ----------
@app.route("/")
def index():
    return app.send_static_file("index.html")

@app.route("/e/<event_id>")
def event_page(event_id):
    return app.send_static_file("index.html")

# ---------- API ----------
@app.route("/api/events", methods=["POST"])
def create_event():
    data = request.get_json(force=True, silent=True) or {}
    name = data.get("name") or "New Event"
    currency = data.get("currency") or "UAH"
    event_id = uuid4().hex[:8]
    with get_db() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO events (id, name, currency, created_at) VALUES (%s, %s, %s, %s)",
            (event_id, name, currency, now_ts())
        )
    return jsonify({"id": event_id, "name": name, "currency": currency})

@app.route("/api/events/<event_id>", methods=["GET"])
def get_event(event_id):
    with get_db() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM events WHERE id=%s", (event_id,))
        ev = cur.fetchone()
        if not ev:
            return jsonify({"error": "Event not found"}), 404
        cur.execute("SELECT id, name FROM participants WHERE event_id=%s ORDER BY id", (event_id,))
        parts = cur.fetchall()
        cur.execute("SELECT * FROM expenses WHERE event_id=%s ORDER BY id", (event_id,))
        expenses = cur.fetchall()
        exp_list = []
        for ex in expenses:
            cur.execute("SELECT participant_id FROM expense_participants WHERE expense_id=%s", (ex["id"],))
            involved = [r["participant_id"] for r in cur.fetchall()]
            exp_list.append({
                "id": ex["id"],
                "title": ex["title"],
                "amount": from_cents(ex["amount_cents"]),
                "paid_by": ex["paid_by"],
                "participants": involved,
                "created_at": ex["created_at"].isoformat() + "Z",
            })
    return jsonify({
        "id": ev["id"],
        "name": ev["name"],
        "currency": ev["currency"],
        "created_at": ev["created_at"].isoformat() + "Z",
        "participants": parts,
        "expenses": exp_list
    })

@app.route("/api/events/<event_id>/participants", methods=["POST"])
def add_participant(event_id):
    if not event_exists(event_id):
        return jsonify({"error": "Event not found"}), 404
    data = request.get_json(force=True, silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Name required"}), 400
    with get_db() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO participants (event_id, name) VALUES (%s, %s) RETURNING id, name",
            (event_id, name)
        )
        row = cur.fetchone()
    return jsonify(row)

@app.route("/api/events/<event_id>/participants/<int:pid>", methods=["DELETE"])
def delete_participant(event_id, pid):
    with get_db() as conn, conn.cursor() as cur:
        cur.execute("SELECT 1 FROM participants WHERE id=%s AND event_id=%s", (pid, event_id))
        if not cur.fetchone():
            return jsonify({"error": "Participant not found"}), 404
        cur.execute("SELECT 1 FROM expenses WHERE paid_by=%s", (pid,))
        if cur.fetchone():
            return jsonify({"error": "Cannot delete participant who paid an expense."}), 400
        cur.execute("DELETE FROM expense_participants WHERE participant_id=%s", (pid,))
        cur.execute("DELETE FROM participants WHERE id=%s", (pid,))
    return jsonify({"ok": True})

@app.route("/api/events/<event_id>/expenses", methods=["POST"])
def add_expense(event_id):
    if not event_exists(event_id):
        return jsonify({"error": "Event not found"}), 404
    data = request.get_json(force=True, silent=True) or {}
    title = (data.get("title") or "").strip() or "Expense"
    try:
        amount_cents = to_cents(data.get("amount", 0))
    except Exception:
        return jsonify({"error": "Invalid amount"}), 400
    paid_by = data.get("paid_by")
    participants = data.get("participants") or []
    if amount_cents <= 0:
        return jsonify({"error": "Amount must be > 0"}), 400
    if not isinstance(paid_by, int):
        return jsonify({"error": "paid_by participant id required"}), 400

    with get_db() as conn, conn.cursor() as cur:
        cur.execute("SELECT 1 FROM participants WHERE id=%s AND event_id=%s", (paid_by, event_id))
        if not cur.fetchone():
            return jsonify({"error": "paid_by participant not found in event"}), 400

        if not participants:
            cur.execute("SELECT id FROM participants WHERE event_id=%s", (event_id,))
            participants = [r["id"] for r in cur.fetchall()]

        # перевірка, що всі учасники з цієї події
        cur.execute(
            "SELECT COUNT(*) AS c FROM participants WHERE event_id=%s AND id = ANY(%s)",
            (event_id, participants)
        )
        if cur.fetchone()["c"] != len(participants):
            return jsonify({"error": "One or more participants invalid for this event"}), 400

        cur.execute(
            "INSERT INTO expenses (event_id, title, amount_cents, paid_by, created_at) "
            "VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (event_id, title, amount_cents, paid_by, now_ts())
        )
        expense_id = cur.fetchone()["id"]
        for pid in participants:
            cur.execute(
                "INSERT INTO expense_participants (expense_id, participant_id) VALUES (%s, %s)",
                (expense_id, pid)
            )
    return jsonify({"id": expense_id})

@app.route("/api/events/<event_id>/expenses/<int:eid>", methods=["DELETE"])
def delete_expense(event_id, eid):
    with get_db() as conn, conn.cursor() as cur:
        cur.execute("SELECT 1 FROM expenses WHERE id=%s AND event_id=%s", (eid, event_id))
        if not cur.fetchone():
            return jsonify({"error": "Expense not found"}), 404
        cur.execute("DELETE FROM expense_participants WHERE expense_id=%s", (eid,))
        cur.execute("DELETE FROM expenses WHERE id=%s", (eid,))
    return jsonify({"ok": True})

@app.route("/api/events/<event_id>/settlements", methods=["GET"])
def settlements(event_id):
    with get_db() as conn, conn.cursor() as cur:
        cur.execute("SELECT currency FROM events WHERE id=%s", (event_id,))
        ev = cur.fetchone()
        if not ev:
            return jsonify({"error": "Event not found"}), 404

        cur.execute("SELECT id, name FROM participants WHERE event_id=%s", (event_id,))
        parts = cur.fetchall()
        part_map = {p["id"]: p["name"] for p in parts}
        balances = {pid: 0 for pid in part_map.keys()}

        cur.execute("SELECT id, amount_cents, paid_by FROM expenses WHERE event_id=%s", (event_id,))
        expenses = cur.fetchall()
        for ex in expenses:
            cur.execute("SELECT participant_id FROM expense_participants WHERE expense_id=%s", (ex["id"],))
            involved = [r["participant_id"] for r in cur.fetchall()]
            if not involved:
                continue
            amount = ex["amount_cents"]
            share = amount // len(involved)
            remainder = amount - share * len(involved)
            for i, pid in enumerate(involved):
                owed = share + (1 if i < remainder else 0)
                balances[pid] -= owed
            balances[ex["paid_by"]] += amount

        debtors = [(pid, -amt) for pid, amt in balances.items() if amt < 0]
        creditors = [(pid, amt) for pid, amt in balances.items() if amt > 0]
        debtors.sort(key=lambda x: x[1])
        creditors.sort(key=lambda x: x[1])

        i, j = 0, 0
        transfers = []
        while i < len(debtors) and j < len(creditors):
            d_pid, d_amt = debtors[i]
            c_pid, c_amt = creditors[j]
            pay = min(d_amt, c_amt)
            if pay > 0:
                transfers.append({"from": part_map[d_pid], "to": part_map[c_pid], "amount": from_cents(pay)})
            d_amt -= pay
            c_amt -= pay
            if d_amt == 0: i += 1
            else: debtors[i] = (d_pid, d_amt)
            if c_amt == 0: j += 1
            else: creditors[j] = (c_pid, c_amt)

    balance_view = [{"participant_id": pid, "name": part_map[pid], "balance": from_cents(amt)}
                    for pid, amt in sorted(balances.items())]
    return jsonify({"currency": ev["currency"], "balances": balance_view, "transfers": transfers})

if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)), debug=True)
