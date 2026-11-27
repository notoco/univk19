/*
 *  Live HLS (MPEG-TS segments) read by the add-on itself, for a channel without an archive (live
 *  TV of a channel with one is the archive with time shift, see ArchiveReader.h).
 *
 *  A thread downloads the segments into memory, Read() only copies ready bytes. Playback starts
 *  at the oldest segment of the live window, so the buffer stays ahead of Kodi. Kodi (with the
 *  Amlogic decoder) takes all data it gets: at the live edge every read would wait for the next
 *  segment and a channel switch waits for that read. So the data goes out at the playback rate,
 *  after a burst that fills Kodi's queues quickly.
 */

#pragma once

#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <ctime>
#include <deque>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

namespace notoco
{

class LiveReader
{
public:
  ~LiveReader();

  // starts the download thread, true once the first data is there
  bool Open(const std::string& playlistUrl);
  // stops the download thread and drops the buffer
  void Close();
  // buffered bytes at the playback rate (-1 on an error or a stop)
  int Read(unsigned char* buffer, unsigned int size);
  // UTC start of the first segment (Kodi's time 0) and the end of the downloaded data after it
  bool GetTimes(time_t& start, int64_t& endMicroseconds);

private:
  // the download thread: the live playlist and its new segments
  void Run();
  // one segment into the buffer, pushed while it arrives
  bool FetchSegment(const std::string& url, double duration, time_t start);
  // tokens of the pacing for the time since the last refill
  void Refill();
  // data appended to the buffer, the oldest dropped over the limit
  void Push(const unsigned char* data, size_t size);
  // a wait that ends at once on Close()
  void SleepFor(int milliseconds);

  std::string m_playlistUrl;
  std::thread m_thread;
  std::atomic<bool> m_stop{false};
  std::atomic<bool> m_failed{false};

  std::mutex m_mutex;
  std::condition_variable m_condition;
  std::deque<std::vector<unsigned char>> m_chunks;
  size_t m_frontOffset = 0;
  size_t m_buffered = 0;

  // pacing: bytes per second of the last segment, the bytes Kodi may take now
  double m_byteRate = 0;
  double m_tokens = 0;
  std::chrono::steady_clock::time_point m_lastRefill;

  time_t m_streamStart = 0;
  double m_streamEnd = 0;
};

} // namespace notoco
