#!/bin/bash
#
# Bootstrap script for the repository to set up a dev/ folder inside the repo
# that can pose as a Blender addon path.
#
# You should run the script without any arguments, unless you have access
# to the proprietary upstream "skybrush" module. In the latter case run it
# with the first argument set to "standalone".
#
# After running this script, open Blender and add the /dev folder to
# Preferences -> "File Paths" -> "Script Directories" to reach the
# Motion Canvas addon from your local source code.
#
# You will need to close and reopen Blender to see Motion Canvas
# in the list of add-ons. You will also need to close and open Blender
# after any code modifications on the source code to take effect.
#
# Share your code modifications with the community as a pull-request to the
# official repo at https://github.com/Axiovel-tech/motion-canvas
#
###############################################################################

set -e

SCRIPT_ROOT=$(dirname $0)
REPO_ROOT="${SCRIPT_ROOT}/../.."

if [ "$1" == "standalone" ]; then
  uv sync -E standalone
  DEPENDENCIES="natsort pyledctrl skybrush svgpathtools svgwrite webcolors"
else
  uv sync
  DEPENDENCIES=natsort
fi

cd "${REPO_ROOT}"

rm -rf dev/
mkdir -p dev/vendor/skybrush
cd dev/
ln -s ../src/addons
ln -s ../src/modules

cd vendor/skybrush/
VENV_PYTHONPATH=$(ls -d ../../../.venv/lib/python*/site-packages | sed -e 's#/$##')

for dependency in $DEPENDENCIES; do
  if [ -d "${VENV_PYTHONPATH}/${dependency}" ]; then
    ln -s "${VENV_PYTHONPATH}/${dependency}"
  fi
done
