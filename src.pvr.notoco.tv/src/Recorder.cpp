#include "Recorder.h"

#include "Utils.h"

#include <algorithm>
#include <cstdio>
#include <cstring>
#include <sstream>

#include <kodi/Filesystem.h>
#include <kodi/General.h>
#include <pugixml.hpp>

using namespace notoco;

namespace
{
constexpr time_t ARCHIVE_DELAY = 60;  // seconds after the end before the archive is complete
constexpr int RESUME_AFTER_PLAYBACK = 30; // seconds without playback before downloads resume
constexpr int SEGMENT_ATTEMPTS = 3;
const char* const STATE_FILE = "special://profile/addon_data/pvr.notoco.tv/recorder.xml";

std::string SafeFileName(const std::string& name)
{
  std::string safe;
  for (const char character : name)
    safe += std::strchr("/\\:*?\"<>|", character) || static_cast<unsigned char>(character) < 32 ? '_' : character;
  return safe;
}

std::string LocalTime(time_t time, const char* format)
{
  char text[64];
  std::tm parts{};
  localtime_r(&time, &parts);
  std::strftime(text, sizeof(text), format, &parts);
  return text;
}
} // namespace

Recorder::Recorder(Callbacks callbacks) : m_callbacks(std::move(callbacks))
{
}

Recorder::~Recorder()
{
  Stop();
}

void Recorder::Start()
{
  Stop();
  m_stateFile = kodi::vfs::TranslateSpecialProtocol(STATE_FILE);
  Load();
  m_stop = false;
  m_thread = std::thread(&Recorder::Run, this);
}

void Recorder::Stop()
{
  m_stop = true;
  m_condition.notify_all();
  if (m_thread.joinable())
    m_thread.join();
}

std::vector<RecorderTimer> Recorder::GetTimers()
{
  std::lock_guard<std::mutex> lock(m_mutex);
  return m_timers;
}

unsigned int Recorder::AddTimer(RecorderTimer timer)
{
  {
    std::lock_guard<std::mutex> lock(m_mutex);
    timer.id = m_nextTimerId++;
    timer.recording = false;
    timer.error.clear();
    m_timers.push_back(timer);
    Save();
  }
  kodi::Log(ADDON_LOG_INFO, "Recorder - '%s' on %s, %s", timer.title.c_str(), timer.channelName.c_str(),
              LocalTime(timer.start, "%Y-%m-%d %H:%M").c_str());
  m_condition.notify_all();
  m_callbacks.timersChanged();
  return timer.id;
}

bool Recorder::UpdateTimer(const RecorderTimer& timer)
{
  {
    std::lock_guard<std::mutex> lock(m_mutex);
    auto found = std::find_if(m_timers.begin(), m_timers.end(), [&timer](const RecorderTimer& item) { return item.id == timer.id; });
    if (found == m_timers.end() || found->recording)
      return false;
    *found = timer;
    found->error.clear();
    Save();
  }
  m_condition.notify_all();
  m_callbacks.timersChanged();
  return true;
}

bool Recorder::DeleteTimer(unsigned int id)
{
  {
    std::lock_guard<std::mutex> lock(m_mutex);
    auto found = std::find_if(m_timers.begin(), m_timers.end(), [id](const RecorderTimer& item) { return item.id == id; });
    if (found == m_timers.end())
      return false;
    if (found->recording)
      m_cancelTimer = id; // Record() removes it and its partial file
    else
      m_timers.erase(found);
    Save();
  }
  m_condition.notify_all();
  m_callbacks.timersChanged();
  return true;
}

std::vector<RecorderRecording> Recorder::GetRecordings()
{
  std::lock_guard<std::mutex> lock(m_mutex);
  return m_recordings;
}

std::string Recorder::GetRecordingFile(const std::string& id)
{
  std::lock_guard<std::mutex> lock(m_mutex);
  for (const RecorderRecording& recording : m_recordings)
  {
    if (recording.id == id)
      return recording.file;
  }
  return {};
}

bool Recorder::DeleteRecording(const std::string& id)
{
  std::string file;
  {
    std::lock_guard<std::mutex> lock(m_mutex);
    auto found = std::find_if(m_recordings.begin(), m_recordings.end(), [&id](const RecorderRecording& item) { return item.id == id; });
    if (found == m_recordings.end())
      return false;
    file = found->file;
    m_recordings.erase(found);
    Save();
  }
  kodi::vfs::DeleteFile(file);
  kodi::Log(ADDON_LOG_INFO, "Recorder - %s", file.c_str());
  m_callbacks.recordingsChanged();
  return true;
}

void Recorder::SetPlaybackActive(bool active)
{
  std::unique_lock<std::mutex> lock(m_mutex);
  m_playback = active;
  if (!active)
  {
    m_playbackEnded = std::chrono::steady_clock::now();
    return;
  }
  // a segment download in progress ends first (at most a few hundred ms): one connection
  m_condition.wait_for(lock, std::chrono::seconds(3), [this] { return !m_downloading; });
}

