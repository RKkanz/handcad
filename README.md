# handcad

Control your mouse and CAD navigation with one hand and a webcam. A transparent,
click-through overlay draws only the skeleton of your hand on top of the desktop,
so you can see everything behind it.

Navigation follows the **SolidWorks** mouse scheme, which Onshape offers as a preset
(*My account → Preferences → Mouse controls → SolidWorks*):

| Hand | What it does | Mouse equivalent |
|---|---|---|
| ☝️ Point (index finger only) | Move the cursor (the fingertip *is* the cursor) | move |
| ☝️ + pull your thumb out | Click; keep the thumb out to drag, tuck it back in to release | left button |
| 🤲 Cupped hand (as if holding a ball) | Rotate the part | middle drag |
| 🤟 Three fingers (index, middle, ring) | Pan / move the part | Ctrl + middle drag |
| ✌️ Two fingers, move up/down | Zoom | scroll wheel |
| ✋ Open hand | Nothing; reposition freely | — |
| ✊ Fist held for 1 s | Pause / resume (lets you use your real mouse) | — |

Optional: `--air-tap` also clicks when you make a quick dip of your index finger.

## How it works

- **MediaPipe Hand Landmarker** finds 21 hand landmarks per camera frame.
- Gestures come from joint angles on MediaPipe's 3D "world" landmarks, so they
  don't depend on how far the hand is from the camera. A gesture must hold for 3
  frames before it takes effect, so passing through shapes doesn't trigger anything.
- The cursor is smoothed with a One Euro filter and freezes briefly while your
  thumb clicks, so clicking doesn't knock the cursor off target.
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
.venv/bin/handcad           # Ctrl+C in the terminal to quit
```

Flags: `--debug` (shows finger curl / thumb values for tuning), `--dry-run`
(draws the skeleton without touching the mouse), `--air-tap`, `--invert-zoom`,
`--camera N`.

## Tuning

Every threshold is in `handcad/config.py`. Run with `--debug`, make each gesture,
and read the numbers at the top left:

- `index/middle/ring/pinky` = finger curl in degrees (straight ≈ 0–40, cupped ≈ 70–150, fist ≈ 200+)
- `thumb` = thumb distance from the index knuckle; click presses above `thumb_press` and releases below `thumb_release`
- `raw` = the gesture detected in this frame, before debouncing

`active_x` / `active_y` sets the part of the camera image that maps to the whole
screen. Shrink it if reaching the screen edges takes too much arm movement.
