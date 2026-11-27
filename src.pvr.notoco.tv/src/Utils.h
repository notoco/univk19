/*
 *  Shared helpers: downloads and Flussonic HLS playlists.
 */

#pragma once

#include <atomic>
#include <cstdint>
#include <ctime>
#include <string>
#include <vector>

namespace notoco
{

struct Segment
{
  int64_t sequence = 0;
  std::string url;
  double duration = 0;
  time_t start = 0; // UTC from a Flussonic DVR name (dvr-2026/11/25/16/38/13-06000.ts), 0 if unknown
};

// The URL without its query (the provider token never goes to the log)
std::string RedactUrl(const std::string& url);

// Whole body of a URL or file; false on an error or when stop was set
bool Download(const std::string& url, std::vector<unsigned char>& data, const std::atomic<bool>& stop);

// Segments of a media playlist, relative URIs resolved against playlistUrl
bool ParsePlaylist(const std::string& playlistUrl,
                   const std::string& content,
                   std::vector<Segment>& segments,
                   double& targetDuration);

// .../mono.m3u8?query -> .../mono-<from>-<seconds>.m3u8?query (the archive of a time range)
std::string ArchivePlaylistUrl(const std::string& liveUrl, time_t from, time_t seconds);

} // namespace notoco
