"""Automated Android play: device wrapper, agent contract, safety checks and session outputs.

Everything runs against fakes: no adb, emulator, network or model call is needed.
"""

from __future__ import annotations

import io
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from gametagger.comparison.budget import BudgetExceeded
from gametagger.genome.dossier import Dossier
from gametagger.play import cli as play_cli
from gametagger.play.agent import GOALS, PlayAgent, PlayerAction, model_image, to_device
from gametagger.play.device import AdbDevice, AdbError, Foreground, valid_package
from gametagger.play.session import PlayConfig, PlaySession

GAME = "com.example.game"


def png(color=(40, 120, 200), size=(1080, 1920), stripe=None) -> bytes:
    image = Image.new("RGB", size, color)
    if stripe is not None:  # make screens distinguishable to the average hash
        for x in range(size[0] // 2):
            for y in range(stripe * 100, stripe * 100 + 300):
                image.putpixel((x, y % size[1]), (250, 250, 250))
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


# --------------------------------------------------------------------------- adb wrapper


class FakeRun:
    def __init__(self, outputs):
        self.outputs, self.calls = outputs, []

    def __call__(self, cmd, capture_output=True, timeout=None):
        self.calls.append(cmd)
        key = " ".join(cmd[1:])
        for pattern, out in self.outputs.items():
            if pattern in key:
                return subprocess.CompletedProcess(cmd, 0, out, b"")
        return subprocess.CompletedProcess(cmd, 0, b"", b"")


def test_device_finds_the_only_emulator_and_builds_commands():
    run = FakeRun({"devices": b"List of devices attached\nemulator-5554\tdevice\n"})
    device = AdbDevice(adb="adb", run=run)
    assert device.serial == "emulator-5554"
    device.tap(10, 20)
    device.swipe(1, 2, 3, 4)
    device.back()
    device.type_text("Kev 42")
    assert run.calls[-4][-3:] == ["tap", "10", "20"]
    assert run.calls[-2][-1] == "KEYCODE_BACK"
    assert run.calls[-1][-1] == "Kev%s42"
    with pytest.raises(ValueError):
        device.type_text("hello everyone in chat!")
    with pytest.raises(ValueError):
        device.launch("not a package; rm -rf /")


def test_device_reports_missing_or_ambiguous_devices():
    with pytest.raises(AdbError, match="No Android device"):
        AdbDevice(adb="adb", run=FakeRun({"devices": b"List of devices attached\n\n"}))
    two = b"List of devices attached\nemulator-5554\tdevice\nR58M\tdevice\n"
    with pytest.raises(AdbError, match="--serial"):
        AdbDevice(adb="adb", run=FakeRun({"devices": two}))


def test_foreground_parses_dumpsys():
    dump = (
        b"  topResumedActivity=ActivityRecord{9f3 u0 com.android.vending/"
        b"com.google.android.finsky.billing.acquire.LockToPortraitUiActivity t12}\n"
    )
    run = FakeRun({"devices": b"x\nemulator-5554\tdevice\n", "dumpsys activity": dump})
    fg = AdbDevice(adb="adb", run=run).foreground()
    assert fg.package == "com.android.vending" and "billing" in fg.activity
    run = FakeRun(
        {
            "devices": b"x\nemulator-5554\tdevice\n",
            "dumpsys activity": b"  mResumedActivity: ActivityRecord{1 u0 "
            b"com.example.game/.Main t3}",
        }
    )
    assert AdbDevice(adb="adb", run=run).foreground().activity == "com.example.game.Main"


def test_package_names_are_validated():
    assert valid_package(GAME) == GAME
    for bad in ["game", "com.example.game && reboot", "1com.x"]:
        with pytest.raises(ValueError):
            valid_package(bad)


# --------------------------------------------------------------------------- agent


def test_actions_are_validated_and_mapped_to_pixels():
    assert PlayerAction(screen="shop", action="tap", x=500, y=1000, note="n").x == 500
    with pytest.raises(ValueError):
        PlayerAction(screen="shop", action="tap", note="missing point")
    with pytest.raises(ValueError):
        PlayerAction(screen="energy_system", action="back", note="unknown screen label")
    action = PlayerAction(screen="event", action="back", goals_reached=["event", "win"], note="")
    assert action.goals_reached == ["event"]
    assert to_device(0, 1080) == 0 and to_device(1000, 1080) == 1079
    jpeg, size = model_image(png())
    assert size == (1080, 1920)
    with Image.open(io.BytesIO(jpeg)) as image:
        assert max(image.size) == 1024 and image.format == "JPEG"


class FakeClient:
    """Answers each call with the next scripted act() input."""

    def __init__(self, answers):
        self.answers, self.requests = list(answers), []
        self.messages = self

    def create(self, **kwargs):
        self.requests.append(kwargs)
        answer = (
            self.answers.pop(0)
            if self.answers
            else {"screen": "gameplay", "action": "wait", "seconds": 5, "note": "waiting"}
        )
        if isinstance(answer, BaseException):
            raise answer
        content = (
            [SimpleNamespace(type="text", text="no tool")]
            if answer == "no-tool"
            else [SimpleNamespace(type="tool_use", name="act", input=answer)]
        )
        return SimpleNamespace(
            content=content, usage=SimpleNamespace(input_tokens=1500, output_tokens=80)
        )


def test_agent_sends_one_image_and_the_workspace_header():
    client = FakeClient([{"screen": "tutorial", "action": "tap", "x": 1, "y": 2, "note": "go"}])
    agent = PlayAgent(client, model="claude-sonnet-5", workspace_id="wrkspc_x")
    action = agent.decide(png(), "Minute 0.1")
    assert action.action == "tap" and agent.last_usage["input_tokens"] == 1500
    request = client.requests[0]
    blocks = request["messages"][0]["content"]
    assert [b["type"] for b in blocks] == ["image", "text"]
    assert request["extra_headers"] == {"anthropic-workspace-id": "wrkspc_x"}
    assert request["tool_choice"] == {"type": "tool", "name": "act"}
    assert "Never buy anything" in request["system"]


def test_agent_rejects_missing_or_malformed_tool_calls():
    agent = PlayAgent(
        FakeClient(["no-tool", {"screen": "shop", "action": "swipe", "x": 1, "y": 1, "note": ""}]),
        model="m",
    )
    with pytest.raises(ValueError, match="did not call"):
        agent.decide(png(), "")
    with pytest.raises(ValueError, match="Malformed"):
        agent.decide(png(), "")


# --------------------------------------------------------------------------- session


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class FakeDevice:
    model = "Pixel 8 (emulator)"

    def __init__(self, clock, foregrounds=None):
        self.clock = clock
        self.calls = []
        self.foregrounds = list(foregrounds or [])
        self.shots = 0

    def foreground(self):
        if self.foregrounds:
            return self.foregrounds.pop(0)
        return Foreground(GAME, f"{GAME}.Main")

    def screenshot(self):
        self.shots += 1
        self.clock.now += 0.5
        return png(stripe=self.shots % 7)

    def launch(self, package):
        self.calls.append(("launch", package))

    def back(self):
        self.calls.append(("back",))

    def tap(self, x, y):
        self.calls.append(("tap", x, y))

    def swipe(self, *args):
        self.calls.append(("swipe", *args))

    def long_press(self, x, y):
        self.calls.append(("long_press", x, y))

    def type_text(self, text):
        self.calls.append(("type", text))

    def info(self):
        return {"serial": "emulator-5554", "model": self.model, "android_version": "15"}


class FakeRecorder:
    def __init__(self, clock):
        self.clock, self.t0, self.error = clock, None, None

    def start(self):
        self.t0 = self.clock()

    def recording_time(self, wall):
        return wall - self.t0

    def stop(self, directory):
        directory.mkdir(parents=True, exist_ok=True)
        part = directory / "segment000.mp4"
        part.write_bytes(b"\x00\x00\x00\x18ftypmp42fake")
        return [part]


def fake_join(parts, output):
    output.write_bytes(b"".join(p.read_bytes() for p in parts))
    return output


def session(tmp_path, answers, *, config=None, foregrounds=None, record=True):
    clock = FakeClock()
    device = FakeDevice(clock, foregrounds)
    config = config or PlayConfig(
        package=GAME, title="Example", minutes=2, first_session_minutes=0.5
    )
    s = PlaySession(
        device,
        PlayAgent(FakeClient(answers), model="claude-sonnet-5"),
        config,
        tmp_path,
        recorder=FakeRecorder(clock) if record else None,
        joiner=fake_join,
        clock=clock,
        sleep=clock.sleep,
    )
    return s, device, clock


def act(screen, action="tap", **kw):
    base = {"screen": screen, "action": action, "note": f"{action} on {screen}"}
    if action == "tap":
        base.update(x=500, y=500)
    return {**base, **kw}


def test_session_plays_records_and_writes_a_taggable_dossier(tmp_path):
    answers = [act("tutorial")] * 3 + [act("gameplay", "wait", seconds=10)] * 2
    answers += [act("shop"), act("shop", "swipe", x=500, y=800, x2=500, y2=200), act("event")]
    answers += [act("social"), act("currency"), act("progression"), act("ad", "wait", seconds=5)]
    config = PlayConfig(package=GAME, title="Example", minutes=2, first_session_minutes=0.4)
    s, device, _ = session(tmp_path, answers, config=config)
    result = s.run()
    assert result.stop_reason == "all_goals_reached"
    assert set(result.goals_reached) == set(GOALS)
    assert ("tap", 540, 960) in device.calls  # 500/1000 of a 1080x1920 screen
    dossier = Dossier.model_validate_json(result.dossier_path.read_text())
    video = dossier.videos[0]
    assert video.role == "gameplay_recording" and video.capture_method == "automated_play"
    contexts = [c.context for c in video.capture_contexts]
    assert contexts[:2] == ["tutorial", "gameplay"] and "shop" in contexts
    assert contexts.count("shop") == 1  # consecutive shop steps merge into one segment
    starts = [c.start_seconds for c in video.capture_contexts]
    assert starts == sorted(starts)
    summary = json.loads((result.directory / "session.json").read_text())
    assert summary["goals_missed"] == [] and summary["model"] == "claude-sonnet-5"
    steps = [json.loads(line) for line in (result.directory / "steps.jsonl").open()]
    assert len(steps) == len(answers) and steps[0]["phase"] == "first session"
    assert len(list((result.directory / "screens").glob("*.jpg"))) == len(answers)


def test_goals_seen_during_the_first_session_do_not_count(tmp_path):
    config = PlayConfig(package=GAME, minutes=1, first_session_minutes=0.9, max_steps=3)
    s, _, _ = session(tmp_path, [act("shop", goals_reached=["shop"])] * 3, config=config)
    result = s.run()
    assert result.goals_reached == {} and result.stop_reason == "max_steps"


def test_purchase_screens_are_closed_before_the_agent_acts(tmp_path):
    billing = Foreground(
        "com.android.vending", "com.google.android.finsky.billing.PurchaseActivity"
    )
    proxy = Foreground(GAME, "com.android.billingclient.api.ProxyBillingActivity")
    config = PlayConfig(package=GAME, minutes=1, first_session_minutes=0.5, max_steps=3)
    s, device, _ = session(
        tmp_path,
        [act("shop")] * 3,
        config=config,
        foregrounds=[billing, Foreground(GAME, "x"), proxy],
    )
    result = s.run()
    assert device.calls.count(("back",)) == 4  # two backs per purchase screen
    events = [e for step in result.steps for e in step.events]
    assert len(events) == 2 and all(e.startswith("purchase_screen_closed") for e in events)


def test_leaving_the_game_is_undone_with_back_then_relaunch(tmp_path):
    chrome = Foreground("com.android.chrome", "org.chromium.chrome.browser.ChromeTabbedActivity")
    config = PlayConfig(package=GAME, minutes=1, first_session_minutes=0.5, max_steps=3)
    s, device, _ = session(
        tmp_path, [act("ad", "back")] * 3, config=config, foregrounds=[chrome] * 6
    )
    result = s.run()
    events = [e for step in result.steps for e in step.events]
    assert events[0].startswith("left_game_back") and any("relaunched_game" in e for e in events)
    assert device.calls.count(("launch", GAME)) == 2  # the start, plus one relaunch


def test_permission_dialogs_are_left_to_the_agent(tmp_path):
    ask = Foreground("com.google.android.permissioncontroller", "GrantPermissionsActivity")
    config = PlayConfig(package=GAME, minutes=1, first_session_minutes=0.5, max_steps=1)
    s, device, _ = session(tmp_path, [act("other")], config=config, foregrounds=[ask])
    s.run()
    assert ("back",) not in device.calls


def test_budget_stop_and_model_errors_still_write_results(tmp_path):
    s, _, _ = session(tmp_path, [act("tutorial"), BudgetExceeded("cap reached")])
    result = s.run()
    assert result.stop_reason == "budget" and result.dossier_path.exists()
    malformed = [{"screen": "shop", "action": "tap", "note": "no point"}] * 5
    s, _, _ = session(tmp_path / "b", malformed)
    result = s.run()
    assert result.stop_reason == "model_errors" and all(st.error for st in result.steps)


def test_without_a_recording_distinct_screenshots_become_evidence(tmp_path):
    config = PlayConfig(
        package=GAME, minutes=1, first_session_minutes=0.5, max_steps=6, record=False
    )
    s, _, _ = session(tmp_path, [act("gameplay")] * 6, config=config, record=False)
    result = s.run()
    dossier = Dossier.model_validate_json(result.dossier_path.read_text())
    assert not dossier.videos and 1 < len(dossier.images) <= 12
    assert all((result.directory / i.path).exists() for i in dossier.images)


def test_config_limits():
    with pytest.raises(ValueError):
        PlayConfig(package=GAME, minutes=20)
    with pytest.raises(ValueError):
        PlayConfig(package=GAME, minutes=5, first_session_minutes=5)


def test_recorded_dossier_loads_in_the_genome_cli(tmp_path, monkeypatch, capsys):
    from gametagger.genome import cli as genome_cli

    s, _, _ = session(tmp_path, [act("tutorial")] * 2)
    result = s.run()
    args = genome_cli.build_parser().parse_args([str(result.dossier_path)])
    dossier = genome_cli.assemble_dossier(args, genome_cli.build_parser())
    assert Path(dossier.videos[0].path).is_absolute() and Path(dossier.videos[0].path).exists()


# --------------------------------------------------------------------------- CLI


def test_cli_check_reports_plainly_and_opens_the_store_when_missing(monkeypatch, capsys):
    opened = []

    class Dev:
        def __init__(self, serial=None):
            pass

        def info(self):
            return {"serial": "emulator-5554", "model": "sdk_gphone64", "android_version": "15"}

        def screenshot(self):
            return png()

        def is_installed(self, package):
            return False

        def open_store_page(self, package):
            opened.append(package)

    monkeypatch.setattr(play_cli, "AdbDevice", Dev)
    monkeypatch.setattr(play_cli, "anthropic_api_key", lambda: None)
    with pytest.raises(SystemExit) as exit_:
        play_cli.main([GAME, "--check"])
    out = capsys.readouterr().out
    assert exit_.value.code == 1 and opened == [GAME]
    assert "NOT installed" in out and "Claude key: MISSING" in out and "Not ready" in out


def test_cli_refuses_a_live_session_without_a_budget(monkeypatch):
    monkeypatch.setattr(play_cli, "AdbDevice", lambda serial=None: object())
    with pytest.raises(SystemExit) as exit_:
        play_cli.main([GAME])
    assert exit_.value.code == 2


def test_recorder_maps_session_time_onto_the_joined_recording():
    from gametagger.play.device import RecordedSegment, ScreenRecorder

    recorder = ScreenRecorder(SimpleNamespace(), clock=lambda: 500.0)
    recorder.segments = [
        RecordedSegment("a", started=100.0, ended=270.0),
        RecordedSegment("b", started=270.5, ended=400.0),
    ]
    assert recorder.recording_time(150.0) == pytest.approx(50.0)
    assert recorder.recording_time(300.5) == pytest.approx(170.0 + 30.0)
    assert recorder.recording_time(50.0) is None


@pytest.mark.skipif(not __import__("shutil").which("ffmpeg"), reason="Local FFmpeg unavailable")
def test_joined_recording_is_constant_rate_and_sampleable(tmp_path):
    from gametagger.genome.dossier import VideoSource
    from gametagger.genome.systems import systems_bursts
    from gametagger.play.device import join_recording

    parts = []
    for n, source in enumerate(["testsrc=size=720x1280:rate=3", "smptebars=size=720x1280:rate=1"]):
        part = tmp_path / f"segment{n:03d}.mp4"
        subprocess.run(
            ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", source, "-t", "12",
             "-pix_fmt", "yuv420p", "-c:v", "libx264", str(part)],
            check=True, timeout=60,
        )  # fmt: skip
        parts.append(part)
    out = join_recording(parts, tmp_path / "recording.mp4")
    video = VideoSource(id="android-play", path=str(out), role="gameplay_recording")
    bursts = systems_bursts(video, tmp_path / "frames", windows=4, frames=4)
    assert bursts  # a 1-frame-a-second still stretch still yields bursts at 10 fps
    for _window, frames, _context in bursts:
        with Image.open(io.BytesIO(frames[0])) as image:
            assert max(image.size) <= 640
