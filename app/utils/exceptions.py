"""异常定义与全局异常处理器注册。

分层设计（面试重点）：
- BizException      业务异常：可预料的业务规则冲突（如"文件类型不支持"）。
                     由全局处理器捕获 → HTTP 200 + 业务码，msg 直接给前端展示；
                     日志记 WARNING，不打堆栈（业务异常是"预期内"，堆栈无排查价值）。
- SystemException   系统异常：不可预料的系统故障（如依赖服务不可用）。
                     返回 HTTP 500 + 通用提示；完整堆栈进日志，不进响应
                     （防止泄漏内部实现细节给调用方）。
- RequestValidationError / HTTPException：FastAPI 框架自带异常，
                     统一转成信封格式，保持 4xx 真实状态码。
- Exception         兜底：任何未捕获异常按系统异常处理，保证接口永远返回
                     统一结构的 JSON，而不是框架默认的纯文本报错。
"""

from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.utils.logger import get_logger
from app.utils.response import RespCode

logger = get_logger(__name__)


class BizException(Exception):
    """业务异常：调用方可通过 code/msg 得知具体业务错误。"""

    def __init__(
        self,
        msg: str,
        code: int = RespCode.BIZ_ERROR,
        data: Any = None,
    ) -> None:
        self.code = code          # 业务码（默认 1003，可自定义细分）
        self.msg = msg            # 提示信息（直接展示给用户）
        self.data = data          # 附加数据（可为空）
        super().__init__(msg)


class SystemException(Exception):
    """系统异常：统一提示语，细节只进日志。"""

    def __init__(self, msg: str = "系统繁忙，请稍后重试") -> None:
        self.msg = msg
        super().__init__(msg)


# ---------------- 全局异常处理器 ----------------

async def biz_exception_handler(request: Request, exc: BizException) -> JSONResponse:
    """业务异常：HTTP 200 + 业务码（预期内错误，WARNING 级日志）。"""
    logger.warning(
        "业务异常: code=%s msg=%s path=%s",
        exc.code, exc.msg, request.url.path,
    )
    return JSONResponse(content={"code": exc.code, "msg": exc.msg, "data": exc.data})


async def system_exception_handler(request: Request, exc: SystemException) -> JSONResponse:
    """系统异常：HTTP 500 + 通用提示，完整堆栈写入日志。"""
    logger.exception("系统异常: path=%s %s", request.url.path, exc)
    return JSONResponse(
        status_code=500,
        content={"code": RespCode.SYSTEM_ERROR, "msg": exc.msg, "data": None},
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """FastAPI/Starlette 自带 HTTPException（404/401 等）转统一信封格式。

    保留原始 HTTP 状态码（探活/监控依赖真实状态码），body 转成 code/msg/data。
    """
    if exc.status_code == 404:
        code, msg = RespCode.NOT_FOUND, "资源不存在"
    elif exc.status_code == 401:
        code, msg = RespCode.BIZ_ERROR, "未授权或凭证无效"
    else:
        code, msg = exc.status_code, str(exc.detail)
    logger.warning(
        "HTTP异常: status=%s path=%s detail=%s",
        exc.status_code, request.url.path, exc.detail,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": code, "msg": msg, "data": None},
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError,
) -> JSONResponse:
    """Pydantic 参数校验失败（FastAPI 默认 422）→ 统一格式 + 字段级错误详情。

    data 里带上完整 errors 列表（字段名 + 错误原因），方便前端定位具体参数。
    """
    errors = exc.errors()
    # 取第一条错误拼成人话：如 "file_size: Input should be a valid integer"
    first = errors[0] if errors else {}
    loc = ".".join(str(x) for x in first.get("loc", []) if x != "body")
    msg = f"参数校验失败: {loc}: {first.get('msg', '')}" if loc else "参数校验失败"
    logger.warning("参数校验失败: path=%s errors=%s", request.url.path, errors)
    return JSONResponse(
        status_code=422,
        content={"code": RespCode.PARAM_ERROR, "msg": msg, "data": errors},
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """兜底处理器：任何未捕获异常统一转系统异常响应。"""
    logger.exception("未捕获异常: path=%s %r", request.url.path, exc)
    return JSONResponse(
        status_code=500,
        content={"code": RespCode.SYSTEM_ERROR, "msg": "系统繁忙，请稍后重试", "data": None},
    )


def register_exception_handlers(app: FastAPI) -> None:
    """在 FastAPI 实例上注册全部异常处理器。

    Starlette 按「异常类型 MRO」匹配处理器：BizException 走自己的处理器，
    HTTPException 走 http 处理器，其余 Exception 走兜底——具体类型优先。
    """
    app.add_exception_handler(BizException, biz_exception_handler)
    app.add_exception_handler(SystemException, system_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
