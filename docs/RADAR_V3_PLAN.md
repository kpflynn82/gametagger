# GameTagger v3: the soft-launch radar and clone pipeline

October 14, 2026. This plan is a new direction for GameTagger, agreed with the owner. It keeps
everything the catalogue already does (tagging the US top grossers, the weekly digest, the APK
kit/code-name reader, the automated player) and adds a pipeline that turns all of it into a single
morning habit: **wake up to a short list of test-market games that are monetizing unusually well,
each with a concrete "here's how we'd build a fairer, differentiated version -- shall I?" The owner
taps yes on one, and the system tears it down, writes a blueprint, and scaffolds a prototype.**

It follows the architecture rules in `AGENTS.md` and the plan-of-record convention in `CLAUDE.md`.

## The north star (the owner's own words)

> I wake up with you saying: there's a new action RPG called *Heroes of the Wall*, using a unique
> social-tournament system that seems popular. It's also using a theme not common in action RPGs.
> Based on recent hits there's an opportunity to differentiate it with a dragon theme and an added
> gacha mechanic. Should I build a prototype with these changes?

Everything below exists to produce that one message, backed by evidence, every morning.

## The pipeline, end to end

```
  (1) RADAR            (2) DEEP DIVE          (3) BLUEPRINT        (4) CLONE          (5) IMPROVE
  read CA/AU/NZ   -->  acquire + play    -->  GDD from the   -->  web prototype -->  digest + genome
  charts, score        + read the APK         teardown            (Codex art)        suggestions
  the money signal     (owner one-tap)        (game-designer)     + Unity later      (fair / revenue)
       |                     |                     |                   |                   |
   cloud, free          Mac, ~1/week          cloud, free         Mac + cloud         cloud, free
   daily                owner-approved                             Claude+Codex
```

Each stage is independent: the radar is useful on its own; a deep dive can run without a clone; the
improvement pass can re-run on any existing clone.

### Stage 1 -- Radar (BUILT in this PR)

**What it does.** Every morning, reads the top-grossing and top-free charts in the three common
mobile soft-launch markets -- Canada, Australia, New Zealand -- and scores every game on four
transparent signals, then sends one push and writes a ranked shortlist.

- **Monetization fingerprint `[the core idea]`.** A high grossing rank paired with a weak or absent
  download (top-free) rank. Earning a lot on few installs is the signature of a strong monetization
  system -- exactly what is worth tearing down. A game that grosses #15 but isn't in the top 60
  downloads scores far above one that grosses #15 and downloads #10.
- **Soft-launch.** Present in the test markets, absent from the US, and spread across more than one
  test market -- the pattern of a studio testing before a wider launch.
- **Novelty.** Not already in GameTagger's catalogue of 218 tagged US top grossers, so it's something
  we haven't already studied.
- **Trend fit.** Its apparent genre or mechanics match what the **weekly digest** currently says is
  hot (hybrid-casual, merge, collection albums, social competition, ...).

The score is a weighted blend (default 40/25/20/15) and every number carries a plain-language
reason, so the morning card can say *why*, not just a number. Weights are data the owner can retune.

**Where the digest plugs in (BUILT).** The weekly digest already runs as a scheduled task and
writes `claude/trend-digest-*.md`. `radar/digest.py` reads the newest such file and scores a fixed
mobile-game vocabulary (merge, collection albums, social tournaments, gacha, season pass, ...) by
how much that week's digest talks about each, producing the `{term: weight}` map the trend-fit
signal uses and that biases which fresh mechanic the build proposal suggests. It is deterministic
(no model call) so the wire works when run by hand; a scheduled run may still replace it with a
richer model extraction. Use it with `gametagger-radar scan --digest <folder-or-file>`. (Setup note
below: the digest task must still drop a copy where this session can read it.)

**Cost and safety.** Zero paid model calls, zero downloads. The radar only reads public chart
positions. Sources: AppBrain's per-country Google Play pages (Canada, Australia) and Apple's free
RSS feed (Canada, Australia, **and** New Zealand -- AppBrain has no NZ page, Apple does). Both are
already on the `genome.net` allowlist.

