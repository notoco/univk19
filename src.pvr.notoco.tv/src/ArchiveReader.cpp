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
constexpr time_t LIVE_LOOKBACK = 60;       // seconds of archive a live start chooses from
constexpr size_t PREFETCH = 3;             // segments downloaded ahead of the read position
constexpr size_t KEEP_BEHIND = 3;          // segments kept behind it (small backward seeks)
constexpr size_t EXTEND_BEFORE_END = 60;   // segments left when a running programme is extended
constexpr int EXTEND_SECONDS = 10;         // between archive extensions
constexpr int EXTEND_SECONDS_LIVE = 2;     // the same for live TV
constexpr double PACE_SECONDS = 30.0;      // live TV this close to the broadcast is paced
constexpr double BURST_SECONDS = 3.0;      // less than the archive ahead of a live start (one segment at least)
constexpr int PACE_WAIT_MS = 20;
constexpr int LIVE_EDGE_SECONDS = 25;
constexpr time_t BROADCAST_SECONDS = 60; // an archive ending this close to now reaches the broadcast
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
  m_stop = false;
  std::vector<Segment> found;
  if (!FetchPlaylist(from, std::min<time_t>(PLAYLIST_SPAN, std::time(nullptr) - from), found) ||
      !Start(liveUrl, found, false))
  {
    kodi::Log(ADDON_LOG_ERROR, "ArchiveReader - no archive from %lld", static_cast<long long>(from));
    return false;
  }
  return true;
}

bool ArchiveReader::OpenLive(const std::string& liveUrl, int delaySeconds)
{
  Close();
  m_liveUrl = liveUrl;
  m_stop = false;
  const time_t now = std::time(nullptr);
  std::vector<Segment> found;
  if (!FetchPlaylist(now - LIVE_LOOKBACK, LIVE_LOOKBACK, found))
  {
    kodi::Log(ADDON_LOG_ERROR, "ArchiveReader - no live archive");
    return false;
  }
  // the newest segment starting early enough, so the next ones arrive before they are needed
  size_t chosen = 0;
  for (size_t index = 0; index < found.size(); ++index)
  {
    if (found[index].start <= now - delaySeconds)
      chosen = index;
  }
  found.erase(found.begin(), found.begin() + static_cast<long>(chosen));
  return Start(liveUrl, found, true);
}

bool ArchiveReader::FetchPlaylist(time_t from, time_t span, std::vector<Segment>& found)
{
  if (span < 2)
    return false;
  const std::string url = ArchivePlaylistUrl(m_liveUrl, from, span);
  std::vector<unsigned char> content;
  double targetDuration = 0;
  const bool downloaded = Download(url, content, m_stop);
  if (m_stop)
    return false;
  ReportServer(downloaded);
  if (!downloaded || !ParsePlaylist(url, std::string(content.begin(), content.end()), found, targetDuration))
    return false;
  found.erase(std::remove_if(found.begin(), found.end(),
                             [](const Segment& segment) { return segment.start == 0 || segment.duration <= 0; }),
              found.end());
  return !found.empty();
}

bool ArchiveReader::Start(const std::string& liveUrl, std::vector<Segment> found, bool live)
{
  m_liveUrl = liveUrl;
  m_live = live;
  m_stop = false;

  // the slot size comes from the first segment, before any slot is laid out
  auto file = std::make_unique<kodi::vfs::CFile>();
  if (!file->OpenFile(ServerUrl(found.front().url), ADDON_READ_NO_CACHE))
  {
    ReportServer(false);
    return false;
  }
  int64_t size = file->GetLength();
  std::vector<unsigned char> whole;
  if (size <= 0)
  {
    // no Content-Length: the whole segment first
    unsigned char chunk[READ_CHUNK];
    ssize_t length;
    while (!m_stop && (length = file->Read(chunk, sizeof(chunk))) > 0)
      whole.insert(whole.end(), chunk, chunk + length);
    file.reset();
    size = static_cast<int64_t>(whole.size());
    if (size == 0)
      return false;
  }

  {
    std::lock_guard<std::mutex> lock(m_mutex);
    m_slotRate = size / found.front().duration * SLOT_FACTOR;
    m_tokens = BURST_SECONDS * m_slotRate;
    m_lastRefill = std::chrono::steady_clock::now();
    m_lastExtend = m_lastRefill;
    Layout(found);
    if (!whole.empty())
    {
      Cached& cached = m_cache[0];
      cached.expected = std::min<int64_t>(size / TS_PACKET * TS_PACKET, m_slots.front().size);
      whole.resize(static_cast<size_t>(cached.expected));
      cached.data = std::move(whole);
      cached.complete = true;
    }
  }
  m_firstFile = std::move(file);
  m_thread = std::thread(&ArchiveReader::Run, this);
  return true;
}

