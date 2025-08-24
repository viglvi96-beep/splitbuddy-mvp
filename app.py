from __future__ import annotations
import os
import json
import sqlite3
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4
from flask import Flask, request, jsonify, redirect, make_response
from flask_cors import CORS
from datetime import datetime

# =========================
#  Flask app + CORS
# =========================
DB_PATH = os.environ.get("DB_PATH", "db.sqlite3")

app = Flask(__name__, static_folder="static", static_url_path="/static")
CORS(app)

# =========================
#  ДОСТУП ЛИШЕ ДЛЯ 4 ЛЮДЕЙ
# =========================
# Варіант 1: задай токени прямо тут (заміни на свої значення)
ACCESS_TOKENS = [
    "you-123-Vitalii",
    "friend1-456",
    "friend2-789",
    "friend3-abc",
]

# Варіант 2 (рекомендовано на проді): через ENV:
# ACCESS_TOKENS = [t.strip() for t in os.environ.get("ACCESS_TOKENS","").split(",") if t.strip()] or ACCESS_TOKENS

@app.before_request
def simple_gate():
    """
    Проста "брама":
    - впускає лише якщо у cookie 'access' є один із дозволених токенів
      або якщо перейшли з ?k=<token> (тоді ставимо cookie)
    - якщо доступу немає — редіректимо на /static/join.html
    """
    # дозволяємо саму сторінку введення ключа й статичні ресурси до неї
    if request.path.startswith("/static/join.html"):
        return None

    # Разовий вхід через параметр ?k=
    k = request.args.get("k")
    if k:
        resp = make_response(redirect(request.path or "/"))
        resp.set_cookie("access", k, httponly=False, samesite="Lax")
        return resp

    # Перевіряємо cookie
    cookie_k = request.cookies.get("access")
    if cookie_k in ACCESS_TOKENS:
        return None

    # Якщо токену немає — просимо ввести ключ
    # (захищаємо головну, SPA-роути та API)
    protected_prefixes = ("/", "/e/", "/api/", "/static/index.html")
    if request.path == "/" or request.path.startswith(protected_prefixes):
        return redirect("/static/join.html")

    return None

