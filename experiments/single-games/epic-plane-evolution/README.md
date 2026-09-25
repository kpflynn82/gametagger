# Epic Plane Evolution: tag profile and clone brief

Voodoo · App Store ID 6504122823 · tagged 2026-09-25 with the Jev pipeline (claude-sonnet-5 describes the screenshots, jev-1.13.0 judges each attribute).
Evidence: the US App Store listing and its 6 screenshots. No Google Play listing or trailer could be found, so anything that only shows up in motion or on Google Play is under-evidenced (see "Gaps").
Cost: $0.055 for the Jev pipeline; the old one-prompt method was also run for comparison.

## The game in one paragraph (from the tags and screenshots)

A casual, free-to-play 3D flight game. You launch a plane (the store describes a slingshot-style launch), fly it with physics-based controls between city skyscrapers and over countryside, avoid crashing into buildings, and try to go as far as possible. Coins earned on each flight buy upgrades to the plane's parts, and the plane itself evolves through levels (the screenshots show a small propeller plane at level 1 growing into a larger airliner-style plane by level 20). Daily rewards and missions sit on top of the loop. The look is bright, stylized 3D with warm sunset skies.

## Core loop to clone

1. **Launch**: the store describes a slingshot-style launch; the screenshots show the plane starting on a runway, with "launch" as the first call to action.
2. **Fly**: physics-based flight through varied environments (city, countryside, even a cartoon house interior); obstacles such as buildings end the run.
3. **Score**: distance travelled is the goal ("how far can you go?").
4. **Earn and upgrade**: coins buy part upgrades that improve the next flight.
5. **Evolve**: the plane changes model as it levels up, which is the visible long-term progression.
6. **Come back**: daily rewards and missions.

## Genre

Jev **declined to name a primary genre**: not enough evidence 46%, Endless Runner 22%, Arcade / Score Attack 15%, Arcade Action 9%, Casual 6%. By family: casual/idle 49%, action 41%, racing 9%. In plain terms: a casual distance/upgrade game with arcade flight, sitting between endless runner and arcade score-attack. (The old one-prompt method on Opus picked "Physics Puzzle", then Arcade and Idle Game.)

## Present (strong evidence)

| Category | Tag | Probability | Definition |
|---|---|---|---|
| Gameplay elements | Strategy gameplay | 100% | Planning, positioning, resource allocation or tactical decisions are a substantial part of play. |
| Gameplay elements | Action gameplay | 99% | Reflexes, timing and real-time execution are a substantial part of the challenge. |
| Gameplay elements | Exploration gameplay | 86% | Discovering and traversing unknown places is a primary motivation of play. |
| Mechanics & systems | Upgrade system | 100% | The player improves weapons, abilities, vehicles, buildings or equipment over time. |
| Mechanics & systems | Drivable vehicles | 100% | The player drives, rides or pilots vehicles, mounts or craft. |
| Mechanics & systems | Physics-based interaction | 100% | Simulated physics such as momentum, weight or destruction is central to how actions play out. |
| Mechanics & systems | Quests and missions | 87% | The player takes on structured objectives such as quests, missions or contracts. |
| Social & live engagement | Daily rewards or quests | 100% | Incentives for logging in or playing every day. |
| Business model | Free to play | 100% | The game can be downloaded and played without an upfront purchase. |
| Setting | Urban environments | 91% | Much of the game takes place in cities or metropolitan environments. |
| Visual style & camera | 3D graphics | 94% | Gameplay is rendered primarily with three-dimensional graphics. |
| Visual style & camera | Stylized visual presentation | 90% | Gameplay visuals intentionally depart from photorealism through exaggerated shape language, color, proportion, materials, or illustration-like rendering. |
| Visual style & camera | Vibrant colours | 85% | A saturated, colourful palette dominates. |

## Likely present (weaker evidence: check before relying on these)

| Category | Tag | Probability | Definition |
|---|---|---|---|
| Gameplay elements | Simulation gameplay | 70% | Play models the rules of a real-world or fictional activity, system or lifestyle in detail. |
| Gameplay elements | Racing gameplay | 45% | Competing on speed and route navigation, usually in vehicles. |
| Gameplay elements | Role-playing gameplay | 44% | Character progression, stats, equipment/build choices, abilities, or role-playing systems materially shape player power and play style over time. |
| Mechanics & systems | Equipment and loadouts | 75% | Gear, weapons or loadouts the player equips change stats or play style. |
| Mechanics & systems | In-game economy and trading | 60% | The player buys, sells or trades using an in-game currency or market. |
| Mechanics & systems | Character customization | 50% | The player adjusts a character's appearance, class or attributes. |
| Narrative structure | Minimal or no story | 56% | The game has little or no authored plot; play is not organised around a story. |
| World structure | Linear levels or stages | 72% | Progression runs mainly through discrete, largely linear levels, stages or missions. |
| Setting | Rural or countryside environments | 62% | Much of the game takes place in villages, farmland or countryside. |
| Setting | Present-day setting | 50% | A contemporary, present-day world. |
| Tone & mood | Whimsical or lighthearted | 70% | A playful, charming or lighthearted atmosphere dominates. |
| Tone & mood | Horror tone | 52% | The game aims to frighten or disturb through atmosphere, threats or dread. |
| Protagonist | Non-human protagonist | 40% | The main playable character is an animal, robot, creature or other non-human. |
| Audience & content | Casual-friendly | 75% | Easy to pick up and suited to short or relaxed play sessions. |
| Audience & content | Family friendly | 56% | Suitable for children and family play. |

Treat these with care: **Horror tone** (52%) is probably a misreading of the dramatic sunset skies, and **Role-playing** (44%), **Racing** (45%), **Non-human protagonist** (40%) and **Character customization** (50%) are close to a coin flip.

## Absent (evidence says no)

| Category | Tag | Probability present | Definition |
|---|---|---|---|
| Business model | Premium purchase | 0% | A one-time purchase is required to play. |
| Visual style & camera | Realistic visual style | 8% | Gameplay rendering primarily pursues physically plausible proportions, materials, lighting, environments, and character depiction rather than overt abstraction or cartoon stylization. |
| Visual style & camera | Dark atmospheric visuals | 0% | Dim lighting, heavy shadow or a desaturated palette dominate. |
| Audience & content | Mature content | 0% | Intended for adults because of violence, sexual content, language or disturbing themes. |

## Gaps: important for a clone, but not decided from this evidence

- **Ads and in-app purchases**: "not enough evidence". The App Store data feed does not state them; Google Play shows "Contains ads / In-app purchases". For a Voodoo game, ads are almost certainly central to monetization.
- **Controls, session length, leaderboards, offline play, live events**: need gameplay in motion. Only still screenshots were available.

## How to sharpen this profile (cheap)

1. **Send the Google Play link** if the game is on Android: adds the store's monetization flags and more screenshots.
2. **Record 30 to 60 seconds of gameplay on your phone** and share the video: the pipeline samples six short clips from it and can then judge controls, timing, session structure and the ad/upgrade flow. Estimated extra cost: about 7 cents.

The full machine-readable profile (all 189 attributes with their four-way probabilities) is in `tags.json` beside this file.
