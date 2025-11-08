#!/usr/bin/env python3
"""
Claude Code statusline — Hangzhou (auto Xihu/Xiasha, JWT inside)
Python version with JWT authentication support
Data: QWeather v7 APIs for weather, minutely, daily forecast, and air quality
"""

import os
import sys
import json
import time
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
import subprocess
import hashlib
import base64
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache

# Try to import JWT library
try:
    import jwt
    HAS_JWT_LIB = True
except ImportError:
    HAS_JWT_LIB = False

# ===================== Configuration =====================
class Config:
    """Configuration management for statusline"""
    
    def __init__(self):
        # API Configuration
        self.api_host = os.environ.get('QWEATHER_API_HOST', '')
        self.key_id = os.environ.get('QWEATHER_KEY_ID', '')
        self.project_id = os.environ.get('QWEATHER_PROJECT_ID', '')
        self.private_key = os.environ.get('QWEATHER_PRIVATE_KEY', '')
        self.jwt_static = os.environ.get('QWEATHER_JWT', '')
        self.jwt_ttl = int(os.environ.get('QWEATHER_JWT_TTL_SEC', '900'))
        
        # Location Configuration
        self.xihu_loc = "120.13,30.26"
        self.xiasha_loc = "120.37,30.30"
        self.xihu_name = "西湖区"
        self.xiasha_name = "下沙大学城"
        
        # Work Schedule
        self.tzname = os.environ.get('STATUSLINE_TZ', 'Asia/Shanghai')
        self.work_start = int(os.environ.get('WORK_START', '8'))
        self.work_end = int(os.environ.get('WORK_END', '19'))
        self.work_days = os.environ.get('WORK_DAYS', '1-5')
        
        # File Paths
        self.site_toggle_file = Path(os.environ.get('STATUSLINE_SITE_TOGGLE_FILE', 
                                                     Path.home() / '.claude' / 'statusline.site'))
        self.cache_dir_base = Path.home() / '.cache' / 'claude-statusline'
        
        # Cache TTLs (seconds) - optimized for better performance
        self.ttl_now = int(os.environ.get('QWEATHER_TTL_NOW_SEC', '300'))
        self.ttl_min = int(os.environ.get('QWEATHER_TTL_MIN_SEC', '300'))
        self.ttl_aqi = int(os.environ.get('QWEATHER_TTL_AQI_SEC', '600'))
        self.ttl_daily = int(os.environ.get('QWEATHER_TTL_DAILY_SEC', '1800'))
        
        # Logging - default to WARNING for better performance
        self.log_level = os.environ.get('STATUSLINE_LOG_LEVEL', 'WARNING')
        self.log_dir = Path.home() / '.cache' / 'claude-statusline' / 'logs'

        # Debug Mode
        self.debug = os.environ.get('STATUSLINE_DEBUG', '0') == '1'
        
        # Color Output
        self.no_color = 'NO_COLOR' in os.environ

    def validate(self) -> bool:
        """Validate configuration"""
        if not self.api_host:
            logging.error("Missing QWEATHER_API_HOST environment variable")
            return False
        
        if not self.api_host.startswith(('http://', 'https://')):
            logging.error(f"Invalid QWEATHER_API_HOST format: {self.api_host}")
            return False
        
        # Expand ~ in private key path
        if self.private_key:
            self.private_key = os.path.expanduser(self.private_key)
        
        # Check JWT configuration
        has_jwt_config = (self.key_id and self.project_id and self.private_key)
        if has_jwt_config and not Path(self.private_key).exists():
            logging.warning(f"Private key file not found: {self.private_key}")
        
        if not has_jwt_config and not self.jwt_static:
            logging.warning("No JWT configuration found, API calls may fail")
        
        return True

# ===================== Logging Setup =====================
def setup_logging(config: Config):
    """Setup logging system"""
    if config.log_level == 'OFF':
        logging.disable(logging.CRITICAL)
        return
    
    config.log_dir.mkdir(parents=True, exist_ok=True)
    
    log_file = config.log_dir / f"statusline-{datetime.now().strftime('%Y%m%d')}.log"
    
    # Configure logging
    logging.basicConfig(
        level=getattr(logging, config.log_level),
        format='[%(asctime)s] [%(levelname)s] [%(funcName)s] %(message)s',
        handlers=[
            logging.FileHandler(log_file),
        ] if config.log_level != 'OFF' else []
    )
    
    # Log rotation (simple version - delete old logs)
    for old_log in config.log_dir.glob("statusline-*.log*"):
        if old_log.stat().st_mtime < time.time() - (7 * 86400):  # 7 days
            old_log.unlink()

