import logging, time, datetime
import asyncio


from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.components.media_player import MediaPlayerEntity, MediaPlayerDeviceClass, MediaPlayerEntityFeature
from homeassistant.components.media_player.const import (
    SUPPORT_TURN_OFF,
    SUPPORT_TURN_ON,
    SUPPORT_VOLUME_STEP,
    SUPPORT_VOLUME_SET,
    SUPPORT_VOLUME_MUTE,
    SUPPORT_SELECT_SOURCE,
    SUPPORT_PLAY_MEDIA,
    SUPPORT_PLAY,
    SUPPORT_PAUSE,
    SUPPORT_SEEK,
    SUPPORT_CLEAR_PLAYLIST,
    SUPPORT_SHUFFLE_SET,
    SUPPORT_REPEAT_SET,
    SUPPORT_NEXT_TRACK,
    SUPPORT_PREVIOUS_TRACK,
    MEDIA_TYPE_ALBUM,
    MEDIA_TYPE_ARTIST,
    MEDIA_TYPE_CHANNEL,
    MEDIA_TYPE_EPISODE,
    MEDIA_TYPE_MOVIE,
    MEDIA_TYPE_PLAYLIST,
    MEDIA_TYPE_SEASON,
    MEDIA_TYPE_TRACK,
    MEDIA_TYPE_TVSHOW,
)
from homeassistant.const import (
    CONF_TOKEN, 
    CONF_URL,
    CONF_NAME,
    STATE_OFF, 
    STATE_ON, 
    STATE_PLAYING,
    STATE_PAUSED,
    STATE_IDLE,
    STATE_UNAVAILABLE
)

from .manifest import manifest
from .lyrics.parser import LyricParser

DOMAIN = manifest.domain

_LOGGER = logging.getLogger(__name__)

SUPPORT_FEATURES = SUPPORT_VOLUME_STEP | SUPPORT_VOLUME_MUTE | SUPPORT_VOLUME_SET | \
    SUPPORT_PLAY_MEDIA | SUPPORT_PLAY | SUPPORT_PAUSE | SUPPORT_PREVIOUS_TRACK | SUPPORT_NEXT_TRACK | \
    MediaPlayerEntityFeature.BROWSE_MEDIA | SUPPORT_SEEK | SUPPORT_CLEAR_PLAYLIST | SUPPORT_SHUFFLE_SET | SUPPORT_REPEAT_SET

# 定时器时间
TIME_BETWEEN_UPDATES = datetime.timedelta(seconds=1)
UNSUB_INTERVAL = None

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:

    entities = []
    for source_media_player in entry.options.get('media_player', []):
      entities.append(CloudMusicMediaPlayer(hass, source_media_player))

    def media_player_interval(now):
      for mp in entities:
        mp.interval(now)

    # 开启定时器
    global UNSUB_INTERVAL
    if UNSUB_INTERVAL is not None:
      UNSUB_INTERVAL()
    UNSUB_INTERVAL = async_track_time_interval(hass, media_player_interval, TIME_BETWEEN_UPDATES)

    async_add_entities(entities, True)

