import os
import random
import time

import psycopg
from dotenv import load_dotenv
from flask import Flask, jsonify, request
from psycopg import IsolationLevel
from psycopg_pool import ConnectionPool, PoolTimeout

load_dotenv()
conn_str = os.environ["DATABASE_URL"]


def reset_conn(conn):
    # /transfer sets SERIALIZABLE; put the default back before the connection is reused
    conn.isolation_level = None


pool = ConnectionPool(conn_str, min_size=2, max_size=8, timeout=5, reset=reset_conn, open=True)


def with_retry(fn, max_retries=10):
    for attempt in range(max_retries):
        try:
            return fn()
        except psycopg.errors.SerializationFailure:
            if attempt == max_retries - 1:
                raise  # out of attempts: give up and let the error out
            # wait a random time, a bit longer after each failure
            time.sleep(random.uniform(0, min(0.5, 0.02 * 2 ** attempt)))


app = Flask(__name__)


@app.route("/customers")
def list_customers():
    city = request.args.get("city")
    if city:
        sql = "SELECT customer_id, full_name, city FROM customers WHERE city = %s ORDER BY customer_id"
        args = (city,)
    else:
        sql = "SELECT customer_id, full_name, city FROM customers ORDER BY customer_id"
        args = ()
    with pool.connection() as conn:
        rows = conn.execute(sql, args).fetchall()
    return jsonify([{"id": r[0], "name": r[1], "city": r[2]} for r in rows])


@app.route("/customers", methods=["POST"])
def create_customer():
    data = request.get_json()
    full_name = data.get("full_name")       # None if missing -> NOT NULL will fail
    city = data.get("city", "Almaty")       # default city if not sent
    email = data.get("email")

    try:
        with pool.connection() as conn:
            row = conn.execute(
                "INSERT INTO customers (full_name, city, email) VALUES (%s, %s, %s) RETURNING customer_id",
                (full_name, city, email)
            ).fetchone()
            conn.commit()
        return jsonify({"id": row[0], "name": full_name}), 201
    except psycopg.errors.UniqueViolation:
        return jsonify({"error": "Email already exists"}), 409
    except psycopg.errors.NotNullViolation:
        return jsonify({"error": "full_name is required"}), 400
    except (psycopg.OperationalError, PoolTimeout):
        return jsonify({"error": "Database unavailable"}), 503


@app.route("/accounts")
def list_accounts():
    customer_id = request.args.get("customer_id")
    with pool.connection() as conn:
        rows = conn.execute(
            "SELECT account_id, account_number, customer_id, balance FROM accounts WHERE customer_id = %s ORDER BY account_id",
            (customer_id,)
        ).fetchall()
    return jsonify([{"id": r[0], "number": r[1], "customer_id": r[2], "balance": float(r[3])} for r in rows])


@app.route("/transactions")
def list_transactions():
    account_id = request.args.get("account_id")
    with pool.connection() as conn:
        rows = conn.execute(
            "SELECT tx_id, account_id, amount, tx_type FROM transactions WHERE account_id = %s ORDER BY tx_id DESC",
            (account_id,)
        ).fetchall()
    return jsonify([{"id": r[0], "account_id": r[1], "amount": float(r[2]), "type": r[3]} for r in rows])


@app.route("/transactions", methods=["POST"])
def create_transaction():
    data = request.get_json()
    account_id = data["account_id"]
    amount = data["amount"]
    tx_type = data["tx_type"]

    if tx_type == "debit":
        change = -amount
    else:
        change = amount

    with pool.connection() as conn:
        # 3. current balance
        row = conn.execute(
            "SELECT balance FROM accounts WHERE account_id = %s",
            (account_id,)
        ).fetchone()
        balance = row[0]

        # 4. check
        if balance + change < 0:
            return jsonify({"error": "Insufficient funds"}), 400

        # 5. update balance
        conn.execute(
            "UPDATE accounts SET balance = balance + %s WHERE account_id = %s",
            (change, account_id)
        )

        # 6. save operation
        conn.execute(
            "INSERT INTO transactions (account_id, amount, tx_type) VALUES (%s, %s, %s)",
            (account_id, amount, tx_type)
        )

        conn.commit()

    return jsonify({"status": "ok", "new_balance": float(balance + change)}), 201


@app.route("/transfer", methods=["POST"])
def transfer():
    data = request.get_json()
    from_acc = data["from_account"]
    to_acc = data["to_account"]
    amount = data["amount"]

    def do_transfer():
        with pool.connection() as conn:
            conn.isolation_level = IsolationLevel.SERIALIZABLE
            try:
                # lock both rows in the same order (smaller id first) to avoid deadlocks
                first, second = sorted([from_acc, to_acc])
                conn.execute("SELECT account_id FROM accounts WHERE account_id = %s FOR UPDATE", (first,))
                conn.execute("SELECT account_id FROM accounts WHERE account_id = %s FOR UPDATE", (second,))

                conn.execute("SAVEPOINT before_transfer")
                try:
                    conn.execute(
                        "UPDATE accounts SET balance = balance - %s WHERE account_id = %s",
                        (amount, from_acc)
                    )
                    conn.execute(
                        "UPDATE accounts SET balance = balance + %s WHERE account_id = %s",
                        (amount, to_acc)
                    )
                except psycopg.errors.CheckViolation:
                    # not enough money: undo only the two UPDATEs
                    conn.execute("ROLLBACK TO SAVEPOINT before_transfer")
                    # but still record the failed attempt
                    conn.execute(
                        "INSERT INTO transactions (account_id, amount, tx_type) VALUES (%s, %s, %s)",
                        (from_acc, amount, "transfer_rejected")
                    )
                    conn.commit()
                    return jsonify({"status": "rejected", "reason": "Insufficient funds"}), 400

                # transfer succeeded: write history
                conn.execute(
                    "INSERT INTO transactions (account_id, amount, tx_type) VALUES (%s, %s, %s)",
                    (from_acc, amount, "transfer_out")
                )
                conn.execute(
                    "INSERT INTO transactions (account_id, amount, tx_type) VALUES (%s, %s, %s)",
                    (to_acc, amount, "transfer_in")
                )

                conn.commit()
            except Exception:
                conn.rollback()
                raise

        return jsonify({"status": "completed", "from": from_acc, "to": to_acc, "amount": amount}), 201

    return with_retry(do_transfer)


@app.route("/health")
def health():
    with pool.connection() as conn:
        conn.execute("SELECT 1")  # is the database alive?
    return jsonify({"status": "ok", "pool": pool.get_stats()})


if __name__ == "__main__":
    app.run(port=5050)