bool Recorder::WaitForConnection()
{
  std::unique_lock<std::mutex> lock(m_mutex);
  while (!m_stop)
  {
    const auto idle = std::chrono::steady_clock::now() - m_playbackEnded;
    if (!m_playback && idle > std::chrono::seconds(RESUME_AFTER_PLAYBACK))
    {
      m_downloading = true;
      return true;
    }
    m_condition.wait_for(lock, std::chrono::seconds(1));
  }
  return false;
}

void Recorder::Run()
{
  while (!m_stop)
  {
    RecorderTimer due;
    bool found = false;
    {
      std::unique_lock<std::mutex> lock(m_mutex);
      const time_t now = std::time(nullptr);
      for (const RecorderTimer& timer : m_timers)
      {
        if (timer.error.empty() && now > timer.end + static_cast<time_t>(timer.marginEnd) * 60 + ARCHIVE_DELAY)
        {
          due = timer;
          found = true;
          break;
        }
      }
      if (!found)
      {
        m_condition.wait_for(lock, std::chrono::seconds(30));
        continue;
      }
    }
    Record(due);
  }
}

void Recorder::Record(RecorderTimer timer)
{
  const auto setState = [this, &timer](bool recording, const std::string& error)
  {
    {
      std::lock_guard<std::mutex> lock(m_mutex);
      for (RecorderTimer& item : m_timers)
      {
        if (item.id == timer.id)
        {
          item.recording = recording;
          item.error = error;
        }
      }
      Save();
    }
    m_callbacks.timersChanged();
  };

  std::string folder = m_callbacks.folder();
  const std::string liveUrl = m_callbacks.channelUrl(timer.channelUid);
  const time_t from = timer.start - static_cast<time_t>(timer.marginStart) * 60;
  const time_t to = timer.end + static_cast<time_t>(timer.marginEnd) * 60;
  const std::string playlistUrl = ArchivePlaylistUrl(liveUrl, from, to - from);
  if (folder.empty() || playlistUrl.empty())
  {
    const std::string error = folder.empty() ? "no recording folder set" : "the channel has no archive";
    kodi::Log(ADDON_LOG_ERROR, "Recorder - '%s': %s", timer.title.c_str(), error.c_str());
    kodi::QueueFormattedNotification(QUEUE_ERROR, "%s: %s", timer.title.c_str(), error.c_str());
    setState(false, error);
    return;
  }
  if (folder.back() != '/' && folder.back() != '\\')
    folder += '/';
  const std::string file = folder + SafeFileName(timer.title + " (" + timer.channelName + ") " +
                                                 LocalTime(timer.start, "%Y-%m-%d %H.%M")) + ".ts";

  setState(true, "");
  kodi::Log(ADDON_LOG_INFO, "Recorder - '%s' -> %s", timer.title.c_str(), file.c_str());

  // the archive playlist of the time range
  std::vector<Segment> segments;
  for (int attempt = 0; attempt < SEGMENT_ATTEMPTS && segments.empty() && !m_stop; ++attempt)
  {
    if (!WaitForConnection())
      return;
    std::vector<unsigned char> playlist;
    Download(playlistUrl, playlist, m_stop);
    EndDownload();
    double targetDuration = 0;
    ParsePlaylist(playlistUrl, std::string(playlist.begin(), playlist.end()), segments, targetDuration);
  }
  if (m_stop)
    return;
  if (segments.empty())
  {
    kodi::Log(ADDON_LOG_ERROR, "Recorder - '%s': no archive for this time", timer.title.c_str());
    kodi::QueueFormattedNotification(QUEUE_ERROR, "%s: no archive", timer.title.c_str());
    setState(false, "no archive for this time");
    return;
  }

  kodi::vfs::CFile output;
  if (!output.OpenFileForWrite(file, true))
  {
    kodi::Log(ADDON_LOG_ERROR, "Recorder - cannot write %s", file.c_str());
    kodi::QueueFormattedNotification(QUEUE_ERROR, "%s: cannot write the file", timer.title.c_str());
    setState(false, "cannot write the file");
    return;
  }

  size_t missing = 0;
  bool cancelled = false;
  for (const Segment& segment : segments)
  {
    std::vector<unsigned char> data;
    bool ok = false;
    for (int attempt = 0; attempt < SEGMENT_ATTEMPTS && !ok && !m_stop; ++attempt)
    {
      if (!WaitForConnection())
        break;
      data.clear();
      ok = Download(segment.url, data, m_stop) && !data.empty();
      EndDownload();
      std::lock_guard<std::mutex> lock(m_mutex);
      cancelled = m_cancelTimer == timer.id;
      if (cancelled)
        break;
    }
    if (m_stop || cancelled)
      break;
    if (ok)
      output.Write(data.data(), data.size());
    else
      ++missing;
  }
  output.Close();

  if (m_stop || cancelled)
  {
    // Kodi stops: the timer is recorded again on the next start; deleted: it is gone
    kodi::vfs::DeleteFile(file);
    std::lock_guard<std::mutex> lock(m_mutex);
    for (RecorderTimer& item : m_timers)
      item.recording = false;
    if (cancelled)
    {
      m_cancelTimer = 0;
      m_timers.erase(std::remove_if(m_timers.begin(), m_timers.end(), [&timer](const RecorderTimer& item) { return item.id == timer.id; }),
                     m_timers.end());
    }
    Save();
    return;
  }

  {
    std::lock_guard<std::mutex> lock(m_mutex);
    RecorderRecording recording;
    recording.id = "rec-" + std::to_string(timer.start) + "-" + std::to_string(timer.channelUid);
    recording.channelUid = timer.channelUid;
    recording.channelName = timer.channelName;
    recording.title = timer.title;
    recording.plot = timer.plot;
    recording.start = from;
    recording.duration = static_cast<int>(to - from);
    recording.file = file;
    m_recordings.erase(std::remove_if(m_recordings.begin(), m_recordings.end(), [&recording](const RecorderRecording& item) { return item.id == recording.id; }),
                       m_recordings.end());
    m_recordings.push_back(recording);
    m_timers.erase(std::remove_if(m_timers.begin(), m_timers.end(), [&timer](const RecorderTimer& item) { return item.id == timer.id; }),
                   m_timers.end());
    Save();
  }
  kodi::Log(ADDON_LOG_INFO, "Recorder - '%s' done, %zu segments, %zu missing", timer.title.c_str(),
              segments.size(), missing);
  kodi::QueueFormattedNotification(QUEUE_INFO, "%s: recorded", timer.title.c_str());
  m_callbacks.timersChanged();
  m_callbacks.recordingsChanged();
}

