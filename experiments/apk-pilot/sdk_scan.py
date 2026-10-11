"""List the software kits (SDKs) and engine inside a game's Android files.

    uv run python experiments/apk-pilot/sdk_scan.py benchmark-runs/apk-pilot/<package>

The folder holds the game's installed APK set (copied from the emulator) and REA's results for its
base APK: ``rea-inspect.json`` (``rea inspect-android-package``) and ``rea-classes.json``
(``rea search-android-classes <base.apk> ""``, every class name). Native library names come from the
split APKs' file lists. Output: ``kits.json`` in the same folder.

A kit's code being present shows the game *can* use it, not that it does in every build or market.
Ad formats are not settled by this: one ad SDK serves rewarded, interstitial and banner ads.
"""

from __future__ import annotations

import json
import re
import sys
import zipfile
from pathlib import Path

# (class-name prefix, kit, category). The first matching prefix wins; order specific before broad.
KITS: list[tuple[str, str, str]] = [
    # Ad networks and mediation
    ("com.applovin.mediation.", "AppLovin MAX (mediation)", "ads"),
    ("com.applovin.", "AppLovin", "ads"),
    ("com.ironsource.", "ironSource / Unity LevelPlay", "ads"),
    ("com.unity3d.mediation.", "Unity LevelPlay (mediation)", "ads"),
    ("com.unity3d.ads.", "Unity Ads", "ads"),
    ("com.unity3d.services.ads.", "Unity Ads", "ads"),
    # The advertising-ID reader ships with attribution kits too; it is not an ad network.
    ("com.google.android.gms.ads.identifier.", "Google advertising ID reader", "identifiers"),
    ("com.google.android.gms.ads.", "Google AdMob", "ads"),
    ("com.google.ads.mediation.", "Google AdMob mediation adapters", "ads"),
    ("com.facebook.ads.", "Meta Audience Network", "ads"),
    ("com.vungle.", "Liftoff Vungle", "ads"),
    ("com.mbridge.msdk.", "Mintegral", "ads"),
    ("com.bytedance.sdk.openadsdk.", "Pangle", "ads"),
    ("com.fyber.", "DT Exchange (Fyber)", "ads"),
    ("com.inmobi.", "InMobi", "ads"),
    ("com.chartboost.", "Chartboost", "ads"),
    ("com.adcolony.", "AdColony", "ads"),
    ("com.my.target.", "myTarget", "ads"),
    ("com.yandex.mobile.ads.", "Yandex Ads", "ads"),
    ("sg.bigo.ads.", "Bigo Ads", "ads"),
    ("com.moloco.sdk.", "Moloco", "ads"),
    ("com.smaato.", "Smaato", "ads"),
    ("com.amazon.device.ads.", "Amazon Publisher Services", "ads"),
    ("com.amazon.aps.", "Amazon Publisher Services", "ads"),
    ("net.pubnative.", "Verve (PubNative)", "ads"),
    ("io.bidmachine.", "BidMachine", "ads"),
    ("com.ogury.", "Ogury", "ads"),
    ("com.hyprmx.", "HyprMX", "ads"),
    ("com.mobilefuse.", "MobileFuse", "ads"),
    ("com.tapjoy.", "Tapjoy (offerwall)", "ads"),
    ("io.adjoe.", "adjoe (playtime rewards)", "ads"),
    # Attribution and analytics
    ("com.adjust.sdk.", "Adjust", "attribution"),
    ("com.appsflyer.", "AppsFlyer", "attribution"),
    ("io.branch.", "Branch", "attribution"),
    ("com.singular.sdk.", "Singular", "attribution"),
    ("com.kochava.", "Kochava", "attribution"),
    ("com.tenjin.", "Tenjin", "attribution"),
    ("com.google.firebase.analytics.", "Firebase Analytics", "analytics"),
    ("com.gameanalytics.", "GameAnalytics", "analytics"),
    ("com.amplitude.", "Amplitude", "analytics"),
    ("com.mixpanel.", "Mixpanel", "analytics"),
    ("com.segment.", "Segment", "analytics"),
    ("com.facebook.appevents.", "Meta app events", "analytics"),
    ("com.google.firebase.crashlytics.", "Firebase Crashlytics", "crash_reporting"),
    ("com.bugsnag.", "Bugsnag", "crash_reporting"),
    ("io.sentry.", "Sentry", "crash_reporting"),
    ("io.embrace.", "Embrace", "crash_reporting"),
    ("com.datadog.", "Datadog", "crash_reporting"),
    # Player messaging, live-ops and support
    ("com.braze.", "Braze", "crm_push"),
    ("com.appboy.", "Braze", "crm_push"),
    ("com.leanplum.", "Leanplum", "crm_push"),
    ("com.swrve.", "Swrve", "crm_push"),
    ("com.onesignal.", "OneSignal", "crm_push"),
    ("com.clevertap.", "CleverTap", "crm_push"),
    ("com.urbanairship.", "Airship", "crm_push"),
    ("com.google.firebase.messaging.", "Firebase Cloud Messaging", "crm_push"),
    ("com.google.firebase.remoteconfig.", "Firebase Remote Config", "liveops"),
    ("com.helpshift.", "Helpshift", "support"),
    ("com.zendesk.", "Zendesk", "support"),
    ("zendesk.", "Zendesk", "support"),
    # Back end, multiplayer and social
    ("com.playfab.", "PlayFab", "backend"),
    ("com.heroiclabs.", "Nakama", "backend"),
    ("de.exitgames.", "Photon", "multiplayer"),
    ("com.google.firebase.firestore.", "Cloud Firestore", "backend"),
    ("com.google.firebase.database.", "Firebase Realtime Database", "backend"),
    ("com.google.android.gms.games.", "Google Play Games Services", "platform"),
    ("com.facebook.login.", "Facebook Login", "social"),
    ("com.facebook.share.", "Facebook Share", "social"),
    ("com.facebook.gamingservices.", "Facebook Gaming Services", "social"),
    ("com.google.android.gms.auth.", "Google Sign-In", "social"),
    # Payments and consent
    ("com.android.billingclient.", "Google Play Billing", "payments"),
    ("com.google.android.ump.", "Google consent (UMP)", "consent"),
    ("com.usercentrics.", "Usercentrics", "consent"),
    ("com.onetrust.", "OneTrust", "consent"),
    ("io.didomi.", "Didomi", "consent"),
    # Engines and runtimes
    ("com.unity3d.player.", "Unity", "engine"),
    ("com.epicgames.", "Unreal Engine", "engine"),
    ("org.cocos2dx.", "Cocos2d-x", "engine"),
    ("org.godotengine.", "Godot", "engine"),
    ("io.flutter.", "Flutter", "engine"),
    ("com.facebook.react.", "React Native", "engine"),
]
NATIVE_ENGINES = {
    "libunity.so": "Unity",
    "libil2cpp.so": "Unity (IL2CPP)",
    "libmonobdwgc-2.0.so": "Unity (Mono)",
    "libUE4.so": "Unreal Engine 4",
    "libUnreal.so": "Unreal Engine 5",
    "libcocos2dcpp.so": "Cocos2d-x",
    "libcocos.so": "Cocos Creator",
    "libgodot_android.so": "Godot",
    "libflutter.so": "Flutter",
    "libhermes.so": "React Native (Hermes)",
}
ADAPTER = re.compile(r"^com\.applovin\.mediation\.adapters\.(\w+?)MediationAdapter$")


