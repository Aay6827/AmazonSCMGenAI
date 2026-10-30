from typing import Literal

from pydantic import BaseModel, Field

ActionType = Literal["notify_customer", "carrier_escalation", "carrier_trace", "reship",
                     "refund", "damage_claim", "address_update"]
Role = Literal["L1", "TEAM_LEAD", "MANAGER"]


class ActionCreate(BaseModel):
    shipment_id: str = Field(min_length=1)
    action_type: ActionType
    amount_inr: int | None = Field(default=None, gt=0)
    note: str = ""
    proposed_by: str = Field(min_length=1)


class ApproveRequest(BaseModel):
    approver: str = Field(min_length=1)
    role: Role


class ExecuteRequest(BaseModel):
    executed_by: str = Field(min_length=1)