# ===================== JWT Management =====================
class JWTManager:
    """Manage JWT token generation and caching"""
    
    def __init__(self, config: Config):
        self.config = config
        self.cache_file = config.cache_dir_base / 'jwt.txt'
        self.jwt_token = None
    
    def _generate_jwt_manual(self) -> Optional[str]:
        """Generate JWT manually using OpenSSL (fallback when PyJWT not available)"""
        try:
            import subprocess
            import base64
            
            # Create header and payload
            iat = int(time.time()) - 30
            exp = iat + self.config.jwt_ttl
            
            header = json.dumps({"alg": "EdDSA", "kid": self.config.key_id}, separators=(',', ':'))
            payload = json.dumps({"sub": self.config.project_id, "iat": iat, "exp": exp}, separators=(',', ':'))
            
            # Base64url encode
            def b64url(data: bytes) -> str:
                return base64.urlsafe_b64encode(data).rstrip(b'=').decode('ascii')
            
            h = b64url(header.encode())
            p = b64url(payload.encode())
            data = f"{h}.{p}"
            
            # Sign with OpenSSL
            private_key_path = os.path.expanduser(self.config.private_key)
            result = subprocess.run(
                ['openssl', 'pkeyutl', '-sign', '-inkey', private_key_path, '-rawin'],
                input=data.encode(),
                capture_output=True
            )
            
            if result.returncode != 0:
                logging.error(f"OpenSSL signing failed: {result.stderr.decode()}")
                return None
            
            sig = b64url(result.stdout)
            jwt_token = f"{data}.{sig}"
            
            logging.info("JWT generated successfully using OpenSSL")
            return jwt_token
            
        except Exception as e:
            logging.error(f"Manual JWT generation failed: {e}")
            return None
    
    def _generate_jwt_pylib(self) -> Optional[str]:
        """Generate JWT using PyJWT library"""
        try:
            private_key_path = os.path.expanduser(self.config.private_key)
            with open(private_key_path, 'r') as f:
                private_key = f.read()
            
            payload = {
                'iat': int(time.time()) - 30,
                'exp': int(time.time()) + self.config.jwt_ttl,
                'sub': self.config.project_id
            }
            headers = {
                'kid': self.config.key_id
            }
            
            jwt_token = jwt.encode(payload, private_key, algorithm='EdDSA', headers=headers)
            
            logging.info("JWT generated successfully using PyJWT")
            return jwt_token
            
        except Exception as e:
            logging.error(f"PyJWT generation failed: {e}")
            return None
    
    def ensure_jwt(self) -> Optional[str]:
        """Ensure we have a valid JWT token"""
        # Check if we can generate JWT
        private_key_path = os.path.expanduser(self.config.private_key) if self.config.private_key else ""
        if self.config.key_id and self.config.project_id and Path(private_key_path).exists():
            # Check cached JWT
            if self.cache_file.exists():
                cache_age = time.time() - self.cache_file.stat().st_mtime
                if cache_age < (self.config.jwt_ttl - 60):
                    self.jwt_token = self.cache_file.read_text().strip()
                    logging.debug("Using cached JWT")
                    return self.jwt_token
            
            # Generate new JWT
            if HAS_JWT_LIB:
                self.jwt_token = self._generate_jwt_pylib()
            else:
                self.jwt_token = self._generate_jwt_manual()
            
            if self.jwt_token:
                self.cache_file.parent.mkdir(parents=True, exist_ok=True)
                self.cache_file.write_text(self.jwt_token)
                return self.jwt_token
        
        # Use static JWT if available
        if self.config.jwt_static:
            self.jwt_token = self.config.jwt_static
            logging.info("Using provided QWEATHER_JWT")
            return self.jwt_token
        
        logging.error("No JWT available for authentication")
        return None

