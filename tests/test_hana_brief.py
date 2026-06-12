from __future__ import annotations

from collectors.hana_brief import HanaBriefCollector


def test_hana_brief_requires_real_channel_id():
    result = HanaBriefCollector({"channel_id": "REPLACE_WITH_CHANNEL_ID"}).collect()
    assert "channel_id" in result.error


def test_hana_brief_extracts_pdf_links(monkeypatch):
    class DummyResponse:
        def __init__(self, text):
            self.text = text

        def raise_for_status(self):
            return None

    feed_xml = """
    <feed xmlns:yt="http://www.youtube.com/xml/schemas/2015" xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <yt:videoId>abc123</yt:videoId>
        <title>하나 Morning Brief</title>
        <published>2026-06-12T07:30:00+09:00</published>
        <media:description xmlns:media="http://search.yahoo.com/mrss/">https://example.com/brief.pdf\nhttps://example.com/brief.pdf</media:description>
      </entry>
    </feed>
    """

    monkeypatch.setattr("collectors.hana_brief.requests.get", lambda url, timeout: DummyResponse(feed_xml))
    monkeypatch.setattr(
        "collectors.hana_brief.download_pdf",
        lambda url, source: f"data/20260612/{source}/{url.rsplit('/', 1)[-1]}",
    )
    monkeypatch.setattr(
        "collectors.hana_brief.HanaBriefCollector._extract_comment_text",
        lambda self, video_id: (
            "■ 데일리발표자료 요약 바로가기\n"
            "https://file.hanaw.com/download/research/FileServer/WEB/info/daily/2026/06/11/Daily_260612.pdf\n"
            "https://www.hanaw.com/main/research/research/RC_000000_M.cmd"
        ),
    )

    result = HanaBriefCollector({"channel_id": "real_channel", "max_videos": 1}).collect()

    assert result.error is None
    assert len(result.items) == 1
    assert result.items[0].pdf_url == "https://file.hanaw.com/download/research/FileServer/WEB/info/daily/2026/06/11/Daily_260612.pdf"
    assert result.items[0].local_path.endswith("Daily_260612.pdf")
