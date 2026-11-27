#include "Utils.h"

#include <cstdio>
#include <mutex>
#include <sstream>

#include <kodi/Filesystem.h>
#include <kodi/General.h>

namespace notoco
{

namespace
{
constexpr int SERVER_FAILURES = 3;

std::mutex serverMutex;
std::string backupServer;
bool useBackup = false;
int serverFailures = 0;

// scheme://host:port of a URL: the start, the length
bool HostPart(const std::string& url, size_t& start, size_t& length)
{
  const size_t scheme = url.find("://");
  if (scheme == std::string::npos)
    return false;
  start = scheme + 3;
  const size_t end = url.find('/', start);
  length = (end == std::string::npos ? url.size() : end) - start;
  return true;
}

bool SegmentTimes(const std::string& url, time_t& start, double& seconds)
{
  const size_t position = url.find("dvr-");
  if (position == std::string::npos)
    return false;
  std::tm parts{};
  int milliseconds = 0;
  if (std::sscanf(url.c_str() + position + 4, "%d/%d/%d/%d/%d/%d-%d", &parts.tm_year, &parts.tm_mon, &parts.tm_mday,
                  &parts.tm_hour, &parts.tm_min, &parts.tm_sec, &milliseconds) != 7)
    return false;
  parts.tm_year -= 1900;
  parts.tm_mon -= 1;
  start = timegm(&parts);
  seconds = milliseconds / 1000.0;
  return true;
}
} // namespace

std::string RedactUrl(const std::string& url)
{
  return url.substr(0, url.find('?'));
}

void SetBackupServer(const std::string& hostPort)
{
  std::lock_guard<std::mutex> lock(serverMutex);
  backupServer = hostPort;
  useBackup = false;
  serverFailures = 0;
}

std::string ServerUrl(const std::string& url)
{
  std::lock_guard<std::mutex> lock(serverMutex);
  size_t start, length;
  if (!useBackup || backupServer.empty() || !HostPart(url, start, length))
    return url;
  return url.substr(0, start) + backupServer + url.substr(start + length);
}

std::string ActiveServer(const std::string& url)
{
  const std::string active = ServerUrl(url);
  size_t start, length;
  return HostPart(active, start, length) ? active.substr(start, length) : std::string();
}

void ReportServer(bool ok)
{
  {
    std::lock_guard<std::mutex> lock(serverMutex);
    if (ok)
    {
      serverFailures = 0;
      return;
    }
    if (backupServer.empty() || ++serverFailures < SERVER_FAILURES)
      return;
    serverFailures = 0;
    useBackup = !useBackup;
  }
  kodi::Log(ADDON_LOG_WARNING, "Server - %d failures, switched to the %s server", SERVER_FAILURES,
            useBackup ? "backup" : "main");
  kodi::QueueNotification(QUEUE_WARNING, "Notoco TV", kodi::addon::GetLocalizedString(useBackup ? 30020 : 30021));
}

bool Download(const std::string& url, std::vector<unsigned char>& data, const std::atomic<bool>& stop)
{
  kodi::vfs::CFile file;
  if (!file.OpenFile(ServerUrl(url), ADDON_READ_NO_CACHE))
    return false;
  unsigned char chunk[READ_CHUNK];
  ssize_t length;
  while (!stop && (length = file.Read(chunk, sizeof(chunk))) > 0)
    data.insert(data.end(), chunk, chunk + length);
  file.Close();
  return !stop && length == 0;
}

bool ParsePlaylist(const std::string& playlistUrl, const std::string& content, std::vector<Segment>& segments,
                   double& targetDuration)
{
  const std::string path = playlistUrl.substr(0, playlistUrl.find('?'));
  const std::string directory = path.substr(0, path.rfind('/') + 1);
  const std::string host = path.substr(0, path.find('/', path.find("://") + 3));

  int64_t sequence = 0;
  double duration = 0;
  bool segmentFollows = false;
  std::istringstream stream(content);
  std::string line;
  while (std::getline(stream, line))
  {
    if (!line.empty() && line.back() == '\r')
      line.pop_back();
    if (line.empty())
      continue;

    if (line.rfind("#EXT-X-MEDIA-SEQUENCE:", 0) == 0)
      sequence = std::stoll(line.substr(22));
    else if (line.rfind("#EXT-X-TARGETDURATION:", 0) == 0)
      targetDuration = std::stod(line.substr(22));
    else if (line.rfind("#EXTINF:", 0) == 0)
    {
      segmentFollows = true;
      duration = std::stod(line.substr(8));
    }
    else if (line[0] != '#' && segmentFollows)
    {
      Segment segment;
      segment.sequence = sequence++;
      segment.url = line.rfind("http", 0) == 0 ? line : (line[0] == '/' ? host : directory) + line;
      segment.duration = duration;
      double named;
      if (SegmentTimes(segment.url, segment.start, named) && named > 0)
        segment.duration = named;
      segments.push_back(segment);
      segmentFollows = false;
    }
  }
  return !segments.empty();
}

std::string ArchivePlaylistUrl(const std::string& liveUrl, time_t from, time_t seconds)
{
  const size_t mono = liveUrl.find("/mono.m3u8");
  if (mono == std::string::npos)
    return {};
  return liveUrl.substr(0, mono) + "/mono-" + std::to_string(from) + "-" + std::to_string(seconds) + ".m3u8" +
         liveUrl.substr(mono + 10);
}

} // namespace notoco