**Run it.**
```
gametagger-radar scan --live                                   # read CA/AU/NZ now, free
gametagger-radar scan --charts-file experiments/radar/demo-charts.json \
  --hints experiments/radar/demo-hints.json --root .           # score a saved reading (demo)
gametagger-radar approve gp-com.studio.heroesofthewall         # one-tap: queue a deep dive
```

### Stage 2 -- Deep dive (owner-approved, runs on the Mac; reuses existing tools)

When the owner approves a game, the Mac-side teardown runs with the tools the October APK pilot and
the automated player already built:

- **Acquire the build.** Soft-launch games usually aren't in the US store, and Google only lets an
  account switch country if you're physically there with a local payment method, so the US test
  account can't just install them. Decision (owner): download the build from a public APK mirror
  (APKPure) with EFF's `apkeep`, and **keep it only if its signing certificate matches the key the
  studio's already-published games are signed with** (`apksigner verify --print-certs`, compared to a
  known-good reference). A signature match means it's the studio's real, unmodified build; a mismatch
  means it's repackaged and it's discarded. The build is only ever run inside the emulator.
- **Read what's readable `[existing: apk-pilot]`.** Ad/mediation kits, engine, and -- for Unity
  IL2CPP and similar -- the unencrypted code-symbol names that reveal the game's systems, their
  gating rules (net worth, boards, level, tutorial done, event active) and which feature each
  tutorial introduces. No decryption, no rooting, no intercepting the game's server traffic -- the
  same line the APK pilot drew.
- **Play it `[existing: gametagger-play]`.** The automated player plays as a guest (never signs in,
  connects Facebook, invites, or spends), records the screen, logs the new-player flow screen by
  screen, and samples shop/event/offer screens. Purchase screens are closed with back.

### Stage 3 -- Blueprint / GDD (cloud, free; reuses the `game-designer` skill)

The teardown's measurements (genome tags, economy numbers, unlock ladder, FTUE script, ad timeline)
feed the existing **`game-designer` skill in GDD mode**, which already knows the project's fair-vs-dark
table and the 95/5 rule. Output: `gdd-<game>.md` -- a build-ready blueprint with the keep/drop/replace
pass done, economy in tables, and the `[KEVIN CALL]` decisions surfaced. This is the "blueprint to
build a clone" from the brief; it's the input to Stage 4.

### Stage 4 -- Clone (BUILT in this PR: the scaffold + Codex handoff)

From the blueprint (or straight from a radar proposal for a fast gray-box), `gametagger-clone`
emits a buildable web prototype and the art handoff:

