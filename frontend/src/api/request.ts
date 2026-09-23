import axios, { type AxiosError, type AxiosInstance } from "axios";
import { ElMessage } from "element-plus";

/** 后端统一信封 {code, msg, data} */
export interface ApiEnvelope<T> {
  code: number;
  msg: string;
  data: T | null;
}

const request: AxiosInstance = axios.create({
  baseURL: "/api/v1",
  timeout: 120_000, // 上传/检索调用；SSE 走原生 fetch，不经过这里
});

request.interceptors.response.use(
  (resp) => {
    const body = resp.data as ApiEnvelope<unknown> | undefined;
    if (body && typeof body === "object" && "code" in body) {
      if (body.code !== 0) {
        ElMessage.error(body.msg || "请求失败");
        return Promise.reject(new Error(body.msg || "请求失败"));
      }
      return body.data as never;
    }
    return resp.data as never;
  },
  (error: AxiosError<{ msg?: string }>) => {
    const msg = error.response?.data?.msg || error.message || "网络异常";
    ElMessage.error(msg);
    return Promise.reject(new Error(msg));
  },
);

/** GET：拦截器已解包信封，直接得到 T */
export function get<T>(url: string, params?: object): Promise<T> {
  return request.get(url, { params }) as unknown as Promise<T>;
}

/** POST：JSON 请求体 */
export function post<T>(url: string, data?: unknown, params?: object): Promise<T> {
  return request.post(url, data, { params }) as unknown as Promise<T>;
}

/** POST：multipart 上传（Interceptor 不设 Content-Type，交给浏览器带 boundary） */
export function postForm<T>(url: string, form: FormData, params?: object): Promise<T> {
  return request.post(url, form, { params }) as unknown as Promise<T>;
}

/** DELETE */
export function del<T>(url: string): Promise<T> {
  return request.delete(url) as unknown as Promise<T>;
}
