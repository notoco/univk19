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
  int genreType = 0; // Kodi's EPG_EVENT_CONTENTMASK_* of the genre (the guide colours), 0 unknown
  std::string icon;
};

// Kodi's genre category of an XMLTV category text (Polish or English)
int GenreType(const std::string& genre);

class Guide
{
public:
  // downloads (or reads the cached copy of) the guide and matches it to the channels
  bool Load(const std::string& url, const std::vector<Channel>& channels);
  // programmes of a channel overlapping a time range
  std::vector<Programme> Get(int channelUid, time_t from, time_t to);
  // the programme of a channel starting at a time
  bool Find(int channelUid, time_t start, Programme& programme);

private:
  std::mutex m_mutex;
  std::map<int, std::vector<Programme>> m_programmes;
};

} // namespace notoco
