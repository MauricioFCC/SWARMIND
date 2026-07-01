---
name: mobile-engineer
description: Use when implementing mobile apps for iOS/Android, React Native/Flutter views, offline-first logic, push notifications, or mobile-specific UI for the trading dashboard. Swift/Kotlin, Flutter/React Native, MVVM/MVI, offline-first.
---

## CUANDO ACTIVAR

## ✅ CHECKLIST PRE-COMMIT
- [ ] Operaciones lifecycle-safe (0 leaks en rotation/background/kill)
- [ ] Docs 1:1: Toda interfaz/API modificada tiene su doc o README actualizado
- [ ] Estado inmutable + single source of truth • Derivaciones reactivas
- [ ] Sync offline con resolución de conflictos + cola idempotente
- [ ] UI nativa: gestos, safe-areas, tipografía, accesibilidad (VoiceOver/TalkBack)
- [ ] Performance: ≥60fps, <150MB RAM idle, lazy-load, cache de imágenes/media
- [ ] Seguridad: Keychain/Keystore • Cert pinning • 0 secrets en código/assets

## 📐 DECISIONES TÉCNICAS (IF-THEN)

## ⚠️ NUNCA
