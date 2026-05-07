---
name: react-native
tier: 2
domain: mobile
description: "React Native-specific patterns"
---

# React Native

Bridge calls minimized. Batch native calls, use JSI for performance-critical paths. Bridge has overhead.

Navigation: React Navigation with typed route params. Define router schema in one place, navigate with type safety.

Lists: FlashList (or Recycler View) over FlatList for large datasets. FlatList slower on android.

Images: cached with `expo-image` or `react-native-fast-image`. Memory management critical.

Offline: define sync strategy before writing code. Conflict resolution on timestamp? Last-write-wins?

## Don'ts

- Run JS-heavy computation on main thread during animations
- Use `useEffect` for navigation side effects (use listeners)
- Store sensitive data in AsyncStorage (use SecureStore)
- Unnecessary re-renders from context updates
- Heavy operations in render function
