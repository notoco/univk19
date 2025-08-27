import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'lib'))

from gql import Client
from gql.transport.requests import RequestsHTTPTransport

from queries import SUGGESTED_TITLES
from queries import TITLE_OFFERS
from queries import URL_TITLE_DETAILS
from queries import NEW_TITLE_BUCKETS
from const import const

class JustWatchAPI:

    def __init__(self, country: str = '', language: str = '') -> None:
        self.base_url: str = 'https://apis.justwatch.com/graphql'
        self.transport = RequestsHTTPTransport(
            url=self.base_url,
            verify=True,
            retries=3,
        )
        self.client = Client(transport=self.transport, fetch_schema_from_transport=False)
        self.country: str = country if country else 'US'
        self.language: str = language if language else 'en'

    def search_item(self, title: str):
        params = {
            "country": self.country,
            "language": self.language,
            "first": 4,
            "filter": {
                "searchQuery": title
            }
        }

        return self.client.execute(SUGGESTED_TITLES, variable_values=params)

    def get_providers(self, node_id: str):
        params = {
            "platform": "WEB",
            "nodeId": node_id,
            "country": self.country,
            "language": self.language,
            "filterBuy": {
                "monetizationTypes": [
                    "BUY"
                ],
                "bestOnly": True
            },
            "filterFlatrate": {
                "monetizationTypes": [
                    "FLATRATE",
                    "FLATRATE_AND_BUY",
                    "ADS",
                    "FREE"
                ],
                "bestOnly": True
            },
            "filterRent": {
                "monetizationTypes": [
                    "RENT"
                ],
                "bestOnly": True
            },
            "filterFree": {
                "monetizationTypes": [
                    "ADS",
                    "FREE"
                ],
                "bestOnly": True
            }
        }

        return self.client.execute(TITLE_OFFERS, variable_values=params)

    def get_title(self, full_path: str):
        params = {
            "platform": "WEB",
            "fullPath": full_path,
            "language": self.language,
            "country": self.country,
            "episodeMaxLimit": const.justwatch.episode_max_limit,
        }

        return self.client.execute(URL_TITLE_DETAILS, variable_values=params)

    def new_titles(self, after: str = ''):
        params = {
                "allowSponsoredRecommendations": {
                  "country": "PL",
                  "platform": "ANDROID"
                },
                "country": self.country,
                "filter": {
                  "excludeIrrelevantTitles": False,
                  "objectTypes": [
                    "MOVIE"
                  ],
                  "packages": []
                },
                "first": 5,
                "imageFormat": "WEBP",
                "language": self.language,
                "packages": [],
                "pageType": "NEW",
                "platform": "ANDROID",
                "priceDrops": False
              }
        if after != '':
            params['after'] = after

        return self.client.execute(NEW_TITLE_BUCKETS, variable_values=params)
