
from sys import version_info
import re
from datetime import datetime, timedelta, timezone, date as dt_date, time as dt_time
from typing import Optional, Union
from .types import DateTime
from ..kolang import L

#: Python has datetime.fromisoformat with timezone support.
HAS_ISO = version_info >= (3, 11)
#: Unix Epoch, timestamp zero.
unix_epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)

EPOCH = datetime(1, 1, 1, tzinfo=timezone.utc)
EPOCH_DATE = EPOCH.date()


if HAS_ISO:
    # fromisoformat = datetime.fromisoformat
    def fromisoformat(date_string: str, /) -> datetime:
        if date_string.endswith(' UTC'):
            date_string = f'{date_string[:-4]}Z'
        return datetime.fromisoformat(date_string)
else:
    # Python < 3.11
    _rx_fmt = re.compile(r'(?P<dt>[-W\d]+)(?:(?P<sep>[ T])(?P<tm>[:\d]+)(?P<f>\.\d+)?)?(?P<tz>[+-]\d{2}:?\d{2}|Z)?')

    def fromisoformat(date_string: str, /) -> datetime:
        """Return a datetime corresponding to a date_string in any valid ISO 8601 format."""
        if date_string.endswith(' UTC'):
            date_string = f'{date_string[:-4]}Z'
        mch = _rx_fmt.fullmatch(date_string)
        if not mch:
            return datetime.fromisoformat(date_string)
        fmt = ''
        if 'W' in mch['dt']:
            fmt += '%G-W%V-%u'
        elif '-' in mch['dt']:
            fmt += '%Y-%m-%d'
        else:
            fmt += '%Y%m%d'
        if mch['sep']:
            fmt += mch['sep']
        if mch['tm']:
            fmt += '%H:%M:%S' if ':' in mch['tm'] else '%H%M%S'
        if mch['f']:
            fmt += '.%f'
        if mch['tz']:
            fmt += '%z'
        return datetime.strptime(date_string, fmt)


def make_datetime(date: Union[None, str, float, datetime, dt_date]) -> datetime:
    if date is None:
        # datetime.utcnow() is obsolete
        return datetime.now(timezone.utc)
    if isinstance(date, str):
        return fromisoformat(date)
    elif isinstance(date, DateTime):
        return date
    elif isinstance(date, dt_date):
        # Combine should work event if is out of C time functions' range.
        return datetime.combine(date, dt_time(12, 0))
    else:
        raise ValueError(f'Unknown datetime format in {date!r}')


def utc_timestamp(date: Optional[Union[str, float, datetime, dt_date]] = None) -> float:
    """Datetime (date or now) into utc-timestamp with timezone support."""
    if date is None:
        return datetime.now(timezone.utc).timestamp()  # for "now" we could use timestamp()
    if isinstance(date, (float, int)):
        return float(date)
    try:
        d = make_datetime(date)
    except ValueError:
        return float(date)  # type: ignore  -- make_datetime() gurads type check
    # See: https://stackoverflow.com/a/41400321/9935708
    #   > If the timestamp is out of the range of values supported by the platform C
    #   > localtime() or gmtime() functions, datetime.fromtimestamp() may raise an exception OSError.
    #   > On Windows platform, this range can sometimes be restricted to years in 1970 through 2038.
    #   > I have never seen this problem on a Linux system.
    # Check on win, py3.8 & py3.12:
    #   - timestmap() could not be negative and must be < date(3001, 1, 20)
    # We use python timedalta to handle timestamp.
    # See: https://stackoverflow.com/a/65564765/9935708
    try:
        return (d.astimezone(timezone.utc) - unix_epoch).total_seconds()
    except OSError:
        from .log_utils import fflog, fflog_exc
        fflog(f'{d = }, {unix_epoch = }')
        fflog_exc()
        return 0


def timestamp(date: Optional[Union[str, float, datetime, dt_date]] = None) -> float:
    """Datetime (date or now) into utc-timestamp with timezone support."""
    if date is None:
        return datetime.now().timestamp()  # for "now" we could use timestamp()
    if isinstance(date, (float, int)):
        return float(date)
    try:
        d = make_datetime(date)
    except ValueError:
        return float(date)  # type: ignore  -- make_datetime() gurads type check
    # Avoid datetime.timestamp on some platforms, see comments in utc_timestamp().
    return (d.astimezone(timezone.utc) - unix_epoch).total_seconds()


def utc_from_timestamp(timestamp: Optional[float] = None) -> datetime:
    """Safe datetime.fromtimestamp().astimezone(timezone.utc). Returns UTC datetime."""
    # Avoid datetime.fromtimestamp on some platforms, see comments in utc_timestamp().
    if timestamp is None or timestamp == '':
        return datetime.now()
    return (unix_epoch + timedelta(seconds=float(timestamp))).replace(tzinfo=None)


def from_timestamp(timestamp: Optional[float] = None) -> datetime:
    """Safe datetime.fromtimestamp(). Returns naive datetime."""
    # Avoid datetime.fromtimestamp on some platforms, see comments in utc_timestamp().
    if timestamp is None or timestamp == '':
        return datetime.now()
    return (unix_epoch.astimezone() + timedelta(seconds=float(timestamp))).replace(tzinfo=None)


def iso_2_utc(date_string: str) -> int:
    """Parse datetime string into utc-timestamp with timezone support."""
    return int(utc_timestamp(date_string))


