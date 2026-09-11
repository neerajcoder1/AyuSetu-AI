# AyuSetu Production Backup & Disaster Recovery Runbook

## 1. Overview & Operational Scope
This runbook defines the disaster recovery model, backup procedures, recovery objectives, and cryptographic preservation guarantees for the AyuSetu backend platform in compliance with DPDP Act 2023 and ABDM specifications.

---

## 2. Recovery Objectives (RPO & RTO)

| Subsystem | RPO (Recovery Point Objective) | RTO (Recovery Time Objective) | Storage Authority | Persistence Nature |
| :--- | :--- | :--- | :--- | :--- |
| **Audit Log Chain** | **0 seconds (RPO=0)** (Synchronous WAL) | **< 15 minutes** | PostgreSQL (`audit_events`) | Append-only, Cryptographically Hash-Chained |
| **Clinical Records & Encounters** | **<= 1 minute** (Continuous WAL Archiving) | **< 15 minutes** | PostgreSQL (`encounters`, `patients`) | Persistent Relational Schema |
| **DPDP Consent Records** | **<= 1 minute** (Continuous WAL Archiving) | **< 15 minutes** | PostgreSQL (`consents`, `consent_history`) | Immutable Multi-Version Trail |
| **RedFlag Alert History** | **<= 1 minute** (Continuous WAL Archiving) | **< 15 minutes** | PostgreSQL (`red_flag_events`) | Persistent Deduplicated Log |
| **User & Device Directory** | **<= 1 hour** (Daily snapshot + WAL) | **< 15 minutes** | PostgreSQL (`staff_users`, `devices`) | Persistent Directory |
| **Ephemeral Session Cache** | **N/A (Transient)** | **< 2 minutes** | Redis (AOF / In-Memory) | Ephemeral Token Cache |
| **De-Identified Research Exports** | **N/A (Non-Persistent)** | **N/A** | In-Memory Streaming Only | Zero Artifact Persistence |

---

## 3. PostgreSQL Database Backup Architecture

### 3.1 Continuous WAL Archiving & Point-In-Time Recovery (PITR)
Production deployments must enable continuous PostgreSQL Write-Ahead Log (WAL) archiving to an isolated, immutable backup storage volume (e.g. S3 Object Lock / WORM compliant storage).

```ini
# postgresql.conf production configuration
wal_level = replica
archive_mode = on
archive_command = 'pgbackrest --stanza=ayusetu archive-push %p'
archive_timeout = 60
```

### 3.2 Automated Backup Schedules
1. **Daily Full Backup**: Executed off-peak (02:00 IST) using `pgbackrest` or `pg_dump` with encryption.
2. **Hourly Incremental / Differential Backup**: Executed every hour to minimize WAL replay duration during restore.
3. **Continuous WAL Archiving**: Shipped every 60 seconds or on WAL segment switch (16MB).

### 3.3 Backup Encryption Standard
- All database dumps and archived WAL segments must be encrypted at rest using **AES-256-GCM** via hardware-security-module (HSM) or KMS managed keys.
- Encryption keys must never reside on the database host.

---

## 4. Cryptographic Audit Chain Preservation

### 4.1 Immutability Guarantees
- The `audit_events` table is protected by PostgreSQL database triggers (`audit_events_prevent_mutation_trigger`) that reject all `UPDATE` and `DELETE` queries at the engine level.
- Each audit entry contains a cryptographic SHA-256 `entry_hash` chained to `prev_hash`.

### 4.2 Disaster Recovery Audit Verification Runbook
Upon performing any database restore:
1. Complete database recovery to target point-in-time.
2. Run the automated chain verification job:
   ```bash
   python -c "from ayusetu.audit.service import audit_service; res = audit_service.verify_global_chain(); print('Audit Valid:', res.valid, 'Checked Events:', res.checked_events)"
   ```
3. If `valid == True`, the cryptographic chain is intact and untampered.
4. If `valid == False`, quarantine the environment and trigger incident response.

---

## 5. Redis Ephemeral Session Recovery Model
- **Nature of Redis**: Redis holds 30-minute transient tokens and rate-limiting sliding windows.
- **Failover Behavior**:
  - In a Redis node crash, sessions fail closed (`/ready` returns HTTP 503).
  - Standby replicas take over via Redis Sentinel / Redis Cluster.
  - If memory state is unrecoverable, patients and staff re-authenticate without compromising database integrity or audit chains.

---

## 6. Secret & Key Recovery (KMS / HSM)
- Secret management relies on external KMS / Vault (e.g. AWS KMS, HashiCorp Vault, Azure Key Vault).
- Database credentials, HMAC research salts, and TLS private keys are injected at container startup via secure environment files or Vault sidecars.
- **No secrets are backed up in plain text.**

---

## 7. Migration Recovery & Rollback Runbook

### 7.1 Linear Version Enforcement
- Alembic migrations are strictly linear (`0001_initial_schema` -> `0002_audit_immutability_and_quarantine`).
- In case of a failed deployment migration:
  ```bash
  # Check current revision status
  alembic current

  # Roll back to previous validated revision if required
  alembic downgrade -1
  ```
- **Safety Rule**: Rollbacks must never execute destructive `DROP TABLE` against tables containing PHI or audit records in production without verified offline snapshot.

---

## 8. Zero Artifact Persistence for De-Identified Exports
Per PRD §21.9, research export datasets are **never saved to disk or object storage**:
- De-identified cohorts are synthesized and streamed directly to authorized callers in-memory over HTTPS.
- Only the non-PHI audit event (`action="EXPORT"`, `outcome="ALLOW"`, `cohort_size`, `k_achieved`) is persisted to PostgreSQL.
- No orphan export files or cache artifacts can leak or require storage recovery.
