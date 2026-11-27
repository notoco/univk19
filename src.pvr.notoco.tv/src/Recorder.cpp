#include "Recorder.h"

#include "Utils.h"

#include <algorithm>
#include <cstdio>
#include <cstring>
#include <sstream>

#include <spawn.h>
#include <sys/statvfs.h>
#include <sys/wait.h>

#include <kodi/Filesystem.h>
#include <kodi/General.h>
#include <pugixml.hpp>

using namespace notoco;

namespace
{
constexpr time_t ARCHIVE_DELAY = 60;      // seconds after the end before the archive is complete
constexpr int RESUME_AFTER_PLAYBACK = 30; // seconds without playback before downloads resume
constexpr int SEGMENT_ATTEMPTS = 3;
const char* const STATE_FILE = "special://profile/addon_data/pvr.notoco.tv/recorder.xml";
// FFmpeg Tools from the CoreELEC repository: recordings become .mp4 (no re-encoding)
const char* const FFMPEG = "special://home/addons/tools.ffmpeg-tools/bin/ffmpeg";

// Free bytes of a local folder, -1 when unknown (a network path)
int64_t FreeSpace(const std::string& folder)
{
  struct statvfs info;
  if (folder.empty() || folder[0] != '/' || statvfs(folder.c_str(), &info) != 0)
    return -1;
  return static_cast<int64_t>(info.f_bavail) * static_cast<int64_t>(info.f_frsize);
}

constexpr int64_t SPACE_RESERVE = 200 * 1024 * 1024;

// The .ts recording as .mp4 with the same streams; the path of the result, or the .ts on failure.
// Local folders only (FFmpeg does not read Kodi's smb:// or nfs:// paths).
std::string ToMp4(const std::string& ts)
{
  const std::string ffmpeg = kodi::vfs::TranslateSpecialProtocol(FFMPEG);
  if (ts.empty() || ts[0] != '/' || !kodi::vfs::FileExists(ffmpeg))
    return ts;
  const std::string mp4 = ts.substr(0, ts.size() - 3) + ".mp4";
  kodi::vfs::FileStatus tsStatus;
  const int64_t available = FreeSpace(ts.substr(0, ts.rfind('/') + 1));
  if (kodi::vfs::StatFile(ts, tsStatus) && available >= 0 &&
      available < static_cast<int64_t>(tsStatus.GetSize()) + SPACE_RESERVE)
  {
    kodi::Log(ADDON_LOG_WARNING, "Recorder - no space for the .mp4 of %s, the .ts stays", ts.c_str());
    return ts;
  }
  // clang-format off
  const char* const arguments[] = {ffmpeg.c_str(), "-nostdin", "-v", "error", "-y", "-i", ts.c_str(),
                                   "-map", "0", "-c", "copy", "-movflags", "+faststart", mp4.c_str(), nullptr};
  // clang-format on
  pid_t process;
  int status = -1;
  if (posix_spawn(&process, ffmpeg.c_str(), nullptr, nullptr, const_cast<char* const*>(arguments), environ) != 0 ||
      waitpid(process, &status, 0) < 0 || !WIFEXITED(status) || WEXITSTATUS(status) != 0)
  {
    kodi::Log(ADDON_LOG_ERROR, "Recorder - FFmpeg failed on %s, the .ts stays", ts.c_str());
    kodi::vfs::DeleteFile(mp4);
    return ts;
  }
  kodi::vfs::DeleteFile(ts);
  return mp4;
}

void Notify(int messageId, const std::string& title)
{
  kodi::QueueFormattedNotification(messageId == 30022 ? QUEUE_INFO : QUEUE_ERROR,
                                   kodi::addon::GetLocalizedString(messageId).c_str(), title.c_str());
}

template <typename Items, typename Id>
void EraseById(Items& items, const Id& id)
{
  items.erase(std::remove_if(items.begin(), items.end(), [&id](const auto& item) { return item.id == id; }),
              items.end());
}

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
    auto found = std::find_if(m_timers.begin(), m_timers.end(),
                              [&timer](const RecorderTimer& item) { return item.id == timer.id; });
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

void Recorder::SetDownloadTime(unsigned int id, time_t downloadAt)
{
  {
    std::lock_guard<std::mutex> lock(m_mutex);
    for (RecorderTimer& timer : m_timers)
    {
      if (timer.id == id)
        timer.downloadAt = downloadAt;
    }
    Save();
  }
  kodi::Log(ADDON_LOG_INFO, "Recorder - timer %u downloads at %lld", id, static_cast<long long>(downloadAt));
  m_condition.notify_all();
}

bool Recorder::DeleteTimer(unsigned int id)
{
  {
    std::lock_guard<std::mutex> lock(m_mutex);
    auto found =
        std::find_if(m_timers.begin(), m_timers.end(), [id](const RecorderTimer& item) { return item.id == id; });
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
    auto found = std::find_if(m_recordings.begin(), m_recordings.end(),
                              [&id](const RecorderRecording& item) { return item.id == id; });
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
        if (timer.error.empty() && timer.downloadAt >= 0 && now >= timer.downloadAt &&
            now > timer.end + static_cast<time_t>(timer.marginEnd) * 60 + ARCHIVE_DELAY)
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
    Notify(folder.empty() ? 30026 : 30023, timer.title);
    setState(false, error);
    return;
  }
  if (folder.back() != '/' && folder.back() != '\\')
    folder += '/';
  const std::string name = timer.episodeName.empty() ? timer.title : timer.title + " - " + timer.episodeName;
  const std::string file =
      folder + SafeFileName(name + " (" + timer.channelName + ") " + LocalTime(timer.start, "%Y-%m-%d %H.%M")) + ".ts";

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
    Notify(30023, timer.title);
    setState(false, "no archive for this time");
    return;
  }

