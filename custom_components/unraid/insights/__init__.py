"""Insights implementations for Unraid."""
def get_docker_insights():
    """Get the Docker insights class."""
    from .docker_insights import UnraidDockerInsights
    return UnraidDockerInsights

__all__ = ["get_docker_insights"]