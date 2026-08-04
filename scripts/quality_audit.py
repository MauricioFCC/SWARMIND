"""Auditoria de memoria y principios de calidad para Swarmind."""
import os
import re
import subprocess

print("=" * 60)
print("  AUDITORIA DE MEMORIA Y PRINCIPIOS DE CALIDAD")
print("=" * 60)

# 1. Archivos > 900 lines
print("\n1. ARCHIVOS > 900 LINES (violacion <900LC)")
big_files = []
for root, dirs, files in os.walk("harness"):
    if "__pycache__" in root or ".cover" in root:
        continue
    for f in files:
        if not f.endswith(".py"):
            continue
        fpath = os.path.join(root, f)
        with open(fpath, "r", encoding="utf-8", errors="ignore") as fh:
            lines = len(fh.readlines())
        if lines > 900:
            rel = os.path.relpath(fpath).replace("\\", "/")
            big_files.append((rel, lines))

if big_files:
    for f, l in sorted(big_files, key=lambda x: -x[1]):
        print(f"  [FAIL] {f} ({l} lines)")
    print(f"\n  Total: {len(big_files)} archivos violan <900LC")
else:
    print("  [OK] 0 archivos > 900 lines")

# 2. Except:pass
print("\n2. EXCEPT:PASS SILENCIOSO")
exc_count = 0
for root, dirs, files in os.walk("harness"):
    if "__pycache__" in root:
        continue
    for f in files:
        if not f.endswith(".py"):
            continue
        fpath = os.path.join(root, f)
        with open(fpath, "r", encoding="utf-8", errors="ignore") as fh:
            for i, line in enumerate(fh, 1):
                stripped = line.strip()
                if re.search(r"except\s*.*:\s*pass\s*(#.*)?$", stripped):
                    rel = os.path.relpath(fpath).replace("\\", "/")
                    print(f"  [FAIL] {rel}:{i} - {stripped[:80]}")
                    exc_count += 1
if exc_count == 0:
    print("  [OK] 0 except:pass silencioso")

# 3. Docstrings en modulos nuevos
print("\n3. DOCSTRINGS EN MODULOS RECIENTES")
new_modules = [
    "harness/memory_rag/shared_cache.py",
    "harness/orchestrator/event_bus.py",
    "harness/orchestrator/speculative_decoder.py",
    "harness/memory_rag/kv_cache_sharing.py",
    "harness/orchestrator/a2a_protocol.py",
    "harness/memory_rag/prompt_compressor.py",
    "harness/orchestrator/got_planner.py",
    "harness/model_router/router.py",
]
all_ok = True
for mod in new_modules:
    if not os.path.exists(mod):
        print(f"  [SKIP] {mod} no existe")
        continue
    with open(mod, "r", encoding="utf-8", errors="ignore") as fh:
        content = fh.read()

    funcs = re.findall(r"^    def (\w+)\(", content, re.MULTILINE)
    pub_funcs = [f for f in funcs if not f.startswith("_")]
    pub_with_doc = 0

    for fn in pub_funcs:
        pattern = f"def {fn}("
        if pattern in content:
            idx = content.index(pattern)
            chunk = content[idx : idx + 500]
            if '"""' in chunk:
                pub_with_doc += 1

    ratio = (pub_with_doc / len(pub_funcs) * 100) if pub_funcs else 100
    status = "[OK]" if ratio >= 80 else "[FAIL]"
    if ratio < 80:
        all_ok = False
    print(f"  {status} {os.path.basename(mod)}: {pub_with_doc}/{len(pub_funcs)} ({ratio:.0f}%)")

if all_ok:
    print("  [OK] Todos los modulos cumplen ADR-0012")

# 4. Memoria de principios
print("\n4. MEMORIA DE PRINCIPIOS (ContextInjector)")
ci_found = False
for root, dirs, files in os.walk("harness"):
    for f in files:
        if "context_injector" in f.lower() or "context_scoped" in f.lower():
            fpath = os.path.join(root, f)
            rel = os.path.relpath(fpath).replace("\\", "/")
            with open(fpath, "r", encoding="utf-8", errors="ignore") as fh:
                content = fh.read()
            principles = ["CleanCode", "DRY", "KISS", "SSOT", "<900LC"]
            found = [p for p in principles if p in content]
            print(f"  [FOUND] {rel}")
            for p in principles:
                s = "[OK]" if p in found else "[MISS]"
                print(f"    {s} {p}")
            ci_found = True
            break
    if ci_found:
        break

if not ci_found:
    print("  [WARN] No se encontro ContextInjector en harness/")

# 5. Verificar ADR-0001 contiene los principios
print("\n5. ADR-0001 - PRINCIPIOS DOCUMENTADOS")
adr_path = "docs/src/adr/adr0001-mejoras.md"
if os.path.exists(adr_path):
    with open(adr_path, "r", encoding="utf-8") as fh:
        content = fh.read()
    checks = {
        "ContextInjector": "ContextInjector" in content,
        "Estandares": "estandares" in content or "estándares" in content,
        "<900LC": "<900LC" in content,
        "Swiss Watch": "Swiss Watch" in content,
    }
    for k, v in checks.items():
        print(f"  {'[OK]' if v else '[MISS]'} {k} en ADR-0001")

# 6. Ultimos commits
print("\n6. ULTIMOS 5 COMMITS")
result = subprocess.run(
    ["git", "log", "--oneline", "-5"],
    capture_output=True, check=False,
    text=True,
)
for line in result.stdout.strip().split("\n"):
    print(f"  {line}")

# 7. Summary
print("\n" + "=" * 60)
total_violations = len(big_files) + exc_count + (0 if all_ok else 1)
if total_violations == 0:
    print("  [OK] Auditoria de memoria: TODOS LOS PRINCIPIOS PRESERVADOS")
else:
    print(f"  [WARN] {total_violations} violaciones encontradas")
print("=" * 60)
