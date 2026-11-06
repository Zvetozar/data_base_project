# KazBank API — Python + PostgreSQL

CSCI2204, KBTU. Flask + psycopg3 REST API over the KazBank schema
(`customers`, `accounts`, `transactions`).

## How to run

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
createdb mybank
cp .env.example .env        # put your DATABASE_URL here
python step1.py             # Step 1: connection check
python step2.py             # Step 2: create tables + seed data
python app.py               # API on http://127.0.0.1:5050
```

Port 5050 is used because macOS reserves 5000 for AirPlay.

## Files

| File | Purpose |
|---|---|
| `step1.py` | Step 1: connect, print server version, show `autocommit = False` |
| `step2.py` | Step 2: create tables, insert 10 customers and 15 accounts, test UNIQUE |
| `app.py` | Steps 3–7: Flask API |
| `DEADLOCK.md` | Step 4: deadlock reproduced in two psql sessions |

## Endpoints

| Method | Path | Description | Success |
|---|---|---|---|
| GET | `/customers?city=X` | list all customers, or only customers from city X | 200 |
| POST | `/customers` | create a customer `{full_name, city?, email?}` | 201 |
| GET | `/accounts?customer_id=n` | accounts of one customer | 200 |
| GET | `/transactions?account_id=n` | history of one account, newest first | 200 |
| POST | `/transactions` | debit or credit `{account_id, amount, tx_type}` | 201 |
| POST | `/transfer` | move money `{from_account, to_account, amount}` | 201 |
| GET | `/health` | check the database and show `pool.get_stats()` | 200 |

## Error codes

| Situation | Exception | HTTP |
|---|---|---|
| duplicate email | `UniqueViolation` | 409 |
| `full_name` is missing | `NotNullViolation` | 400 |
| not enough money (`/transactions`, `/transfer`) | check in code / `CheckViolation` | 400 |
| database is down | `OperationalError` / `PoolTimeout` | 503 |

All user values are passed as `%s` parameters, so SQL injection does not work:
`curl -G .../customers --data-urlencode "city=Almaty' OR '1'='1"` returns `[]`.

## Step 4: transactions

**Atomic transfer.** When I sent a transfer to account 999 (which does not exist), the first UPDATE ___, but the second one failed with ___. Because of `rollback()`, the balance of account 1 ___. So either both UPDATEs are saved or ___.

**SAVEPOINT.** Account 15 had balance ___. The UPDATE broke the rule ___, so I used `ROLLBACK TO SAVEPOINT` to undo only ___. The transaction was still alive, so I could INSERT a ___ row and commit it. Without a savepoint, ___.

**SERIALIZABLE.** A transfer reads the balance, checks it and then writes. With the default level (READ COMMITTED) two transfers at the same time can ___. SERIALIZABLE makes the result the same as if ___. If there is a conflict, PostgreSQL cancels one transaction with error ___.

**Deadlock.** Session A locked row ___ and waited for row ___. Session B locked row ___ and waited for row ___. They waited for each other forever, so PostgreSQL killed one of them. Full commands and the captured error are in [DEADLOCK.md](DEADLOCK.md).

**Lock order fix.** Now `/transfer` always locks the account with the ___ id first (`sorted()` + `SELECT ... FOR UPDATE`). A transfer 1→3 and a transfer 3→1 both lock row ___ first, so the second one just ___ instead of making a circle.

## Step 5: retry

10 transfers sent at the same time (5 in each direction between accounts 1 and 3):

| | Result |
|---|---|
| without retry | 2 × 201, 8 × 500 (`SerializationFailure`) |
| with `with_retry()` | 10 × 201 |

`with_retry()` runs the whole transaction again (up to 10 times) after a short
random pause. The 8 failed transfers left no rows in `transactions`, so
`rollback` removed them completely.

## Step 6: connection pool

One `ConnectionPool(min_size=2, max_size=8)` is created when the app starts.
Routes borrow a connection with `with pool.connection() as conn`.

20 concurrent `GET /customers`:

```
20 200
{"pool":{"connections_num":7,"pool_max":8,"pool_min":2,"pool_size":7,
 "requests_num":22,"requests_queued":18,"requests_waiting":0, ...},"status":"ok"}
```

22 requests were served by only 7 connections, so connections are reused
instead of being opened for every request.

## Sample curl commands

```bash
B=http://127.0.0.1:5050

curl "$B/customers?city=Almaty"                                            # 200
curl "$B/accounts?customer_id=1"                                           # 200
curl "$B/transactions?account_id=1"                                        # 200
curl $B/health                                                             # 200

curl -X POST $B/customers -H "Content-Type: application/json" \
     -d '{"full_name": "Test User", "email": "test@mail.kz"}'              # 201
curl -X POST $B/customers -H "Content-Type: application/json" \
     -d '{"full_name": "Another", "email": "test@mail.kz"}'                # 409
curl -X POST $B/customers -H "Content-Type: application/json" \
     -d '{"email": "new@mail.kz"}'                                         # 400

curl -X POST $B/transactions -H "Content-Type: application/json" \
     -d '{"account_id": 12, "amount": 5000, "tx_type": "debit"}'           # 201

curl -X POST $B/transfer -H "Content-Type: application/json" \
     -d '{"from_account": 1, "to_account": 3, "amount": 1000}'             # 201
curl -X POST $B/transfer -H "Content-Type: application/json" \
     -d '{"from_account": 15, "to_account": 1, "amount": 500}'             # 400 rejected
```
