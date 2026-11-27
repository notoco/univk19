#include "Utils.h"

#include <cstdio>
#include <sstream>

#include <kodi/Filesystem.h>

namespace notoco
{

namespace
{
constexpr size_t READ_CHUNK = 64 * 1024;

bool SegmentTimes(const std::string& url, time_t& start, double& seconds)
{
  const size_t position = url.find("dvr-");
  if (position == std::string::npos)
    return false;
  std::tm parts{};
  int milliseconds = 0;
  if (std::sscanf(url.c_str() + position + 4, "%d/%d/%d/%d/%d/%d-%d", &parts.tm_year, &parts.tm_mon,
                  &parts.tm_mday, &parts.tm_hour, &parts.tm_min, &parts.tm_sec, &milliseconds) != 7)
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

bool Download(const std::string& url, std::vector<unsigned char>& data, const std::atomic<bool>& stop)
{
  kodi::vfs::CFile file;
  if (!file.OpenFile(url, ADDON_READ_NO_CACHE))
    return false;
  unsigned char chunk[READ_CHUNK];
  ssize_t length;
  while (!stop && (length = file.Read(chunk, sizeof(chunk))) > 0)
    data.insert(data.end(), chunk, chunk + length);
  file.Close();
  return !stop && length == 0;
}

bool ParsePlaylist(const std::string& playlistUrl,
                   const std::string& content,
                   std::vector<Segment>& segments,
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
