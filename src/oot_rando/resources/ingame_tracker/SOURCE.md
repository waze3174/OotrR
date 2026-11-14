# The in-game tracker module (`subsdk7`)

`subsdk7` is a prebuilt Horizon module (NSO) for Ocarina of Time (Switch 2, program id 0400486024DEC000). The
application copies it into each seed it generates, as `exefs/subsdk7`, so the game loads it while that seed is enabled.
It draws the in-game randomizer tracker (R + right stick up) from `romfs/RandoTracker/seed.trk`, and its postcard (a small card with the icons in a corner of the screen), whose settings it keeps in `ootrTracker/postcard.cfg` on the SD card.

It is **not** part of this application's MIT licence: it is free software under the GNU General Public License,
version 3 or later (the text is in `LICENSE` here), built from [ocarinaMIDI](https://github.com/waze3174/ocarinaMIDI) and
[sloperinaGZ](https://github.com/PracticeROM/sloperina)'s GPL-3 code.

- Source: the `ingame_tracker/` folder of this repository (GPL-3, with its own `LICENSE`)
- Commit: `4d9da98` (module version 0.3.0)
- Built with devkitA64: `make ship` in `ingame_tracker/` at that commit (it embeds `0.3.0 (v0.5.2-43-g4d9da98)`); the build is
  the same from any folder, so `make PACKAGE_VERSION="0.3.0 (v0.5.2-43-g4d9da98)"` there gives this binary again
- sha256 of `subsdk7`: `ad34464b2e696163bf9e1ef679ac851b556f53bf8ffecf95282ee7490c5eb511` (81,854 bytes)

The source of this exact binary is that folder at the commit above. To change the module, change it there, run `make ship` in that
folder (it copies the new build here and prints its checksum and size), and update this file's commit and checksum (the tests check
that the checksum matches the binary).
