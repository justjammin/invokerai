---
name: expo
tier: 3
domain: mobile
subdomain: react-native
description: "Expo-specific patterns"
---

# Expo

OTA updates: `expo-updates` with rollback channel configured. Test update flow on real device before production push.

Build: EAS Build for all binary builds—no local `expo build`. Managed updates via Expo Updates service.

Native modules: `expo-modules-core` for new native code. Prefer Expo equivalents over bare RN packages.

Prebuild: auto-generates native projects before build. Commit `ios/` and `android/` folders or regenerate in CI.

Environment variables: use `eas.json` for build env vars, `.env` for local. Don't hardcode in code.

## Don'ts

- Eject without exhausting expo-modules options first
- Use bare RN packages when Expo equivalent exists
- Skip OTA update testing before production push
- Hardcode API URLs (use environment config)
- Commit secrets to repository