void ArchiveReader::Close()
{
  m_stop = true;
  m_condition.notify_all();
  if (m_thread.joinable())
    m_thread.join();
  m_firstFile.reset();
  std::lock_guard<std::mutex> lock(m_mutex);
  m_cache.clear();
  m_slots.clear();
  m_length = 0;
  m_position = 0;
  m_sequential = 0;
  m_wanted = 0;
  m_slotRate = 0;
  m_rangeEnd = 0;
  m_bitrate = 0;
  m_downloadRate = 0;
  m_live = false;
}

void ArchiveReader::Layout(const std::vector<Segment>& found)
{
  // called with m_mutex held
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
  const Segment& last = m_slots.back().segment;
  m_rangeEnd = last.start + static_cast<time_t>(std::ceil(last.duration));
  m_condition.notify_all();
}

bool ArchiveReader::Extend()
{
  time_t from;
  {
    std::lock_guard<std::mutex> lock(m_mutex);
    from = m_rangeEnd;
    m_lastExtend = std::chrono::steady_clock::now();
  }
  std::vector<Segment> found;
  if (!FetchPlaylist(from, std::min<time_t>(PLAYLIST_SPAN, std::time(nullptr) - from), found))
    return false;
  std::lock_guard<std::mutex> lock(m_mutex);
  const size_t before = m_slots.size();
  Layout(found);
  if (!m_live)
    kodi::Log(ADDON_LOG_INFO, "ArchiveReader - %zu segments (+%zu), %lld s", m_slots.size(), m_slots.size() - before,
              static_cast<long long>(m_rangeEnd - m_slots.front().segment.start));
  return true;
}

void ArchiveReader::Run()
{
  if (m_firstFile)
  {
    DownloadSlot(0, *m_firstFile);
    m_firstFile.reset();
  }

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
      // a running programme or live TV: more archive near the end of the known range
      const int interval = AtBroadcast() ? EXTEND_SECONDS_LIVE : EXTEND_SECONDS;
      extend = target == m_slots.size() && m_wanted + EXTEND_BEFORE_END > m_slots.size() &&
               std::chrono::steady_clock::now() - m_lastExtend > std::chrono::seconds(interval);
      if (target == m_slots.size() && !extend)
      {
        m_condition.wait_for(lock, std::chrono::milliseconds(500));
        continue;
      }
    }

    if (extend)
    {
      Extend();
      continue;
    }

    kodi::vfs::CFile file;
    bool opened = file.OpenFile(ServerUrl(url), ADDON_READ_NO_CACHE);
    if (!opened && !m_stop)
    {
      // once more, on the other server after enough failures
      ReportServer(false);
      opened = file.OpenFile(ServerUrl(url), ADDON_READ_NO_CACHE);
      if (!opened)
        ReportServer(false);
    }
    if (m_stop)
      return;
    if (opened)
      DownloadSlot(target, file);
    else
    {
      // a missing segment plays as padding
      std::lock_guard<std::mutex> lock(m_mutex);
      m_cache[target].complete = true;
      m_condition.notify_all();
    }
  }
}

void ArchiveReader::DownloadSlot(size_t index, kodi::vfs::CFile& file)
{
  const auto started = std::chrono::steady_clock::now();
  int64_t slotSize;
  double duration;
  {
    std::lock_guard<std::mutex> lock(m_mutex);
    if (index >= m_slots.size())
      return;
    slotSize = m_slots[index].size;
    duration = m_slots[index].segment.duration;
    Cached& cached = m_cache[index];
    if (cached.complete)
      return; // read whole already (no Content-Length)
    const int64_t length = file.GetLength();
    if (length > slotSize)
      kodi::Log(ADDON_LOG_WARNING, "ArchiveReader - segment %zu cut from %lld to %lld bytes", index,
                static_cast<long long>(length), static_cast<long long>(slotSize));
    cached.expected = length > 0 ? std::min<int64_t>(length / TS_PACKET * TS_PACKET, slotSize) : 0;
    cached.data.clear();
  }

  unsigned char chunk[READ_CHUNK];
  ssize_t length;
  int64_t total = 0;
  while (!m_stop && (length = file.Read(chunk, sizeof(chunk))) > 0)
  {
    total += length;
    std::lock_guard<std::mutex> lock(m_mutex);
    Cached& cached = m_cache[index];
    const size_t limit = static_cast<size_t>(cached.expected > 0 ? cached.expected : slotSize);
    const size_t room = limit > cached.data.size() ? limit - cached.data.size() : 0;
    cached.data.insert(cached.data.end(), chunk, chunk + std::min<size_t>(room, static_cast<size_t>(length)));
    m_condition.notify_all();
  }
  file.Close();
  if (m_stop)
    return;

  const double seconds = std::chrono::duration<double>(std::chrono::steady_clock::now() - started).count();
  const bool whole = total > 0;
  // a download slower than playback counts as a server failure
  ReportServer(whole && seconds < duration);

  std::lock_guard<std::mutex> lock(m_mutex);
  Cached& cached = m_cache[index];
  if (cached.expected == 0)
    cached.expected = static_cast<int64_t>(cached.data.size()) / TS_PACKET * TS_PACKET;
  // a broken download: what came, then null packets
  cached.data.resize(static_cast<size_t>(std::min<int64_t>(cached.data.size(), cached.expected)) / TS_PACKET *
                     TS_PACKET);
  while (static_cast<int64_t>(cached.data.size()) < cached.expected)
    cached.data.push_back(NullPacketByte(static_cast<int64_t>(cached.data.size())));
  cached.complete = true;
  if (whole && duration > 0 && seconds > 0)
  {
    const double bitrate = total * 8.0 / duration;
    m_bitrate = m_bitrate > 0 ? m_bitrate * 0.7 + bitrate * 0.3 : bitrate;
    m_downloadRate = total * 8.0 / seconds;
  }
  m_condition.notify_all();
}