def class_names(result: dict) -> tuple[list[str], str]:
    """Class names from REA's result, or from the raw pages REA keeps when it refuses one.

    REA refuses a class inventory whose names repeat (an obfuscated build can list a name twice)
    and keeps the engine's raw pages in ``details.partial_observation``. Those pages are still a
    full listing, so the names are taken from them, de-duplicated, and the coverage says so.
    """
    if "normalized_result" in result:
        found = result["normalized_result"]
        return found["matches"], found["coverage"]
    pages = [
        c["response"]
        for c in result["details"]["partial_observation"]["calls"]
        if c["operation"] == "list_classes"
    ]
    names: list[str] = []
    total = None
    for page in pages:
        body = json.loads("".join(x.get("text", "") for x in page.get("content", [])))
        names += body["items"]
        total = body.get("total", total)
    unique = sorted(set(names))
    return unique, (
        f"from REA's raw pages: {len(names)} names listed, {len(names) - len(unique)} repeated, "
        f"engine total {total}"
    )


def scan(folder: Path) -> dict:
    inspect = json.loads((folder / "rea-inspect.json").read_text())["normalized_result"]
    names, coverage = class_names(json.loads((folder / "rea-classes.json").read_text()))
    found: dict[str, dict] = {}
    for name in names:
        for prefix, kit, category in KITS:
            if name.startswith(prefix):
                entry = found.setdefault(kit, {"kit": kit, "category": category, "classes": 0})
                entry["classes"] += 1
                entry.setdefault("example", name)
                break
    adapters = sorted({m.group(1) for n in names if (m := ADAPTER.match(n))})
    libs: dict[str, list[str]] = {}
    for apk in sorted(folder.glob("*.apk")):
        with zipfile.ZipFile(apk) as z:
            for item in z.namelist():
                if item.startswith("lib/") and item.endswith(".so"):
                    libs.setdefault(item.split("/")[1], []).append(item.rsplit("/", 1)[1])
    lib_names = sorted({n for v in libs.values() for n in v})
    engines = sorted({NATIVE_ENGINES[n] for n in lib_names if n in NATIVE_ENGINES})
    manifest = inspect["manifest"]["text"]
    ad_activities = sorted(
        set(
            re.findall(
                r'android:name="([^"]*(?:applovin|ironsource|unity3d\.ads|gms\.ads)[^"]*)"',
                manifest,
            )
        )
    )
    return {
        "package": inspect["package_name"],
        "version": inspect["version_name"],
        "target_sdk": inspect["target_sdk"],
        "class_count": len(names),
        "class_inventory_coverage": coverage,
        "apk_files": [p.name for p in sorted(folder.glob("*.apk"))],
        "engines_from_native_libraries": engines,
        "native_libraries": lib_names,
        "kits": sorted(found.values(), key=lambda k: (k["category"], k["kit"])),
        "applovin_mediation_adapters": adapters,
        "ad_components_in_manifest": ad_activities,
        "advertising_id_permission": "com.google.android.gms.permission.AD_ID" in manifest,
        "permissions": inspect["permissions"],
    }


def main() -> None:
    folder = Path(sys.argv[1])
    result = scan(folder)
    (folder / "kits.json").write_text(json.dumps(result, indent=1))
    by_cat: dict[str, list[str]] = {}
    for k in result["kits"]:
        by_cat.setdefault(k["category"], []).append(k["kit"])
    print(
        f"{result['package']} {result['version']}: engine {result['engines_from_native_libraries']}"
    )
    for cat, kits in sorted(by_cat.items()):
        print(f"  {cat}: {', '.join(kits)}")
    if result["applovin_mediation_adapters"]:
        print(f"  MAX adapters: {', '.join(result['applovin_mediation_adapters'])}")


if __name__ == "__main__":
    main()