  kodi::vfs::CFile output;
  if (!output.OpenFileForWrite(file, true))
  {
    kodi::Log(ADDON_LOG_ERROR, "Recorder - cannot write %s", file.c_str());
    Notify(30025, timer.title);
    setState(false, "cannot write the file");
    return;
  }

  size_t missing = 0;
  bool cancelled = false;
  bool spaceChecked = false;
  bool noSpace = false;
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
    if (ok && !spaceChecked && segment.duration > 0)
    {
      // the size of the whole recording from its first segment, the .mp4 copy needs as much again
      spaceChecked = true;
      double seconds = 0;
      for (const Segment& item : segments)
        seconds += item.duration;
      const int64_t needed = static_cast<int64_t>(data.size() / segment.duration * seconds);
      const int64_t available = FreeSpace(folder);
      if (available >= 0 && available < needed + SPACE_RESERVE)
      {
        kodi::Log(ADDON_LOG_ERROR, "Recorder - '%s' needs %lld bytes, %lld free", timer.title.c_str(),
                  static_cast<long long>(needed), static_cast<long long>(available));
        kodi::QueueFormattedNotification(QUEUE_ERROR, kodi::addon::GetLocalizedString(30024).c_str(),
                                         timer.title.c_str(), needed / 1e9, available / 1e9);
        noSpace = true;
        break;
      }
    }
    if (ok)
      output.Write(data.data(), data.size());
    else
      ++missing;
  }
  output.Close();
  if (noSpace)
  {
    kodi::vfs::DeleteFile(file);
    setState(false, "not enough disk space");
    return;
  }

  std::string result = file;
  if (!m_stop && !cancelled)
    result = ToMp4(file);

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
      EraseById(m_timers, timer.id);
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
    recording.episodeName = timer.episodeName;
    recording.plot = timer.plot;
    recording.genre = timer.genre;
    recording.genreType = timer.genreType;
    recording.icon = timer.icon;
    recording.start = from;
    recording.duration = static_cast<int>(to - from);
    kodi::vfs::FileStatus status;
    if (kodi::vfs::StatFile(result, status))
      recording.size = static_cast<int64_t>(status.GetSize());
    recording.file = result;
    EraseById(m_recordings, recording.id);
    m_recordings.push_back(recording);
    EraseById(m_timers, timer.id);
    Save();
  }
  kodi::Log(ADDON_LOG_INFO, "Recorder - '%s' done (%s), %zu segments, %zu missing", timer.title.c_str(), result.c_str(),
            segments.size(), missing);
  Notify(30022, timer.title);
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
    timer.episodeName = node.attribute("episode").as_string();
    timer.genre = node.attribute("genre").as_string();
    timer.genreType = node.attribute("genreType").as_int();
    timer.icon = node.attribute("icon").as_string();
    timer.start = static_cast<time_t>(node.attribute("start").as_llong());
    timer.end = static_cast<time_t>(node.attribute("end").as_llong());
    timer.marginStart = node.attribute("marginStart").as_uint();
    timer.marginEnd = node.attribute("marginEnd").as_uint();
    timer.epgUid = node.attribute("epg").as_uint();
    timer.type = node.attribute("type").as_uint();
    timer.downloadAt = std::max<time_t>(0, static_cast<time_t>(node.attribute("downloadAt").as_llong()));
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
    recording.episodeName = node.attribute("episode").as_string();
    recording.genre = node.attribute("genre").as_string();
    recording.genreType = node.attribute("genreType").as_int();
    recording.icon = node.attribute("icon").as_string();
    recording.size = node.attribute("size").as_llong();
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
    node.append_attribute("episode") = timer.episodeName.c_str();
    node.append_attribute("genre") = timer.genre.c_str();
    node.append_attribute("genreType") = timer.genreType;
    node.append_attribute("icon") = timer.icon.c_str();
    node.append_attribute("start") = static_cast<long long>(timer.start);
    node.append_attribute("end") = static_cast<long long>(timer.end);
    node.append_attribute("marginStart") = timer.marginStart;
    node.append_attribute("marginEnd") = timer.marginEnd;
    node.append_attribute("epg") = timer.epgUid;
    node.append_attribute("type") = timer.type;
    if (timer.downloadAt != 0)
      node.append_attribute("downloadAt") = static_cast<long long>(timer.downloadAt);
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
    node.append_attribute("episode") = recording.episodeName.c_str();
    node.append_attribute("genre") = recording.genre.c_str();
    node.append_attribute("genreType") = recording.genreType;
    node.append_attribute("icon") = recording.icon.c_str();
    node.append_attribute("size") = static_cast<long long>(recording.size);
    node.append_attribute("start") = static_cast<long long>(recording.start);
    node.append_attribute("duration") = recording.duration;
    node.append_attribute("file") = recording.file.c_str();
  }
  if (!document.save_file(m_stateFile.c_str()))
    kodi::Log(ADDON_LOG_ERROR, "Recorder - cannot write %s", m_stateFile.c_str());
}