# =========================
#  DB helpers
# =========================
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS events (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        currency TEXT NOT NULL DEFAULT 'UAH',
        created_at TEXT NOT NULL
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS participants (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id TEXT NOT NULL,
        name TEXT NOT NULL,
        FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS expenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id TEXT NOT NULL,
        title TEXT NOT NULL,
        amount_cents INTEGER NOT NULL,
        paid_by INTEGER NOT NULL, -- participant id
        created_at TEXT NOT NULL,
        FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE,
        FOREIGN KEY (paid_by) REFERENCES participants(id) ON DELETE CASCADE
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS expense_participants (
        expense_id INTEGER NOT NULL,
        participant_id INTEGER NOT NULL,
        PRIMARY KEY (expense_id, participant_id),
        FOREIGN KEY (expense_id) REFERENCES expenses(id) ON DELETE CASCADE,
        FOREIGN KEY (participant_id) REFERENCES participants(id) ON DELETE CASCADE
    )
    """)
    conn.commit()
    conn.close()

def to_cents(amount: str | float | int) -> int:
    d = Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return int(d * 100)

def from_cents(cents: int) -> str:
    return f"{Decimal(cents) / Decimal(100):.2f}"

def now_iso():
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

def event_exists(event_id: str) -> bool:
    conn = get_db()
    row = conn.execute("SELECT id FROM events WHERE id = ?", (event_id,)).fetchone()
    conn.close()
    return row is not None

# =========================
#  PAGES
# =========================
@app.route("/")
def index():
    return app.send_static_file("index.html")

@app.route("/e/<event_id>")
def event_page(event_id):
    # SPA deep-link
    return app.send_static_file("index.html")

# =========================
#  API
# =========================
@app.route("/api/events", methods=["POST"])
def create_event():
    data = request.get_json(force=True, silent=True) or {}
    name = data.get("name") or "New Event"
    currency = data.get("currency") or "UAH"
    event_id = uuid4().hex[:8]
    conn = get_db()
    conn.execute(
        "INSERT INTO events (id, name, currency, created_at) VALUES (?, ?, ?, ?)",
        (event_id, name, currency, now_iso())
    )
    conn.commit()
    conn.close()
    return jsonify({"id": event_id, "name": name, "currency": currency})

@app.route("/api/events/<event_id>", methods=["GET"])
def get_event(event_id):
    conn = get_db()
    ev = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    if not ev:
        conn.close()
        return jsonify({"error": "Event not found"}), 404
    parts = conn.execute("SELECT * FROM participants WHERE event_id = ? ORDER BY id", (event_id,)).fetchall()
    expenses = conn.execute("SELECT * FROM expenses WHERE event_id = ? ORDER BY id", (event_id,)).fetchall()
    exp_list = []
    for ex in expenses:
        rows = conn.execute("SELECT participant_id FROM expense_participants WHERE expense_id = ?", (ex["id"],)).fetchall()
        exp_part_ids = [r["participant_id"] for r in rows]
        exp_list.append({
            "id": ex["id"],
            "title": ex["title"],
            "amount": from_cents(ex["amount_cents"]),
            "paid_by": ex["paid_by"],
            "participants": exp_part_ids,
            "created_at": ex["created_at"],
        })
    conn.close()
    return jsonify({
        "id": ev["id"],
        "name": ev["name"],
        "currency": ev["currency"],
        "created_at": ev["created_at"],
        "participants": [{"id": p["id"], "name": p["name"]} for p in parts],
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
    conn = get_db()
    cur = conn.execute("INSERT INTO participants (event_id, name) VALUES (?, ?)", (event_id, name))
    pid = cur.lastrowid
    conn.commit()
    conn.close()
    return jsonify({"id": pid, "name": name})

@app.route("/api/events/<event_id>/participants/<int:pid>", methods=["DELETE"])
def delete_participant(event_id, pid):
    conn = get_db()
    row = conn.execute("SELECT id FROM participants WHERE id=? AND event_id=?", (pid, event_id)).fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "Participant not found"}), 404
    ex = conn.execute("SELECT id FROM expenses WHERE paid_by=?", (pid,)).fetchone()
    if ex:
        conn.close()
        return jsonify({"error": "Cannot delete participant who paid an expense."}), 400
    conn.execute("DELETE FROM expense_participants WHERE participant_id=?", (pid,))
    conn.execute("DELETE FROM participants WHERE id=?", (pid,))
    conn.commit()
    conn.close()
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
    conn = get_db()
    pb = conn.execute("SELECT id FROM participants WHERE id=? AND event_id=?", (paid_by, event_id)).fetchone()
    if not pb:
        conn.close()
        return jsonify({"error": "paid_by participant not found in event"}), 400
    if not participants:
        rows = conn.execute("SELECT id FROM participants WHERE event_id=?", (event_id,)).fetchall()
        participants = [r["id"] for r in rows]
    q_marks = ",".join("?" for _ in participants)
    rows = conn.execute(f"SELECT id FROM participants WHERE event_id=? AND id IN ({q_marks})",
                        (event_id, *participants)).fetchall()
    if len(rows) != len(participants):
        conn.close()
        return jsonify({"error": "One or more participants invalid for this event"}), 400
    cur = conn.execute(
        "INSERT INTO expenses (event_id, title, amount_cents, paid_by, created_at) VALUES (?, ?, ?, ?, ?)",
        (event_id, title, amount_cents, paid_by, now_iso())
    )
    expense_id = cur.lastrowid
    for pid in participants:
        conn.execute(
            "INSERT INTO expense_participants (expense_id, participant_id) VALUES (?, ?)",
            (expense_id, pid)
        )
    conn.commit()
    conn.close()
    return jsonify({"id": expense_id})

@app.route("/api/events/<event_id>/expenses/<int:eid>", methods=["DELETE"])
def delete_expense(event_id, eid):
    conn = get_db()
    row = conn.execute("SELECT id FROM expenses WHERE id=? AND event_id=?", (eid, event_id)).fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "Expense not found"}), 404
    conn.execute("DELETE FROM expense_participants WHERE expense_id=?", (eid,))
    conn.execute("DELETE FROM expenses WHERE id=?", (eid,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})

@app.route("/api/events/<event_id>/settlements", methods=["GET"])
def settlements(event_id):
    conn = get_db()
    ev = conn.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
    if not ev:
        conn.close()
        return jsonify({"error": "Event not found"}), 404
    parts = conn.execute("SELECT id, name FROM participants WHERE event_id=?", (event_id,)).fetchall()
    part_map = {p["id"]: p["name"] for p in parts}
    balances = {pid: 0 for pid in part_map.keys()}
    expenses = conn.execute("SELECT * FROM expenses WHERE event_id=?", (event_id,)).fetchall()
    for ex in expenses:
        ex_id = ex["id"]
        amount = ex["amount_cents"]
        paid_by = ex["paid_by"]
        rows = conn.execute("SELECT participant_id FROM expense_participants WHERE expense_id=?", (ex_id,)).fetchall()
        involved = [r["participant_id"] for r in rows]
        if not involved:
            continue
        share = amount // len(involved)
        remainder = amount - share * len(involved)
        for i, pid in enumerate(involved):
            owed = share + (1 if i < remainder else 0)
            balances[pid] -= owed
        balances[paid_by] += amount
    conn.close()

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
            transfers.append({
                "from_id": d_pid,
                "to_id": c_pid,
                "amount": from_cents(pay)
            })
        d_amt -= pay
        c_amt -= pay
        if d_amt == 0:
            i += 1
        else:
            debtors[i] = (d_pid, d_amt)
        if c_amt == 0:
            j += 1
        else:
            creditors[j] = (c_pid, c_amt)

    balance_view = [
        {"participant_id": pid, "name": part_map[pid], "balance": from_cents(amt)}
        for pid, amt in sorted(balances.items())
    ]
    transfer_view = [
        {"from": part_map[t["from_id"]], "to": part_map[t["to_id"]], "amount": t["amount"]}
        for t in transfers
    ]
    return jsonify({
        "currency": ev["currency"],
        "balances": balance_view,
        "transfers": transfer_view
    })

if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)), debug=True)
