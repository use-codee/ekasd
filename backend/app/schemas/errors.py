from pydantic import BaseModel


class ErrorDetail(BaseModel):
    loc: list[str | int]
    message: str
    type: str


class ErrorInfo(BaseModel):
    code: str
    message: str
    details: list[ErrorDetail] = []


class ErrorResponse(BaseModel):
    error: ErrorInfo
