"""One place for calling outside APIs.

Every call is logged in ApiCall (without keys), so we can see failures
and stay under free limits.
"""

import json
from datetime import date
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings

from .models import ApiCall

SECRET_PARAMS = {"key", "api_key"}
HEADERS = {"Accept": "application/json", "User-Agent": "RentCheck/1.0"}


class ApiError(Exception):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


def _send(service, request, log_url, timeout=30):
    """Send the request, log the result, and return the JSON. Raises ApiError on any failure."""
    try:
        with urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except HTTPError as e:
        ApiCall.objects.create(service=service, url=log_url, ok=False, status_code=e.code, error=str(e.reason)[:300])
        raise ApiError(f"{service} returned HTTP {e.code} ({e.reason})", status=e.code)
    except (URLError, TimeoutError, json.JSONDecodeError) as e:
        ApiCall.objects.create(service=service, url=log_url, ok=False, error=str(e)[:300])
        raise ApiError(f"{service} request failed: {e}")
    ApiCall.objects.create(service=service, url=log_url, ok=True, status_code=200)
    return data


def get_json(service, url, params=None, headers=None):
    """GET a URL and return the JSON. Keys in params are left out of the log."""
    params = params or {}
    full_url = f"{url}?{urlencode(params)}" if params else url
    safe_params = {k: v for k, v in params.items() if k not in SECRET_PARAMS}
    log_url = (f"{url}?{urlencode(safe_params)}" if safe_params else url)[:500]
    request = Request(full_url, headers={**HEADERS, **(headers or {})})
    return _send(service, request, log_url)


def post_json(service, url, body, headers=None, timeout=30):
    """POST a JSON body and return the JSON response. Logged like get_json."""
    request = Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={**HEADERS, "Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    return _send(service, request, url[:500], timeout)


def calls_this_month(service):
    """Successful calls this calendar month. RentCast only bills successful calls."""
    first = date.today().replace(day=1)
    return ApiCall.objects.filter(service=service, ok=True, called_at__date__gte=first).count()


def rentcast_calls_left():
    return max(settings.RENTCAST_MONTHLY_LIMIT - calls_this_month("rentcast"), 0)


def pick(record, dotted_key):
    """Read "latest.student.size" from either a flat dict or nested dicts."""
    if dotted_key in record:
        return record[dotted_key]
    value = record
    for part in dotted_key.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value
