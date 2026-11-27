#include "LiveReader.h"

#include "Utils.h"

#include <algorithm>
#include <cstring>

#include <kodi/Filesystem.h>
#include <kodi/General.h>

namespace notoco
{

namespace
{
constexpr size_t READ_CHUNK = 64 * 1024;
constexpr size_t MAX_BUFFERED = 256 * 1024 * 1024; // a long pause keeps downloading, the oldest data goes first
constexpr int OPEN_TIMEOUT_MS = 15000;
constexpr int READ_TIMEOUT_MS = 20000;
constexpr double BURST_SECONDS = 10.0;
constexpr int PACE_WAIT_MS = 20;
constexpr int PLAYLIST_FAILURES = 10;
} // namespace

LiveReader::~LiveReader()
{
  Close();
}

bool LiveReader::Open(const std::string& playlistUrl)
{
  Close();
  m_playlistUrl = playlistUrl;
  m_stop = false;
  m_failed = false;
  m_thread = std::thread(&LiveReader::Run, this);

  std::unique_lock<std::mutex> lock(m_mutex);
  m_condition.wait_for(lock, std::chrono::milliseconds(OPEN_TIMEOUT_MS),
                       [this] { return m_buffered > 0 || m_failed || m_stop; });
  const bool ready = m_buffered > 0;
  lock.unlock();
  if (!ready)
  {
    kodi::Log(ADDON_LOG_ERROR, "LiveReader - no data from %s", RedactUrl(playlistUrl).c_str());
    Close();
  }
  return ready;
}

void LiveReader::Close()
{
  m_stop = true;
  m_condition.notify_all();
  if (m_thread.joinable())
    m_thread.join();

  std::lock_guard<std::mutex> lock(m_mutex);
  m_chunks.clear();
  m_frontOffset = 0;
  m_buffered = 0;
  m_byteRate = 0;
  m_tokens = 0;
  m_streamStart = 0;
  m_streamEnd = 0;
}

bool LiveReader::GetTimes(time_t& start, int64_t& endMicroseconds)
{
  std::lock_guard<std::mutex> lock(m_mutex);
  if (m_streamStart == 0)
    return false;
  start = m_streamStart;
  endMicroseconds = static_cast<int64_t>((m_streamEnd - static_cast<double>(m_streamStart)) * 1000000);
  return true;
}

int LiveReader::Read(unsigned char* buffer, unsigned int size)
{
  std::unique_lock<std::mutex> lock(m_mutex);
  const auto deadline = std::chrono::steady_clock::now() + std::chrono::milliseconds(READ_TIMEOUT_MS);
  while (!m_stop && !m_failed && std::chrono::steady_clock::now() < deadline)
  {
    Refill();
    if (m_buffered > 0 && (m_byteRate <= 0 || m_tokens >= 1))
      break;
    m_condition.wait_for(lock, std::chrono::milliseconds(PACE_WAIT_MS));
  }
  if (m_buffered == 0 || m_stop)
    return -1;

  size_t allowed = size;
  if (m_byteRate > 0)
    allowed = std::min<size_t>(size, static_cast<size_t>(m_tokens));

  unsigned int copied = 0;
  while (copied < allowed && !m_chunks.empty())
  {
    std::vector<unsigned char>& front = m_chunks.front();
    const size_t length = std::min<size_t>(allowed - copied, front.size() - m_frontOffset);
    std::memcpy(buffer + copied, front.data() + m_frontOffset, length);
    copied += length;
    m_frontOffset += length;
    m_buffered -= length;
    if (m_frontOffset == front.size())
    {
      m_chunks.pop_front();
      m_frontOffset = 0;
    }
  }
  if (m_byteRate > 0)
    m_tokens -= copied;
  return static_cast<int>(copied);
}

void LiveReader::Refill()
{
  const auto now = std::chrono::steady_clock::now();
  if (m_byteRate > 0)
  {
    const double seconds = std::chrono::duration<double>(now - m_lastRefill).count();
    m_tokens = std::min(m_tokens + seconds * m_byteRate, BURST_SECONDS * m_byteRate);
  }
  m_lastRefill = now;
}

void LiveReader::Run()
{
  int64_t nextSequence = -1;
  int failures = 0;

  while (!m_stop)
  {
    std::vector<unsigned char> content;
    std::vector<Segment> segments;
    double targetDuration = 5.0;
    if (!Download(m_playlistUrl, content, m_stop) ||
        !ParsePlaylist(m_playlistUrl, std::string(content.begin(), content.end()), segments, targetDuration))
    {
      if (++failures >= PLAYLIST_FAILURES)
      {
        m_failed = true;
        m_condition.notify_all();
        kodi::Log(ADDON_LOG_ERROR, "LiveReader - playlist failed %d times, giving up", failures);
        return;
      }
      SleepFor(1000);
      continue;
    }
    failures = 0;

    // Start at the oldest segment of the live window, also after a stall longer than the window
    if (nextSequence < segments.front().sequence)
      nextSequence = segments.front().sequence;

    for (const Segment& segment : segments)
    {
      if (m_stop)
        return;
      if (segment.sequence < nextSequence)
        continue;
      if (!FetchSegment(segment.url, segment.duration, segment.start))
        break;
      nextSequence = segment.sequence + 1;
    }

    SleepFor(static_cast<int>(targetDuration * 500));
  }
}

bool LiveReader::FetchSegment(const std::string& url, double duration, time_t start)
{
  kodi::vfs::CFile file;
  if (!file.OpenFile(url, ADDON_READ_NO_CACHE))
  {
    kodi::Log(ADDON_LOG_ERROR, "LiveReader - cannot open %s", RedactUrl(url).c_str());
    return false;
  }

  // pushed while it arrives: the first data of a channel is ready after the first chunk
  size_t total = 0;
  unsigned char data[READ_CHUNK];
  ssize_t length;
  while (!m_stop && (length = file.Read(data, sizeof(data))) > 0)
  {
    Push(data, static_cast<size_t>(length));
    total += static_cast<size_t>(length);
  }
  file.Close();
  if (m_stop || total == 0)
    return !m_stop;

  std::lock_guard<std::mutex> lock(m_mutex);
  if (start > 0)
  {
    if (m_streamStart == 0)
      m_streamStart = start;
    m_streamEnd = static_cast<double>(start) + duration;
  }
  if (duration > 0)
  {
    const bool first = m_byteRate <= 0;
    m_byteRate = total / duration;
    if (first)
    {
      // the first segment went out unpaced: the burst starts with what is still buffered
      m_tokens = std::max(0.0, BURST_SECONDS * m_byteRate - (total - static_cast<double>(m_buffered)));
      m_lastRefill = std::chrono::steady_clock::now();
    }
  }
  return true;
}

void LiveReader::Push(const unsigned char* data, size_t size)
{
  {
    std::lock_guard<std::mutex> lock(m_mutex);
    m_chunks.emplace_back(data, data + size);
    m_buffered += size;
    while (m_buffered > MAX_BUFFERED && m_chunks.size() > 1)
    {
      m_buffered -= m_chunks.front().size() - m_frontOffset;
      m_chunks.pop_front();
      m_frontOffset = 0;
    }
  }
  m_condition.notify_all();
}

void LiveReader::SleepFor(int milliseconds)
{
  std::unique_lock<std::mutex> lock(m_mutex);
  m_condition.wait_for(lock, std::chrono::milliseconds(milliseconds), [this] { return m_stop.load(); });
}

} // namespace notoco