void Recorder::EndDownload()
{
  {
    std::lock_guard<std::mutex> lock(m_mutex);
    m_downloading = false;
  }
  m_condition.notify_all();
}

void Recorder::Load()
{
  std::lock_guard<std::mutex> lock(m_mutex);
  m_timers.clear();
  m_recordings.clear();
  pugi::xml_document document;
  if (!document.load_file(m_stateFile.c_str()))
    return;
  const pugi::xml_node root = document.child("recorder");
  for (const pugi::xml_node node : root.children("timer"))
  {
    RecorderTimer timer;
    timer.id = node.attribute("id").as_uint();
    timer.channelUid = node.attribute("channel").as_int();
    timer.channelName = node.attribute("channelName").as_string();
    timer.title = node.attribute("title").as_string();
    timer.plot = node.attribute("plot").as_string();
    timer.start = static_cast<time_t>(node.attribute("start").as_llong());
    timer.end = static_cast<time_t>(node.attribute("end").as_llong());
    timer.marginStart = node.attribute("marginStart").as_uint();
    timer.marginEnd = node.attribute("marginEnd").as_uint();
    timer.epgUid = node.attribute("epg").as_uint();
    timer.type = node.attribute("type").as_uint();
    timer.error = node.attribute("error").as_string();
    m_nextTimerId = std::max(m_nextTimerId, timer.id + 1);
    m_timers.push_back(timer);
  }
  for (const pugi::xml_node node : root.children("recording"))
  {
    RecorderRecording recording;
    recording.id = node.attribute("id").as_string();
    recording.channelUid = node.attribute("channel").as_int();
    recording.channelName = node.attribute("channelName").as_string();
    recording.title = node.attribute("title").as_string();
    recording.plot = node.attribute("plot").as_string();
    recording.start = static_cast<time_t>(node.attribute("start").as_llong());
    recording.duration = node.attribute("duration").as_int();
    recording.file = node.attribute("file").as_string();
    m_recordings.push_back(recording);
  }
}

void Recorder::Save()
{
  // called with m_mutex held
  pugi::xml_document document;
  pugi::xml_node root = document.append_child("recorder");
  for (const RecorderTimer& timer : m_timers)
  {
    pugi::xml_node node = root.append_child("timer");
    node.append_attribute("id") = timer.id;
    node.append_attribute("channel") = timer.channelUid;
    node.append_attribute("channelName") = timer.channelName.c_str();
    node.append_attribute("title") = timer.title.c_str();
    node.append_attribute("plot") = timer.plot.c_str();
    node.append_attribute("start") = static_cast<long long>(timer.start);
    node.append_attribute("end") = static_cast<long long>(timer.end);
    node.append_attribute("marginStart") = timer.marginStart;
    node.append_attribute("marginEnd") = timer.marginEnd;
    node.append_attribute("epg") = timer.epgUid;
    node.append_attribute("type") = timer.type;
    if (!timer.error.empty())
      node.append_attribute("error") = timer.error.c_str();
  }
  for (const RecorderRecording& recording : m_recordings)
  {
    pugi::xml_node node = root.append_child("recording");
    node.append_attribute("id") = recording.id.c_str();
    node.append_attribute("channel") = recording.channelUid;
    node.append_attribute("channelName") = recording.channelName.c_str();
    node.append_attribute("title") = recording.title.c_str();
    node.append_attribute("plot") = recording.plot.c_str();
    node.append_attribute("start") = static_cast<long long>(recording.start);
    node.append_attribute("duration") = recording.duration;
    node.append_attribute("file") = recording.file.c_str();
  }
  if (!document.save_file(m_stateFile.c_str()))
    kodi::Log(ADDON_LOG_ERROR, "Recorder - cannot write %s", m_stateFile.c_str());
}
