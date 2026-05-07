---
name: mobile
tier: 1
description: "Universal mobile domain rules"
---

# Mobile

60fps target: profile with platform tools (Android Profiler, Instruments) before optimizing. Measure frame time.

Startup: cold start <2s, time-to-interactive <3s. Profile on 4G network.

Offline-first: define conflict resolution strategy before writing sync code. What happens when user edits while offline then comes online?

Push notifications: handle all states—foreground, background, killed app. User opt-in, opt-out clear.

App store compliance: review guidelines before build (iOS HIG, Android Material Design, app store rules). Don't learn via rejection.

Deep links: handle invalid/expired links gracefully. Show error or fallback UI.

## Don'ts

- Block main thread with sync IO
- Assume network always available
- Skip platform UX guidelines (HIG for iOS, Material for Android)
- Use deprecated APIs without migration plan
- Store sensitive data in plain SharedPreferences/UserDefaults
