"""Theme preferences and semantic palettes; no GUI dependencies."""
import sys
from app_settings import load_settings, save_setting

THEME_LABELS = {"system": "跟随系统", "light": "浅色", "dark": "深色"}
LIGHT = {'BG': '#F6F8FC',
 'CARD': '#FFFFFF',
 'TEXT': '#202124',
 'MUTED': '#5F6368',
 'BORDER': '#E1E5EE',
 'BLUE': '#1A73E8',
 'BLUE_HOVER': '#1765CC',
 'GREEN': '#188038',
 'RED': '#D93025',
 'DANGER_BG': '#FCE8E6',
 'DANGER_HOVER': '#F9DEDC',
 'DANGER_TEXT': '#B3261E',
 'AMBER': '#F9AB00',
 'SELECTED': '#D2E3FC',
 'SURFACE': '#F8FAFD',
 'SCROLL': '#C7CDD8',
 'TROUGH': '#F1F3F4',
 'SCROLL_HOVER': '#9AA4B2',
 'SCROLL_PRESSED': '#7B8794',
 'TINT': '#E8F0FE',
 'ON_ACCENT': '#FFFFFE',
 'DANGER_PRESSED': '#8C1D18',
 'DISABLED': '#A9AFB8',
 'LOG_TEXT': '#3C4043'}
DARK = {'BG': '#141820',
 'CARD': '#1D2430',
 'TEXT': '#E8EAED',
 'MUTED': '#AAB4C4',
 'BORDER': '#354154',
 'BLUE': '#8AB4F8',
 'BLUE_HOVER': '#A6C8FF',
 'GREEN': '#81C995',
 'RED': '#F28B82',
 'DANGER_BG': '#482B2D',
 'DANGER_HOVER': '#603235',
 'DANGER_TEXT': '#FFB4AB',
 'AMBER': '#FDD663',
 'SELECTED': '#304969',
 'SURFACE': '#232C3A',
 'SCROLL': '#536176',
 'TROUGH': '#19212C',
 'SCROLL_HOVER': '#6A7C93',
 'SCROLL_PRESSED': '#8597AF',
 'TINT': '#293C56',
 'ON_ACCENT': '#152238',
 'DANGER_PRESSED': '#FFC9C2',
 'DISABLED': '#788596',
 'LOG_TEXT': '#D6DCE5'}


def load_theme(data_dir):
    value = load_settings(data_dir).get("theme")
    return value if isinstance(value, str) and value in THEME_LABELS else "system"


def save_theme(data_dir, preference):
    if preference not in THEME_LABELS:
        raise ValueError("Unknown theme preference")
    save_setting(data_dir, "theme", preference)


def system_theme():
    if sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
                value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
                return "dark" if value == 0 else "light"
        except (OSError, ImportError):
            pass
    return "light"


def resolve_theme(preference):
    return system_theme() if preference == "system" else preference
