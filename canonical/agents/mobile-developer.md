---
name: mobile-developer
description: Invoke for iOS (Swift/SwiftUI), Android (Kotlin/Compose), React Native, or Flutter tasks including state management, native integrations, store submission, and cross-platform architecture decisions.
---

## Patterns

**SwiftUI state management** -- Use @State for local value types, @Observable (iOS 17+) or @ObservableObject for shared models, @Binding to pass writable state down, @EnvironmentObject for app-wide singletons only. Never reach up into parent state.

**Compose state hoisting** -- Stateless composables receive (state, onEvent) pairs. Screen-level state lives in ViewModel + StateFlow. Use remember{} for ephemeral UI state; collectAsStateWithLifecycle() to consume flows safely.

**React Native New Architecture (JSI)** -- Old bridge serializes all calls to JSON asynchronously. JSI gives JS a direct C++ reference, enabling synchronous native calls. Use TurboModules for performance-critical native code. Reanimated 3 and Gesture Handler v2 already run on JSI.

**Flutter widget lifecycle** -- initState (setup, subscriptions) -> build (pure, no side effects) -> dispose (cancel subscriptions). Never perform async work or API calls inside build().

**Deep linking** -- iOS requires AASA file at /.well-known/apple-app-site-association (HTTPS, no redirect). Android requires assetlinks.json + autoVerify=true intent-filter. Both must be verified before App Store / Play Store submission.

**Push notification permissions** -- Show a custom pre-prompt before the OS dialog on iOS. On Android 13+ (API 33), request POST_NOTIFICATIONS explicitly. Sync FCM/APNs token to backend immediately after grant.

**Background tasks** -- iOS: BGProcessingTask (minutes, deferred) or BGAppRefreshTask (~30s). Android: WorkManager with Constraints. React Native: Headless JS. Flutter: workmanager plugin. Never rely on silent push for critical background work.

**Secure storage** -- Keychain (iOS) or EncryptedSharedPreferences + Android Keystore (Android). react-native-keychain in RN. flutter_secure_storage in Flutter. Never AsyncStorage, UserDefaults, or SharedPreferences for secrets.

**Biometric auth** -- LocalAuthentication (iOS), BiometricPrompt API 28+ (Android). Always check capability, provide PIN fallback, never transmit biometric data. Store secret in Keychain/Keystore; biometrics only unlock access.

**Offline-first** -- Write to local DB first, sync in background. Core Data / SwiftData (iOS), Room + WorkManager (Android), WatermelonDB or expo-sqlite (RN). Define conflict resolution strategy (last-write-wins vs server-authority) before building sync.

## Anti-Patterns

**AsyncStorage for tokens (RN)** -- Unencrypted, readable from device backup. Use react-native-keychain.

**Blocking the iOS main thread** -- Network, JSON decode, or file I/O on main thread causes frame drops and watchdog kills. Use async/await or DispatchQueue.global() and MainActor for UI updates.

**Swift closure retain cycles** -- Capturing self strongly in stored closures creates leaks. Always use [weak self] in closures that outlive their function scope. Verify with Instruments Allocations.

**useEffect as event handler (RN)** -- Leads to infinite loops, stale closures, race conditions. Derive values from state; use event handlers for user actions; reserve useEffect for external synchronization only.

**Ignoring Android back stack** -- Not handling Back button correctly accumulates ghost Activities. Use Navigation component and proper FLAG_ACTIVITY_* flags for task management.

**Side effects in Flutter build()** -- build() fires many times per second. Network calls, subscriptions, or analytics in build() cause duplicates and undefined behavior. Move all side effects to initState() or state management callbacks.

## Gotchas

**iOS Simulator: no real push notifications or Touch ID** -- APNs registration always fails on simulator. Use "xcrun simctl push <device-id> <bundle-id> payload.apns" for local simulation. Gate biometric and push code for simulator with "#if !targetEnvironment(simulator)". All final QA must run on physical hardware.

**Android API level guards** -- BiometricPrompt: API 28+. POST_NOTIFICATIONS: API 33+. Exact alarms: API 31+. Use Build.VERSION.SDK_INT checks or AndroidX compat libraries. Check Play Console version distribution before raising minSdk.

**Metro bundler cache corruption (RN)** -- Stale cache after native module installs causes "module not found" on installed packages. Fix: "npx react-native start --reset-cache". Full clean: gradlew clean (Android) + xcodebuild clean (iOS) + watchman watch-del-all (macOS).

**Flutter hot reload preserves state** -- initState does not re-run on hot reload. Changes to initialization logic, constructors, or provider setup require hot restart (Shift+R). Hot reload is for build() / UI iteration only.

**iOS ATS blocks HTTP** -- All plaintext HTTP is blocked by App Transport Security in production. Add NSExceptionDomains scoped to specific staging hosts in Info.plist. Never set NSAllowsArbitraryLoads=true (App Store flags it). Use Charles Proxy or mitmproxy to inspect TLS.

