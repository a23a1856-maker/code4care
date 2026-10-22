"""Calls to outside services: a timeout, then retries with back-off."""
from __future__ import annotations

import logging
import time
from typing import Any

import httpx

logger = logging.getLogger("code4care.outbound")


class OutboundError(RuntimeError):
    """An outside service failed; the caller shows a clear message and saves nothing."""


RETRYABLE_STATUSES = {408, 425, 429, 500, 502, 503, 504}


def request_with_retry(
    method: str,
    url: str,
    *,
    headers: dict | None = None,
    data: dict | None = None,
    json: dict | None = None,
    params: dict | None = None,
    timeout: float = 5.0,
    retries: int = 2,
    client: httpx.Client | None = None,
    sleep=time.sleep,
) -> httpx.Response:
    """One request, with a hard timeout and exponential back-off on failure."""
    delay = 0.25
    attempts = max(1, retries + 1)
    last_error: Exception | None = None

    for attempt in range(attempts):
        try:
            if client is not None:
                response = client.request(
                    method, url, headers=headers, data=data, json=json, params=params,
                    timeout=timeout,
                )
            else:
                response = httpx.request(
                    method, url, headers=headers, data=data, json=json, params=params,
                    timeout=timeout,
                )
            if response.status_code in RETRYABLE_STATUSES:
                last_error = OutboundError(f"upstream returned {response.status_code}")
            elif response.status_code >= 400:
                raise OutboundError(f"upstream refused the request ({response.status_code})")
            else:
                return response
        except (httpx.HTTPError, OutboundError) as exc:
            last_error = exc
        if attempt < attempts - 1:
            logger.warning(
                "outbound retry attempt=%s url=%s reason=%s",
                attempt + 1,
                url.split("?")[0],
                type(last_error).__name__,
            )
            sleep(delay)
            delay = min(delay * 2, 4.0)

    raise OutboundError(f"could not reach {url.split('?')[0]}: {last_error}")


def parse_json(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise OutboundError("upstream did not return JSON") from exc
    if not isinstance(payload, dict):
        raise OutboundError("upstream returned an unexpected payload")
    return payload