size_t ArchiveReader::IndexAt(int64_t position) const
{
  const auto found = std::upper_bound(m_slots.begin(), m_slots.end(), position,
                                      [](int64_t value, const Slot& slot) { return value < slot.offset; });
  return found == m_slots.begin() ? 0 : static_cast<size_t>(found - m_slots.begin() - 1);
}

time_t ArchiveReader::PlayingTime() const
{
  // called with m_mutex held
  if (m_slots.empty())
    return 0;
  const Slot& slot = m_slots[IndexAt(std::min(m_position, m_length - 1))];
  return slot.segment.start +
         static_cast<time_t>(slot.segment.duration * (m_position - slot.offset) / static_cast<double>(slot.size));
}

bool ArchiveReader::AtBroadcast() const
{
  return m_live || std::time(nullptr) - m_rangeEnd < BROADCAST_SECONDS;
}

void ArchiveReader::Refill()
{
  const auto now = std::chrono::steady_clock::now();
  const double seconds = std::chrono::duration<double>(now - m_lastRefill).count();
  m_tokens = std::min(m_tokens + seconds * m_slotRate, BURST_SECONDS * m_slotRate);
  m_lastRefill = now;
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
  const int64_t offset = m_position - m_slots[index].offset;
  // the slot's padding is known with the segment size, its data as it arrives
  const auto ready = [this, index, offset]
  {
    const auto found = m_cache.find(index);
    if (found == m_cache.end() || (!found->second.complete && found->second.expected == 0))
      return false;
    const int64_t padding = m_slots[index].size - found->second.expected;
    return offset < padding || offset - padding < static_cast<int64_t>(found->second.data.size());
  };
  if (!m_condition.wait_for(lock, std::chrono::milliseconds(WAIT_MS), [&] { return ready() || m_stop.load(); }) ||
      m_stop)
    return -1;

  const Slot& slot = m_slots[index];
  const Cached& cached = m_cache[index];
  const int64_t padding = slot.size - cached.expected;
  int64_t length = std::min<int64_t>(size, slot.size - offset);
  if (offset < padding)
    length = std::min<int64_t>(length, padding - offset);
  else
    length = std::min<int64_t>(length, static_cast<int64_t>(cached.data.size()) - (offset - padding));

  // near the broadcast (live TV or a running programme): Kodi gets the data at the playback rate,
  // so a read never waits for the next segment (a channel switch or a pause waits for that read)
  if (AtBroadcast() && m_length - m_position < PACE_SECONDS * m_slotRate)
  {
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::milliseconds(WAIT_MS);
    Refill();
    while (m_tokens < 1 && !m_stop && std::chrono::steady_clock::now() < deadline)
    {
      m_condition.wait_for(lock, std::chrono::milliseconds(PACE_WAIT_MS));
      Refill();
    }
    if (m_stop || m_tokens < 1)
      return -1;
    length = std::min<int64_t>(length, static_cast<int64_t>(m_tokens));
    m_tokens -= length;
  }

  // the slot and the cache entry stay: only this thread's Seek() and the Run() thread's
  // eviction (never the wanted segment) change them
  if (offset < padding)
  {
    for (int64_t byte = 0; byte < length; ++byte)
      buffer[byte] = NullPacketByte(offset + byte);
  }
  else
    std::memcpy(buffer, m_cache[index].data.data() + (offset - padding), static_cast<size_t>(length));
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

bool ArchiveReader::AtLiveEdge()
{
  std::lock_guard<std::mutex> lock(m_mutex);
  return m_live && !m_slots.empty() && m_rangeEnd - PlayingTime() < LIVE_EDGE_SECONDS;
}

bool ArchiveReader::GetStatus(Status& status)
{
  std::lock_guard<std::mutex> lock(m_mutex);
  if (m_slots.empty())
    return false;
  status.behindSeconds = static_cast<int>(std::time(nullptr) - PlayingTime());
  status.bitrate = m_bitrate;
  status.downloadRate = m_downloadRate;
  return true;
}

} // namespace notoco
