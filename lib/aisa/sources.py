#!/usr/bin/env python3
"""三个 Bot 用到的 AIsa 数据源，一个函数对应一个接口。

接口路径和参数以 https://aisa.one/openapi.json 为准（2026-11-09 核对）。
这里只做「取数据」，不做判断；判断交给 Agent。
"""
from __future__ import annotations

import datetime as dt

from client import call

# ---------- 社交平台 ----------

def twitter_search(query: str, query_type: str = 'Latest', cursor: str = '') -> dict:
    """X 高级搜索。query_type: Latest | Top"""
    return call('GET', 'twitter/tweet/advanced_search',
                params={'query': query, 'queryType': query_type, 'cursor': cursor or None})


def tweets_by_ids(ids: list[str] | str) -> dict:
    ids = ids if isinstance(ids, str) else ','.join(ids)
    return call('GET', 'twitter/tweets', params={'tweet_ids': ids})


def douyin_video(share_url: str) -> dict:
    """抖音分享链接 -> 视频详情（标题、作者、数据、音视频地址）。"""
    return call('GET', 'tikhub/douyin/web/fetch_one_video_by_share_url', params={'share_url': share_url})


def xhs_note(share_text: str, video: bool = False) -> dict:
    """小红书分享链接（xiaohongshu.com / xhslink.com）-> 笔记详情。"""
    kind = 'get_video_note_detail' if video else 'get_image_note_detail'
    return call('GET', f'tikhub/xiaohongshu/app_v2/{kind}', params={'share_text': share_text})


def youtube_subtitles(video_id: str, subtitles_language: str | None = None) -> dict:
    """YouTube 字幕（DataForSEO）。subtitles_language 不填时取视频默认字幕。"""
    task = {'video_id': video_id, 'location_code': 2840, 'language_code': 'en'}
    if subtitles_language:
        task['subtitles_language'] = subtitles_language
    return call('POST', 'dataforseo/serp/youtube/video_subtitles/live/advanced', body=[task], max_price='0.01')


def youtube_video_info(video_id: str) -> dict:
    task = {'video_id': video_id, 'location_code': 2840, 'language_code': 'en'}
    return call('POST', 'dataforseo/serp/youtube/video_info/live/advanced', body=[task], max_price='0.01')


# ---------- 网页 / 搜索 ----------

def web_page(url: str) -> dict:
    """网页 -> Markdown 正文（Firecrawl）。"""
    return call('POST', 'firecrawl/scrape', body={'url': url, 'proxy': 'basic', 'formats': ['markdown']})


def web_extract(urls: list[str] | str, query: str | None = None) -> dict:
    """备用的网页正文提取（Tavily Extract）。"""
    body = {'urls': urls, 'format': 'markdown'}
    if query:
        body['query'] = query
    return call('POST', 'tavily/extract', body=body)


def web_search(query: str, max_results: int = 5, days: int | None = None) -> dict:
    """交叉核实用的网页搜索（Tavily）。"""
    body = {'query': query, 'max_results': max_results}
    if days:
        body['start_date'] = (dt.date.today() - dt.timedelta(days=days)).isoformat()
    return call('POST', 'tavily/search', body=body)


def perplexity(question: str, model: str = 'sonar') -> dict:
    """带引用的检索问答（Perplexity Sonar），用来核实消息真假。"""
    return call('POST', f'perplexity/{model}',
                body={'model': model, 'messages': [{'role': 'user', 'content': question}], 'return_citations': True},
                max_price='0.05')


def serp_google(keyword: str, location_code: int = 2840, language_code: str = 'en', depth: int = 30) -> dict:
    """Google 自然搜索结果（DataForSEO）：搜词找站。"""
    task = {'keyword': keyword, 'location_code': location_code, 'language_code': language_code, 'depth': depth}
    return call('POST', 'dataforseo/serp/google/organic/live/advanced', body=[task], max_price='0.06')


# ---------- 站点指标 ----------

def ahrefs_domain_rating(target: str, date: str | None = None) -> dict:
    return call('GET', 'ahrefs/site-explorer/domain-rating',
                params={'target': target, 'date': date or dt.date.today().isoformat()})


def ahrefs_metrics(target: str, date: str | None = None) -> dict:
    return call('GET', 'ahrefs/site-explorer/metrics',
                params={'target': target, 'date': date or dt.date.today().isoformat()})


# ---------- 行情 / 事件 ----------

def coin_prices(ids: list[str] | str, vs: str = 'usd') -> dict:
    """CoinGecko 现价 + 24 小时涨跌。ids 用 CoinGecko 的 id，例如 bitcoin,ethereum。"""
    ids = ids if isinstance(ids, str) else ','.join(ids)
    return call('GET', 'coingecko/simple/price',
                params={'ids': ids, 'vs_currencies': vs, 'include_24hr_change': True, 'include_last_updated_at': True})


def stock_snapshot(ticker: str) -> dict:
    return call('GET', 'financial/prices/snapshot', params={'ticker': ticker})


def stock_news(ticker: str, limit: int = 10) -> dict:
    return call('GET', 'financial/news', params={'ticker': ticker, 'limit': limit})


def polymarket_events(tag_slug: str | None = None, limit: int = 20) -> dict:
    """进行中的预测市场事件，按成交量排序。"""
    return call('GET', 'polymarket/events',
                params={'active': True, 'closed': False, 'limit': limit, 'order': 'volume', 'ascending': False,
                        'tag_slug': tag_slug})


def fred_series(series_id: str, limit: int = 12) -> dict:
    """FRED 宏观数据，例如 FEDFUNDS（联邦基金利率）、CPIAUCSL（CPI）。"""
    return call('GET', 'fred/series/observations',
                params={'series_id': series_id, 'limit': limit, 'sort_order': 'desc', 'file_type': 'json'})
