# CoreELEC 21 Amlogic-ng: 32-bit userland, CPU flags from its config/arch.arm. Its glibc uses a
# 32-bit time_t (Kodi passes times as time_t), Debian's cross compiler defaults to 64-bit.
set(CMAKE_SYSTEM_NAME Linux)
set(CMAKE_SYSTEM_PROCESSOR arm)
set(CMAKE_C_COMPILER arm-linux-gnueabihf-gcc)
set(CMAKE_CXX_COMPILER arm-linux-gnueabihf-g++)
set(NG_FLAGS "-march=armv8-a+crc -mtune=cortex-a53 -mfpu=neon-fp-armv8 -mfloat-abi=hard -mabi=aapcs-linux -U_TIME_BITS")
set(CMAKE_C_FLAGS_INIT "${NG_FLAGS}")
set(CMAKE_CXX_FLAGS_INIT "${NG_FLAGS}")
set(CMAKE_FIND_ROOT_PATH /usr/arm-linux-gnueabihf ${ADDON_DEPENDS_PATH})
set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE ONLY)
