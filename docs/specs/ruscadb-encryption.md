# Spec — Cifrado en Reposo (RuscaDB) en SWARMIND

> Estado: proposed — Dueño: harness/memory_rag — Frontera: 2026-10.
> RuscaDB spec: `crypto.md`, `encrypted_at_rest.md`, `encrypted_pool.md`, `encrypted_rollback.md`.

## 1. Objetivo
Proteger la memoria central con cifrado en reposo (XChaCha20-Poly1305 + Argon2id).

## 2. Diseno
- `EncryptionConfig.from_passphrase(passphrase)` para derivar clave.
- WAL cifrado (AEAD).
- Keystore KMS-lite con rotacion (SPEC-0088).

## 3. Integracion
- `RuscaDBStore` acepta `encryption_passphrase` en config.
- `open_with_options` pasa encryption a la DLL (requiere FFI extension).
- Env: `RUSCADB_PASSPHRASE` (opcional).

## 4. Outcome medible
- Datos en reposo cifrados.
- Overhead de cifrado < 5%.

## 5. Esfuerzo: 3 dias (FFI) + 2 dias (integracion).
