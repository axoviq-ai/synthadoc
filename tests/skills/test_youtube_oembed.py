# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 William Johnason / axoviq.com
import httpx
import respx

from synthadoc.skills.youtube.scripts.main import _fetch_video_title


@respx.mock
async def test_video_id_is_encoded_and_cannot_inject_query_parameters():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"title": "A title"})

    respx.get(url__startswith="https://www.youtube.com/oembed").mock(side_effect=handler)
    title = await _fetch_video_title("abc123&format=xml")
    assert title == "A title"
    params = seen[0].url.params
    assert params.get_list("format") == ["json"]
    assert params["url"] == "https://www.youtube.com/watch?v=abc123%26format%3Dxml"


@respx.mock
async def test_plain_video_id_still_works():
    respx.get(url__startswith="https://www.youtube.com/oembed").mock(
        return_value=httpx.Response(200, json={"title": "Plain"}))
    assert await _fetch_video_title("dQw4w9WgXcQ") == "Plain"
