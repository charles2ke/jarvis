"""Jarvis, a personal AI companion.

The package exposes a small, dependency-free assistant engine that routes
natural language requests to registered skills.
"""

from jarvis.assistant import Assistant
from jarvis.skills import Skill, SkillRegistry, build_default_registry

__all__ = [
    "Assistant",
    "Skill",
    "SkillRegistry",
    "build_default_registry",
    "__version__",
]

__version__ = "0.1.0"
