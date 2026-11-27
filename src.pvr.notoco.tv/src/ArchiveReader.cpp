#include "ArchiveReader.h"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstring>

#include <kodi/General.h>

namespace notoco
{

namespace
{
constexpr int64_t TS_PACKET = 188;
constexpr double SLOT_FACTOR = 2.0;
constexpr time_t PLAYLIST_SPAN = 4 * 3600; // seconds of archive per playlist request
constexpr size_t PREFETCH = 3;             // segments downloaded ahead of the read position
constexpr size_t KEEP_BEHIND = 3;          // segments kept behind it (small backward seeks)
constexpr size_t EXTEND_BEFORE_END = 60;   // segments left when a running programme is extended
constexpr int WAIT_MS = 20000;

// MPEG-TS null packet (PID 0x1FFF), the padding of a slot
unsigned char NullPacketByte(int64_t index)
{
  static const unsigned char header[4] = {0x47, 0x1F, 0xFF, 0x10};
  const int64_t inPacket = index % TS_PACKET;
  return inPacket < 4 ? header[inPacket] : 0xFF;
}
} // namespace

ArchiveReader::~ArchiveReader()
{
  Close();
}

bool ArchiveReader::Open(const std::string& liveUrl, time_t from)
{
  Close();
  m_liveUrl = liveUrl;
  m_rangeEnd = from;
  m_slots.clear();
  m_cache.clear();
  m_length = 0;
  m_position = 0;
  m_sequential = 0;
  m_wanted = 0;
  m_slotRate = 0;
  m_stop = false;

  if (!Extend() || m_slots.empty())
  {
    kodi::Log(ADDON_LOG_ERROR, "ArchiveReader - no archive from %lld", static_cast<long long>(from));
    return false;
  }
  m_thread = std::thread(&ArchiveReader::Run, this);
  return true; // the first segment is in the cache already (Extend() measured its size)
}

void ArchiveReader::Close()
{
  m_stop = true;
  m_condition.notify_all();
  if (m_thread.joinable())
    m_thread.join();
  std::lock_guard<std::mutex> lock(m_mutex);
  m_cache.clear();
  m_slots.clear();
  m_length = 0;
}

bool ArchiveReader::Extend()
{
  const time_t now = std::time(nullptr);
  time_t from;
  {
    std::lock_guard<std::mutex> lock(m_mutex);
    from = m_rangeEnd;
    m_lastExtend = std::chrono::steady_clock::now();
  }
  const time_t span = std::min<time_t>(PLAYLIST_SPAN, now - from);
  if (span < 10)
    return false;

  const std::string url = ArchivePlaylistUrl(m_liveUrl, from, span);
  std::vector<unsigned char> content;
  std::vector<Segment> found;
  double targetDuration = 0;
  if (!Download(url, content, m_stop) ||
      !ParsePlaylist(url, std::string(content.begin(), content.end()), found, targetDuration))
    return false;
  found.erase(std::remove_if(found.begin(), found.end(), [](const Segment& segment) { return segment.start == 0; }),
              found.end());
  if (found.empty())
    return false;

  // the slot size comes from the first segment, before any slot is laid out
  std::vector<unsigned char> first;
  if (m_slotRate <= 0)
  {
    if (!Download(found.front().url, first, m_stop) || first.empty())
      return false;
    m_slotRate = first.size() / found.front().duration * SLOT_FACTOR;
  }

  std::lock_guard<std::mutex> lock(m_mutex);
  for (const Segment& segment : found)
  {
    // a playlist from a time may begin with the segment holding it: already known
    if (!m_slots.empty() &&
        segment.start < m_slots.back().segment.start + static_cast<time_t>(m_slots.back().segment.duration))
      continue;
    const int64_t size = static_cast<int64_t>(std::ceil(segment.duration * m_slotRate / TS_PACKET)) * TS_PACKET;
    m_slots.push_back({segment, m_length, size});
    m_length += size;
  }
  if (!first.empty())
  {
    first.resize(std::min<size_t>(first.size() / TS_PACKET * TS_PACKET, m_slots.front().size));
    m_cache[0] = std::move(first);
  }
  const Segment& last = m_slots.back().segment;
  m_rangeEnd = last.start + static_cast<time_t>(std::ceil(last.duration));
  kodi::Log(ADDON_LOG_INFO, "ArchiveReader - %zu segments, %lld s", m_slots.size(),
            static_cast<long long>(m_rangeEnd - m_slots.front().segment.start));
  m_condition.notify_all();
  return true;
}

void ArchiveReader::Run()
{
  while (!m_stop)
  {
    size_t target = 0;
    std::string url;
    bool extend = false;
    {
      std::unique_lock<std::mutex> lock(m_mutex);
      // forget segments far from the read position
      for (auto entry = m_cache.begin(); entry != m_cache.end();)
      {
        if (entry->first + KEEP_BEHIND < m_wanted || entry->first > m_wanted + PREFETCH + 2)
          entry = m_cache.erase(entry);
        else
          ++entry;
      }
      target = m_slots.size();
      for (size_t index = m_wanted; index < m_slots.size() && index <= m_wanted + PREFETCH; ++index)
      {
        if (!m_cache.count(index))
        {
          target = index;
          url = m_slots[index].segment.url;
          break;
        }
      }
      // a running programme: more archive near the end of the known range
      extend = target == m_slots.size() && m_wanted + EXTEND_BEFORE_END > m_slots.size() &&
               std::chrono::steady_clock::now() - m_lastExtend > std::chrono::seconds(10);
      if (target == m_slots.size() && !extend)
      {
        m_condition.wait_for(lock, std::chrono::seconds(2));
        continue;
      }
    }

    if (extend)
    {
      Extend();
      continue;
    }

    std::vector<unsigned char> data;
    if (!Download(url, data, m_stop))
      data.clear(); // a missing segment plays as padding
    if (m_stop)
      return;
    std::lock_guard<std::mutex> lock(m_mutex);
    if (target < m_slots.size())
    {
      const size_t limit = static_cast<size_t>(m_slots[target].size);
      if (data.size() > limit)
        kodi::Log(ADDON_LOG_WARNING, "ArchiveReader - segment %zu cut from %zu to %zu bytes", target, data.size(), limit);
      data.resize(std::min(data.size() / TS_PACKET * TS_PACKET, limit));
      m_cache[target] = std::move(data);
    }
    m_condition.notify_all();
  }
}

size_t ArchiveReader::IndexAt(int64_t position) const
{
  const auto found = std::upper_bound(m_slots.begin(), m_slots.end(), position,
                                      [](int64_t value, const Slot& slot) { return value < slot.offset; });
  return found == m_slots.begin() ? 0 : static_cast<size_t>(found - m_slots.begin() - 1);
}

int ArchiveReader::Read(unsigned char* buffer, unsigned int size)
{
  std::unique_lock<std::mutex> lock(m_mutex);
  if (m_slots.empty())
    return -1;

  // At the end: playback of a running programme waits for more archive, FFmpeg probing the
  // last timestamp (a seek to the end) gets the end of the file at once.
  if (m_position >= m_length)
  {
    if (m_sequential < m_slots.back().size)
      return 0;
    m_wanted = m_slots.size();
    m_condition.notify_all();
    if (!m_condition.wait_for(lock, std::chrono::milliseconds(WAIT_MS),
                              [this] { return m_position < m_length || m_stop; }) ||
        m_stop)
      return m_stop ? -1 : 0;
  }

  const size_t index = IndexAt(m_position);
  if (index != m_wanted)
  {
    m_wanted = index;
    m_condition.notify_all();
  }
  if (!m_condition.wait_for(lock, std::chrono::milliseconds(WAIT_MS),
                            [this, index] { return m_cache.count(index) > 0 || m_stop; }) ||
      m_stop)
    return -1;

  const Slot& slot = m_slots[index];
  const std::vector<unsigned char>& data = m_cache[index];
  const int64_t offset = m_position - slot.offset;
  const int64_t padding = slot.size - static_cast<int64_t>(data.size());
  int64_t length = std::min<int64_t>(size, slot.size - offset);
  if (offset < padding)
  {
    length = std::min<int64_t>(length, padding - offset);
    for (int64_t byte = 0; byte < length; ++byte)
      buffer[byte] = NullPacketByte(offset + byte);
  }
  else
    std::memcpy(buffer, data.data() + (offset - padding), static_cast<size_t>(length));
  m_position += length;
  m_sequential += length;
  return static_cast<int>(length);
}

int64_t ArchiveReader::Seek(int64_t position, int whence)
{
  std::lock_guard<std::mutex> lock(m_mutex);
  int64_t target = position;
  if (whence == SEEK_CUR)
    target = m_position + position;
  else if (whence == SEEK_END)
    target = m_length + position;
  if (target < 0 || target > m_length)
    return -1;
  if (target != m_position)
    m_sequential = 0;
  m_position = target;
  const size_t index = IndexAt(target);
  if (index != m_wanted)
  {
    m_wanted = index;
    m_condition.notify_all();
  }
  return target;
}

int64_t ArchiveReader::Length()
{
  std::lock_guard<std::mutex> lock(m_mutex);
  return m_length;
}

bool ArchiveReader::GetTimes(time_t& start, int64_t& endMicroseconds)
{
  std::lock_guard<std::mutex> lock(m_mutex);
  if (m_slots.empty())
    return false;
  start = m_slots.front().segment.start;
  endMicroseconds = static_cast<int64_t>(m_rangeEnd - start) * 1000000;
  return true;
}

} // namespace notoco
