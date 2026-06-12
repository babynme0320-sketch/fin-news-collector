from __future__ import annotations

import itertools
import re
from datetime import date, timedelta

import requests
import yt_dlp
from bs4 import BeautifulSoup
from yt_dlp.utils import DownloadError

from .base import CollectorResult, Report, normalize_date
from .pdf_downloader import download_pdf

YDL_TIMEOUT = 10
PDF_URL_PATTERN = re.compile(r"https?://[^\s\"')>]+?\.pdf(?:\?[^\s\"')>]*)?", re.IGNORECASE)
_HANAW_BASE = "https://file.hanaw.com/download/research/FileServer/WEB/info/daily"


class HanaBriefCollector:
    def __init__(self, config: dict):
        self.config = config

    def collect(self) -> CollectorResult:
        result = CollectorResult(source_name="하나증권 모닝브리프", kind="section")

        # Primary: stable direct URL construction — no YouTube dependency
        try:
            direct_items = self._collect_via_direct_urls()
        except Exception:
            direct_items = []

        if direct_items:
            result.items = direct_items
            return result

        # Fallback: YouTube RSS / yt-dlp
        channel_id = self.config.get("channel_id", "")
        if not channel_id or channel_id.startswith("REPLACE"):
            result.error = "직접 URL 실패 및 channel_id 미설정"
            return result

        try:
            entries = self._fetch_video_entries(channel_id)
        except Exception as exc:
            result.error = str(exc)
            return result

        target_count = self.config.get("max_videos", 5)
        for entry in entries:
            if not self._is_morning_brief_entry(entry):
                continue
            report_items = self._collect_video_reports(entry)
            result.items.extend(report_items)
            if len(result.items) >= target_count:
                result.items = result.items[:target_count]
                break

        if not result.items:
            result.error = "PDF 링크를 찾지 못함"

        return result

    def _collect_via_direct_urls(self) -> list[Report]:
        """최근 영업일 하나증권 PDF URL을 패턴으로 직접 생성 후 검증."""
        n_days = self.config.get("max_videos", 5)
        today = date.today()
        reports: list[Report] = []
        candidate = today

        for _ in range(30):  # 최대 30 캘린더일 소급
            if len(reports) >= n_days:
                break
            if candidate.weekday() < 5:  # 평일만 처리
                brief_date_str = candidate.strftime("%y%m%d")
                # URL 경로 날짜 = 브리프 날짜 - 1일 (전날 저녁 업로드)
                url_path_date = candidate - timedelta(days=1)
                pdf_url = (
                    f"{_HANAW_BASE}/"
                    f"{url_path_date.strftime('%Y/%m/%d')}/"
                    f"Daily_{brief_date_str}.pdf"
                )
                try:
                    resp = requests.head(pdf_url, timeout=(3, 8), allow_redirects=True)
                    if resp.status_code == 200:
                        try:
                            local_path = download_pdf(pdf_url, "하나증권")
                        except Exception:
                            local_path = ""
                        reports.append(Report(
                            title=f"하나증권 모닝브리프 {candidate.strftime('%Y-%m-%d')}",
                            pdf_url=pdf_url,
                            local_path=local_path,
                            date=candidate.strftime("%Y-%m-%d"),
                            source="하나증권",
                        ))
                except Exception:
                    pass
            candidate -= timedelta(days=1)

        return reports

    def _fetch_video_entries(self, channel_id: str) -> list[dict]:
        feed_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
        try:
            response = requests.get(feed_url, timeout=(5, 15))
            response.raise_for_status()
        except requests.RequestException:
            response = None

        if response is not None:
            soup = BeautifulSoup(response.text, "xml")
            entries = []
            scan_limit = self.config.get("feed_scan_limit", self.config.get("max_videos", 5) * 5)
            for entry in soup.find_all("entry")[:scan_limit]:
                video_id = entry.find("videoId") or entry.find("yt:videoId")
                title = entry.find("title")
                published = entry.find("published")
                description = entry.find("description") or entry.find("media:description")
                entries.append({
                    "id": video_id.get_text(strip=True) if video_id else "",
                    "title": title.get_text(strip=True) if title else "모닝브리프",
                    "upload_date": published.get_text(strip=True) if published else "",
                    "description": description.get_text("\n", strip=True) if description else "",
                })
            if entries:
                return entries

        options = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": True,
            "playlistend": self.config.get("feed_scan_limit", self.config.get("max_videos", 5) * 5),
            "socket_timeout": YDL_TIMEOUT,
        }
        with yt_dlp.YoutubeDL(options) as ydl:
            payload = ydl.extract_info(
                f"https://www.youtube.com/channel/{channel_id}/videos",
                download=False,
            )
        return list((payload or {}).get("entries", []))

    def _is_morning_brief_entry(self, entry: dict) -> bool:
        title = (entry.get("title") or "").strip()
        lowered = title.lower()
        return "모닝브리프" in title or "morning brief" in lowered

    def _collect_video_reports(self, entry: dict) -> list[Report]:
        video_id = entry.get("id", "")
        if not video_id:
            return []

        details = {
            "upload_date": entry.get("upload_date", ""),
            "title": entry.get("title", "모닝브리프"),
            "description": entry.get("description", ""),
        }
        comment_text = self._extract_comment_text(video_id)
        if comment_text:
            details["comment_text"] = comment_text

        if not details["description"] and "comment_text" not in details:
            details = self._fetch_video_detail(video_id)
            if not details:
                return []

        upload_date = normalize_date(details.get("upload_date", ""))
        title = details.get("title", "모닝브리프")
        reports: list[Report] = []
        seen_urls: set[str] = set()
        source_texts = (
            [details.get("comment_text", "")]
            if details.get("comment_text")
            else [details.get("description", "")]
        )
        for matched_url in PDF_URL_PATTERN.findall("\n".join(text for text in source_texts if text)):
            pdf_url = matched_url.rstrip(".,)")
            if pdf_url in seen_urls:
                continue
            seen_urls.add(pdf_url)
            try:
                local_path = download_pdf(pdf_url, "하나증권")
            except requests.RequestException:
                local_path = ""
            reports.append(Report(
                title=title,
                pdf_url=pdf_url,
                local_path=local_path,
                date=upload_date,
                source="하나증권",
            ))
        return reports

    def _extract_comment_text(self, video_id: str) -> str:
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        options = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "getcomments": True,
            "socket_timeout": YDL_TIMEOUT,
        }
        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(video_url, download=False, process=False) or {}
        except DownloadError:
            return ""

        extractor = info.get("__post_extractor")
        if not extractor:
            return ""

        try:
            comment_data = extractor() or {}
        except Exception:
            return ""

        comments = comment_data.get("comments") or []
        preferred_comments = [
            c for c in comments
            if c.get("author_is_uploader") or c.get("is_pinned")
        ]
        for comment in itertools.chain(preferred_comments, comments):
            text = comment.get("text", "")
            if "file.hanaw.com" in text or "hanaw.com/main/research" in text:
                return text
        return ""

    def _fetch_video_detail(self, video_id: str) -> dict:
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        options = {
            "quiet": True,
            "no_warnings": True,
            "socket_timeout": YDL_TIMEOUT,
            "skip_download": True,
        }
        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                return ydl.extract_info(video_url, download=False) or {}
        except DownloadError:
            return {}
