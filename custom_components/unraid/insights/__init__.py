"""Insights implementations for Unraid."""
from typing import Type
from .docker_insights import UnraidDockerInsights

def get_docker_insights() -> Type[UnraidDockerInsights]:
    """Get the Docker insights class."""
    return UnraidDockerInsights

__all__ = ["get_docker_insights", "UnraidDockerInsights"]