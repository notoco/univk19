/*
 *  Notoco TV: a Kodi TV client for a Flussonic IPTV list (.../mono.m3u8 channels with a DVR
 *  archive). The add-on reads the streams itself (no inputstream add-on), so a channel switch
 *  takes a fraction of a second, the archive is seekable and programmes are recorded from it.
 */

#pragma once

#include "ArchiveReader.h"
#include "Guide.h"
#include "LiveReader.h"
#include "Playlist.h"
#include "Recorder.h"

#include <atomic>
#include <chrono>
#include <condition_variable>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

#include <kodi/addon-instance/PVR.h>

namespace notoco
{

class ATTR_DLL_LOCAL Client : public kodi::addon::CInstancePVRClient
{
public:
  explicit Client(const kodi::addon::IInstanceInfo& instance);
  ~Client() override;

  PVR_ERROR GetCapabilities(kodi::addon::PVRCapabilities& capabilities) override;
  PVR_ERROR GetBackendName(std::string& name) override;
  PVR_ERROR GetBackendVersion(std::string& version) override;

  PVR_ERROR GetChannelsAmount(int& amount) override;
  PVR_ERROR GetChannels(bool radio, kodi::addon::PVRChannelsResultSet& results) override;
#ifdef NOTOCO_PVR_API_8 // Kodi 21: no PVR_SOURCE
  PVR_ERROR GetChannelStreamProperties(const kodi::addon::PVRChannel& channel,
                                       std::vector<kodi::addon::PVRStreamProperty>& properties) override;
#else
  PVR_ERROR GetChannelStreamProperties(const kodi::addon::PVRChannel& channel, PVR_SOURCE source,
                                       std::vector<kodi::addon::PVRStreamProperty>& properties) override;
#endif

  PVR_ERROR GetEPGForChannel(int channelUid, time_t start, time_t end,
                             kodi::addon::PVREPGTagsResultSet& results) override;
  PVR_ERROR IsEPGTagPlayable(const kodi::addon::PVREPGTag& tag, bool& isPlayable) override;
  PVR_ERROR IsEPGTagRecordable(const kodi::addon::PVREPGTag& tag, bool& isRecordable) override;
  PVR_ERROR GetEPGTagStreamProperties(const kodi::addon::PVREPGTag& tag,
                                      std::vector<kodi::addon::PVRStreamProperty>& properties) override;

  bool OpenLiveStream(const kodi::addon::PVRChannel& channel) override;
  void CloseLiveStream() override;
  int ReadLiveStream(unsigned char* buffer, unsigned int size) override;
  int64_t SeekLiveStream(int64_t position, int whence) override;
  int64_t LengthLiveStream() override;
  bool CanPauseStream() override { return true; }
  bool CanSeekStream() override { return m_archive; }
  bool IsRealTimeStream() override { return m_archive ? m_live && m_archiveReader.AtLiveEdge() : true; }
  PVR_ERROR GetStreamTimes(kodi::addon::PVRStreamTimes& times) override;
  PVR_ERROR GetSignalStatus(int channelUid, kodi::addon::PVRSignalStatus& status) override;

  PVR_ERROR GetRecordingsAmount(bool deleted, int& amount) override;
  PVR_ERROR GetRecordings(bool deleted, kodi::addon::PVRRecordingsResultSet& results) override;
  PVR_ERROR GetRecordingStreamProperties(const kodi::addon::PVRRecording& recording,
                                         std::vector<kodi::addon::PVRStreamProperty>& properties) override;
  PVR_ERROR DeleteRecording(const kodi::addon::PVRRecording& recording) override;

  PVR_ERROR GetTimerTypes(std::vector<kodi::addon::PVRTimerType>& types) override;
  PVR_ERROR GetTimersAmount(int& amount) override;
  PVR_ERROR GetTimers(kodi::addon::PVRTimersResultSet& results) override;
  PVR_ERROR AddTimer(const kodi::addon::PVRTimer& timer) override;
  PVR_ERROR UpdateTimer(const kodi::addon::PVRTimer& timer) override;
  PVR_ERROR DeleteTimer(const kodi::addon::PVRTimer& timer, bool forceDelete) override;

private:
  // a copy of the channel with a unique id
  bool FindChannel(int uid, Channel& channel);
  // the programme has started and is still in the channel's archive
  bool InArchive(const kodi::addon::PVREPGTag& tag);
  // Kodi's timer with the channel and the guide data of its programme
  RecorderTimer ToRecorderTimer(const kodi::addon::PVRTimer& timer);
  // the guide thread: loads the guide every GUIDE_REFRESH_HOURS
  void RefreshGuide();
  // asks when the recording of a new timer is downloaded
  void AskDownloadTime(unsigned int timerId, time_t programmeEnd);

  std::string m_playlistPath;
  std::string m_guideUrl;
  std::string m_recordingFolder;
  int m_liveDelay = 10;

  std::mutex m_mutex;
  std::vector<Channel> m_channels;
  Guide m_guide;

  // A programme from the guide plays as a channel stream (Kodi's "EPG as live"): the archive
  // start chosen for that channel waits here until Kodi opens the channel.
  int m_archiveChannel = 0;
  time_t m_archiveFrom = 0;
  std::chrono::steady_clock::time_point m_archiveChosen;

  bool m_archive = false; // read by the ArchiveReader: a programme from the guide or live TV
  bool m_live = false;    // live TV (with time shift when m_archive)
  LiveReader m_liveReader;
  ArchiveReader m_archiveReader;
  std::unique_ptr<Recorder> m_recorder;

  std::thread m_guideThread;
  std::thread m_askThread;
  std::atomic<bool> m_stop{false};
  std::condition_variable m_stopCondition;
};

} // namespace notoco
