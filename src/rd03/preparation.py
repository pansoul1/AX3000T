"""Produce files for an explicitly requested one-time RAM-only native verifier mount."""
from pathlib import Path
from .builder import stock_image, write_json
from .patches import patch_verifier
from .formats import sha256, require


def prepare(rom: Path, output: Path):
    _, _, _, _, _, _, fs = stock_image(rom)
    patched = patch_verifier(fs.get("/bin/mkxqimage").open().read())
    require(not output.exists(), "Preparation output already exists; choose a new directory")
    output.mkdir(parents=True)
    (output / "mkxqimage.patched").write_bytes(patched)
    write_json(output / "preparation.json", {"verifier_sha256": sha256(patched), "flash_performed": False})
    script = '''#!/bin/sh
set -eu
cd "$(dirname "$0")"
[ "$(cat /proc/xiaoqiang/model)" = RD03 ] || { echo 'Wrong device model'; exit 1; }
digest() { openssl dgst -sha256 "$1" | awk '{print $NF}'; }
current=$(digest /bin/mkxqimage)
[ "$current" = d703fd0d3eab7ce8db6e26c96b9441f92df103c214af55ed6f77bc0b314f37ed ] || \
[ "$current" = f078bd7dfb4775441d3dab7d7b972a681798bcff1d36d139dcdfe9b2674ab47c ] || { echo 'Unknown installed verifier'; exit 1; }
[ "$(digest mkxqimage.patched)" = f078bd7dfb4775441d3dab7d7b972a681798bcff1d36d139dcdfe9b2674ab47c ] || exit 1
[ "$(digest firmware.bin)" = "$1" ] || { echo 'Firmware transfer checksum mismatch'; exit 1; }
chmod 755 mkxqimage.patched
./mkxqimage.patched -v firmware.bin
if [ "$current" != f078bd7dfb4775441d3dab7d7b972a681798bcff1d36d139dcdfe9b2674ab47c ]; then
    mount -o bind "$PWD/mkxqimage.patched" /bin/mkxqimage
fi
/bin/mkxqimage -v firmware.bin
rm -f firmware.bin
echo 'READY: no flash or reboot. Upload your firmware in the Xiaomi web interface.'
echo 'Preparation is in RAM. Keep the router running until the web upload.'
echo 'Undo before uploading: umount /bin/mkxqimage'
'''
    (output / "prepare.sh").write_text(script, encoding="ascii", newline="\n")
    print(f"Preparation files generated in {output}; no router was contacted.")
