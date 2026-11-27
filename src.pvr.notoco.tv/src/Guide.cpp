#include "Guide.h"

#include "Utils.h"

#include <algorithm>
#include <atomic>
#include <cctype>
#include <cstdio>

#include <kodi/Filesystem.h>
#include <kodi/General.h>
#include <pugixml.hpp>
#include <zlib.h>

namespace notoco
{

namespace
{
const char* const CACHE_FILE = "special://profile/addon_data/pvr.notoco.tv/guide.xml";

bool Gunzip(const std::vector<unsigned char>& input, std::string& output)
{
  z_stream stream{};
  if (inflateInit2(&stream, 16 + MAX_WBITS) != Z_OK)
    return false;
  stream.next_in = const_cast<unsigned char*>(input.data());
  stream.avail_in = static_cast<uInt>(input.size());
  char chunk[256 * 1024];
  int result = Z_OK;
  while (result == Z_OK)
  {
    stream.next_out = reinterpret_cast<Bytef*>(chunk);
    stream.avail_out = sizeof(chunk);
    result = inflate(&stream, Z_NO_FLUSH);
    output.append(chunk, sizeof(chunk) - stream.avail_out);
  }
  inflateEnd(&stream);
  return result == Z_STREAM_END;
}

// XMLTV time: 20261127180000 +0100
time_t ParseTime(const char* text)
{
  std::tm parts{};
  char sign = '+';
  int zoneHours = 0;
  int zoneMinutes = 0;
  const int read = std::sscanf(text, "%4d%2d%2d%2d%2d%2d %c%2d%2d", &parts.tm_year, &parts.tm_mon, &parts.tm_mday,
                               &parts.tm_hour, &parts.tm_min, &parts.tm_sec, &sign, &zoneHours, &zoneMinutes);
  if (read < 6)
    return 0;
  parts.tm_year -= 1900;
  parts.tm_mon -= 1;
  time_t time = timegm(&parts);
  if (read == 9)
    time -= (sign == '-' ? -1 : 1) * (zoneHours * 3600 + zoneMinutes * 60);
  return time;
}

std::string Normalized(const std::string& name)
{
  std::string result;
  for (const char character : name)
  {
    if (!std::isspace(static_cast<unsigned char>(character)))
      result += static_cast<char>(std::tolower(static_cast<unsigned char>(character)));
  }
  return result;
}
} // namespace

bool Guide::Load(const std::string& url, const std::vector<Channel>& channels)
{
  const std::atomic<bool> stop{false};
  const std::string cache = kodi::vfs::TranslateSpecialProtocol(CACHE_FILE);
  std::vector<unsigned char> data;
  std::string xml;
  if (!url.empty() && Download(url, data, stop) && !data.empty())
  {
    if (data.size() > 2 && data[0] == 0x1F && data[1] == 0x8B)
    {
      if (!Gunzip(data, xml))
        xml.clear();
    }
    else
      xml.assign(data.begin(), data.end());
    if (!xml.empty())
    {
      kodi::vfs::CFile file;
      if (file.OpenFileForWrite(cache, true))
        file.Write(xml.data(), xml.size());
    }
  }
  if (xml.empty())
  {
    kodi::Log(ADDON_LOG_WARNING, "Guide - %s not read, using the last copy", RedactUrl(url).c_str());
    data.clear();
    if (Download(cache, data, stop))
      xml.assign(data.begin(), data.end());
  }

  pugi::xml_document document;
  if (xml.empty() || !document.load_buffer(xml.data(), xml.size()))
  {
    kodi::Log(ADDON_LOG_ERROR, "Guide - no guide");
    return false;
  }

  // XMLTV channel id -> channel uid: tvg-id first, else the display name
  std::map<std::string, int> byId;
  std::map<std::string, int> byName;
  for (const Channel& channel : channels)
  {
    if (!channel.tvgId.empty())
      byId[channel.tvgId] = channel.uid;
    byName[Normalized(channel.tvgName.empty() ? channel.name : channel.tvgName)] = channel.uid;
    byName.emplace(Normalized(channel.name), channel.uid);
  }
  std::map<std::string, int> guideChannels;
  const pugi::xml_node tv = document.child("tv");
  for (const pugi::xml_node node : tv.children("channel"))
  {
    const std::string id = node.attribute("id").as_string();
    auto found = byId.find(id);
    if (found == byId.end())
    {
      for (const pugi::xml_node name : node.children("display-name"))
      {
        found = byName.find(Normalized(name.text().as_string()));
        if (found != byName.end())
          break;
      }
      if (found == byName.end())
        continue;
    }
    guideChannels[id] = found->second;
  }

  std::map<int, std::vector<Programme>> programmes;
  for (const pugi::xml_node node : tv.children("programme"))
  {
    const auto channel = guideChannels.find(node.attribute("channel").as_string());
    if (channel == guideChannels.end())
      continue;
    Programme programme;
    programme.start = ParseTime(node.attribute("start").as_string());
    programme.end = ParseTime(node.attribute("stop").as_string());
    programme.title = node.child("title").text().as_string();
    programme.episodeName = node.child("sub-title").text().as_string();
    programme.plot = node.child("desc").text().as_string();
    programme.genre = node.child("category").text().as_string();
    programme.icon = node.child("icon").attribute("src").as_string();
    if (programme.start > 0 && programme.end > programme.start)
      programmes[channel->second].push_back(programme);
  }
  for (auto& entry : programmes)
    std::sort(entry.second.begin(), entry.second.end(),
              [](const Programme& left, const Programme& right) { return left.start < right.start; });

  kodi::Log(ADDON_LOG_INFO, "Guide - %zu of %zu channels have a guide", programmes.size(), channels.size());
  std::lock_guard<std::mutex> lock(m_mutex);
  m_programmes = std::move(programmes);
  return true;
}

std::vector<Programme> Guide::Get(int channelUid, time_t from, time_t to)
{
  std::lock_guard<std::mutex> lock(m_mutex);
  std::vector<Programme> result;
  const auto found = m_programmes.find(channelUid);
  if (found == m_programmes.end())
    return result;
  for (const Programme& programme : found->second)
  {
    if (programme.end > from && programme.start < to)
      result.push_back(programme);
  }
  return result;
}

} // namespace notoco
