from dataclasses import dataclass


@dataclass
class Config:
    camera: int = 0
    cam_width: int = 1280
    cam_height: int = 720

    # Part of the (mirrored) camera image that maps onto the whole screen.
    # Smaller box = less arm movement needed to reach the screen edges.
    active_x: tuple[float, float] = (0.15, 0.85)
    active_y: tuple[float, float] = (0.10, 0.75)

    # A gesture has to be seen for this many frames in a row before it takes effect.
    stable_frames: int = 3

    # Finger "curl" = sum of bend angles at the 3 joints, in degrees.
    extended_max: float = 65.0   # below this a finger counts as straight
    curled_min: float = 150.0    # above this a finger counts as folded into the palm
    cup_min: float = 55.0        # cupped hand: every finger bent between these
    cup_max: float = 175.0

    # How to click while in cursor mode:
    #   "pinch": touch thumb tip to index tip (cursor follows the index knuckle, which stays still)
    #   "thumb": point and pull the thumb out (cursor follows the index tip)
    click: str = "pinch"

    # Pinch = thumb tip to index tip distance / palm size.
    pinch_press: float = 0.25
    pinch_release: float = 0.40
    pinch_freeze_speed: float = 2.0   # ratio units per second

    # Thumb "pulled out" = thumb tip distance from index knuckle / palm size.
    thumb_press: float = 0.85
    thumb_release: float = 0.65
    # Freeze the cursor while the thumb is moving fast so a click doesn't drag it.
    thumb_freeze_speed: float = 2.5   # ratio units per second
    click_freeze_s: float = 0.15

    # Optional air tap: quick dip of the index finger.
    air_tap: bool = False
    tap_depth_deg: float = 25.0
    tap_max_s: float = 0.35

    rotate_gain: float = 1.6
    pan_gain: float = 1.3
    zoom_gain: float = 25.0        # wheel notches per screen height of hand travel
    zoom_invert: bool = False

    pause_hold_s: float = 1.0      # hold a fist this long to pause / resume

    # One Euro filter for the cursor (lower min_cutoff = smoother, beta = less lag on fast moves).
    filter_min_cutoff: float = 1.2
    filter_beta: float = 8.0

    debug: bool = False