**Android ProGuard stripping classes** -- R8 removes reflection-accessed classes in release builds. Crashes appear only in release APK. Add keep rules in proguard-rules.pro and always test "app-release.apk" before Play Store submission.

**Android keyboard windowSoftInputMode** -- Inconsistent adjustResize vs adjustPan causes layouts to shift or clip when keyboard appears. Set android:windowSoftInputMode="adjustResize" in AndroidManifest.xml. Use KeyboardAvoidingView with platform-specific behavior prop (padding on iOS, height on Android).

## Commands

```bash
# iOS -- Simulator management
xcrun simctl list devices available
xcrun simctl boot "iPhone 16 Pro"
xcrun simctl push booted com.yourapp payload.apns
xcrun simctl openurl booted "https://yourdomain.com/products/123"

# iOS -- Xcode build and archive
xcodebuild -workspace App.xcworkspace -scheme App -configuration Release \
  -archivePath build/App.xcarchive archive
xcodebuild -exportArchive -archivePath build/App.xcarchive \
  -exportOptionsPlist ExportOptions.plist -exportPath build/ipa

# Android -- ADB utilities
adb devices
adb install -r app/build/outputs/apk/release/app-release.apk
adb logcat --pid=$(adb shell pidof -s com.yourapp)
adb shell am start -W -a android.intent.action.VIEW \
  -d "https://yourdomain.com/products/123" com.yourapp

# Android -- Gradle
./gradlew assembleRelease
./gradlew bundleRelease        # AAB for Play Store
./gradlew clean

# React Native
npx react-native start --reset-cache
npx react-native run-ios --device "My iPhone"
npx react-native run-android
npx react-native run-android --variant=release
npx react-native log-ios
npx react-native log-android

# Flutter
flutter doctor -v
flutter devices
flutter run -d <device-id>
flutter run --release
flutter build apk --release
flutter build appbundle --release
flutter build ipa --release
flutter clean && flutter pub get
flutter analyze
flutter test
```

## Version Notes

**iOS / Swift**
- SwiftUI @Observable macro available iOS 17+ (replaces @ObservableObject boilerplate)
- SwiftData available iOS 17+ (replaces Core Data for new projects)
- Swift concurrency (async/await, actors) -- iOS 15+; back-deploy to iOS 13/14 with Swift 5.5 package
- Privacy manifest (PrivacyInfo.xcprivacy) required for App Store submission as of Spring 2024
- Xcode 15+ required for iOS 17 SDK; always match Xcode version to target SDK

**Android / Kotlin**
- Jetpack Compose stable from 1.0 (2021); prefer Compose for new projects over XML Views
- Material 3 (Material You) available in Compose via androidx.compose.material3
- Kotlin coroutines + Flow are the standard; avoid RxJava for new code
- Target API 34 required for new apps/updates on Google Play (as of 2024)
- 64-bit requirement: all APKs must include ARM64 native libraries

**React Native**
- New Architecture (Fabric + TurboModules) is opt-in from 0.68, default from 0.73
- Expo SDK 50+ supports New Architecture; bare workflow requires manual enablement
- Hermes is the default JS engine from RN 0.70; JavaScriptCore no longer default
- Metro 0.80+ supports package exports field; align with node_modules expectations

**Flutter**
- Flutter 3.x (Dart 3): required for records, patterns, class modifiers
- Impeller renderer is default on iOS from Flutter 3.10; opt-in on Android from 3.13
- flutter_secure_storage v8+ requires Android Gradle Plugin 7.0+
- Null safety is mandatory; all packages must be null-safe for Flutter 3.x

## Cross-Platform Decision Guide

**Choose native (Swift/Kotlin) when:**
- Heavy use of platform APIs (ARKit, CoreML, CameraX, Health)
- App is the primary product and performance is paramount
- Team has existing platform expertise and long-term maintenance commitment

**Choose React Native when:**
- Existing React/TypeScript codebase to leverage
- Team needs to ship on both platforms simultaneously with one JS team
- Heavy web-to-mobile parity (same business logic, shared API layer)

**Choose Flutter when:**
- Custom design system that diverges from platform defaults
- Targeting multiple platforms including web and desktop
- Starting greenfield with no existing web codebase investment

**Store submission checklist (both platforms):**
- Screenshots and metadata in all required sizes/locales
- Privacy policy URL live and accessible
- All required permissions with usage descriptions (iOS Info.plist NSUsageDescription keys)
- Test on oldest supported OS version (minSdk / minimum deployment target)
- Release APK or IPA -- not debug build -- signed with production certificate
- iOS: TestFlight beta tested before App Store submission
- Android: Internal/Closed track tested in Play Console before production rollout
