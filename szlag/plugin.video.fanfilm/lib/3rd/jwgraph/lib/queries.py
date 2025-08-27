from gql import gql

SUGGESTED_TITLES = gql("""
query GetSuggestedTitles($country: Country!, $language: Language!, $first: Int!, $filter: TitleFilter) {
  popularTitles(country: $country, first: $first, filter: $filter) {
    edges {
      node {
        ...SuggestedTitle
        __typename
      }
      __typename
    }
    __typename
  }
}

fragment SuggestedTitle on MovieOrShow {
  id
  objectType
  objectId
  content(country: $country, language: $language) {
    fullPath
    title
    originalReleaseYear
    posterUrl
    fullPath
    __typename
  }
  __typename
}
""")

TITLE_OFFERS = gql("""
query GetTitleOffers($nodeId: ID!, $country: Country!, $language: Language!, $filterFlatrate: OfferFilter!, $filterBuy: OfferFilter!, $filterRent: OfferFilter!, $filterFree: OfferFilter!, $platform: Platform! = WEB) {
  node(id: $nodeId) {
    id
    ... on MovieOrShowOrSeasonOrEpisode {
      offerCount(country: $country, platform: $platform)
      flatrate: offers(
        country: $country
        platform: $platform
        filter: $filterFlatrate
      ) {
        ...TitleOffer
        __typename
      }
      buy: offers(country: $country, platform: $platform, filter: $filterBuy) {
        ...TitleOffer
        __typename
      }
      rent: offers(country: $country, platform: $platform, filter: $filterRent) {
        ...TitleOffer
        __typename
      }
      free: offers(country: $country, platform: $platform, filter: $filterFree) {
        ...TitleOffer
        __typename
      }
      __typename
    }
    __typename
  }
}

fragment TitleOffer on Offer {
  id
  presentationType
  monetizationType
  retailPrice(language: $language)
  retailPriceValue
  currency
  lastChangeRetailPriceValue
  type
  package {
    id
    packageId
    clearName
    __typename
  }
  standardWebURL
  elementCount
  availableTo
  deeplinkRoku: deeplinkURL(platform: ROKU_OS)
  __typename
}
""")


