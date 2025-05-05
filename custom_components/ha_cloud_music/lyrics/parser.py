import re
from typing import List, Dict, Optional
import aiohttp
import asyncio
import json
import base64
from Crypto.Cipher import AES
import random
import codecs
import logging

_LOGGER = logging.getLogger(__name__)

class LyricLine:
    def __init__(self, time: float, text: str):
        self.time = time
        self.text = text

class LyricParser:
    def __init__(self):
        self.lyrics: List[LyricLine] = []
        self.current_index = 0
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Referer': 'https://music.163.com/',
            'Origin': 'https://music.163.com'
        }

    def parse_lrc(self, lrc_content: str) -> None:
        """解析LRC格式的歌词"""
        self.lyrics.clear()
        self.current_index = 0
        
        # 匹配时间标签和歌词文本
        pattern = r'\[(\d{2}):(\d{2})\.(\d{2,3})\](.*)'
        
        for line in lrc_content.split('\n'):
            match = re.match(pattern, line)
            if match:
                minutes, seconds, milliseconds, text = match.groups()
                time = float(minutes) * 60 + float(seconds) + float(milliseconds) / 1000
                if text.strip():  # 只添加非空歌词
                    self.lyrics.append(LyricLine(time, text.strip()))
        
        # 按时间排序
        self.lyrics.sort(key=lambda x: x.time)
        _LOGGER.warning("解析到 %d 行歌词", len(self.lyrics))

    def get_current_lyric(self, current_time: float) -> Optional[str]:
        """根据当前时间获取对应的歌词"""
        if not self.lyrics:
            return None
            
        # 找到当前时间对应的歌词
        for i, line in enumerate(self.lyrics):
            if i == len(self.lyrics) - 1 or (line.time <= current_time < self.lyrics[i + 1].time):
                self.current_index = i
                return line.text
                
        return None

    def get_next_lyric(self) -> Optional[str]:
        """获取下一句歌词"""
        if not self.lyrics or self.current_index >= len(self.lyrics) - 1:
            return None
        return self.lyrics[self.current_index + 1].text

    def get_previous_lyric(self) -> Optional[str]:
        """获取上一句歌词"""
        if not self.lyrics or self.current_index <= 0:
            return None
        return self.lyrics[self.current_index - 1].text

    async def search_song(self, song_name: str, artist: str) -> Optional[str]:
        """搜索歌曲获取ID"""
        try:
            search_url = "https://music.163.com/api/search/get/web"
            params = {
                's': f"{song_name} {artist}",
                'type': 1,  # 1: 单曲, 10: 专辑, 100: 歌手, 1000: 歌单
                'limit': 1
            }
            
            _LOGGER.warning("搜索歌曲: %s - %s", song_name, artist)
            async with aiohttp.ClientSession() as session:
                async with session.get(search_url, params=params, headers=self.headers) as response:
                    if response.status == 200:
                        text = await response.text()
                        try:
                            data = json.loads(text)
                            _LOGGER.warning("搜索响应: %s", data)
                            if data.get('result', {}).get('songs'):
                                song_id = str(data['result']['songs'][0]['id'])
                                _LOGGER.warning("找到歌曲ID: %s", song_id)
                                return song_id
                            else:
                                _LOGGER.warning("未找到歌曲，响应数据: %s", data)
                        except json.JSONDecodeError as e:
                            _LOGGER.error("解析JSON失败: %s, 响应内容: %s", e, text)
        except Exception as e:
            _LOGGER.error("搜索歌曲出错: %s", e)
        return None

    async def fetch_lyrics(self, song_name: str, artist: str) -> Optional[str]:
        """从网易云音乐获取歌词"""
        try:
            # 1. 搜索歌曲获取ID
            song_id = await self.search_song(song_name, artist)
            if not song_id:
                _LOGGER.warning("无法获取歌曲ID，跳过获取歌词")
                return None

            # 2. 获取歌词
            lyrics_url = f"https://music.163.com/api/song/lyric?id={song_id}&lv=1&kv=1&tv=-1"
            _LOGGER.warning("获取歌词URL: %s", lyrics_url)
            
            async with aiohttp.ClientSession() as session:
                async with session.get(lyrics_url, headers=self.headers) as response:
                    if response.status == 200:
                        text = await response.text()
                        try:
                            data = json.loads(text)
                            _LOGGER.warning("歌词响应: %s", data)
                            # 优先使用翻译歌词，如果没有则使用原文歌词
                            lrc = data.get('lrc', {}).get('lyric', '')
                            if not lrc:
                                _LOGGER.warning("未找到歌词内容，完整响应: %s", data)
                                return None
                            _LOGGER.warning("获取到歌词，长度: %d", len(lrc))
                            return lrc
                        except json.JSONDecodeError as e:
                            _LOGGER.error("解析JSON失败: %s, 响应内容: %s", e, text)
                    else:
                        _LOGGER.error("获取歌词失败，状态码: %d", response.status)
        except Exception as e:
            _LOGGER.error("获取歌词出错: %s", e)
        return None 