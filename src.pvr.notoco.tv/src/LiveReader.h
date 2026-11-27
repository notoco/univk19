/*
 *  Live HLS (MPEG-TS segments) read by the add-on itself.
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

  bool Open(const std::string& playlistUrl);
  void Close();
  int Read(unsigned char* buffer, unsigned int size);
  // UTC start of the first segment (Kodi's time 0) and the end of the downloaded data after it
  bool GetTimes(time_t& start, int64_t& endMicroseconds);

private:
  void Run();
  bool FetchSegment(const std::string& url, double duration, time_t start);
  void Refill();
  void Push(const unsigned char* data, size_t size);
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
