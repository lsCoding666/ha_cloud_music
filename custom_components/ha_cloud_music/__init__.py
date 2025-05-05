"""The ha_cloud_music component."""
import os
import logging
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.typing import ConfigType
from homeassistant.components.frontend import add_extra_js_url
import homeassistant.helpers.config_validation as cv
from homeassistant.const import CONF_URL

import asyncio
from .const import PLATFORMS
from .manifest import manifest
from .http import HttpView
from .cloud_music import CloudMusic

DOMAIN = "ha_cloud_music"
_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.deprecated(DOMAIN)

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the ha_cloud_music component."""
    # Register frontend resources
    root_path = os.path.dirname(os.path.abspath(__file__))
    frontend_path = os.path.join(root_path, "frontend")
    
    # Register the card
    add_extra_js_url(hass, f"/ha_cloud_music/frontend/lyrics-card.js")
    
    # Make frontend directory available
    hass.http.register_static_path(
        f"/{DOMAIN}/frontend",
        frontend_path,
        cache_headers=False
    )
    
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up ha_cloud_music from a config entry."""
    try:
        # 设置云音乐服务
        data = entry.data
        api_url = data.get(CONF_URL)
        hass.data['cloud_music'] = CloudMusic(hass, api_url)

        hass.http.register_view(HttpView)
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        entry.async_on_unload(entry.add_update_listener(update_listener))
        
        return True
    except Exception as e:
        _LOGGER.error(f"Error setting up ha_cloud_music: {str(e)}")
        return False

async def update_listener(hass, entry):
    await async_unload_entry(hass, entry)
    await asyncio.sleep(1)
    await async_setup_entry(hass, entry)

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)