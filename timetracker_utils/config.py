"""Configuration module.

Provides configuration management using Pydantic models.
"""

from pydantic import BaseModel, Field


class Config(BaseModel):
    """Configuration for the HelloWorld class.

    Attributes:
        name: The name to greet. Defaults to "World".

    """

    name: str = Field(default="World", min_length=1, description="The name to greet")

    model_config = {"title": "Hello World Config", "frozen": True}
