# Step 4: deadlock in two psql sessions

Two terminals, both connected with `psql mybank`. Commands run in this order:

```sql
-- 1. Session A
BEGIN;
UPDATE accounts SET balance = balance - 1 WHERE account_id = 1;   -- A locks row 1

-- 2. Session B
BEGIN;
UPDATE accounts SET balance = balance - 1 WHERE account_id = 2;   -- B locks row 2

-- 3. Session A
UPDATE accounts SET balance = balance + 1 WHERE account_id = 2;   -- A waits for B

-- 4. Session B
UPDATE accounts SET balance = balance + 1 WHERE account_id = 1;   -- B waits for A -> deadlock

-- 5. Both sessions
ROLLBACK;
```

Captured error (Session B):

```
ERROR:  deadlock detected
DETAIL:  Process 85737 waits for ShareLock on transaction 2068; blocked by process 85608.
Process 85608 waits for ShareLock on transaction 2069; blocked by process 85737.
HINT:  See server log for query details.
CONTEXT:  while updating tuple (0,23) in relation "accounts"
```

PostgreSQL detected the cycle after about 1 second (`deadlock_timeout`) and
cancelled Session B. Session A's UPDATE then finished.
