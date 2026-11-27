/*
 *  The Flussonic archive read by the add-on itself as one seekable file.
 *
 *  Kodi seeks a client-handled stream by bytes and FFmpeg finds a time by many small seeks,
 *  so the archive must allow cheap random access. Every DVR segment gets a fixed-size slot of
 *  a virtual MPEG-TS file (twice the first segment's byte rate). A slot starts with null-packet
 *  padding and ends with the segment, so every probed position is followed by timestamps.
 *  One thread (the provider allows one connection) downloads the segments around the read
 *  position into memory: small seeks never touch the network.
 */

#pragma once

#include "Utils.h"

#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <ctime>
#include <map>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

namespace notoco
{

class ArchiveReader
{
public:
  ~ArchiveReader();

  // liveUrl: the channel's .../mono.m3u8?..., the archive starts at the UTC time from
  bool Open(const std::string& liveUrl, time_t from);
  void Close();
  int Read(unsigned char* buffer, unsigned int size);
  int64_t Seek(int64_t position, int whence);
  int64_t Length();
  // UTC start of the archive (Kodi's time 0) and its known length
  bool GetTimes(time_t& start, int64_t& endMicroseconds);

private:
  struct Slot
  {
    Segment segment;
    int64_t offset; // in the virtual file
    int64_t size;
  };

  void Run();
  bool Extend();
  size_t IndexAt(int64_t position) const;

  std::string m_liveUrl;
  time_t m_rangeEnd = 0;
  std::chrono::steady_clock::time_point m_lastExtend;

  std::thread m_thread;
  std::atomic<bool> m_stop{false};
  std::mutex m_mutex;
  std::condition_variable m_condition;

  double m_slotRate = 0; // bytes per second of a slot
  std::vector<Slot> m_slots;
  int64_t m_length = 0;
  std::map<size_t, std::vector<unsigned char>> m_cache;
  int64_t m_position = 0;
  int64_t m_sequential = 0; // bytes read since the last seek
  size_t m_wanted = 0;
};

} // namespace notoco
