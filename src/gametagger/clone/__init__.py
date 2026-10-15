"""Turn a teardown blueprint into a buildable clone: a spec, a web skeleton, and a Codex art brief.

The split, the same one that worked on the dragon prototype:

* **Claude** owns mechanics: the core loop, economy numbers, unlock order, screen flow and the
  directions (reskin, loop changes, an added mechanic). That lives in the ``CloneSpec`` and the
  scaffolded code.
* **Codex** owns art: it reads ``ART_BRIEF.md`` and ``assets/MANIFEST.json`` from the repo and
  generates assets that drop straight into ``assets/`` by name and size.

The two meet in the git repo -- there is no account link between them; sharing the repo is the
sync. See ``docs/RADAR_V3_PLAN.md``.
"""

from gametagger.clone.scaffold import scaffold_clone
from gametagger.clone.spec import ArtAsset, CloneSpec

__all__ = ["CloneSpec", "ArtAsset", "scaffold_clone"]
