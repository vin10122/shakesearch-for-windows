"""Validated local preferences for the desktop controller."""
from localization import read_settings, write_settings

DEFAULTS = dict(shake_enabled=True, sensitivity='normal', animation='balanced')
DISTANCES = {'low': 450, 'normal': 300, 'high': 180}


def preferences():
    saved = read_settings()
    values = dict(DEFAULTS)
    if isinstance(saved.get('shake_enabled'), bool):
        values['shake_enabled'] = saved['shake_enabled']
    for key, choices in [('sensitivity', DISTANCES), ('animation', ('balanced', 'light'))]:
        if saved.get(key) in choices:
            values[key] = saved[key]
    return values


def save_preferences(language, shake_enabled, sensitivity, animation):
    if language not in ('it', 'en') or sensitivity not in DISTANCES or animation not in ('balanced', 'light'):
        raise ValueError('Invalid preferences')
    write_settings(dict(read_settings(), language=language, shake_enabled=bool(shake_enabled),
                        sensitivity=sensitivity, animation=animation, setup_complete=True))
