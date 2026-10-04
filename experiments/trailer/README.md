# GameTagger trailer

`web/trailer.mp4` (played on the site, poster `web/trailer-poster.jpg`): a silent, square
(1080 x 1080) video of about 82 seconds, for LinkedIn and the site. It has ten parts. The first
five show how the tag database was built and how tags are assigned; the last five show the newer
loop: play a game, learn what makes it work, and build a playable prototype.

1. It started with the 40,000 hours of gameplay (1,000+ games) in NVIDIA's NitroGen dataset.
   Its game list seeded the catalog. No model was trained on it.
2. 189 gameplay attributes and 100 genres, each with a definition and the evidence allowed to
   prove it.
3. Claude (the Observer) describes screenshots and gameplay video without tagging.
4. Jev, by TypeSafe, decides: one question per tag, with a full four-way distribution (present,
   absent, not enough evidence, conflicting). The benchmark figures are real: a median of 192
   questions and 5.9 s per game, and 0.3¢ of Jev per game. It called 0.8% of Steam players'
   tags absent, against 5.9% for one big Claude prompt. "Not seen" never means "no".
5. The site shows what is in the top 100 (real figures from `web/index.html`).
6. **Play.** Store pages leave gaps, so an AI player plays the game on an Android emulator. The
   example is a slingshot plane game (Epic Plane Evolution, not named in the video): 13.2 hours
   of play; in the first 8 hours, 159 flights and 154 forced ads. The notes on screen are the
   AI player's own, trimmed.
7. **Learn.** The store page's tags for that game (real Jev output, from
   `experiments/single-games/epic-plane-evolution/tags.json`) next to what playing measured:
   "Ad-supported" and "Energy or stamina timers" were "not enough evidence" from the store page;
   playing measured 0.97 forced ads per flight and a 5-flight energy limit. Then the core loop
   and a keep / drop / replace pass.
8. **Build.** Real footage of the prototype, Fold & Fly: the hangar, the slingshot, the valley
   course, a finish line, the harbour town with rocket jets, and all six planes. First playable
   overnight; bot-player simulations give 1 forced ad in 9 flights (11% of the original) and
   the first new plane in about 25 minutes.
9. The pitch: spot a game climbing the charts, play it, learn what makes it work, build a
   prototype. "Find out if a feature is fun before you staff a team."
10. End card.

## The 30-second cut

`web/linkedin/trailer-30s.mp4` (thumbnail `trailer-30s-thumbnail.jpg`), for a LinkedIn post on
game discovery: `build.py --cut highlight`. Four new cards, then parts of the Play and Build
scenes, then an end card:

1. Royal Match's studio, Dream Games: about $1.5bn of revenue in 2023 and about $1bn spent on
   marketing and distribution (its 2023 UK accounts as reported by the Financial Times, via
   MenaBytes).
2. About 190,000 new mobile games released in 2025; 2,500 passed 500,000 downloads in their
   first year (Moloco, via PocketGamer.biz, August 2026).
3. A Google Play listing gets one category and up to five tags, picked by the developer
   (Google Play Console Help), against 189 gameplay questions per game here.
4. From store pages and trailers, GameTagger could not settle ads for 28 and energy timers for
   47 of the Google Play top 50 grossing (computed from `web/index.html` at build time).

## Sources and honesty rules

* The original game's screens (part 6) are invented illustrations drawn in code (`games.js`
  and `scene.html`), labelled as such. No store screenshots, trailers, ads or logos are used,
  and the original game is not named. Screenshots from the AI player's run are third-party
  content and are never used or committed.
* The AI player's figures were measured by the teardown player (a separate project) on
  Sept 28-29, 2026; see the Fold & Fly entries in `docs/EXECUTION_STATUS.md`. From about hour
  8, two copies of the player wrote into the same run, so the per-flight figures use the first
  8 hours only. Model calls for the whole run cost $6.95 paid plus $76.69 of subscription calls
  at API prices (about $84).
* The prototype figures marked "simulated" come from Fold & Fly's bot players
  (`node sim/sim.mjs`, 6 players), not from people.
* The prototype footage (`footage/prototype.mp4`, 390 x 844, 30 fps, 3.6 MB) is our own
  game with CC0 models (Kenney, Quaternius) and OFL fonts (Lilita One, Atkinson Hyperlegible).
  `footage/prototype.json` lists where each clip starts and the taps to draw over it.

## Rebuilding

```
uv run python experiments/trailer/build.py --fonts fonts.css
uv run python experiments/trailer/build.py --fonts fonts.css --still 33,45,60   # stills only
```

`fonts.css` embeds Chivo, Chivo Mono, Fredoka and Lilita One as base64 @font-face rules, built
from the `@fontsource/chivo`, `@fontsource/chivo-mono`, `@fontsource/fredoka` and
`@fontsource/lilita-one` npm packages. Without it the system sans is used.

To re-record the prototype footage, in a Fold & Fly checkout:

```
npm install
node scripts/page.mjs && node scripts/trailer-clips.mjs shots/trailer
cp shots/trailer/prototype.mp4 shots/trailer/prototype.json <gametagger>/experiments/trailer/footage/
```

The recorder runs the game on a virtual clock (timers, animation frames and CSS animations),
so each frame is exactly 1/30 s after the last however slow the headless renderer is. The edit
(which part of each clip is used) is `BUILD["edit"]` in `build.py`.

Source for the NitroGen figures:
https://huggingface.co/nvidia/NitroGen and https://nitrogen.minedojo.org/