- **Web prototype first, Unity for the final build** (owner's call). `gametagger-clone` picks the web
  engine by genre -- Phaser for 2D (puzzle, RPG, strategy, sim), three.js for 3D (flight, racing) --
  and writes a runnable skeleton that boots in a phone browser, lists the loop and screens, and loads
  art as it appears. `Hoard & Hatch` and `Fold & Fly` already prove this web-prototype path. The
  skeleton's README states Unity is the shipping target; the web build is for proving loop and feel.
- **Mechanics = Claude, art = Codex.** The scaffold writes `DIRECTIONS.md` (reskin, systems to keep,
  mechanics to add, Kevin's notes, economy) and `ART_BRIEF.md` + `assets/MANIFEST.json` -- an exact,
  named, sized asset list for Codex to generate against. **The two meet in the git repo; there is no
  account link between Claude and Codex, and none is needed** (see "Codex" below). This is the same
  split that worked on the dragon prototype.
- **Directions.** "Match it faithfully" is the default; the owner can also say "dragon theme",
  "change the second loop", "add gacha" -- these become `DIRECTIONS.md` entries and change set.

### Stage 5 -- Improvement suggestions (cloud, free; labeled both ways)

Suggestions come from two places: patterns across the tagged genome (what the current top grossers in
this genre do that the target doesn't) and the weekly digest (what's trending). Decision (owner):
**each suggestion is shown with both an expected effect on retention/revenue and on player fairness,
labeled, so the owner chooses** -- not fair-by-default, not revenue-maximizing. The radar's build
proposal is the first, lightweight instance of this (it already suggests a differentiating theme +
mechanic); the full pass runs against a finished clone.

## Codex for art -- how the hand-off and "account sync" actually work

There is no direct link between a Claude account and a Codex/OpenAI account, and the pipeline doesn't
need one. **The sync point is the private GitHub repo**, exactly as on dragongo:

1. Claude (this pipeline) writes the prototype code and `ART_BRIEF.md` + `assets/MANIFEST.json` and
   commits them.
2. Codex is pointed at the repo (either run locally on the Mac against the checkout, or given access
   to the private repo). It reads the brief, generates the named assets, and commits them to
   `assets/`.
3. The skeleton loads assets by the manifest names, so no code change is needed when art lands.

So "syncing accounts" = giving Codex access to the same private repo (add it as a collaborator, or
just run Codex locally where the repo is checked out). Nothing else to connect.

## Where the outputs live (owner's call: private repo for all)

The `gametagger` repo is **public**. GDDs and clones describe other studios' games in detail, so
(owner's decision) the radar picks, deep dives, blueprints and clones go in a **new private repo**
(suggested `kpflynn82/gametagger-intel`). The tools stay in the public repo. One setup step is needed
(the owner creates the private repo -- about a minute -- since this session can't create repos). Until
it exists, outputs can land in the owner's Google Drive, which the scheduled tasks already use.

## Legal and "reverse engineer everything" -- the boundary

- **Clones copy how a game works, not how it looks.** Systems, economy numbers, progression, unlock
  order and tutorial pacing are the copyable part (the owner's lawyers confirmed economy/progression
  aren't protected). The clone ships **original** art, characters, names, text, audio and levels.
  Copying the look is where cloners lose (Tetris v. Xio, 2012) and where stores reject copycats.
- **"Reverse engineer everything" = read what's readable.** Ad kits, engine, unencrypted code symbol
  names, shared files -- the APK pilot's established line. No decryption, no rooting, no intercepting
  server traffic. Signature-verified mirror downloads are an interoperability/competitive-analysis
  step, not circumvention.

## What this PR delivers

- `src/gametagger/radar/` -- the full radar: multi-region chart reading (`charts_multi.py`), the
  signal scorer (`signals.py`), candidate assembly with cross-store de-duplication (`candidate.py`),
  the catalogue loader for novelty (`catalogue.py`), the digest trend map (`trends.py`), the
  digest-markdown parser that builds that map from the weekly digest (`digest.py`), the morning
  brief + build proposal (`brief.py`), and the `gametagger-radar` CLI (`cli.py`).
- `src/gametagger/clone/` -- `CloneSpec` (`spec.py`), the web-skeleton + Codex-handoff generator
  (`scaffold.py`) and the `gametagger-clone` CLI (`cli.py`).
- `experiments/radar/demo-charts.json` + `demo-hints.json` -- a runnable example (the Heroes of the
  Wall scenario) so the CLI works out of the box.
- Tests: `tests/test_radar_signals.py`, `test_radar_brief.py`, `test_radar_charts.py`,
  `test_clone_scaffold.py` (22 new tests; whole suite green, lint/format clean).

All offline. No paid calls, no downloads, no taxonomy changes.

## Owner decisions / next steps

1. **Create the private repo** (`kpflynn82/gametagger-intel` or a name you prefer) for the intel
   outputs, or say "use Google Drive for now".
2. **Wire the digest to the radar:** the parser is built (`digest.py`, `--digest`); the one remaining
   step is to have the weekly digest task also drop a copy of `trend-digest-*.md` where a scheduled
   radar run can read it (a committed file in the intel repo, or a Drive doc it fetches). Then schedule
   `gametagger-radar scan --live --digest <that location>` as a daily cloud task (like the digest and
   job-search tasks) with a push.
3. **Confirm the acquisition rule** (mirror download + signature match, emulator-only) before the first
   real deep dive, and point me at one already-published game from each target studio as the signature
   reference.
4. **A first live radar run** to tune the weights and the priority bar against real CA/AU/NZ charts.

## Confidence

`[BUILT]` radar scoring, brief, clone scaffold, cross-store merge, CLIs, tests. `[EXISTING]` deep-dive
tools (apk-pilot, gametagger-play), the game-designer GDD skill, the weekly digest. `[PENDING]` the
daily schedule, the digest-to-radar wire, the private repo, and the first live run's weight tuning.
