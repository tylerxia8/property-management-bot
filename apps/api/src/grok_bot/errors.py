from fastapi import HTTPException


def problem(
    status: int,
    code: str,
    message: str,
    details: dict | None = None,
    retryable: bool = False,
) -> None:
    raise HTTPException(
        status_code=status,
        detail={
            "code": code,
            "message": message,
            "details": details or {},
            "retryable": retryable,
        },
    )
