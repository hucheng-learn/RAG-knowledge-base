"""MinerU 4.0 本地 V1 API 解析适配器。

只依赖本地 MinerU 服务，不调用公有云。V1 API 流程为上传文件、创建任务、
轮询任务、下载结构化结果和 Markdown；任务失败直接抛出异常，由上层决定重试
或降级到 pdfplumber。
"""

import json
import mimetypes
from pathlib import Path
from time import perf_counter, sleep
from urllib.parse import urljoin

import httpx

from app.config.settings import get_settings
from app.service.parser.base import DocumentBlock, DocumentParser, ParseResult
from app.utils.exceptions import BizException
from app.utils.logger import get_logger

logger = get_logger(__name__)


def guess_mime_type(filename: str) -> str:
    """按扩展名推断 MIME 类型；无法识别时退化为二进制流。

    MinerU 支持 PDF / 图片 / DOC(X) / PPT(X) / XLS(X) 等多种输入，
    因此不能像最初那样把 mime_type 写死为 application/pdf。
    """
    return mimetypes.guess_type(filename)[0] or "application/octet-stream"


class MinerUParser(DocumentParser):
    """通过本地 MinerU 4.0 V1 API 解析 PDF。"""

    def parse(self, file_path: Path) -> ParseResult:
        settings = get_settings()
        started = perf_counter()
        # 本地 MinerU 服务默认无鉴权；若日后启用 --api-key，
        # 在此处加 Authorization 头即可（并相应加回配置项）
        headers: dict[str, str] = {}
        base_url = settings.mineru_api_url.rstrip("/")
        try:
            # 创建上传 → 上传文件 → 完成上传 → 创建解析任务 → 轮询任务 → 下载结构化 JSON → 下载 Markdown
            with httpx.Client(timeout=settings.mineru_timeout_seconds) as client:
                upload = self._create_upload(client, base_url, file_path, headers)
                file_id = self._upload_bytes(client, base_url, file_path, headers, upload)
                job = self._create_job(client, base_url, file_id, headers, settings)
                result = self._poll_job(client, base_url, job["job_id"], headers, settings)
                parsed = self._download_result(client, base_url, result, headers)
        except BizException:
            logger.info(
                "MinerU 解析耗时: 文件=%s 耗时_ms=%.2f 结果=failed",
                file_path.name, (perf_counter() - started) * 1000,
            )
            raise
        except Exception as exc:
            logger.exception("MinerU 解析失败: %s", file_path.name)
            logger.info(
                "MinerU 解析耗时: 文件=%s 耗时_ms=%.2f 结果=failed",
                file_path.name, (perf_counter() - started) * 1000,
            )
            raise BizException(f"MinerU 本地解析失败: {file_path.name}") from exc

        logger.info(
            "MinerU 解析完成: 文件=%s 页数=%d 字符数=%d 块数=%d 耗时_ms=%.2f 解析器=mineru",
            file_path.name, len(parsed.page_texts), len(parsed.text), len(parsed.blocks),
            (perf_counter() - started) * 1000,
        )
        return parsed

    @staticmethod
    def _raise_for_response(response: httpx.Response, operation: str) -> None:
        if response.is_error:
            raise BizException(
                f"MinerU {operation}失败: HTTP {response.status_code}"
            )

    def _create_upload(self, client, base_url, file_path, headers):
        response = client.post(
            f"{base_url}/v1/uploads",
            headers=headers,
            json={
                "filename": file_path.name,
                "bytes": file_path.stat().st_size,
                # MIME 按扩展名推断（支持 pdf/docx/pptx/xlsx/图片等多格式），
                # 不能写死 application/pdf
                "mime_type": guess_mime_type(file_path.name),
                "purpose": "parse",
            },
        )
        self._raise_for_response(response, "创建上传")
        data = response.json()
        if not data.get("id") or data.get("status") not in {"pending", "completed"}:
            raise BizException("MinerU 创建上传返回无效结果")
        return data

    def _upload_bytes(self, client, base_url, file_path, headers, upload):
        if upload["status"] == "completed":
            return upload["file"]["id"]
        upload_url = upload.get("upload_url")
        if not upload_url:
            raise BizException("MinerU 未返回文件上传地址")
        response = client.put(
            urljoin(f"{base_url}/", upload_url),
            headers={**headers, **upload.get("upload_headers", {})},
            content=file_path.read_bytes(),
        )
        self._raise_for_response(response, "上传文件")
        response = client.post(
            f"{base_url}/v1/uploads/{upload['id']}/complete", headers=headers
        )
        self._raise_for_response(response, "完成上传")
        data = response.json()
        if data.get("status") != "completed" or not data.get("file", {}).get("id"):
            raise BizException("MinerU 完成上传返回无效结果")
        return data["file"]["id"]

    def _create_job(self, client, base_url, file_id, headers, settings):
        response = client.post(
            f"{base_url}/v1/parse/jobs",
            headers=headers,
            json={
                "files": [{"source": {"type": "file_id", "file_id": file_id}}],
                "tier": settings.mineru_tier,
                "output_formats": ["markdown", "structured_content"],
            },
        )
        self._raise_for_response(response, "创建解析任务")
        data = response.json()
        if not data.get("job_id"):
            raise BizException("MinerU 创建解析任务返回无效结果")
        return data

    def _poll_job(self, client, base_url, job_id, headers, settings):
        data = {"status": "queued"}
        for attempt in range(settings.mineru_max_polls + 1):
            if data["status"] in {"completed", "partial", "failed", "canceled"}:
                break
            if attempt:
                sleep(settings.mineru_poll_interval_seconds)
            response = client.get(f"{base_url}/v1/parse/jobs/{job_id}", headers=headers)
            self._raise_for_response(response, "查询解析任务")
            data = response.json()
        if data.get("status") not in {"completed", "partial"}:
            raise BizException(f"MinerU 解析任务未完成: {data.get('status', 'unknown')}")
        return data

    def _download_result(self, client, base_url, job, headers):
        files = job.get("files", [])
        if not files or files[0].get("status") != "completed":
            raise BizException("MinerU 没有返回可用解析结果")
        output_files = files[0].get("output_files", {})
        structured = self._download_json(client, base_url, output_files.get("structured_content"), headers)
        markdown = self._download_text(client, base_url, output_files.get("markdown"), headers)
        pages = structured.get("pages", []) if structured else []
        blocks = []
        assets = []
        page_texts = []
        for page in pages:
            page_number = int(page.get("page_idx", 0)) + 1
            page_blocks = page.get("blocks", [])
            page_contents = []
            for block_index, block in enumerate(page_blocks):
                content = block.get("content", "")
                if isinstance(content, list):
                    content = "\n".join(
                        str(item.get("content", item)) if isinstance(item, dict) else str(item)
                        for item in content
                    )
                content = str(content).strip()
                if not content:
                    continue
                page_contents.append(content)
                blocks.append(DocumentBlock(
                    block_type=str(block.get("type", "text")),
                    content=content,
                    page_number=page_number,
                    block_index=block_index,
                    metadata=block,
                ))
                if str(block.get("type", "")).lower() in {"table", "image", "figure", "formula"}:
                    assets.append({
                        "asset_type": str(block.get("type")), "page_number": page_number,
                        "block_index": block_index, "content": content,
                        "metadata": block,
                    })
            page_texts.append("\n\n".join(page_contents))
        text = markdown or "\n\n".join(page_texts)
        # 兜底：structured_content 缺失但 markdown 成功时 page_texts 会是空列表，
        # 而分块是按 page_texts 切分的 → 会产出 0 块（文档入库却检索不到）。
        # 此时把全文当作单页，保证至少能分块入库。
        if not page_texts and text:
            page_texts = [text]
            logger.warning("MinerU 未返回结构化分页，已按整篇单页兜底: 字符数=%d", len(text))
        return ParseResult(
            text=text, page_texts=page_texts, blocks=blocks, assets=assets,
            parser_name="mineru", parser_version="4.x",
            metadata={"tier": get_settings().mineru_tier},
        )

    @staticmethod
    def _download_json(client, base_url, output, headers):
        if not output or not output.get("file_id"):
            return {}
        response = client.get(f"{base_url}/v1/files/{output['file_id']}/content", headers=headers)
        response.raise_for_status()
        return json.loads(response.text)

    @staticmethod
    def _download_text(client, base_url, output, headers):
        if not output or not output.get("file_id"):
            return ""
        response = client.get(f"{base_url}/v1/files/{output['file_id']}/content", headers=headers)
        response.raise_for_status()
        return response.text
