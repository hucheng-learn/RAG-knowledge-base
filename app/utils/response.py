"""统一接口返回体。

所有接口（SSE 流式接口除外）统一返回 JSON：
    {"code": int, "msg": str, "data": Any}

约定：
- code = 0 表示成功；非 0 表示失败，msg 为给人看的提示信息；
- 业务异常：HTTP 状态码 200 + 非 0 业务码（前端只需判断 body.code）；
- 参数/系统级错误：保留真实 HTTP 状态码（4xx/5xx），body 仍是统一结构，
  便于 Nginx、监控、探活按状态码感知故障（这是与「一律返回 200」方案
  的关键区别，也是工业实践更推荐的做法）。
"""

from typing import Any

from fastapi.responses import JSONResponse


class RespCode:
    """业务码常量表：新增错误类型时在此登记，禁止在代码里写魔法数字。"""

    SUCCESS = 0          # 成功
    PARAM_ERROR = 1001   # 参数校验失败（Pydantic 422）
    NOT_FOUND = 1002     # 资源不存在（HTTP 404）
    BIZ_ERROR = 1003     # 通用业务异常
    SYSTEM_ERROR = 500   # 系统异常（HTTP 500）


def success(data: Any = None, msg: str = "success") -> dict:
    """构造成功响应体（普通接口直接 return 该 dict，FastAPI 自动序列化）。"""
    return {"code": RespCode.SUCCESS, "msg": msg, "data": data}


def fail(code: int = RespCode.BIZ_ERROR, msg: str = "error", data: Any = None) -> dict:
    """构造失败响应体。"""
    return {"code": code, "msg": msg, "data": data}


def json_success(data: Any = None, msg: str = "success") -> JSONResponse:
    """成功响应的 JSONResponse 版（异常处理器 / 需要显式控制响应对象时用）。"""
    return JSONResponse(content=success(data, msg))


def json_fail(
    code: int,
    msg: str,
    data: Any = None,
    status_code: int = 200,
) -> JSONResponse:
    """失败响应的 JSONResponse 版，可显式指定 HTTP 状态码。

    业务异常默认 status_code=200（错误语义放 body.code）；
    系统异常/参数异常传 500/422 等真实状态码。
    """
    return JSONResponse(status_code=status_code, content=fail(code, msg, data))
