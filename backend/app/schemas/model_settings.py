"""Per-organization model selection, on the wire."""

from pydantic import BaseModel, Field


class OrgModelSettingsRead(BaseModel):
    """The model in force, and the context needed to read that as a decision."""

    model_id: str
    #: True when the organization chose this model rather than inheriting the deployment default.
    is_override: bool
    default_model_id: str
    #: What this deployment permits, so a client can offer exactly that and no more.
    allowed_model_ids: list[str]


class OrgModelSettingsUpdate(BaseModel):
    """Set the model, or clear the choice.

    ``model_id = null`` clears it and returns the organization to the deployment default — which is
    also how an organization undoes a choice, so there is no separate delete.
    """

    model_id: str | None = Field(default=None, max_length=100)
