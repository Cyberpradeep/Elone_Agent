from pydantic import BaseModel, Field
from typing import Literal


class StepVerification(BaseModel):
    verdict: Literal["PASS", "FAIL"]
    reasoning: str = Field(
        description="Brief reasoning citing the specific field(s) in the result that confirm or contradict success"
    )
