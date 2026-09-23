import { del, get, post, postForm } from "./request";

/* ---------- 与后端 Pydantic 模型对齐的接口契约 ---------- */

export interface KnowledgeBase {
  id: number;
  name: string;
  description: string | null;
  doc_count: number;
  created_at: string;
}

export interface KnowledgeBaseDetail extends KnowledgeBase {
  documents: DocumentBrief[];
}

export interface DocumentBrief {
  file_id: string;
  original_filename: string;
  file_size: number;
  char_count: number;
  chunk_count: number;
  created_at: string;
  /** 0待处理 1处理中 2完成 3失败 4降级完成 */
  status: number;
  parser_name: string | null;
  parse_error: string | null;
}

export interface UploadResponse {
  file_id: string;
  original_filename: string;
  file_size: number;
  status: string | null;
  task_id: number | null;
}

export interface DocumentStatus {
  file_id: string;
  status: number;
  task_status: number | null;
  attempts: number;
  chunk_count: number;
  parser_name: string | null;
  parse_error: string | null;
}

export interface DeleteResult {
  deleted: boolean;
  kb_id?: number | null;
  file_id?: string | null;
  name?: string | null;
  deleted_documents: number;
}

/* ---------- 接口函数 ---------- */

export const kbApi = {
  list(): Promise<KnowledgeBase[]> {
    return get<KnowledgeBase[]>("/kbs");
  },
  detail(id: number): Promise<KnowledgeBaseDetail> {
    return get<KnowledgeBaseDetail>(`/kbs/${id}`);
  },
  create(name: string, description?: string): Promise<KnowledgeBase> {
    return post<KnowledgeBase>("/kbs", { name, description });
  },
  remove(id: number): Promise<DeleteResult> {
    return del<DeleteResult>(`/kbs/${id}`);
  },
};

export const documentApi = {
  upload(kbId: number, file: File, overwrite: boolean): Promise<UploadResponse> {
    const form = new FormData();
    form.append("file", file);
    return postForm<UploadResponse>(`/documents/upload?kb_id=${kbId}&overwrite=${overwrite}`, form);
  },
  status(fileId: string): Promise<DocumentStatus> {
    return get<DocumentStatus>(`/documents/${encodeURIComponent(fileId)}/status`);
  },
  remove(fileId: string): Promise<DeleteResult> {
    return del<DeleteResult>(`/documents/${encodeURIComponent(fileId)}`);
  },
};

export const retrievalApi = {
  test(query: string, kbId: number | null, topK: number): Promise<RetrievalTestResult> {
    return post<RetrievalTestResult>("/retrieval/test", {
      query,
      kb_id: kbId ?? undefined,
      top_k: topK,
    });
  },
};

/* ---------- Chunk 查看器（P1：原文 ↔ Chunk ↔ Metadata 可追溯） ---------- */

export interface ChunkItem {
  chunk_index: number;
  content: string;
  page_number: number;
  block_type: string | null;
  heading_path: string[];
  token_count: number | null;
  /** 0待嵌入 1已嵌入 2失败 */
  embedding_status: number;
  vector_id: string | null;
}

export interface DocumentChunksResult {
  file_id: string;
  doc_name: string;
  /** 0待处理 1处理中 2完成 3失败 4降级完成 */
  status: number;
  parser_name: string | null;
  chunk_count: number;
  embedded_count: number;
  chunks: ChunkItem[];
}

export const chunksApi = {
  byDoc(fileId: string): Promise<DocumentChunksResult> {
    return get<DocumentChunksResult>(`/documents/${encodeURIComponent(fileId)}/chunks`);
  },
};

/* ---------- 检索测试（P0：只检索不生成） ---------- */

export interface RetrievalHit {
  idx: number;
  doc_name: string;
  file_id: string;
  chunk_index: number;
  content: string;
  page: number | null;
  similarity: number;
}

export interface RetrievalTestResult {
  query: string;
  kb_id: number | null;
  top_k: number;
  hits: RetrievalHit[];
  embedding_ms: number;
  retrieval_ms: number;
  total_ms: number;
}
