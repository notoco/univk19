# pvr.notoco.tv – sources

Kodi TV client for a Flussonic IPTV list (channels `.../mono.m3u8`, DVR archive). The add-on reads
the streams itself (no inputstream add-on): the archive as a seekable file (`ArchiveReader`), used for
guide programmes and for live TV with time shift (a few seconds behind the broadcast, the delay is a
setting), the plain live list for a channel without an archive (`LiveReader`) and recordings made from
the archive (`Recorder`, .mp4 by FFmpeg Tools from the CoreELEC repository, a dependency installed with the add-on).
`service.py` writes a keymap for the |<< and >>| keys in live TV and handles them (Kodi reads keymaps
only from its folders).

CoreELEC only: the add-on imports `service.coreelec.settings` (it exists nowhere else) and the 64-bit
builds have `<platform>linux-aarch64</platform>`. The built add-on is in a repository for one Kodi
version (dirs with minversion/maxversion in `repository.notoco.univ19`):

| Folder | Kodi | CoreELEC | Version |
| --- | --- | --- | --- |
| `kodi22/pvr.notoco.tv` | 22 (21.90.x), PVR API 9 | aarch64 | `x.y.z` |
| `kodi21/ne/pvr.notoco.tv` | 21 Omega, PVR API 8 | Amlogic-ne, aarch64 | `x.y.z` |
| `kodi21/ng/pvr.notoco.tv` | 21 Omega, PVR API 8 | Amlogic-ng, 32-bit arm | `x.y.z~ng` |

Kodi on Amlogic-ng (armv8-a in 32-bit mode) has no `linux-armv7` platform tag, only `linux`, so
the ng build is also visible on a Kodi 21 Amlogic-ne box. `~ng` makes its version lower, so ne takes
its own build. Both get the same release number.

## Build

Needs a Kodi source tree (`xbmc`, branch `Piers` for Kodi 22, `Omega` for Kodi 21) and a cross
compiler: `aarch64-linux-gnu` (`build/aarch64-toolchain.cmake`) or, for Amlogic-ng,
`arm-linux-gnueabihf` (`build/arm-ng-toolchain.cmake`). The PVR API version comes from Kodi's
headers (`CMakeLists.txt` switches the Kodi 21 differences).

1. Add-on definition in Kodi's tree:
   `xbmc/cmake/addons/addons/pvr.notoco.tv/pvr.notoco.tv.txt` = `pvr.notoco.tv https://localhost/pvr.notoco.tv main`,
   `platforms.txt` = `all`.
2. Copy this folder as `<prefix>/pvr.notoco.tv` and run:

```
cmake -S xbmc/cmake/addons -B build-notoco -DADDONS_TO_BUILD=pvr.notoco.tv \
  -DADDON_SRC_PREFIX=<prefix> -DCMAKE_TOOLCHAIN_FILE=<this folder>/build/aarch64-toolchain.cmake \
  -DADDON_DEPENDS_PATH=<build-notoco>/build/depends \
  -DCMAKE_INSTALL_PREFIX=<prefix>/install-notoco -DCMAKE_BUILD_TYPE=Release -DCORE_SYSTEM_NAME=linux
cmake --build build-notoco -j8
```

3. Copy `install-notoco/pvr.notoco.tv` (addon.xml, icon, resources, service.py,
   `pvr.notoco.tv.so.<version>`) to its folder from the table (ng: add `~ng` to the add-on version)
   and run `generator.py` (it builds `kodi21/` and `kodi22/` too).

Code style: `.clang-format` (Kodi's add-on style, 120 columns), English comments, no one-letter names,
a one-line comment for every function that is not Kodi's API.

The library is built with `-fno-gnu-unique`: disabling the add-on unloads it, so a new build loads
without restarting Kodi.
