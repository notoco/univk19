/*
 *  The Flussonic archive read by the add-on itself as one seekable file: programmes from the
 *  guide, and live TV with time shift (live = the archive a few seconds behind the broadcast,
 *  so pause has no limit and the watched part can be rewound).
 *
 *  Kodi seeks a client-handled stream by bytes and FFmpeg finds a time by many small seeks,
 *  so the archive must allow cheap random access. Every DVR segment gets a fixed-size slot of
 *  a virtual MPEG-TS file (twice the first segment's byte rate). A slot starts with null-packet
 *  padding and ends with the segment, so every probed position is followed by timestamps.
 *  One thread (the provider allows one connection) downloads the segments around the read
 *  position into memory: small seeks never touch the network. A segment is readable while it
 *  arrives (its size comes first, from Content-Length), so a channel starts at once.
 */

#pragma once

#include "Utils.h"

#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <ctime>
#include <map>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

#include <kodi/Filesystem.h>

namespace notoco
{

class ATTR_DLL_LOCAL ArchiveReader
{
public:
  struct Status
  {
    int behindSeconds = 0;   // the playing position behind the broadcast
    double bitrate = 0;      // bits per second of the stream
    double downloadRate = 0; // bits per second of the last download
  };

  ~ArchiveReader();

  // liveUrl: the channel's .../mono.m3u8?..., the archive starts at the UTC time from
  bool Open(const std::string& liveUrl, time_t from);
  // live TV: from the newest segment that starts at least delaySeconds before now
  bool OpenLive(const std::string& liveUrl, int delaySeconds);
  // stops the download thread and forgets the archive
  void Close();
  // bytes of the virtual file at the read position (-1 on an error or a stop)
  int Read(unsigned char* buffer, unsigned int size);
  // a position in the virtual file (SEEK_SET, SEEK_CUR, SEEK_END), -1 outside it
  int64_t Seek(int64_t position, int whence);
  // the size of the virtual file, it grows with a running programme
  int64_t Length();
  // UTC start of the archive (Kodi's time 0) and its known length
  bool GetTimes(time_t& start, int64_t& endMicroseconds);
  // live TV playing close to the broadcast (Kodi keeps its buffers small then)
  bool AtLiveEdge();
  // what Kodi shows as the stream information
  bool GetStatus(Status& status);

private:
  struct Slot
  {
    Segment segment;
    int64_t offset; // in the virtual file
    int64_t size;
  };
  struct Cached
  {
    std::vector<unsigned char> data;
    int64_t expected = 0; // segment bytes in the slot, known before the data arrives
    bool complete = false;
  };

  // slots from the found segments, the first one opened for its size; starts Run()
  bool Start(const std::string& liveUrl, std::vector<Segment> found, bool live);
  // the DVR segments of a time range (with a known start)
  bool FetchPlaylist(time_t from, time_t span, std::vector<Segment>& found);
  // new segments appended as slots (m_mutex held)
  void Layout(const std::vector<Segment>& found);
  // the archive after the known range, for a running programme and live TV
  bool Extend();
  // the download thread: segments around the read position, extensions near the end
  void Run();
  // an opened segment into the cache, readable while it arrives
  void DownloadSlot(size_t index, kodi::vfs::CFile& file);
  // the slot holding a position of the virtual file
  size_t IndexAt(int64_t position) const;
  // UTC time of the read position (m_mutex held)
  time_t PlayingTime() const;
  // tokens of the live pacing for the time since the last refill
  void Refill();

  std::string m_liveUrl;
  bool m_live = false;
  time_t m_rangeEnd = 0;
  std::chrono::steady_clock::time_point m_lastExtend;

  std::thread m_thread;
  std::atomic<bool> m_stop{false};
  std::mutex m_mutex;
  std::condition_variable m_condition;
  std::unique_ptr<kodi::vfs::CFile> m_firstFile; // the first segment, opened for its size

  double m_slotRate = 0; // bytes per second of a slot
  std::vector<Slot> m_slots;
  int64_t m_length = 0;
  std::map<size_t, Cached> m_cache;
  int64_t m_position = 0;
  int64_t m_sequential = 0; // bytes read since the last seek
  size_t m_wanted = 0;

  // live TV goes out at the playback rate near the broadcast (see LiveReader.h)
  double m_tokens = 0;
  std::chrono::steady_clock::time_point m_lastRefill;

  double m_bitrate = 0;
  double m_downloadRate = 0;
};

} // namespace notoco
