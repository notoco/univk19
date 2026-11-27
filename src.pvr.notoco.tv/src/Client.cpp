#include "Client.h"

#include "Utils.h"

#include <kodi/General.h>

namespace notoco
{

namespace
{
constexpr unsigned int TIMER_MANUAL = 1;
constexpr unsigned int TIMER_GUIDE = 2;
constexpr time_t ARCHIVE_LEAD = 60;          // an archive programme starts a minute early
constexpr int ARCHIVE_CHOICE_SECONDS = 30;   // the chosen archive start waits this long for Kodi
constexpr int GUIDE_REFRESH_HOURS = 12;
} // namespace

Client::Client(const kodi::addon::IInstanceInfo& instance) : CInstancePVRClient(instance)
{
  m_playlistPath = kodi::addon::GetSettingString("playlist");
  m_guideUrl = kodi::addon::GetSettingString("guideUrl");
  m_recordingFolder = kodi::addon::GetSettingString("recordingFolder");

  if (!m_playlistPath.empty())
    LoadPlaylist(m_playlistPath, m_channels);

  Recorder::Callbacks callbacks;
  callbacks.channelUrl = [this](int channelUid)
  {
    Channel channel;
    return FindChannel(channelUid, channel) ? channel.url : std::string();
  };
  callbacks.folder = [this] { return m_recordingFolder; };
  callbacks.timersChanged = [this] { TriggerTimerUpdate(); };
  callbacks.recordingsChanged = [this] { TriggerRecordingUpdate(); };
  m_recorder = std::make_unique<Recorder>(callbacks);
  m_recorder->Start();

  m_guideThread = std::thread([this] { RefreshGuide(); });
}

Client::~Client()
{
  m_stop = true;
  m_stopCondition.notify_all();
  if (m_guideThread.joinable())
    m_guideThread.join();
  m_recorder->Stop();
  m_liveReader.Close();
  m_archiveReader.Close();
}

void Client::RefreshGuide()
{
  while (!m_stop)
  {
    std::vector<Channel> channels;
    {
      std::lock_guard<std::mutex> lock(m_mutex);
      channels = m_channels;
    }
    if (m_guide.Load(m_guideUrl, channels))
    {
      for (const Channel& channel : channels)
        TriggerEpgUpdate(static_cast<unsigned int>(channel.uid));
    }
    std::unique_lock<std::mutex> lock(m_mutex);
    m_stopCondition.wait_for(lock, std::chrono::hours(GUIDE_REFRESH_HOURS), [this] { return m_stop.load(); });
  }
}

bool Client::FindChannel(int uid, Channel& channel)
{
  std::lock_guard<std::mutex> lock(m_mutex);
  for (const Channel& item : m_channels)
  {
    if (item.uid == uid)
    {
      channel = item;
      return true;
    }
  }
  return false;
}

PVR_ERROR Client::GetCapabilities(kodi::addon::PVRCapabilities& capabilities)
{
  capabilities.SetSupportsTV(true);
  capabilities.SetSupportsEPG(true);
  capabilities.SetSupportsRecordings(true);
  capabilities.SetSupportsRecordingsDelete(true);
  capabilities.SetSupportsTimers(true);
  capabilities.SetHandlesInputStream(true);
  return PVR_ERROR_NO_ERROR;
}

PVR_ERROR Client::GetBackendName(std::string& name)
{
  name = "Notoco TV";
  return PVR_ERROR_NO_ERROR;
}

PVR_ERROR Client::GetBackendVersion(std::string& version)
{
  version = STR(NOTOCO_VERSION);
  return PVR_ERROR_NO_ERROR;
}

/***************************************************************************
 * Channels
 **************************************************************************/

PVR_ERROR Client::GetChannelsAmount(int& amount)
{
  std::lock_guard<std::mutex> lock(m_mutex);
  amount = static_cast<int>(m_channels.size());
  return PVR_ERROR_NO_ERROR;
}

PVR_ERROR Client::GetChannels(bool radio, kodi::addon::PVRChannelsResultSet& results)
{
  if (radio)
    return PVR_ERROR_NO_ERROR;
  std::lock_guard<std::mutex> lock(m_mutex);
  for (const Channel& item : m_channels)
  {
    kodi::addon::PVRChannel channel;
    channel.SetUniqueId(static_cast<unsigned int>(item.uid));
    channel.SetChannelNumber(static_cast<unsigned int>(item.number));
    channel.SetChannelName(item.name);
    channel.SetIconPath(item.logo);
    channel.SetIsRadio(false);
    results.Add(channel);
  }
  return PVR_ERROR_NO_ERROR;
}

PVR_ERROR Client::GetChannelStreamProperties(const kodi::addon::PVRChannel& channel,
                                             PVR_SOURCE,
                                             std::vector<kodi::addon::PVRStreamProperty>& properties)
{
  // No stream URL: Kodi plays the channel through OpenLiveStream()/ReadLiveStream().
  // Kodi resolves a guide programme played as live twice (EPG_AS_LIVE, then DEFAULT): the
  // archive choice lives until OpenLiveStream(), not per call.
  std::lock_guard<std::mutex> lock(m_mutex);
  const bool archive = static_cast<int>(channel.GetUniqueId()) == m_archiveChannel;
  properties.emplace_back(PVR_STREAM_PROPERTY_MIMETYPE, "video/mp2t");
  properties.emplace_back(PVR_STREAM_PROPERTY_ISREALTIMESTREAM, archive ? "false" : "true");
  return PVR_ERROR_NO_ERROR;
}

/***************************************************************************
 * Guide and archive
 **************************************************************************/

PVR_ERROR Client::GetEPGForChannel(int channelUid, time_t start, time_t end, kodi::addon::PVREPGTagsResultSet& results)
{
  for (const Programme& programme : m_guide.Get(channelUid, start, end))
  {
    kodi::addon::PVREPGTag tag;
    tag.SetUniqueBroadcastId(static_cast<unsigned int>(programme.start));
    tag.SetUniqueChannelId(static_cast<unsigned int>(channelUid));
    tag.SetTitle(programme.title);
    tag.SetEpisodeName(programme.episodeName);
    tag.SetPlot(programme.plot);
    tag.SetStartTime(programme.start);
    tag.SetEndTime(programme.end);
    tag.SetIconPath(programme.icon);
    tag.SetGenreType(EPG_GENRE_USE_STRING);
    tag.SetGenreDescription(programme.genre);
    tag.SetSeriesNumber(EPG_TAG_INVALID_SERIES_EPISODE);
    tag.SetEpisodeNumber(EPG_TAG_INVALID_SERIES_EPISODE);
    tag.SetEpisodePartNumber(EPG_TAG_INVALID_SERIES_EPISODE);
    tag.SetFlags(EPG_TAG_FLAG_UNDEFINED);
    results.Add(tag);
  }
  return PVR_ERROR_NO_ERROR;
}

PVR_ERROR Client::IsEPGTagPlayable(const kodi::addon::PVREPGTag& tag, bool& isPlayable)
{
  Channel channel;
  const time_t now = std::time(nullptr);
  isPlayable = FindChannel(static_cast<int>(tag.GetUniqueChannelId()), channel) && channel.archiveDays > 0 &&
               !ArchivePlaylistUrl(channel.url, 0, 0).empty() && tag.GetStartTime() < now &&
               tag.GetStartTime() > now - static_cast<time_t>(channel.archiveDays) * 86400;
  return PVR_ERROR_NO_ERROR;
}

PVR_ERROR Client::GetEPGTagStreamProperties(const kodi::addon::PVREPGTag& tag,
                                            std::vector<kodi::addon::PVRStreamProperty>& properties)
{
  std::lock_guard<std::mutex> lock(m_mutex);
  m_archiveChannel = static_cast<int>(tag.GetUniqueChannelId());
  m_archiveFrom = tag.GetStartTime() - ARCHIVE_LEAD;
  m_archiveChosen = std::chrono::steady_clock::now();
  // played as the channel: Kodi's OSD, seek bar and the following programmes keep working
  properties.emplace_back(PVR_STREAM_PROPERTY_EPGPLAYBACKASLIVE, "true");
  return PVR_ERROR_NO_ERROR;
}

/***************************************************************************
 * Stream
 **************************************************************************/

bool Client::OpenLiveStream(const kodi::addon::PVRChannel& kodiChannel)
{
  Channel channel;
  if (!FindChannel(static_cast<int>(kodiChannel.GetUniqueId()), channel))
    return false;

  time_t archiveFrom = 0;
  {
    std::lock_guard<std::mutex> lock(m_mutex);
    if (m_archiveChannel == channel.uid &&
        std::chrono::steady_clock::now() - m_archiveChosen < std::chrono::seconds(ARCHIVE_CHOICE_SECONDS))
      archiveFrom = m_archiveFrom;
    m_archiveChannel = 0;
  }

  // one connection: downloads of recordings stop, the other reader is closed first
  m_recorder->SetPlaybackActive(true);
  m_archive = archiveFrom > 0;
  if (m_archive)
  {
    m_liveReader.Close();
    kodi::Log(ADDON_LOG_INFO, "Client - archive of %s from %lld", channel.name.c_str(), static_cast<long long>(archiveFrom));
    return m_archiveReader.Open(channel.url, archiveFrom);
  }
  m_archiveReader.Close();
  kodi::Log(ADDON_LOG_INFO, "Client - live %s", channel.name.c_str());
  return m_liveReader.Open(channel.url);
}

void Client::CloseLiveStream()
{
  m_liveReader.Close();
  m_archiveReader.Close();
  m_recorder->SetPlaybackActive(false);
}

int Client::ReadLiveStream(unsigned char* buffer, unsigned int size)
{
  return m_archive ? m_archiveReader.Read(buffer, size) : m_liveReader.Read(buffer, size);
}

int64_t Client::SeekLiveStream(int64_t position, int whence)
{
  return m_archive ? m_archiveReader.Seek(position, whence) : -1;
}

int64_t Client::LengthLiveStream()
{
  return m_archive ? m_archiveReader.Length() : -1;
}

PVR_ERROR Client::GetStreamTimes(kodi::addon::PVRStreamTimes& times)
{
  // the real UTC time of the stream start: the OSD shows the programme actually playing
  time_t start;
  int64_t end;
  if (!(m_archive ? m_archiveReader.GetTimes(start, end) : m_liveReader.GetTimes(start, end)))
    return PVR_ERROR_NOT_IMPLEMENTED;
  times.SetStartTime(start);
  times.SetPTSStart(0);
  times.SetPTSBegin(0);
  times.SetPTSEnd(end);
  return PVR_ERROR_NO_ERROR;
}

/***************************************************************************
 * Recordings
 **************************************************************************/

PVR_ERROR Client::GetRecordingsAmount(bool deleted, int& amount)
{
  amount = deleted ? 0 : static_cast<int>(m_recorder->GetRecordings().size());
  return PVR_ERROR_NO_ERROR;
}

PVR_ERROR Client::GetRecordings(bool deleted, kodi::addon::PVRRecordingsResultSet& results)
{
  if (deleted)
    return PVR_ERROR_NO_ERROR;
  for (const RecorderRecording& item : m_recorder->GetRecordings())
  {
    kodi::addon::PVRRecording recording;
    recording.SetRecordingId(item.id);
    recording.SetTitle(item.title);
    recording.SetPlot(item.plot);
    recording.SetChannelName(item.channelName);
    recording.SetChannelUid(item.channelUid);
    recording.SetChannelType(PVR_RECORDING_CHANNEL_TYPE_TV);
    recording.SetRecordingTime(item.start);
    recording.SetDuration(item.duration);
    results.Add(recording);
  }
  return PVR_ERROR_NO_ERROR;
}

PVR_ERROR Client::GetRecordingStreamProperties(const kodi::addon::PVRRecording& recording,
                                               std::vector<kodi::addon::PVRStreamProperty>& properties)
{
  const std::string file = m_recorder->GetRecordingFile(recording.GetRecordingId());
  if (file.empty())
    return PVR_ERROR_SERVER_ERROR;
  properties.emplace_back(PVR_STREAM_PROPERTY_STREAMURL, file);
  properties.emplace_back(PVR_STREAM_PROPERTY_MIMETYPE, "video/mp2t");
  properties.emplace_back(PVR_STREAM_PROPERTY_ISREALTIMESTREAM, "false");
  return PVR_ERROR_NO_ERROR;
}

PVR_ERROR Client::DeleteRecording(const kodi::addon::PVRRecording& recording)
{
  return m_recorder->DeleteRecording(recording.GetRecordingId()) ? PVR_ERROR_NO_ERROR : PVR_ERROR_FAILED;
}

/***************************************************************************
 * Timers: recordings from the archive after the programme (see Recorder.h)
 **************************************************************************/

PVR_ERROR Client::GetTimerTypes(std::vector<kodi::addon::PVRTimerType>& types)
{
  const uint64_t common = PVR_TIMER_TYPE_SUPPORTS_CHANNELS | PVR_TIMER_TYPE_SUPPORTS_START_TIME |
                          PVR_TIMER_TYPE_SUPPORTS_END_TIME | PVR_TIMER_TYPE_SUPPORTS_START_MARGIN |
                          PVR_TIMER_TYPE_SUPPORTS_END_MARGIN;
  kodi::addon::PVRTimerType manual;
  manual.SetId(TIMER_MANUAL);
  manual.SetAttributes(PVR_TIMER_TYPE_IS_MANUAL | common);
  manual.SetDescription(kodi::addon::GetLocalizedString(30011));
  types.emplace_back(manual);

  kodi::addon::PVRTimerType guide;
  guide.SetId(TIMER_GUIDE);
  guide.SetAttributes(PVR_TIMER_TYPE_REQUIRES_EPG_TAG_ON_CREATE | common);
  guide.SetDescription(kodi::addon::GetLocalizedString(30010));
  types.emplace_back(guide);
  return PVR_ERROR_NO_ERROR;
}

PVR_ERROR Client::GetTimersAmount(int& amount)
{
  amount = static_cast<int>(m_recorder->GetTimers().size());
  return PVR_ERROR_NO_ERROR;
}

PVR_ERROR Client::GetTimers(kodi::addon::PVRTimersResultSet& results)
{
  for (const RecorderTimer& item : m_recorder->GetTimers())
  {
    kodi::addon::PVRTimer timer;
    timer.SetClientIndex(item.id);
    timer.SetTimerType(item.type);
    timer.SetClientChannelUid(item.channelUid);
    timer.SetTitle(item.title);
    timer.SetSummary(item.plot);
    timer.SetStartTime(item.start);
    timer.SetEndTime(item.end);
    timer.SetMarginStart(item.marginStart);
    timer.SetMarginEnd(item.marginEnd);
    timer.SetEPGUid(item.epgUid);
    timer.SetState(!item.error.empty() ? PVR_TIMER_STATE_ERROR
                                       : item.recording ? PVR_TIMER_STATE_RECORDING : PVR_TIMER_STATE_SCHEDULED);
    results.Add(timer);
  }
  return PVR_ERROR_NO_ERROR;
}

RecorderTimer Client::ToRecorderTimer(const kodi::addon::PVRTimer& timer)
{
  RecorderTimer item;
  item.id = timer.GetClientIndex();
  item.type = timer.GetTimerType();
  item.channelUid = timer.GetClientChannelUid();
  item.title = timer.GetTitle();
  item.plot = timer.GetSummary();
  item.start = timer.GetStartTime();
  item.end = timer.GetEndTime();
  item.marginStart = timer.GetMarginStart();
  item.marginEnd = timer.GetMarginEnd();
  item.epgUid = timer.GetEPGUid();
  Channel channel;
  if (FindChannel(item.channelUid, channel))
  {
    item.channelName = channel.name;
    if (item.title.empty())
      item.title = channel.name;
  }
  return item;
}

PVR_ERROR Client::AddTimer(const kodi::addon::PVRTimer& timer)
{
  RecorderTimer item = ToRecorderTimer(timer);
  if (item.channelName.empty())
    return PVR_ERROR_INVALID_PARAMETERS;
  m_recorder->AddTimer(item);
  return PVR_ERROR_NO_ERROR;
}

PVR_ERROR Client::UpdateTimer(const kodi::addon::PVRTimer& timer)
{
  return m_recorder->UpdateTimer(ToRecorderTimer(timer)) ? PVR_ERROR_NO_ERROR : PVR_ERROR_FAILED;
}

PVR_ERROR Client::DeleteTimer(const kodi::addon::PVRTimer& timer, bool)
{
  return m_recorder->DeleteTimer(timer.GetClientIndex()) ? PVR_ERROR_NO_ERROR : PVR_ERROR_FAILED;
}

} // namespace notoco