URL_TITLE_DETAILS = gql("""
query GetUrlTitleDetails($fullPath: String!, $country: Country!, $language: Language!, $episodeMaxLimit: Int, $platform: Platform! = WEB) {
  url(fullPath: $fullPath) {
    id
    metaDescription
    metaKeywords
    metaRobots
    metaTitle
    heading1
    heading2
    htmlContent
    node {
      id
      ... on MovieOrShowOrSeason {
        objectType
        objectId
        offerCount(country: $country, platform: $platform)
        offers(country: $country, platform: $platform) {
          monetizationType
          package {
            id
            packageId
            __typename
          }
          __typename
        }
        promotedBundles(country: $country, platform: $platform) {
          promotionUrl
          __typename
        }
        availableTo(country: $country, platform: $platform) {
          availableCountDown(country: $country)
          availableToDate
          package {
            id
            shortName
            __typename
          }
          __typename
        }
        fallBackClips: content(country: "US", language: "en") {
          videobusterClips: clips(providers: [VIDEOBUSTER]) {
            externalId
            provider
            __typename
          }
          dailymotionClips: clips(providers: [DAILYMOTION]) {
            externalId
            provider
            __typename
          }
          __typename
        }
        content(country: $country, language: $language) {
          backdrops {
            backdropUrl
            __typename
          }
          clips {
            externalId
            provider
            __typename
          }
          videobusterClips: clips(providers: [VIDEOBUSTER]) {
            externalId
            provider
            __typename
          }
          dailymotionClips: clips(providers: [DAILYMOTION]) {
            externalId
            provider
            __typename
          }
          videobusterClips: clips(providers: [VIDEOBUSTER]) {
            externalId
            __typename
          }
          externalIds {
            imdbId
            __typename
          }
          fullPath
          genres {
            shortName
            __typename
          }
          posterUrl
          runtime
          isReleased
          scoring {
            imdbScore
            imdbVotes
            tmdbPopularity
            tmdbScore
            __typename
          }
          shortDescription
          title
          originalReleaseYear
          originalReleaseDate
          upcomingReleases(releaseTypes: DIGITAL) {
            releaseCountDown(country: $country)
            releaseDate
            label
            package {
              id
              packageId
              shortName
              __typename
            }
            __typename
          }
          ... on MovieOrShowContent {
            originalTitle
            ageCertification
            credits {
              role
              name
              characterName
              personId
              __typename
            }
            productionCountries
            __typename
          }
          ... on SeasonContent {
            seasonNumber
            __typename
          }
          __typename
        }
        __typename
      }
      ... on MovieOrShow {
        watchlistEntry {
          createdAt
          __typename
        }
        likelistEntry {
          createdAt
          __typename
        }
        dislikelistEntry {
          createdAt
          __typename
        }
        customlistEntries {
          createdAt
          genericTitleList {
            id
            __typename
          }
          __typename
        }
        __typename
      }
      ... on Movie {
        permanentAudiences
        seenlistEntry {
          createdAt
          __typename
        }
        __typename
      }
      ... on Show {
        permanentAudiences
        totalSeasonCount
        seenState(country: $country) {
          progress
          seenEpisodeCount
          __typename
        }
        seasons(sortDirection: DESC) {
          id
          objectId
          objectType
          availableTo(country: $country, platform: $platform) {
            availableToDate
            availableCountDown(country: $country)
            package {
              id
              shortName
              __typename
            }
            __typename
          }
          content(country: $country, language: $language) {
            posterUrl
            seasonNumber
            fullPath
            upcomingReleases(releaseTypes: DIGITAL) {
              releaseDate
              releaseCountDown(country: $country)
              package {
                id
                shortName
                __typename
              }
              __typename
            }
            isReleased
            __typename
          }
          show {
            id
            objectId
            objectType
            watchlistEntry {
              createdAt
              __typename
            }
            content(country: $country, language: $language) {
              title
              __typename
            }
            __typename
          }
          __typename
        }
        recentEpisodes: episodes(
          sortDirection: DESC
          limit: 3
          releasedInCountry: $country
        ) {
          id
          objectId
          content(country: $country, language: $language) {
            title
            shortDescription
            episodeNumber
            seasonNumber
            isReleased
            upcomingReleases {
              releaseDate
              label
              __typename
            }
            __typename
          }
          seenlistEntry {
            createdAt
            __typename
          }
          __typename
        }
        __typename
      }
      ... on Season {
        totalEpisodeCount
        episodes(limit: $episodeMaxLimit) {
          id
          objectType
          objectId
          seenlistEntry {
            createdAt
            __typename
          }
          content(country: $country, language: $language) {
            title
            shortDescription
            episodeNumber
            seasonNumber
            isReleased
            upcomingReleases(releaseTypes: DIGITAL) {
              releaseDate
              label
              package {
                id
                packageId
                __typename
              }
              __typename
            }
            __typename
          }
          __typename
        }
        show {
          id
          objectId
          objectType
          totalSeasonCount
          customlistEntries {
            createdAt
            genericTitleList {
              id
              __typename
            }
            __typename
          }
          fallBackClips: content(country: "US", language: "en") {
            videobusterClips: clips(providers: [VIDEOBUSTER]) {
              externalId
              provider
              __typename
            }
            dailymotionClips: clips(providers: [DAILYMOTION]) {
              externalId
              provider
              __typename
            }
            __typename
          }
          content(country: $country, language: $language) {
            title
            ageCertification
            fullPath
            credits {
              role
              name
              characterName
              personId
              __typename
            }
            productionCountries
            externalIds {
              imdbId
              __typename
            }
            upcomingReleases(releaseTypes: DIGITAL) {
              releaseDate
              __typename
            }
            backdrops {
              backdropUrl
              __typename
            }
            posterUrl
            isReleased
            videobusterClips: clips(providers: [VIDEOBUSTER]) {
              externalId
              provider
              __typename
            }
            dailymotionClips: clips(providers: [DAILYMOTION]) {
              externalId
              provider
              __typename
            }
            __typename
          }
          seenState(country: $country) {
            progress
            __typename
          }
          watchlistEntry {
            createdAt
            __typename
          }
          dislikelistEntry {
            createdAt
            __typename
          }
          likelistEntry {
            createdAt
            __typename
          }
          __typename
        }
        seenState(country: $country) {
          progress
          __typename
        }
        __typename
      }
      __typename
    }
    __typename
  }
}
""")

