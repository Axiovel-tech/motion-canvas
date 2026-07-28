# Motion Canvas

![Motion Canvas screenshot](/doc/screenshot_small.jpg)

This repo contains [Motion Canvas](https://github.com/Axiovel-tech/motion-canvas),
Axiovel's professional drone show designer framework integrated into
[Blender](https://blender.org).

The output of Motion Canvas is a single `.skyc` file, which contains the
trajectories and light programs for all the drones in the show. `.skyc` files
are compiled and certified by the [Axio trajectory
engine](https://github.com/Axiovel-tech/axio-trajectory-engine) and executed by
the rest of the Axiovel stack, allowing you to preview, validate, verify,
analyze, plot and execute drone shows with a few clicks.

## Installation

Motion Canvas is distributed as a ZIP file that can be installed in Blender
according to the official
[Blender add-on guide](https://docs.blender.org/manual/en/latest/editors/preferences/addons.html).
This repository does not contain the ZIP version of the plugin or the
standalone executables but the _source code_ of the plugin; you can [build the
ZIP yourself](#building-the-plugin).

## Building the plugin

The build process is tested on macOS at the moment. It is very likely to work
on Linux as well. On Windows, you can try building inside Cygwin or Windows
Subsystem for Linux; the build script is written in `bash` so you will
definitely need an environment that provides `bash`.

The build script can be executed as follows:

```sh
bash etc/scripts/create_blender_dist.sh
```

When successful, the script creates the ZIP bundle of the addon in the `dist/`
folder.

## Development

If you want to modify the plugin and add your own functionality, the easiest is
to set up a folder that can be used directly as an entry in the Blender addon
path. This way you can modify the source code of the plugin without having to
build a ZIP after every modification.

First, run `uv install` in the root folder of the repository to install the
dependencies of the plugin.

Next, on Linux or macOS, you can run `etc/scripts/bootstrap.sh` to create a folder
named `dev/` within the repository. This folder sets up symbolic links in a
way that allows you to load the plugin directly if you add the `dev/` folder to
your Blender addon path. On Windows, you can achieve the same thing by running
`etc/scripts/bootstrap_windows.bat`.

Note that you might still need to exit Blender and restart it again if you
make a modification to the plugin code to ensure that your modifications are
picked up by Blender.

## Support

For any support questions please open an issue in the
[issue tracker](https://github.com/Axiovel-tech/motion-canvas/issues).

## About this fork

Motion Canvas is a fork of [Skybrush Studio for
Blender](https://github.com/skybrush-io/studio-blender) by CollMot Robotics
Ltd., maintained by Axiovel as free software under the same GPL license. It
defaults to the local Axio trajectory engine as its backend.

## License

Copyright 2020-2025 CollMot Robotics Ltd.
Copyright 2025-2026 Axiovel

Motion Canvas is free software: you can redistribute it and/or
modify it under the terms of the GNU General Public License as published by the
Free Software Foundation, either version 3 of the License, or (at your option)
any later version.

Motion Canvas is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for
more details.

You should have received a copy of the GNU General Public License along with
this program. If not, see <https://www.gnu.org/licenses/>.
