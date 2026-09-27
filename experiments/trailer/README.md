# GameTagger trailer

`web/trailer.mp4` (played on the site, poster `web/trailer-poster.jpg`): a silent, square (1080 x 1080) video of 54 seconds, for LinkedIn and
the site. It has six parts:

1. It started with the 40,000 hours of gameplay (1,000+ games) in NVIDIA's NitroGen dataset.
   Its game list seeded the catalog. No model was trained on it.
2. 189 gameplay attributes and 100 genres, each with a definition and the evidence allowed to
   prove it.
3. Claude (the Observer) describes screenshots and gameplay video without tagging.
4. Jev, by TypeSafe, decides: one question per tag, with a full four-way distribution (present,
   absent, not enough evidence, conflicting). The benchmark figures are real: a median of 192
   questions and 5.9 s per game, and 0.3¢ of Jev per game. It called 0.8% of Steam players'
   tags absent, against 5.9% for one big Claude prompt. "Not seen" never means "no".
5. When evidence is missing, the automated Android player plays the game and records shops,
   events and guild screens. A purchase screen is closed automatically.
6. The site shows what is in the top 100 (real figures from `web/index.html`).

The game screens are invented illustrations and are labelled as such. The counts come from
`taxonomy/`, Jev's figures from `experiments/jev-vs-legacy/results/`, and the top-100
figures from the published dashboard data.

Rebuild it with:

```
uv run python experiments/trailer/build.py --fonts fonts.css
```

`fonts.css` embeds Chivo and Chivo Mono as base64 @font-face rules, built from the
`@fontsource/chivo` and `@fontsource/chivo-mono` npm packages. Without it the system sans is
used.

Source for the NitroGen figures:
https://huggingface.co/nvidia/NitroGen and https://nitrogen.minedojo.org/