NEW_TITLE_BUCKETS = gql("""
query NewContentVerticalPaginationQuery(
  $after: String
  $allowSponsoredRecommendations: SponsoredRecommendationsInput
  $country: Country!
  $filter: TitleFilter
  $first: Int = 5
  $imageFormat: ImageFormat
  $language: Language!
  $packages: [String!]
  $pageType: NewPageType!
  $platform: Platform!
  $priceDrops: Boolean!
) {
  ...NewContentFragment_2HEEH6
}
fragment NewContentFragment_2HEEH6 on Query {
  newTitleBuckets(after: $after, allowSponsoredRecommendations: $allowSponsoredRecommendations, country: $country, filter: $filter, first: $first, groupBy: DATE_PACKAGE, pageType: $pageType, priceDrops: $priceDrops) {
    edges {
      key {
        __typename
        ... on DatePackageAggregationKey {
          date
          package {
            icon(format: $imageFormat, profile: S50)
            packageId
            shortName
            id
          }
        }
        ... on BucketPackageAggregationKey {
          bucketType
          package {
            icon(format: $imageFormat, profile: S50)
            packageId
            shortName
            id
          }
        }
      }
      node {
        activeCampaign {
          node {
            __typename
            id
            ... on MovieOrShow {
              __isMovieOrShow: __typename
              content(country: $country, language: $language) {
                __typename
                backdrops(format: $imageFormat) {
                  backdropBlurHash
                  backdropUrl
                }
                externalIds {
                  imdbId
                }
                fullPath
                originalReleaseYear
                originalTitle
                posterUrl(format: $imageFormat)
                posterBlurHash
                runtime
                scoring {
                  imdbScore
                  imdbVotes
                }
                shortDescription
                title
              }
              dislikelistEntry {
                createdAt
              }
              likelistEntry {
                createdAt
              }
              objectId
              objectType
              watchlistEntry {
                createdAt
              }
            }
          }
          promotionalImageUrl
          watchNowLabel
          watchNowOffer {
            id
            currency
            deeplinkURL(platform: $platform)
            lastChangeRetailPriceValue
            monetizationType
            package {
              icon(format: $imageFormat, profile: S100)
              id
              clearName
              packageId
              shortName
            }
            presentationType
            retailPriceValue
            standardWebURL
          }
        }
        edges {
          newOffer(platform: $platform) {
            currency
            deeplinkURL(platform: $platform)
            lastChangePercent
            lastChangeRetailPrice(language: $language)
            lastChangeRetailPriceValue
            monetizationType
            newElementCount
            package {
              icon(format: $imageFormat, profile: S50)
              clearName
              packageId
              shortName
              id
            }
            presentationType
            retailPrice(language: $language)
            retailPriceValue
            standardWebURL
            id
          }
          node {
            __typename
            availableTo(country: $country, platform: $platform, packages: $packages) {
              availableCountDown(country: $country)
              availableToDate
            }
            content(country: $country, language: $language) {
              __typename
              backdrops(format: $imageFormat) {
                backdropBlurHash
                backdropUrl
              }
              externalIds {
                imdbId
              }
              fullPath
              originalReleaseYear
              posterBlurHash
              posterUrl(format: $imageFormat)
              runtime
              scoring {
                imdbScore
                imdbVotes
              }
              shortDescription
              title
              upcomingReleases {
                releaseDate
                releaseType
                releaseCountDown(country: $country)
              }
            }
            id
            objectId
            objectType
            ... on Season {
              seasonContent: content(country: $country, language: $language) {
                seasonNumber
                title
              }
              seenState(country: $country) {
                caughtUp
                progress
              }
              show {
                dislikelistEntry {
                  createdAt
                }
                likelistEntry {
                  createdAt
                }
                showContent: content(country: $country, language: $language) {
                  showAgeCertification: ageCertification
                  showBackdrops: backdrops(format: $imageFormat) {
                    backdropBlurHash
                    backdropUrl
                  }
                  showDescription: shortDescription
                  showExternalIds: externalIds {
                    imdbId
                  }
                  showOriginalTitle: originalTitle
                  showTitle: title
                }
                showId: id
                showObjectId: objectId
                showObjectType: objectType
                watchlistEntry {
                  createdAt
                }
                id
              }
            }
            ... on Movie {
              titleContent: content(country: $country, language: $language) {
                ageCertification
                originalTitle
              }
              dislikelistEntry {
                createdAt
              }
              likelistEntry {
                createdAt
              }
              seenlistEntry {
                createdAt
              }
              watchlistEntry {
                createdAt
              }
            }
          }
        }
        pageInfo {
          endCursor
          hasNextPage
        }
        totalCount
        __typename
      }
      cursor
    }
    pageInfo {
      endCursor
      hasNextPage
    }
  }
}
""")
