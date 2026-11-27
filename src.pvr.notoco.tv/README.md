# pvr.notoco.tv – sources

Kodi TV client for a Flussonic IPTV list (channels `.../mono.m3u8`, DVR archive). The add-on reads
the streams itself (no inputstream add-on): the archive as a seekable file (`ArchiveReader`), used for
guide programmes and for live TV with time shift (a few seconds behind the broadcast, the delay is a
setting), the plain live list for a channel without an archive (`LiveReader`) and recordings made from
the archive (`Recorder`, .mp4 by FFmpeg Tools from the CoreELEC repository). The built add-on for the CoreELEC box (aarch64)
is the `pvr.notoco.tv` folder in the repository root.

## Build (aarch64, Kodi 22)

Needs a Kodi source tree (`xbmc`, branch matching the box) and the `aarch64-linux-gnu` cross compiler.

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

3. Copy `install-notoco/pvr.notoco.tv` (addon.xml, icon, resources, `pvr.notoco.tv.so.<version>`) to the
   repository root and run `generator.py`.

Code style: `.clang-format` (Kodi's add-on style, 120 columns), English comments, no one-letter names,
a one-line comment for every function that is not Kodi's API.

The library is built with `-fno-gnu-unique`: disabling the add-on unloads it, so a new build loads
without restarting Kodi.
