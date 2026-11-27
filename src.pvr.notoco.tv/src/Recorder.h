/*
 *  Recordings made from the Flussonic archive.
 *
 *  A timer waits until its programme (with margins) is in the archive, then the DVR segments
 *  of that time range are downloaded into one MPEG-TS file in the folder set by the user.
 *  The provider allows one connection: downloads only run while no stream is played and
 *  pause between segments as soon as playback starts. Timers and finished recordings are
 *  kept in addon_data/pvr.notoco.tv/recorder.xml.
 */

#pragma once

#include <atomic>
#include <chrono>
#include <condition_variable>
#include <ctime>
#include <functional>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

namespace notoco
{

struct RecorderTimer
{
  unsigned int id = 0;
  int channelUid = 0;
  std::string channelName;
  std::string title;
  std::string plot;
  time_t start = 0;
  time_t end = 0;
  unsigned int marginStart = 0; // minutes
  unsigned int marginEnd = 0;   // minutes
  unsigned int epgUid = 0;
  unsigned int type = 0;
  bool recording = false;
  std::string error;
};

struct RecorderRecording
{
  std::string id;
  int channelUid = 0;
  std::string channelName;
  std::string title;
  std::string plot;
  time_t start = 0;
  int duration = 0;
  std::string file;
};

class Recorder
{
public:
  struct Callbacks
  {
    std::function<std::string(int channelUid)> channelUrl; // live URL .../mono.m3u8?token=...
    std::function<std::string()> folder;                   // the user's recording folder
    std::function<void()> timersChanged;
    std::function<void()> recordingsChanged;
  };

  explicit Recorder(Callbacks callbacks);
  ~Recorder();

  void Start();
  void Stop();

  std::vector<RecorderTimer> GetTimers();
  unsigned int AddTimer(RecorderTimer timer);
  bool UpdateTimer(const RecorderTimer& timer);
  bool DeleteTimer(unsigned int id);

  std::vector<RecorderRecording> GetRecordings();
  std::string GetRecordingFile(const std::string& id);
  bool DeleteRecording(const std::string& id);

  // Playback owns the provider connection: downloads wait while it is active
  void SetPlaybackActive(bool active);

private:
  void Run();
  void Record(RecorderTimer timer);
  bool WaitForConnection();
  void EndDownload();
  void Load();
  void Save();

  Callbacks m_callbacks;
  std::string m_stateFile;

  std::thread m_thread;
  std::atomic<bool> m_stop{false};
  std::mutex m_mutex;
  std::condition_variable m_condition;

  std::vector<RecorderTimer> m_timers;
  std::vector<RecorderRecording> m_recordings;
  unsigned int m_nextTimerId = 1;
  unsigned int m_cancelTimer = 0; // the timer being recorded was deleted

  bool m_playback = false;
  bool m_downloading = false;
  std::chrono::steady_clock::time_point m_playbackEnded;
};

} // namespace notoco
