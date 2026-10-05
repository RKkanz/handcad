#!/usr/bin/env bash
# One-time system setup (Ubuntu / GNOME).
#  - lets the logged-in desktop user create virtual input devices (/dev/uinput) without root
#  - installs the X11 cursor lib Qt needs to draw the overlay through XWayland
# Undo: sudo rm /etc/udev/rules.d/70-handcad-uinput.rules
set -euo pipefail

sudo apt-get install -y libxcb-cursor0

# "uaccess" grants access to the user at the physical seat only, scoped to /dev/uinput
# (unlike joining the `input` group, which would also expose keyboard events).
echo 'KERNEL=="uinput", SUBSYSTEM=="misc", TAG+="uaccess", OPTIONS+="static_node=uinput"' \
  | sudo tee /etc/udev/rules.d/70-handcad-uinput.rules >/dev/null
sudo udevadm control --reload-rules
sudo udevadm trigger --name-match=uinput

if [ -w /dev/uinput ]; then
  echo "Done: /dev/uinput is writable."
else
  echo "Rule installed. Log out and back in if /dev/uinput is still not writable."
fi
