"""__init__ for the optional platform-specific modules folder.

Modules here are imported lazily by ``os_control``; missing native deps on a
non-Windows host should not break import time.
"""
