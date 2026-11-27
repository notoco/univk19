/*
 *  XMLTV programme guide (plain or gzip), matched to the channels by tvg-id, else by name.
 *  The last download is kept in addon_data, so the guide is there without network.
 */

#pragma once

#include "Playlist.h"

#include <ctime>
#include <map>
#include <mutex>
#include <string>
#include <vector>

namespace notoco
{

struct Programme
{
  time_t start = 0;
  time_t end = 0;
  std::string title;
  std::string episodeName;
  std::string plot;
  std::string genre;
  std::string icon;
};

class Guide
{
public:
  bool Load(const std::string& url, const std::vector<Channel>& channels);
  std::vector<Programme> Get(int channelUid, time_t from, time_t to);

private:
  std::mutex m_mutex;
  std::map<int, std::vector<Programme>> m_programmes;
};

} // namespace notoco