# ===================== Site Selection =====================
class SiteSelector:
    """Handle site selection logic"""
    
    def __init__(self, config: Config):
        self.config = config
    
    def _in_workdays(self, dow: int) -> bool:
        """Check if day of week is a workday"""
        spec = self.config.work_days.replace(' ', '')
        parts = spec.split(',')
        
        for part in parts:
            if '-' in part:
                a, b = map(int, part.split('-'))
                if a <= b:
                    if a <= dow <= b:
                        return True
                else:
                    if dow >= a or dow <= b:
                        return True
            elif part.isdigit():
                if int(part) == dow:
                    return True
        
        return False
    
    def _in_workhours(self, hour: int) -> bool:
        """Check if hour is within work hours"""
        s = self.config.work_start % 24
        e = self.config.work_end % 24
        h = hour % 24
        
        if s == e:
            return False
        elif s < e:
            return s <= h < e
        else:
            return h >= s or h < e
    
    def choose_site(self) -> Tuple[str, str, str]:
        """Choose site based on time and configuration
        Returns: (site_name, location, display_name)
        """
        # Check environment variable override
        if site_env := os.environ.get('STATUSLINE_SITE'):
            logging.debug(f"Site from env: {site_env}")
            if site_env.lower() == 'xiasha':
                return 'xiasha', self.config.xiasha_loc, self.config.xiasha_name
            else:
                return 'xihu', self.config.xihu_loc, self.config.xihu_name
        
        # Check toggle file
        if self.config.site_toggle_file.exists():
            content = self.config.site_toggle_file.read_text().strip().lower()
            if content in ['xihu', 'xiasha']:
                logging.debug(f"Site from file: {content}")
                if content == 'xiasha':
                    return 'xiasha', self.config.xiasha_loc, self.config.xiasha_name
                else:
                    return 'xihu', self.config.xihu_loc, self.config.xihu_name
        
        # Auto-detect based on time
        now = datetime.now()
        dow = now.isoweekday()  # 1=Monday, 7=Sunday
        hour = now.hour
        
        if self._in_workdays(dow) and self._in_workhours(hour):
            logging.debug(f"Auto site: xihu (workday={dow}, hour={hour})")
            return 'xihu', self.config.xihu_loc, self.config.xihu_name
        else:
            logging.debug(f"Auto site: xiasha (workday={dow}, hour={hour})")
            return 'xiasha', self.config.xiasha_loc, self.config.xiasha_name

# ===================== Weather API Client =====================
class WeatherClient:
    """Client for QWeather API"""
    
    def __init__(self, config: Config, jwt_token: Optional[str]):
        self.config = config
        self.jwt_token = jwt_token
        self.session = requests.Session()
        self.session.headers.update({
            'Accept-Encoding': 'gzip, deflate',
            'User-Agent': 'Claude-Statusline/1.0'
        })
        if jwt_token:
            self.session.headers['Authorization'] = f'Bearer {jwt_token}'
    
    def _validate_response(self, response: Dict[str, Any], api_name: str) -> bool:
        """Validate API response"""
        if not response:
            logging.error(f"{api_name}: Empty response")
            return False
        
        code = response.get('code')
        if code and code != '200':
            logging.error(f"{api_name}: API error code {code}")
            return False
        
        logging.debug(f"{api_name}: Response validated successfully")
        return True
    
    def _fetch(self, url: str, cache_file: Path, ttl: int, api_name: str) -> Optional[Dict[str, Any]]:
        """Fetch data from API with caching"""
        # Check cache
        if cache_file.exists():
            cache_age = time.time() - cache_file.stat().st_mtime
            if cache_age < ttl:
                try:
                    data = json.loads(cache_file.read_text())
                    logging.debug(f"{api_name}: Using cached data")
                    return data
                except Exception as e:
                    logging.warning(f"{api_name}: Failed to read cache: {e}")
        
        # Fetch from API
        try:
            logging.debug(f"API request: {api_name}")
            response = self.session.get(url, timeout=5)
            response.raise_for_status()
            data = response.json()
            
            if self._validate_response(data, api_name):
                # Cache the response
                cache_file.parent.mkdir(parents=True, exist_ok=True)
                cache_file.write_text(json.dumps(data, ensure_ascii=False))
                logging.info(f"{api_name}: Data updated")
                return data
            
        except requests.exceptions.RequestException as e:
            logging.error(f"{api_name}: Request failed: {e}")
        except json.JSONDecodeError as e:
            logging.error(f"{api_name}: Invalid JSON response: {e}")
        
        return None
    
    def fetch_all(self, site: str, location: str) -> Dict[str, Any]:
        """Fetch all weather data in parallel"""
        cache_dir = self.config.cache_dir_base / site
        cache_dir.mkdir(parents=True, exist_ok=True)
        
        results = {}
        
        # Define fetch tasks
        tasks = [
            ('now', f"{self.config.api_host.rstrip('/')}/v7/weather/now?location={location}&lang=zh&unit=m",
             cache_dir / 'now.json', self.config.ttl_now),
            ('minutely', f"{self.config.api_host.rstrip('/')}/v7/minutely/5m?location={location}&lang=zh",
             cache_dir / 'min.json', self.config.ttl_min),
            ('daily', f"{self.config.api_host.rstrip('/')}/v7/weather/3d?location={location}&lang=zh&unit=m",
             cache_dir / 'daily.json', self.config.ttl_daily),
        ]
        
        # Add AQI task
        lat, lon = location.split(',')[1], location.split(',')[0]
        # Try China AQI API first for China locations
        if 100 <= float(lon) <= 125 and 25 <= float(lat) <= 45:
            tasks.append(
                ('aqi', f"{self.config.api_host.rstrip('/')}/v7/air/now?location={location}&lang=zh",
                 cache_dir / 'aqi.json', self.config.ttl_aqi)
            )
        else:
            tasks.append(
                ('aqi', f"{self.config.api_host.rstrip('/')}/airquality/v1/current/{lat}/{lon}?lang=zh",
                 cache_dir / 'aqi.json', self.config.ttl_aqi)
            )
        
        # Fetch in parallel
        with ThreadPoolExecutor(max_workers=4) as executor:
            future_to_key = {
                executor.submit(self._fetch, url, cache, ttl, key): key
                for key, url, cache, ttl in tasks
            }
            
            for future in as_completed(future_to_key):
                key = future_to_key[future]
                try:
                    results[key] = future.result()
                except Exception as e:
                    logging.error(f"Failed to fetch {key}: {e}")
                    results[key] = None
        
        return results

