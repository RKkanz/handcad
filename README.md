# handcad

**Webcam-only gesture navigation for CAD. Works on Wayland.**

Rotate, pan and zoom your model in Onshape by moving your hand in front of a laptop
camera. No Leap Motion, no SpaceMouse, no plugin. A transparent, click-through
overlay draws only the skeleton of your hand on top of the desktop, so you can see
your model through it.

- **CAD navigation, not just a cursor.** Hand shapes press the real SolidWorks-style
  mouse shortcuts, so it works in Onshape (and any app with that preset) without
  an add-in.
- **Works on Wayland.** Most webcam-mouse projects use PyAutoGUI, which can't move
  the cursor on Wayland (the default on current Ubuntu and Fedora). handcad
  creates a kernel-level virtual mouse instead, so it works on Wayland and X11.
- **See-through skeleton overlay** instead of a camera window. The drawn hand
  lines up with the cursor on screen.
- **Just a webcam.** Hand tracking runs locally on the CPU with MediaPipe.

Navigation follows the **SolidWorks** mouse scheme, which Onshape offers as a preset
(*My account → Preferences → Mouse controls → SolidWorks*):

| Hand | What it does | Mouse equivalent |
|---|---|---|
| ☝️ Point (index finger only) | Move the cursor | move |
| 🤏 Pinch thumb tip to index tip | Click; hold the pinch to drag | left button |
| 🤏 Pinch thumb tip to middle tip | Right click (context menu) | right button |
| 🤲 Cupped hand (as if holding a ball) | Rotate the part | middle drag |
| 🤟 Three fingers (index, middle, ring) | Pan / move the part | Ctrl + middle drag |
| ✌️ Two fingers, move up/down | Zoom | scroll wheel |
| ✋ Open hand | Nothing; reposition freely | — |
| ✊ Fist held for 1 s | Pause / resume (lets you use your real mouse) | — |

While pinching, the cursor follows your index knuckle rather than the fingertip,
because the knuckle stays still when the finger bends, so clicking doesn't move
the cursor. A ring around the cursor fills as you pinch (blue = left, orange = right)
and a ripple with "click" / "right click" shows each click.

Run `handcad --calibrate` once so clicks trigger at the right point for your hand.

Other click styles: `--click thumb` (point, then pull the thumb out like a finger
gun), and `--air-tap` (quick dip of the index finger).

## How it works

- **MediaPipe Hand Landmarker** finds 21 hand landmarks per camera frame.
- Gestures come from joint angles on MediaPipe's 3D "world" landmarks, so they
  don't depend on how far the hand is from the camera. A gesture must hold for 3
  frames before it takes effect, so passing through shapes doesn't trigger anything.
- The cursor is smoothed with a One Euro filter and freezes briefly while you
  pinch, so clicking doesn't knock the cursor off target.
- Mouse events go through **`/dev/uinput`** as a virtual absolute pointer, which
  works on Wayland. Rotate/pan press the middle button (and Ctrl) on the
  virtual devices, then move the cursor with your palm.
- The overlay is a PySide6 window running through XWayland, so GNOME keeps it on
  top and passes clicks through it.

## Setup (Ubuntu, GNOME on Wayland or X11)

```bash
git clone https://github.com/RKkanz/handcad && cd handcad
./scripts/setup.sh          # one time: uinput permission + libxcb-cursor0
uv venv -p 3.12 && uv pip install -e .
.venv/bin/handcad --calibrate   # ~10 s: fits the pinch-click thresholds to your hand
.venv/bin/handcad               # Ctrl+C in the terminal to quit
```

Flags: `--fps N` (max tracking rate, default 15; lower it on a slow laptop), `--debug` (shows finger curl / thumb values for tuning), `--dry-run`
(draws the skeleton without touching the mouse), `--air-tap`, `--invert-zoom`,
`--camera N`.

## Performance

Hand tracking costs about 30–45 ms of CPU per frame (MediaPipe's pip build has no
GPU path on Linux), so handcad limits how often it runs: 15 fps while tracking,
8 fps while paused, 4 fps with no hand in view. On a dual-core i5 that's roughly
45% of one core while tracking and 25% idle. Frames it skips are never decoded,
and the overlay only repaints the area around your hand.

## Tuning

Every threshold is in `handcad/config.py`; values saved by `--calibrate` (or added
by hand) in `~/.config/handcad/config.json` override them. Run with `--debug`, make each gesture,
and read the numbers at the top left:

- `index/middle/ring/pinky` = finger curl in degrees (straight ≈ 0–40, cupped ≈ 70–150, fist ≈ 200+)
- `pinch` / `rpinch` = thumb tip to index / middle tip distance (left / right click); click presses below `pinch_press` and releases above `pinch_release`
- `thumb` = (with `--click thumb`) thumb distance from the index knuckle; click presses above `thumb_press` and releases below `thumb_release`
- `raw` = the gesture detected in this frame, before debouncing

`active_x` / `active_y` sets the part of the camera image that maps to the whole
screen. Shrink it if reaching the screen edges takes too much arm movement.