def local_from_utc_timestamp(timestamp: Union[float, datetime, dt_date]) -> datetime:
    """Return local datetime from utc-timestamp."""
    if isinstance(timestamp, DateTime):
        timestamp = timestamp.timestamp()
    elif isinstance(timestamp, dt_date):
        timestamp = datetime.combine(timestamp, dt_time(12, 0)).timestamp()
    utc = datetime.fromtimestamp(timestamp).replace(tzinfo=timezone.utc)
    return utc.astimezone()


def local_str_from_utc_timestamp(timestamp: Union[float, datetime, dt_date]) -> str:
    """Return local datetime from utc-timestamp as "YYYY-MM-DD HH:MM:SS" string."""
    return f'{local_from_utc_timestamp(timestamp):%Y-%m-%d %H:%M:%S}'


def datestamp(date: Optional[Union[str, float, datetime, dt_date]] = None) -> int:
    """Safe date (or now) into (utc) datestamp (number of days)."""
    if date is None:
        date = dt_date.today()
    if isinstance(date, (float, int)):
        return int(date)
    if isinstance(date, str):
        try:
            date = dt_date.fromisoformat(date)
        except ValueError:
            if date.isdigit():
                return int(date)
            raise
    if isinstance(date, DateTime):
        date = date.date()
    return (date - EPOCH_DATE).days


def from_datestamp(datestamp: Optional[int] = None) -> dt_date:
    """Safe date from date-stamp."""
    if datestamp is None or datestamp == '':
        return dt_date.today()
    return EPOCH_DATE + timedelta(days=int(datestamp))


class Translations:
    """Some basic date phrases to translate."""

    today = L(30270, "Today")
    tomorrow = L(30271, "Tomorrow")
    yesterday = L(30272, "Yesterday")
    days = [L(30273, 'Monday'), L(30274, 'Tuesday'), L(30275, 'Wednesday'),
            L(30276, 'Thursday'), L(30277, 'Friday'), L(30278, 'Saturday'), L(30279, 'Sunday')]
    isodays = [L(30279, 'Sunday'), L(30273, 'Monday'), L(30274, 'Tuesday'), L(30275, 'Wednesday'),
               L(30276, 'Thursday'), L(30277, 'Friday'), L(30278, 'Saturday'), L(30279, 'Sunday')]
    months = [L(30280, 'January'), L(30281, 'February'), L(30282, 'March'),
              L(30283, 'April'), L(30284, 'May'), L(30285, 'June'),
              L(30286, 'July'), L(30287, 'August'), L(30288, 'September'),
              L(30289, 'October'), L(30290, 'November'), L(30291, 'December')]
    upcoming_week_day = '{weekday}'
    last_week_day = L(30292, 'Last {weekday}')


def day_label(dt: Union[dt_date, datetime],
              *,
              now: Union[dt_date, datetime, None] = None,
              week_day: bool = True,
              week_without_date: bool = False,
              date_format: Optional[str] = None,
              ) -> str:
    """Returns nice date label (today, Monday, 11.12.2013)."""
    if dt is None:
        return ''
    if now is None:
        now = datetime.now()
    if isinstance(now, datetime):
        now = now.date()
    if isinstance(dt, datetime):
        dt = dt.date()
    if now == dt:
        return L(30270, 'Today')
    if (now + timedelta(days=1)) == dt:
        return L(30271, 'Tomorrow')
    if (now - timedelta(days=1)) == dt:
        return L(30272, 'Yesterday')
    if week_without_date:
        dd = (dt - now).days
        if 0 < dd <= 7:
            return Translations.upcoming_week_day.format(weekday=Translations.days[dt.weekday()])
        if 0 > dd >= -7:
            return Translations.last_week_day.format(weekday=Translations.days[dt.weekday()])
    dt_str = f'{dt}' if date_format is None else f'{dt:{date_format}}'
    if week_day:
        return f'{Translations.days[dt.weekday()]}, {dt_str}'
    return dt_str

if __name__ == '__main__':
    print(repr(fromisoformat('2023-10-18T18:10:27.000')))
    print(repr(fromisoformat('2023-10-18T18:10:27.000Z')))
    print(repr(fromisoformat('2023-10-18T18:10:27.000+00:00')))
    print(repr(fromisoformat('2023-10-18T18:10:27.000+01:00')))
    print(repr(fromisoformat('2023-10-18T18:10:27.000-02:00')))
    print(repr(fromisoformat('2023-10-18T18:10:27.000-0200')))
    print(repr(fromisoformat('2011-W01-2T00:05:23.283')))

    # test from py 3.12 doc
    assert fromisoformat('2011-11-04') == datetime(2011, 11, 4, 0, 0)
    assert fromisoformat('20111104') == datetime(2011, 11, 4, 0, 0)
    assert fromisoformat('2011-11-04T00:05:23') == datetime(2011, 11, 4, 0, 5, 23)
    assert fromisoformat('2011-11-04T00:05:23Z') == datetime(2011, 11, 4, 0, 5, 23, tzinfo=timezone.utc)
    assert fromisoformat('20111104T000523') == datetime(2011, 11, 4, 0, 5, 23)
    assert fromisoformat('2011-W01-2T00:05:23.283') == datetime(2011, 1, 4, 0, 5, 23, 283000)
    assert fromisoformat('2011-11-04 00:05:23.283') == datetime(2011, 11, 4, 0, 5, 23, 283000)
    assert (fromisoformat('2011-11-04 00:05:23.283+00:00')
            == datetime(2011, 11, 4, 0, 5, 23, 283000, tzinfo=timezone.utc))
    assert (fromisoformat('2011-11-04T00:05:23+04:00')
            == datetime(2011, 11, 4, 0, 5, 23, tzinfo=timezone(timedelta(seconds=14400))))
