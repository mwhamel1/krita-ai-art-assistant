# SPDX-License-Identifier: MIT

"""Krita docker plugin: AI Art Assistant."""

try:
    from krita import DockWidgetFactory, DockWidgetFactoryBase, Krita
except ImportError:
    pass
else:
    from .docker import AIArtAssistantDocker

    DOCKER_ID = "ai_art_assistant"

    try:
        _DOCK_RIGHT = DockWidgetFactoryBase.DockPosition.DockRight
    except AttributeError:
        _DOCK_RIGHT = DockWidgetFactoryBase.DockRight

    Krita.instance().addDockWidgetFactory(
        DockWidgetFactory(DOCKER_ID, _DOCK_RIGHT, AIArtAssistantDocker)
    )
