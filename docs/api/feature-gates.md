# Feature Gates & Internet-Free Mode

**App version:** 2.55.5

## Overview

The app uses a feature gate system to control which features are available based on user role, subscription tier, and network connectivity. This is how "Internet-Free Mode" works -- it's not a separate mode, but the result of feature gates evaluating against a `Wifi(hasInternet=false)` network state.

## Network Types

| Type | Description |
|------|-------------|
| `NetworkType.Wifi(hasInternet=true)` | WiFi with internet access |
| `NetworkType.Wifi(hasInternet=false)` | WiFi without internet (Internet-Free Mode) |
| `NetworkType.Cellular` | Mobile data |
| `NetworkType.Offline` | No network at all |

## Network Conditions

| Condition | Returns `true` when | Denial reason |
|-----------|---------------------|---------------|
| `NeedInternet` | Cellular, or Wifi with internet | `NOT_AVAILABLE_OFFLINE` |
| `NeedNetwork` | Wifi without internet (but local network present) | `NOT_AVAILABLE_OFFLINE` |
| `AvailableOffline` | Fully offline (no wifi, no cellular) | `NOT_AVAILABLE_OFFLINE` |

## Internet-Free Mode Detection

`NoInternetModeDetectionHandler` detects this state:

1. **Timer:** Fires every 15 seconds
2. **Precondition:** `isLocalConnected() && !isRemoteConnected()`
3. **Ping test:** HEAD requests to Google, Cloudflare, Amazon (5s timeout each)
4. **If all pings fail:** Sets `NetworkType.Wifi(hasInternet=false)`

Ping targets:
- `https://www.google.com`
- `https://www.cloudflare.com`
- `https://www.amazon.com`

## Feature Registry

| Feature | Conditions | Works without internet? |
|---------|------------|------------------------|
| `HomeTab` | AlwaysAvailable | Yes |
| `VideoFeed` | AlwaysAvailable | Yes |
| `InboxTab` | AlwaysAvailable | Yes (cached) |
| `AnalyticsTab` | ViewHearControlOrHigher | Yes (user-role only) |
| `ExploreTab` | ViewHearControlOrHigher | Yes (user-role only) |
| `ExploreTabContent` | ViewHearControlOrHigher AND NeedInternet | No |
| `LullabiesTab` | ViewHearControlOrHigher | Yes (user-role only) |
| `SettingsTab` | (implicit) | Yes |
| `SettingsCribSection` | ViewHearControlOrHigher | Yes |
| `SettingsMyPlanSection` | AdminOnly | Yes |
| `SettingsUnpairCribOption` | AdminOnly | Yes |
| `SettingsCareGiverOption` | AdminOnly | Yes |
| `SettingsDataPrivacyOption` | ViewHearControlOrHigher | Yes |
| `SettingsCribHealthCheckOption` | AdminOnly | Yes |
| `SettingsWebStreamingOption` | ShowWebStreaming | Yes |
| `SettingsWebStreamingPlusTag` | ShowWebStreaming AND ShowWebStreamingPlusTag | Yes |
| `SettingsUploadDiagnosticsOption` | NeedInternet AND ShowUploadDiagnostics | No |
| `InternetFreeModeBanner` | NeedNetwork | Shown only in this mode |
| `HomeCradleStateMessageScreen` | NeedInternet | No |
| `HomeCradleNotReachableScreen` | NeedNetwork | Shown only in this mode |

## User Types / Roles

| Condition | Description |
|-----------|-------------|
| `AlwaysAvailableCondition` | No restrictions |
| `ViewOrHigher` | View access or above |
| `ViewAndHearOrHigher` | View + hear access or above |
| `ViewHearControlOrHigher` | Full control access |
| `AdminOnly` | Admin (primary caregiver) only |

## Subscription Types

| Condition | Description |
|-----------|-------------|
| `NoSubscriptionNeeded` | Free features |
| `NurtureCoreOrHigher` | Nurture Core subscription |
| `OnlyNurturePlus` | Nurture Plus subscription |

## Denial Reasons

| Reason | Description |
|--------|-------------|
| `NO_ACCESS` | User role insufficient |
| `NOT_SUBSCRIBED` | Subscription required |
| `NOT_AVAILABLE` | Feature not available |
| `NOT_AVAILABLE_OFFLINE` | Requires internet |
| `UNKNOWN` | Catch-all |

## Troubleshoot Types

| Type | Description |
|------|-------------|
| `AppOffline` | App has no network |
| `CradleOffline` | Crib is unreachable |

## Source Files

- `com/cradlewise/nini/core/featuregate/base/AppFeature.java`
- `com/cradlewise/nini/core/featuregate/base/NetworkType.java`
- `com/cradlewise/nini/core/featuregate/base/DeniedReason.java`
- `com/cradlewise/nini/core/featuregate/core/FeatureRegistry.java`
- `com/cradlewise/nini/core/featuregate/core/AppFeatureManager.java`
- `com/cradlewise/nini/core/featuregate/condition/network/NeedInternet.java`
- `com/cradlewise/nini/core/featuregate/condition/network/NeedNetwork.java`
- `com/cradlewise/nini/core/featuregate/condition/network/AvailableOffline.java`
- `com/cradlewise/nini/core/mqtt/utils/NoInternetModeDetectionHandler.java`