# ===================== Weather Data Parser =====================
class WeatherParser:
    """Parse weather data from API responses"""
    
    @staticmethod
    def parse_now(data: Optional[Dict[str, Any]]) -> Dict[str, str]:
        """Parse current weather data - simplified for better readability"""
        result = {
            'temp': '--',
            'desc': '--'
        }

        if data and 'now' in data:
            now = data['now']
            result['temp'] = str(now.get('temp', '--'))
            result['desc'] = now.get('text', '--')

        return result
    
    @staticmethod
    def parse_minutely(data: Optional[Dict[str, Any]]) -> str:
        """Parse minutely precipitation data"""
        if not data:
            return '--'
        
        # Check for summary first
        if summary := data.get('summary'):
            return summary
        
        # Parse minutely data
        minutely = data.get('minutely', [])
        if not minutely:
            return '--'
        
        precip = [float(m.get('precip', 0)) for m in minutely]
        
        # Determine current and future precipitation
        currently_rain = precip[0] > 0 if precip else False
        
        if currently_rain:
            # Find when rain stops
            for i, p in enumerate(precip):
                if p == 0:
                    return f"{i*5}分钟后雨停"
            return "未来2小时持续降水"
        else:
            # Find when rain starts
            for i, p in enumerate(precip):
                if p > 0:
                    return f"{i*5}分钟后下雨"
            return "2小时内无降水"
    
    @staticmethod
    def parse_daily(data: Optional[Dict[str, Any]]) -> str:
        """Parse daily forecast for tomorrow - simplified"""
        if not data or 'daily' not in data:
            return ''

        tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')

        for day in data['daily']:
            if day.get('fxDate') == tomorrow:
                tmin = day.get('tempMin', '--')
                tmax = day.get('tempMax', '--')
                dday = day.get('textDay', '--')
                dnight = day.get('textNight', '--')

                # Simplified: just show temp range and weather
                if dday == dnight:
                    return f"明日{tmin}~{tmax}°C {dday}"
                else:
                    return f"明日{tmin}~{tmax}°C {dday}转{dnight}"

        return ''
    
    @staticmethod
    def parse_aqi(data: Optional[Dict[str, Any]]) -> str:
        """Parse AQI data - simplified to show only value"""
        if not data:
            return ''

        # Try China AQI format
        if 'now' in data and 'aqi' in data['now']:
            aqi = data['now'].get('aqi', '--')
            # Only show AQI number for brevity
            return f"AQI{aqi}"

        # Try global AQI format
        if 'indexes' in data:
            for index in data['indexes']:
                if index.get('code') in ['cn-mee', 'cn-mee-1h']:
                    aqi = index.get('aqiDisplay', '--')
                    return f"AQI{aqi}"

            # Fallback to first index
            if data['indexes']:
                aqi = data['indexes'][0].get('aqiDisplay', '--')
                return f"AQI{aqi}"

        return ''

