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
#include <cstdint>
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
  std::string episodeName;
  std::string plot;
  std::string genre;
  int genreType = 0;
  std::string icon;
  time_t start = 0;
  time_t end = 0;
  unsigned int marginStart = 0; // minutes
  unsigned int marginEnd = 0;   // minutes
  unsigned int epgUid = 0;
  unsigned int type = 0;
  time_t downloadAt = 0; // 0 = as soon as the programme is in the archive, -1 = not decided yet
  bool recording = false;
  std::string error;
};

struct RecorderRecording
{
  std::string id;
  int channelUid = 0;
  std::string channelName;
  std::string title;
  std::string episodeName;
  std::string plot;
  std::string genre;
  int genreType = 0;
  std::string icon;
  time_t start = 0;
  int duration = 0;
  int64_t size = 0;
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

  // loads the saved state and starts the download thread
  void Start();
  // stops the download thread (a running download is repeated on the next start)
  void Stop();

  std::vector<RecorderTimer> GetTimers();
  // a new timer, its id
  unsigned int AddTimer(RecorderTimer timer);
  bool UpdateTimer(const RecorderTimer& timer);
  // removes a timer, a running download of it is cancelled
  bool DeleteTimer(unsigned int id);
  // when the archive of a timer is downloaded (0 as soon as possible)
  void SetDownloadTime(unsigned int id, time_t downloadAt);

  std::vector<RecorderRecording> GetRecordings();
  std::string GetRecordingFile(const std::string& id);
  // removes a recording and its file
  bool DeleteRecording(const std::string& id);

  // Playback owns the provider connection: downloads wait while it is active
  void SetPlaybackActive(bool active);

private:
  // the download thread: the first due timer
  void Run();
  // downloads the archive of a timer into a file, then the .mp4
  void Record(RecorderTimer timer);
  // waits until no stream plays (one connection), then marks a download
  bool WaitForConnection();
  // the marked download ended, playback may take the connection
  void EndDownload();
  // timers and recordings from recorder.xml
  void Load();
  // timers and recordings to recorder.xml (m_mutex held)
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
