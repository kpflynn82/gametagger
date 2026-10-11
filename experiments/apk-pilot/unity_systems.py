"""Which systems a Unity (IL2CPP) game is built from, and how it gates them, from its code names.

    uv run python experiments/apk-pilot/unity_systems.py \
        benchmark-runs/apk-pilot/com.scopely.monopolygo Tophat

An IL2CPP game compiles its logic to native code but keeps every type, method and field name in
``global-metadata.dat`` inside the base APK. This script reads those names only, and only when the
file is unencrypted (some games encrypt it; then it stops). ``Tophat`` is the game's own namespace
prefix (Monopoly GO's); the script writes ``systems.json`` next to the APK with:

* ``systems``: the game's own namespaces ``<prefix>.<layer>.<system>``, one entry per system;
* ``gates``: the kinds of prerequisite the game can put on a feature, and its unlock triggers;
* ``tutorials``: features that ship their own tutorial;
* ``progression_settings``: names of unlock and per-board settings.

Names show what the game can do and how it decides. The values (which board, which net worth) are
not in the code; the game's servers send them.
"""

from __future__ import annotations

import json
import re
import struct
import sys
import zipfile
from collections import Counter
from pathlib import Path

METADATA = "assets/bin/Data/Managed/Metadata/global-metadata.dat"
SANITY = 0xFAB11BAF
# Names that end like a prerequisite or tutorial but are helpers, not kinds of gate or features.
NOT_GATES = {
    "Prerequisite",
    "TPrerequisite",
    "UnknownPrerequisite",
    "EvaluatePrerequisite",
    "TryEvaluatePrerequisite",
    "GetGameConfigPrerequisite",
}
HELPER_VERB = re.compile(r"^(Get|Create|Check|Handle|Try|Set|Is|Has)[A-Z]")
PROGRESSION = re.compile(
    r"(AtBoard|ByBoard|BoardLevel|MinBoard|MinimumBoards|BoardUnlocks|BoardsCompleted"
    r"|InNetWorth|NetWorthAmount|RequiredNetWorth|FeatureUnlock|ToUnlock|UnlockMap|UnlockConfig)"
)


def read_names(data: bytes) -> tuple[int, list[str], list[str]]:
    """(metadata version, identifier names, string literals) from global-metadata.dat."""
    sanity, version = struct.unpack_from("<Ii", data, 0)
    if sanity != SANITY:
        raise SystemExit("global-metadata.dat is encrypted or not IL2CPP metadata: stopping")
    if version >= 38:  # Unity 6: sections are (offset, size, count); literals are offset tables
        (lit_off, _, lit_count), (data_off, data_size, _), (str_off, str_size, _) = (
            struct.unpack_from("<III", data, 8 + 12 * i) for i in range(3)
        )
        starts = list(struct.unpack_from(f"<{lit_count}I", data, lit_off)) + [data_size]
        spans = [(starts[i], starts[i + 1] - starts[i]) for i in range(lit_count)]
    elif (
        version >= 24
    ):  # Unity 2018-2023: sections are (offset, size); literals are (length, index)
        (lit_off, lit_size), (data_off, _), (str_off, str_size) = (
            struct.unpack_from("<ii", data, 8 + 8 * i) for i in range(3)
        )
        pairs = struct.iter_unpack("<Ii", data[lit_off : lit_off + lit_size])
        spans = [(index, length) for length, index in pairs]
    else:
        raise SystemExit(f"metadata version {version} is older than this script reads: stopping")
    literals = [data[data_off + a : data_off + a + n].decode("utf-8", "replace") for a, n in spans]
    identifiers = data[str_off : str_off + str_size].decode("utf-8", "replace").split("\0")
    return version, [s for s in identifiers if s], literals


def summarize(apk: Path, prefix: str) -> dict:
    with zipfile.ZipFile(apk) as z:
        version, identifiers, literals = read_names(z.read(METADATA))
    names = set(identifiers)
    namespaces = sorted(s for s in names if s.startswith(prefix + ".") and s.count(".") >= 2)
    systems = Counter(s.split(".")[2] for s in namespaces)
    layers = Counter(s.split(".")[1] for s in namespaces)
    gates = sorted(
        s for s in names if re.fullmatch(r"[A-Z]\w*Prerequisite", s) and s not in NOT_GATES
    )
    triggers = sorted(
        s for s in names if re.fullmatch(r"[A-Z]\w*UnlockTrigger", s) and not s.startswith("IUn")
    )
    tutorials = sorted(
        {
            m.group(1)
            for s in names
            if (m := re.fullmatch(r"([A-Z]\w+?)TutorialFiber", s)) and not HELPER_VERB.match(s)
        }
    )
    settings = sorted(
        s
        for s in names | set(literals)
        if PROGRESSION.search(s)
        and re.fullmatch(r"[A-Z][A-Za-z0-9]+", s)
        and not HELPER_VERB.match(s)
        and len(s) < 60
    )
    return {
        "apk": apk.name,
        "metadata_version": version,
        "identifiers": len(names),
        "string_literals": len(literals),
        "namespace_prefix": prefix,
        "layers": dict(layers.most_common()),
        "systems": dict(sorted(systems.items())),
        "gates": {"prerequisite_kinds": gates, "unlock_triggers": triggers},
        "tutorials": tutorials,
        "progression_settings": settings,
        "notes": [
            "Each system is one namespace segment <prefix>.<layer>.<system>; the number is how "
            "many namespaces sit under it (Client and Common counted together).",
            "Names only: no values, code or art. Thresholds come from the game's servers.",
        ],
    }


def main() -> None:
    folder, prefix = Path(sys.argv[1]), sys.argv[2]
    out = summarize(folder / "base.apk", prefix)
    (folder / "systems.json").write_text(json.dumps(out, indent=1))
    print(
        f"metadata v{out['metadata_version']}: {len(out['systems'])} {prefix} systems, "
        f"{len(out['gates']['prerequisite_kinds'])} prerequisite kinds, "
        f"{len(out['tutorials'])} feature tutorials, "
        f"{len(out['progression_settings'])} progression settings"
    )


if __name__ == "__main__":
    main()
