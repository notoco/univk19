import re
import sys

import xbmcplugin

from lib.indexers import navigator
from lib.ff import client, control
from const import const


class channels:
    def __init__(self):
        self.filmweb_url = "http://www.filmweb.pl"

    def fetch_filmweb_content(self):
        try:
            return client.request(f"{self.filmweb_url}/program-tv")
        except Exception as e:
            print(f"Error fetching content: {e}")
            return None

    def get(self):
        filmweb_content = self.fetch_filmweb_content()
        if filmweb_content:
            movie_divs = client.parseDOM(
                filmweb_content, name="div", attrs={"class": "area"}
            )
            for movie_div in movie_divs:
                try:
                    self.process_movie_div(movie_div)
                except IndexError:
                    continue
        else:
            self.add_empty_directory()

        self.finalize_directory()

    def process_movie_div(self, movie_div):
        try:
            movie_link = client.parseDOM(movie_div, name="a", ret="href")[0]
            movie_title = client.parseDOM(movie_div, name="img", ret="alt")[0].replace(
                "plakat filmu ", ""
            )
            movie_year = movie_link.split("-")
            time_info, channel = self.extract_time_and_channel(movie_div)
            image_url = self.extract_image_url(movie_div)
            self.add_to_directory(
                movie_title, time_info, channel, movie_year[1], image_url
            )
        except Exception as e:
            print(f"Error processing movie div: {e}")
            self.add_empty_directory()

    def extract_time_and_channel(self, movie_div):
        try:
            time_html = client.parseDOM(
                movie_div, name="div", attrs={"class": "top-5 maxlines-2 cap"}
            )[0]
            time_info = time_html.split(",")[0]
            channel = client.parseDOM(time_html.split(",")[-1], name="a")[0]
            return time_info, channel
        except Exception as e:
            print(f"Error extracting time and channel: {e}")
            return None, None

    def extract_image_url(self, movie_div):
        try:
            image_url = client.parseDOM(movie_div, name="img", ret="src")[0]
            return re.sub(r".\.jpg", "2.jpg", image_url)
        except Exception as e:
            print(f"Error extracting image URL: {e}")
            return None

    def add_to_directory(self, title, time_info, channel, year, image_url):
        try:
            navigator.navigator().addDirectoryItem(
                f"{title} [B]({time_info}, {channel})[/B]",
                f"movieSearchEPG&name={title}&year={year}",
                image_url,
                image_url,
                isFolder=True,
            )
        except Exception as e:
            print(f"Error adding to directory: {e}")

    def add_empty_directory(self):
        try:
            navigator.navigator().addDirectoryItem(
                30100,
                "empty",
                "",
                "",
                isFolder=True,
            )
        except Exception as e:
            print(f"Error adding empty directory: {e}")

    def finalize_directory(self):
        try:
            xbmcplugin.setContent(int(sys.argv[1]), "movies")
            xbmcplugin.endOfDirectory(int(sys.argv[1]), cacheToDisc=const.folder.cache_to_disc)
        except Exception as e:
            print(f"Error finalizing directory: {e}")