class CloudMusicMediaPlayer(MediaPlayerEntity):

    def __init__(self, hass, source_media_player):
        self.hass = hass
        self._attributes = {
            'platform': 'cloud_music'
        }
        # fixed attribute
        self._attr_media_image_remotely_accessible = True
        self._attr_device_class = MediaPlayerDeviceClass.TV.value
        self._attr_supported_features = SUPPORT_FEATURES

        # default attribute
        self.source_media_player = source_media_player
        self._attr_name = f'{manifest.name} {source_media_player.split(".")[1]}'
        self._attr_unique_id = f'{manifest.domain}{source_media_player}'
        self._attr_state =  STATE_ON
        self._attr_volume_level = 1
        self._attr_repeat = 'all'
        self._attr_shuffle = False

        self.cloud_music = hass.data['cloud_music']
        self.before_state = None
        self.current_state = None
        self._last_seek_time = None
        
        # 歌词相关
        self.lyric_parser = LyricParser()
        self._attr_lyrics = None
        self._attr_current_lyric = None
        self._last_lyric_update = None

    def interval(self, now):
        # _LOGGER.warning("播放状态：%s", self._attr_state)
        
        # 暂停时不更新
        if self._attr_state != STATE_PLAYING:
            return
    
        # 获取当前时间
        new_updated_at = datetime.datetime.now()
        
        # 如果是第一次调用或者需要重置计时
        if not hasattr(self, '_last_position_update') or self._last_position_update is None:
            self._last_position_update = new_updated_at
            self._attr_media_position = 0
        else:
            self._attr_media_position += 1  # 增加整数秒
            self._last_position_update = new_updated_at
            self._attr_media_position_updated_at = datetime.datetime.now(datetime.timezone.utc)
            
            # 更新歌词
            if self._attr_lyrics:
                current_lyric = self.lyric_parser.get_current_lyric(self._attr_media_position)
                if current_lyric != self._attr_current_lyric:
                    _LOGGER.warning("更新歌词 - 位置: %d, 歌词: %s", self._attr_media_position, current_lyric)
                    self._attr_current_lyric = current_lyric
                    self._attributes['current_lyric'] = current_lyric
                    
                    # 获取下一句歌词
                    next_lyric = self.lyric_parser.get_next_lyric()
                    self._attributes['next_lyric'] = next_lyric
                    
                    self.hass.loop.call_soon_threadsafe(self.async_write_ha_state)
            
        self.hass.loop.call_soon_threadsafe(self.async_write_ha_state)
        # 更新其他属性（从DLNA设备获取）
        media_player = self.media_player
        if media_player is not None:
            attrs = media_player.attributes
            self._attr_media_duration = attrs.get('media_duration', 0)

            # 判断是否下一曲
            if self.before_state is not None:
                # 判断音乐总时长
                if self.before_state['media_duration'] > 0:
                    delta = self._attr_media_duration - self._attr_media_position
                    # _LOGGER.warning("差值：%s", delta)
                    if delta <= 1 and self._attr_media_duration > 1 and delta >= 0:
                        _LOGGER.warning("小于1 切歌")
                        self._attr_state = STATE_PAUSED
                        self.before_state = None
                        self.hass.loop.call_soon_threadsafe(
                            lambda: asyncio.create_task(self.async_media_next_track())
                        )
                        return
    
                # if (self.before_state['media_duration'] == 0 and 
                #     self.before_state['media_position'] == 0 and 
                #     self.current_state == STATE_PLAYING and
                #     self._attr_media_duration == 0 and 
                #     self._attr_media_position == 0 and 
                #     self._attr_state == STATE_PLAYING):
                #     time.sleep(10)
                #     if (self.before_state['media_duration'] == 0 and 
                #         self.before_state['media_position'] == 0 and 
                #         self.current_state == STATE_PLAYING and
                #         self._attr_media_duration == 0 and 
                #         self._attr_media_position == 0 and 
                #         self._attr_state == STATE_PLAYING):
                #         self.hass.loop.call_soon_threadsafe(
                #             lambda: asyncio.create_task(self.async_media_next_track())
                #         )
                #         self.before_state = None
                #         return
    
        # 更新状态记录
        self.before_state = {
            'media_position': int(self._attr_media_position),
            'media_duration': int(self._attr_media_duration),
            'state': self.current_state
        }
        self.current_state = media_player.state if media_player is not None else self._attr_state
    
        if hasattr(self, 'playlist'):
            music_info = self.playlist[self.playindex]
            self._attr_app_name = music_info.singer
            self._attr_media_image_url = music_info.thumbnail
            self._attr_media_album_name = music_info.album
            self._attr_media_title = music_info.song
            self._attr_media_artist = music_info.singer
        # self.hass.loop.call_soon_threadsafe(lambda: asyncio.create_task(self.async_write_ha_state()))

    @property
    def media_player(self):
        if self.entity_id is not None and self.source_media_player is not None:
            return self.hass.states.get(self.source_media_player)

    @property
    def device_info(self):
        return {
            'identifiers': {
                (DOMAIN, manifest.documentation)
            },
            'name': self.name,
            'manufacturer': 'shaonianzhentan',
            'model': 'CloudMusic',
            'sw_version': manifest.version
        }

    @property
    def extra_state_attributes(self):
        return self._attributes

    async def async_browse_media(self, media_content_type=None, media_content_id=None):
        return await self.cloud_music.async_browse_media(self, media_content_type, media_content_id)

    async def async_volume_up(self):
        await self.async_call('volume_up')

    async def async_volume_down(self):
        await self.async_call('volume_down')

    async def async_mute_volume(self, mute):
        self._attr_is_volume_muted = mute
        await self.async_call('mute_volume', { 'is_volume_muted': mute })

    async def async_set_volume_level(self, volume: float):
        self._attr_volume_level = volume
        await self.async_call('volume_set', { 'volume_level': volume })

    async def async_play_media(self, media_type, media_id, **kwargs):
        self._attr_state = STATE_PAUSED
        self._attr_media_position = 0  # 重置进度
        self._attr_media_position_updated_at = datetime.datetime.now(datetime.timezone.utc)
        
        media_content_id = media_id
        result = await self.cloud_music.async_play_media(self, self.cloud_music, media_id)
        if result is not None:
            if result == 'index':
                # 播放当前列表指定项
                media_content_id = self.playlist[self.playindex].url
            elif result.startswith('http'):
                # HTTP播放链接
                media_content_id = result
            else:
                # 添加播放列表到播放器
                media_content_id = self.playlist[self.playindex].url

        self._attr_media_content_id = media_content_id
        
        # 获取并解析歌词
        if hasattr(self, 'playlist'):
            music_info = self.playlist[self.playindex]
            _LOGGER.warning("正在获取歌词 - 歌曲: %s, 歌手: %s", music_info.song, music_info.singer)
            lyrics = await self.lyric_parser.fetch_lyrics(music_info.song, music_info.singer)
            if lyrics:
                _LOGGER.warning("成功获取歌词，长度: %d", len(lyrics))
                self.lyric_parser.parse_lrc(lyrics)
                self._attr_lyrics = lyrics
                self._attr_current_lyric = None
                self._attributes['lyrics'] = lyrics
                self._attributes['current_lyric'] = None
            else:
                _LOGGER.warning("未能获取到歌词")

        await self.async_call('play_media', {
            'media_content_id': media_content_id,
            'media_content_type': 'music'
        })
        self._attr_state = STATE_PLAYING

        self.before_state = None

    async def async_media_play(self):
        # 强制暂停一次
        await self.async_call('media_pause')
        await asyncio.sleep(0.1)
         # 强制暂停一次
        await self.async_call('media_play')
        await asyncio.sleep(0.1)
         # 强制暂停一次
        await self.async_call('media_pause')
        await asyncio.sleep(0.1)
        
        # 然后再播放
        await self.async_call('media_play')
        self._attr_state = STATE_PLAYING

    async def async_media_pause(self):
        self._attr_state = STATE_PAUSED
        await self.async_call('media_pause')

    async def async_set_repeat(self, repeat):
        self._attr_repeat = repeat

    async def async_set_shuffle(self, shuffle):
        self._attr_shuffle = shuffle

    async def async_media_next_track(self):
        self._attr_state = STATE_PAUSED
        await self.cloud_music.async_media_next_track(self, self._attr_shuffle)
        self._attr_media_position = 0
        self._attr_media_position_updated_at = datetime.datetime.now()

    async def async_media_previous_track(self):
        self._attr_state = STATE_PAUSED
        await self.cloud_music.async_media_previous_track(self, self._attr_shuffle)
        self._attr_media_position = 0
        self._attr_media_position_updated_at = datetime.datetime.now()

    async def async_media_seek(self, position):
        await self.async_call('media_seek', { 'seek_position': position })
        # 更新进度状态
        self._attr_media_position = position
        self._attr_media_position_updated_at = datetime.datetime.now()
        self._last_seek_time = datetime.datetime.now()
        # 通知前端更新 UI
        self.async_write_ha_state()
        # 立即执行一次 interval，防止延迟或卡住不切歌
        self._attr_state = STATE_PLAYING
        self.interval(datetime.datetime.now())
        

    async def async_media_stop(self):
        await self.async_call('media_stop')

    # 更新属性
    async def async_update(self):
        pass

    # 调用服务
    async def async_call(self, service, service_data={}):
        media_player = self.media_player
        if media_player is not None:
            service_data.update({ 'entity_id': media_player.entity_id })
            await self.hass.services.async_call('media_player', service, service_data)