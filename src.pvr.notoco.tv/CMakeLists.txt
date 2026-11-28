cmake_minimum_required(VERSION 3.5...4.0)
project(pvr.notoco.tv)

set(CMAKE_MODULE_PATH ${CMAKE_MODULE_PATH} ${PROJECT_SOURCE_DIR})

# no GNU unique symbols: disabling the add-on unloads the library, a new build loads without a Kodi restart
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -fno-gnu-unique")

find_package(Kodi REQUIRED)
find_package(pugixml REQUIRED)
find_package(ZLIB REQUIRED)

include_directories(${KODI_INCLUDE_DIR}/..
                    ${PUGIXML_INCLUDE_DIRS}
                    ${ZLIB_INCLUDE_DIRS})

set(DEPLIBS ${PUGIXML_LIBRARIES}
            ${ZLIB_LIBRARIES})

set(NOTOCO_SOURCES src/Addon.cpp
                   src/ArchiveReader.cpp
                   src/Client.cpp
                   src/Guide.cpp
                   src/LiveReader.cpp
                   src/Playlist.cpp
                   src/Recorder.cpp
                   src/Utils.cpp)

set(NOTOCO_HEADERS src/ArchiveReader.h
                   src/Client.h
                   src/Guide.h
                   src/LiveReader.h
                   src/Playlist.h
                   src/Recorder.h
                   src/Utils.h)

# Kodi 21 (PVR API 8): GetChannelStreamProperties() has no PVR_SOURCE
file(STRINGS ${KODI_INCLUDE_DIR}/versions.h PVR_API_LINE REGEX "define ADDON_INSTANCE_VERSION_PVR +\"")
string(REGEX MATCH "\"([0-9]+)\\." PVR_API_MAJOR "${PVR_API_LINE}")
if(CMAKE_MATCH_1 LESS 9)
  add_definitions(-DNOTOCO_PVR_API_8)
endif()

# 64-bit builds only for 64-bit Kodi (the repository hides them elsewhere)
if(CMAKE_SYSTEM_PROCESSOR STREQUAL "aarch64")
  set(PLATFORM_TAG linux-aarch64)
endif()

addon_version(pvr.notoco.tv NOTOCO)
add_definitions(-DNOTOCO_VERSION=${NOTOCO_VERSION})

build_addon(pvr.notoco.tv NOTOCO DEPLIBS)

include(CPack)
