#include "Playlist.h"

#include "Utils.h"

#include <atomic>
#include <sstream>

#include <kodi/General.h>

namespace notoco
{

namespace
{
std::string Attribute(const std::string& line, const std::string& name)
{
  const std::string key = " " + name + "=\"";
  const size_t start = line.find(key);
  if (start == std::string::npos)
    return {};
  const size_t valueStart = start + key.size();
  const size_t valueEnd = line.find('"', valueStart);
  return valueEnd == std::string::npos ? std::string() : line.substr(valueStart, valueEnd - valueStart);
}

// the name follows the last comma outside the quoted attributes
std::string ChannelName(const std::string& line)
{
  bool quoted = false;
  size_t comma = std::string::npos;
  for (size_t index = 0; index < line.size(); ++index)
  {
    if (line[index] == '"')
      quoted = !quoted;
    else if (line[index] == ',' && !quoted)
      comma = index;
  }
  if (comma == std::string::npos)
    return {};
  std::string name = line.substr(comma + 1);
  name.erase(0, name.find_first_not_of(" \t"));
  name.erase(name.find_last_not_of(" \t") + 1);
  return name;
}

int StableId(const std::string& text)
{
  // FNV-1a: the same name keeps the same id across starts and builds
  uint32_t hash = 2166136261u;
  for (const char character : text)
  {
    hash ^= static_cast<unsigned char>(character);
    hash *= 16777619u;
  }
  return static_cast<int>(hash & 0x7FFFFFFF);
}
} // namespace

bool LoadPlaylist(const std::string& path, std::vector<Channel>& channels)
{
  std::vector<unsigned char> data;
  const std::atomic<bool> stop{false};
  if (!Download(path, data, stop))
  {
    kodi::Log(ADDON_LOG_ERROR, "Playlist - cannot read %s", RedactUrl(path).c_str());
    return false;
  }

  channels.clear();
  Channel pending;
  bool infoRead = false;
  std::istringstream stream(std::string(data.begin(), data.end()));
  std::string line;
  while (std::getline(stream, line))
  {
    if (!line.empty() && line.back() == '\r')
      line.pop_back();
    if (line.rfind("\xEF\xBB\xBF", 0) == 0)
      line.erase(0, 3);
    if (line.empty())
      continue;

    if (line.rfind("#EXTINF", 0) == 0)
    {
      pending = Channel();
      pending.name = ChannelName(line);
      pending.tvgId = Attribute(line, "tvg-id");
      pending.tvgName = Attribute(line, "tvg-name");
      pending.logo = Attribute(line, "tvg-logo");
      const std::string days = Attribute(line, "timeshift");
      pending.archiveDays = days.empty() ? 0 : std::atoi(days.c_str());
      infoRead = true;
    }
    else if (line[0] != '#' && infoRead)
    {
      pending.url = line;
      if (pending.name.empty())
        pending.name = pending.tvgName;
      pending.uid = StableId(pending.name);
      pending.number = static_cast<int>(channels.size()) + 1;
      channels.push_back(pending);
      infoRead = false;
    }
  }
  kodi::Log(ADDON_LOG_INFO, "Playlist - %zu channels", channels.size());
  return !channels.empty();
}

} // namespace notoco
