-- ============================================================
-- 企业知识库 RAG 后端 — MySQL 建表 SQL（权威版本）
-- 与实际数据库一致；init_db() 的 create_all 只在表不存在时创建，
-- 不会改动已存在的表。建表或字段对齐以本文件为准。
-- ============================================================

-- 知识库表：文档的顶层容器
CREATE TABLE knowledge_bases (
  id              INT AUTO_INCREMENT PRIMARY KEY COMMENT '主键',
  name            VARCHAR(64)  NOT NULL UNIQUE COMMENT '知识库名称',
  description     VARCHAR(255) NULL COMMENT '描述',
  owner_id        INT NULL COMMENT '所属用户ID',
  embedding_model VARCHAR(64)  NULL COMMENT '嵌入模型名称',
  chunk_strategy  VARCHAR(32)  NULL COMMENT '分块策略(fixed/semantic/sentence)',
  chunk_size      INT NULL COMMENT '分块大小(字符数)',
  chunk_overlap   INT NULL COMMENT '分块重叠(字符数)',
  doc_count       INT NOT NULL DEFAULT 0 COMMENT '文档数量',
  status          TINYINT NOT NULL DEFAULT 1 COMMENT '状态: 0-禁用 1-启用',
  updated_at      DATETIME NULL COMMENT '更新时间',
  created_at      DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  KEY ix_kb_owner_id (owner_id),
  KEY ix_kb_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='知识库（对应一个文件夹，是文档的顶层容器）';

-- 文档表：上传文件的元数据记录
CREATE TABLE documents (
  id                INT AUTO_INCREMENT PRIMARY KEY COMMENT '主键',
  kb_id             INT NULL COMMENT '知识库ID',
  file_id           VARCHAR(64)  NOT NULL UNIQUE COMMENT '上传返回的文件ID（uuid存储名）',
  original_filename VARCHAR(255) NOT NULL COMMENT '原始文件名',
  file_type         VARCHAR(32)  NULL COMMENT '文件类型(pdf/docx/txt/md等)',
  file_size         BIGINT       NOT NULL COMMENT '文件大小（字节）',
  char_count        INT NOT NULL COMMENT '清洗后总字符数',
  chunk_count       INT NOT NULL COMMENT '分块数量',
  status            TINYINT NOT NULL DEFAULT 0 COMMENT '处理状态: 0-待解析 1-解析中 2-解析完成 3-失败',
  parse_error       TEXT NULL COMMENT '解析失败原因',
  created_at        DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at        DATETIME NULL COMMENT '更新时间',
  KEY kb_id (kb_id),
  KEY ix_doc_status (status),
  KEY ix_doc_file_type (file_type),
  CONSTRAINT fk_documents_kb FOREIGN KEY (kb_id) REFERENCES knowledge_bases(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='文档（对应一个上传的文件，属于某个知识库）';

-- 分块表：检索最小单元，与 Milvus 向量一一对应
CREATE TABLE chunks (
  id               INT AUTO_INCREMENT PRIMARY KEY COMMENT '主键',
  doc_id           INT NOT NULL COMMENT '所属文档ID',
  kb_id            INT NULL COMMENT '知识库ID',
  chunk_index      INT NOT NULL COMMENT '文档内块编号（从0开始）',
  content          TEXT NOT NULL COMMENT '块原始文本',
  token_count      INT NULL COMMENT 'token数量',
  embedding_status TINYINT NOT NULL DEFAULT 0 COMMENT '嵌入状态: 0-待嵌入 1-已嵌入 2-失败',
  page_number      INT NOT NULL COMMENT '来源页码（从1开始）',
  vector_id        VARCHAR(64) NULL COMMENT 'Milvus向量ID（与chunk id一一对应）',
  created_at       DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  KEY kb_id (kb_id),
  KEY ix_chunks_doc_id (doc_id),
  KEY ix_chunks_created_at (created_at),
  KEY ix_chunk_embedding_status (embedding_status),
  CONSTRAINT fk_chunks_doc FOREIGN KEY (doc_id) REFERENCES documents(id),
  CONSTRAINT fk_chunks_kb  FOREIGN KEY (kb_id)  REFERENCES knowledge_bases(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='检索片段（文档切分后的chunk，是检索和嵌入的最小单元）';