# ===================== Claude Context Parser =====================
def parse_claude_context() -> Dict[str, Any]:
    """Parse Claude Code context from stdin"""
    result = {
        'model': 'Claude',
        'dir': '.',
        'branch': '',
        'cost': None,
        'duration': None
    }

    try:
        input_data = sys.stdin.read()
        if input_data:
            data = json.loads(input_data)

            # Parse model
            if 'model' in data:
                result['model'] = data['model'].get('display_name') or data['model'].get('id', 'Claude')

            # Parse directory
            if 'workspace' in data:
                cwd = data['workspace'].get('current_dir', '.')
                result['dir'] = Path(cwd).name

                # Check for git branch
                git_head = Path(cwd) / '.git' / 'HEAD'
                if git_head.exists():
                    content = git_head.read_text().strip()
                    if content.startswith('ref: '):
                        result['branch'] = content.split('/')[-1]

            # Parse cost metrics (important for tracking usage)
            if 'cost' in data:
                cost_usd = data['cost'].get('usd')
                if cost_usd is not None:
                    result['cost'] = f"${cost_usd:.3f}"

                # Parse duration
                duration_sec = data['cost'].get('duration_sec')
                if duration_sec is not None and duration_sec > 0:
                    minutes = int(duration_sec // 60)
                    if minutes > 0:
                        result['duration'] = f"{minutes}m"

    except Exception as e:
        logging.debug(f"Failed to parse Claude context: {e}")

    return result

# ===================== Main Function =====================
def main():
    """Main entry point"""
    # Initialize configuration
    config = Config()
    
    # Setup logging
    setup_logging(config)
    logging.info("StatusLine script started")
    
    # Validate configuration
    if not config.validate():
        print("ERROR: Configuration invalid")
        sys.exit(1)
    
    # Parse Claude context
    context = parse_claude_context()
    logging.debug(f"Context: {context}")
    
    # Initialize JWT manager
    jwt_manager = JWTManager(config)
    jwt_token = jwt_manager.ensure_jwt()
    
    # Select site
    selector = SiteSelector(config)
    site, location, place = selector.choose_site()
    logging.info(f"Selected site: {site} ({place}) at {location}")
    
    # Fetch weather data
    client = WeatherClient(config, jwt_token)
    data = client.fetch_all(site, location)
    
    # Parse weather data
    parser = WeatherParser()
    now_data = parser.parse_now(data.get('now'))
    minutely_text = parser.parse_minutely(data.get('minutely'))
    daily_text = parser.parse_daily(data.get('daily'))
    aqi_text = parser.parse_aqi(data.get('aqi'))
    
    # Format output with colors
    if not config.no_color:
        ORANGE = '\033[38;5;208m'  # Model name
        CYAN = '\033[38;5;51m'     # Cost/metrics
        DIM = '\033[2m'            # Directory
        GREEN = '\033[38;5;46m'    # Weather info
        RESET = '\033[0m'
    else:
        ORANGE = CYAN = DIM = GREEN = RESET = ''

    # Build header with current time
    current_time = datetime.now().strftime('%H:%M')
    header = f"⏰ {current_time}"

    # Add model info
    header += f" | {ORANGE}{context['model']}{RESET}"

    # Add directory and branch
    header += f" {DIM}{context['dir']}{RESET}"
    if context['branch']:
        header += f":{context['branch']}"

    # Add cost metrics if available
    metrics = []
    if context.get('cost'):
        metrics.append(f"{CYAN}{context['cost']}{RESET}")
    if context.get('duration'):
        metrics.append(f"{CYAN}{context['duration']}{RESET}")
    if metrics:
        header += f" [{' '.join(metrics)}]"

    # Build weather part (simplified and compact)
    weather_parts = []
    weather_parts.append(f"{GREEN}{place}{RESET}")
    weather_parts.append(f"{now_data['temp']}°C {now_data['desc']}")
    weather_parts.append(minutely_text)
    if aqi_text:
        weather_parts.append(aqi_text)
    if daily_text:
        weather_parts.append(daily_text)

    wx_part = " | ".join(weather_parts)

    # Ensure output even on error
    if not wx_part or wx_part.strip() == "|":
        wx_part = f"Status loading..."

    # Output (first line only, as per official docs)
    print(f"{header} | {wx_part}")

    logging.info(f"Status displayed successfully")
    logging.info("Execution completed")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logging.error(f"Unhandled exception: {e}", exc_info=True)
        print(f"ERROR: {e}")
        sys.exit(1)