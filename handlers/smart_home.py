"""
Smart Home Integration Hub
==========================
Universal smart home control for JARVIS.
Supports: IFTTT, Home Assistant, Philips Hue, SmartThings, and generic webhooks.
"""

import os
import logging
import requests
import json
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from enum import Enum

logger = logging.getLogger(__name__)


class DeviceType(Enum):
    LIGHT = "light"
    SWITCH = "switch"
    THERMOSTAT = "thermostat"
    LOCK = "lock"
    CAMERA = "camera"
    SPEAKER = "speaker"
    TV = "tv"
    BLINDS = "blinds"
    FAN = "fan"
    SENSOR = "sensor"
    CUSTOM = "custom"


class SmartHomeHub:
    """Universal smart home controller"""
    
    def __init__(self):
        # IFTTT Configuration
        self.ifttt_key = os.getenv("IFTTT_WEBHOOK_KEY")
        
        # Home Assistant Configuration  
        self.hass_url = os.getenv("HOME_ASSISTANT_URL")
        self.hass_token = os.getenv("HOME_ASSISTANT_TOKEN")
        
        # Philips Hue Configuration
        self.hue_bridge_ip = os.getenv("PHILIPS_HUE_BRIDGE_IP")
        self.hue_username = os.getenv("PHILIPS_HUE_USERNAME")
        
        # SmartThings Configuration
        self.smartthings_token = os.getenv("SMARTTHINGS_TOKEN")
        
        # Custom webhooks
        self.custom_webhooks: Dict[str, str] = {}
        
        # Device registry
        self.devices: Dict[str, Dict[str, Any]] = {}
        
        # Scene presets
        self.scenes = {
            'movie': {'lights': 20, 'blinds': 'closed', 'tv': 'on'},
            'work': {'lights': 100, 'blinds': 'open', 'music': 'focus'},
            'sleep': {'lights': 0, 'blinds': 'closed', 'thermostat': 68},
            'morning': {'lights': 80, 'blinds': 'open', 'coffee': 'brew'},
            'party': {'lights': 'disco', 'music': 'party', 'thermostat': 72},
            'away': {'lights': 0, 'thermostat': 65, 'security': 'armed'},
            'romantic': {'lights': 30, 'music': 'romantic', 'blinds': 'closed'},
            'focus': {'lights': 80, 'music': 'lo-fi', 'notifications': 'silent'},
        }
        
        self._log_configuration()
    
    def _log_configuration(self):
        """Log available integrations"""
        integrations = []
        if self.ifttt_key:
            integrations.append("IFTTT")
        if self.hass_url and self.hass_token:
            integrations.append("Home Assistant")
        if self.hue_bridge_ip:
            integrations.append("Philips Hue")
        if self.smartthings_token:
            integrations.append("SmartThings")
        
        if integrations:
            logger.info(f"🏠 Smart Home integrations: {', '.join(integrations)}")
        else:
            logger.info("🏠 Smart Home: No integrations configured")
    
    # ==================== IFTTT ====================
    
    def trigger_ifttt(self, event: str, value1: str = "", value2: str = "", value3: str = "") -> bool:
        """Trigger IFTTT webhook event"""
        if not self.ifttt_key:
            logger.warning("IFTTT not configured")
            return False
        
        try:
            url = f"https://maker.ifttt.com/trigger/{event}/with/key/{self.ifttt_key}"
            payload = {}
            if value1:
                payload["value1"] = value1
            if value2:
                payload["value2"] = value2
            if value3:
                payload["value3"] = value3
            
            response = requests.post(url, json=payload, timeout=10)
            success = response.status_code == 200
            
            if success:
                logger.info(f"IFTTT triggered: {event}")
            else:
                logger.warning(f"IFTTT trigger failed: {response.status_code}")
            
            return success
            
        except Exception as e:
            logger.error(f"IFTTT error: {e}")
            return False
    
    # ==================== Home Assistant ====================
    
    def _hass_headers(self) -> Dict[str, str]:
        """Home Assistant API headers"""
        return {
            "Authorization": f"Bearer {self.hass_token}",
            "Content-Type": "application/json"
        }
    
    def hass_call_service(self, domain: str, service: str, entity_id: str = None, data: Dict = None) -> bool:
        """Call Home Assistant service"""
        if not self.hass_url or not self.hass_token:
            logger.warning("Home Assistant not configured")
            return False
        
        try:
            url = f"{self.hass_url}/api/services/{domain}/{service}"
            payload = data or {}
            if entity_id:
                payload["entity_id"] = entity_id
            
            response = requests.post(url, headers=self._hass_headers(), json=payload, timeout=10)
            success = response.status_code == 200
            
            if success:
                logger.info(f"Home Assistant: {domain}.{service} for {entity_id}")
            else:
                logger.warning(f"Home Assistant call failed: {response.status_code}")
            
            return success
            
        except Exception as e:
            logger.error(f"Home Assistant error: {e}")
            return False
    
    def hass_get_states(self) -> List[Dict]:
        """Get all Home Assistant entity states"""
        if not self.hass_url or not self.hass_token:
            return []
        
        try:
            response = requests.get(
                f"{self.hass_url}/api/states",
                headers=self._hass_headers(),
                timeout=10
            )
            if response.status_code == 200:
                return response.json()
            return []
        except Exception as e:
            logger.error(f"Home Assistant states error: {e}")
            return []
    
    def hass_get_entity(self, entity_id: str) -> Optional[Dict]:
        """Get specific entity state"""
        if not self.hass_url or not self.hass_token:
            return None
        
        try:
            response = requests.get(
                f"{self.hass_url}/api/states/{entity_id}",
                headers=self._hass_headers(),
                timeout=10
            )
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            logger.error(f"Home Assistant entity error: {e}")
            return None
    
    # ==================== Philips Hue ====================
    
    def hue_set_light(self, light_id: str, on: bool = None, brightness: int = None, color: str = None) -> bool:
        """Control Philips Hue light"""
        if not self.hue_bridge_ip or not self.hue_username:
            logger.warning("Philips Hue not configured")
            return False
        
        try:
            url = f"http://{self.hue_bridge_ip}/api/{self.hue_username}/lights/{light_id}/state"
            payload = {}
            
            if on is not None:
                payload["on"] = on
            if brightness is not None:
                payload["bri"] = min(254, max(1, int(brightness * 2.54)))  # Convert 0-100 to 1-254
            if color:
                # Convert color name to hue value
                colors = {
                    'red': 0, 'orange': 5000, 'yellow': 12750,
                    'green': 25500, 'blue': 46920, 'purple': 56100,
                    'pink': 56100, 'white': None
                }
                if color.lower() in colors and colors[color.lower()] is not None:
                    payload["hue"] = colors[color.lower()]
                    payload["sat"] = 254
            
            response = requests.put(url, json=payload, timeout=5)
            return response.status_code == 200
            
        except Exception as e:
            logger.error(f"Philips Hue error: {e}")
            return False
    
    def hue_get_lights(self) -> Dict:
        """Get all Hue lights"""
        if not self.hue_bridge_ip or not self.hue_username:
            return {}
        
        try:
            response = requests.get(
                f"http://{self.hue_bridge_ip}/api/{self.hue_username}/lights",
                timeout=5
            )
            if response.status_code == 200:
                return response.json()
            return {}
        except Exception as e:
            logger.error(f"Hue lights error: {e}")
            return {}
    
    # ==================== Universal Controls ====================
    
    def lights_on(self, room: str = "all", brightness: int = 100, color: str = None) -> str:
        """Turn lights on"""
        results = []
        
        # Try IFTTT
        if self.ifttt_key:
            event = f"lights_on_{room}" if room != "all" else "lights_on"
            if self.trigger_ifttt(event, str(brightness), color or ""):
                results.append("IFTTT")
        
        # Try Home Assistant
        if self.hass_url:
            entity = f"light.{room}" if room != "all" else "all"
            data = {"brightness_pct": brightness}
            if color:
                data["color_name"] = color
            if self.hass_call_service("light", "turn_on", entity, data):
                results.append("Home Assistant")
        
        # Try Hue
        if self.hue_bridge_ip:
            lights = self.hue_get_lights()
            for light_id in lights:
                self.hue_set_light(light_id, on=True, brightness=brightness, color=color)
            if lights:
                results.append("Philips Hue")
        
        if results:
            return f"✅ Lights on via {', '.join(results)}"
        return "❌ No smart home integrations available"
    
    def lights_off(self, room: str = "all") -> str:
        """Turn lights off"""
        results = []
        
        if self.ifttt_key:
            event = f"lights_off_{room}" if room != "all" else "lights_off"
            if self.trigger_ifttt(event):
                results.append("IFTTT")
        
        if self.hass_url:
            entity = f"light.{room}" if room != "all" else "all"
            if self.hass_call_service("light", "turn_off", entity):
                results.append("Home Assistant")
        
        if self.hue_bridge_ip:
            lights = self.hue_get_lights()
            for light_id in lights:
                self.hue_set_light(light_id, on=False)
            if lights:
                results.append("Philips Hue")
        
        if results:
            return f"✅ Lights off via {', '.join(results)}"
        return "❌ No smart home integrations available"
    
    def set_thermostat(self, temperature: int, mode: str = "auto") -> str:
        """Set thermostat temperature"""
        results = []
        
        if self.ifttt_key:
            if self.trigger_ifttt("set_thermostat", str(temperature), mode):
                results.append("IFTTT")
        
        if self.hass_url:
            data = {"temperature": temperature}
            if mode:
                data["hvac_mode"] = mode
            if self.hass_call_service("climate", "set_temperature", "climate.thermostat", data):
                results.append("Home Assistant")
        
        if results:
            return f"✅ Thermostat set to {temperature}°F via {', '.join(results)}"
        return "❌ No thermostat integrations available"
    
    def lock_doors(self, lock: str = "all") -> str:
        """Lock doors"""
        results = []
        
        if self.ifttt_key:
            if self.trigger_ifttt("lock_doors", lock):
                results.append("IFTTT")
        
        if self.hass_url:
            entity = f"lock.{lock}" if lock != "all" else "all"
            if self.hass_call_service("lock", "lock", entity):
                results.append("Home Assistant")
        
        if results:
            return f"🔒 Doors locked via {', '.join(results)}"
        return "❌ No lock integrations available"
    
    def unlock_doors(self, lock: str = "all") -> str:
        """Unlock doors"""
        results = []
        
        if self.ifttt_key:
            if self.trigger_ifttt("unlock_doors", lock):
                results.append("IFTTT")
        
        if self.hass_url:
            entity = f"lock.{lock}" if lock != "all" else "all"
            if self.hass_call_service("lock", "unlock", entity):
                results.append("Home Assistant")
        
        if results:
            return f"🔓 Doors unlocked via {', '.join(results)}"
        return "❌ No lock integrations available"
    
    def activate_scene(self, scene_name: str) -> str:
        """Activate a predefined scene"""
        scene_name = scene_name.lower()
        
        if scene_name not in self.scenes:
            available = ', '.join(self.scenes.keys())
            return f"❌ Unknown scene. Available: {available}"
        
        scene = self.scenes[scene_name]
        results = []
        
        # Apply scene settings
        if 'lights' in scene:
            if scene['lights'] == 0:
                self.lights_off()
            elif scene['lights'] == 'disco':
                # Special disco mode
                self.lights_on(brightness=100, color='blue')
            else:
                self.lights_on(brightness=scene['lights'])
            results.append("lights")
        
        if 'thermostat' in scene:
            self.set_thermostat(scene['thermostat'])
            results.append("thermostat")
        
        if 'security' in scene:
            if scene['security'] == 'armed':
                self.lock_doors()
                results.append("security")
        
        # IFTTT scene trigger
        if self.ifttt_key:
            self.trigger_ifttt(f"scene_{scene_name}")
        
        # Home Assistant scene
        if self.hass_url:
            self.hass_call_service("scene", "turn_on", f"scene.{scene_name}")
        
        return f"🎬 Scene '{scene_name}' activated: {', '.join(results)}"
    
    def get_home_status(self) -> Dict[str, Any]:
        """Get overall home status"""
        status = {
            'timestamp': datetime.now().isoformat(),
            'integrations': [],
            'devices': {}
        }
        
        if self.ifttt_key:
            status['integrations'].append('IFTTT')
        
        if self.hass_url:
            status['integrations'].append('Home Assistant')
            states = self.hass_get_states()
            for state in states[:20]:  # Limit to 20 devices
                entity_id = state.get('entity_id', '')
                status['devices'][entity_id] = {
                    'state': state.get('state'),
                    'friendly_name': state.get('attributes', {}).get('friendly_name')
                }
        
        if self.hue_bridge_ip:
            status['integrations'].append('Philips Hue')
            lights = self.hue_get_lights()
            for light_id, light in lights.items():
                status['devices'][f'hue_light_{light_id}'] = {
                    'state': 'on' if light.get('state', {}).get('on') else 'off',
                    'friendly_name': light.get('name')
                }
        
        return status
    
    def execute_command(self, command: str, params: Dict = None) -> str:
        """Execute a smart home command by name"""
        params = params or {}
        
        commands = {
            'lights_on': lambda: self.lights_on(
                params.get('room', 'all'),
                params.get('brightness', 100),
                params.get('color')
            ),
            'lights_off': lambda: self.lights_off(params.get('room', 'all')),
            'set_thermostat': lambda: self.set_thermostat(
                params.get('temperature', 72),
                params.get('mode', 'auto')
            ),
            'lock_doors': lambda: self.lock_doors(params.get('lock', 'all')),
            'unlock_doors': lambda: self.unlock_doors(params.get('lock', 'all')),
            'activate_scene': lambda: self.activate_scene(params.get('scene', 'default')),
        }
        
        if command in commands:
            return commands[command]()
        
        return f"❌ Unknown command: {command}"


# Global instance
smart_home = SmartHomeHub()
