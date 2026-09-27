# Running the YouTube analyzer and the Android player on a Mac

Both tools run on your own Mac. YouTube refuses video downloads from cloud machines, and the
Android emulator runs on your computer. This guide assumes no prior setup.

## What each tool does

**YouTube analyzer.** It searches YouTube for gameplay videos of a game and downloads a
low-resolution copy of the most-watched ones (up to 15 minutes each). Then it samples the
video screen by screen:

* It looks at every second of the video for free and finds the distinct screens: menus, shops
  and dialogs that hold still, plus stretches of normal play.
* Only a short burst of frames from each distinct screen goes to Claude (the Observer) to
  describe, so a 15-minute video costs about the same as a store trailer.
* Jev then tags the game from those descriptions plus the store page.

**Android player.** Claude plays the game on an Android emulator while the screen is
recorded:

* It plays normally for the first 5 minutes.
* It then visits the shop, currency, event, social and upgrade screens, and watches one
  optional reward ad.
* The recording is tagged the same way as a YouTube video. Each moment is labelled with the
  screen the player was trying to reach, so shop screens are sure to be sampled.

Safety checks in the code, not only in Claude's instructions:

* A Google Play purchase screen is closed with the back button before Claude can act on it.
* Leaving the game (an ad's link, the Play Store, a sign-in sheet) is undone automatically.
* Typing is limited to a short player name.

Use a Google account **with no payment method** on the emulator anyway.

## One-time setup

1. **Get the code.** Open Terminal (press Cmd+Space, type Terminal) and paste:

   ```
   cd ~/"Claude Workspace/gametagger"
   git clone https://github.com/kpflynn82/gametagger repo
   cd repo
   ```

2. **Install the tools.** This needs Homebrew (https://brew.sh). Then paste:

   ```
   scripts/mac/setup.sh
   ```

3. **Keys.** The scripts read `~/Claude Workspace/gametagger/gametagger.env`. It holds your
   TypeSafe (Jev), Anthropic, Anthropic workspace ID and YouTube keys, plus
   `OBSERVER_MODEL=claude-sonnet-5`. The file sits outside the code folder, so it is never
   uploaded.

4. **For the Android player only**, set up the emulator:
   * Install Android Studio (https://developer.android.com/studio).
   * Open **Device Manager** and create a phone: a Pixel with a system image marked
     **Google Play** (arm64 on an Apple-silicon Mac).
   * Start it and sign in to the Play Store with a Google account that has **no payment
     method**.
   * Install the game you want to test from the Play Store on the emulator.

## Running

Every paid command shares one spending cap: **$2.00 in total** by default, booked in
`benchmark-runs/ledger.jsonl` in your copy of the code. For a different cap, put
`GAMETAGGER_BUDGET_USD=5` before the command.

**YouTube analyzer:**

```
scripts/mac/youtube.sh "Royal Match" --google-play com.dreamgames.royalmatch
scripts/mac/youtube.sh "Royal Match" --google-play com.dreamgames.royalmatch --dry-run
```

`--dry-run` downloads and samples the videos and shows the estimated cost without paying for
anything. `--videos 1` uses one video instead of two. Results go to
`gametagger-media/<game>/result.json`.

**Android player** (start the emulator first):

```
scripts/mac/android.sh com.dreamgames.royalmatch            # free check: is everything ready?
scripts/mac/android.sh com.dreamgames.royalmatch --play     # play 12 minutes, then tag
scripts/mac/android.sh com.dreamgames.royalmatch --play --minutes 6
```

If the game is not installed, the check opens its Play Store page on the emulator for you.
Press Ctrl+C to stop a session early; what was recorded so far is still saved. Results go to
`gametagger-play/<package>/<time>/`:

* `recording.mp4`: the screen recording.
* `steps.jsonl`: every action and why Claude took it.
* `screens/`: the screenshot Claude saw at each step.
* `session.json`: the summary: goals reached, safety events and cost.
* `result.json`: the tags.

## What it costs

These are estimates from list prices. The real figures are recorded per run.

| Step | Model | Rough cost |
|---|---|---|
| Android play, 12 minutes (about 150 actions) | Claude Sonnet 5 | $0.80–1.20 |
| Android play, 6 minutes | Claude Sonnet 5 | $0.40–0.60 |
| Describing one recording or YouTube video (10–12 bursts) | Claude Sonnet 5 | $0.10–0.20 |
| Jev tagging | jev-latest | under $0.01 |

For a first test inside $2, run one YouTube game and one 6-minute Android session.

## Good to know

* Downloading from YouTube is against YouTube's terms. It was approved as a proof of concept
  on September 27, 2026. Downloads stay in the git-ignored `gametagger-media/` folder.
* Some games' terms forbid automated play. Recordings and screenshots stay in the git-ignored
  `gametagger-play/` folder, and only descriptions and hashes go into results.
* The player's screen labels (shop, event, ...) are navigation context, not evidence. Jev is
  told so, and the Observer still describes the frames on its own.
* Claude Haiku 4.5 was tried as the player and sometimes returned an action that doesn't
  exist. Keep the player on Sonnet 5 (`--model` changes it).
