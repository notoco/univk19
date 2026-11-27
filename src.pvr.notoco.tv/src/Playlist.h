/*
 *  M3U channel list: #EXTINF with tvg-id, tvg-name, tvg-logo, timeshift (archive days) and the
 *  channel name after the comma; the next line is the stream URL. Channels are numbered by order.
 */

#pragma once

#include <string>
#include <vector>

namespace notoco
{

struct Channel
{
  int uid = 0; // stable: a hash of the name
  int number = 0;
  std::string name;
  std::string tvgId;
  std::string tvgName;
  std::string logo;
  std::string url;
  int archiveDays = 0;
};

bool LoadPlaylist(const std::string& path, std::vector<Channel>& channels);

} // namespace notoco
